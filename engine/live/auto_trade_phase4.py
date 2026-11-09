"""Process safe scheduling primitives and Alpaca sourced account report."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from ..db.schema import get_connection
from .alpaca import AlpacaPaperClient
from .auto_trade_outbox import enqueue_system_alert
from .pair_execution import list_pairs


def claim_job(name: str, slot: str, lease_seconds: int = 900) -> bool:
    """A unique slot and SQLite write lock prevent duplicate worker execution."""
    now = datetime.now(timezone.utc)
    conn = get_connection()
    try:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("SELECT status, lease_until FROM auto_trade_job_runs "
                           "WHERE name=? AND slot=?", (name, slot)).fetchone()
        if row and (row["status"] == "complete" or row["lease_until"] > now.isoformat()):
            conn.commit()
            return False
        conn.execute("INSERT INTO auto_trade_job_runs "
                     "(name, slot, status, started_at, lease_until) VALUES (?,?,?,?,?) "
                     "ON CONFLICT(name,slot) DO UPDATE SET status=excluded.status, "
                     "started_at=excluded.started_at, lease_until=excluded.lease_until, "
                     "finished_at=NULL, error_type=NULL",
                     (name, slot, "running", now.isoformat(),
                      (now + timedelta(seconds=lease_seconds)).isoformat()))
        conn.commit()
        return True
    finally:
        conn.close()


def finish_job(name: str, slot: str, error: Exception | None = None) -> None:
    conn = get_connection()
    try:
        conn.execute("UPDATE auto_trade_job_runs SET status=?, finished_at=?, "
                     "error_type=? WHERE name=? AND slot=?",
                     ("failed" if error else "complete", datetime.now(timezone.utc).isoformat(),
                      type(error).__name__ if error else None, name, slot))
        conn.commit()
    finally:
        conn.close()


def account_report(broker: AlpacaPaperClient) -> str:
    account = broker.get_account()
    positions = broker.list_positions().items
    orders = broker.list_orders(status="open").items
    tracked = {leg["symbol"] for pair in list_pairs() if pair["state"] not in ("CLOSED", "FLAT")
               for leg in pair["legs"]}
    long_value = sum(max(float(p.get("market_value") or 0), 0) for p in positions)
    short_value = sum(abs(min(float(p.get("market_value") or 0), 0)) for p in positions)
    unrealized = sum(float(p.get("unrealized_pl") or 0) for p in positions)
    lines = ["Alpaca paper account · 10:00 IST", f"Equity: ${account.equity:,.2f}",
             f"Cash: ${account.cash:,.2f} · Buying power: ${account.buying_power:,.2f}",
             f"Long: ${long_value:,.2f} · Short: ${short_value:,.2f}",
             f"Unrealized P&L: ${unrealized:+,.2f}", f"Open orders: {len(orders)}"]
    for p in positions:
        symbol = str(p.get("symbol") or "?")
        label = " (unmatched/manual)" if symbol not in tracked else ""
        lines.append(f"{symbol}{label}: {p.get('side', '?')} {p.get('qty', '?')} @ "
                     f"${float(p.get('avg_entry_price') or 0):,.2f}, now "
                     f"${float(p.get('current_price') or 0):,.2f}, "
                     f"P&L ${float(p.get('unrealized_pl') or 0):+,.2f}")
    return "\n".join(lines)[:4000]


def report_slot(now: datetime | None = None) -> str:
    return (now or datetime.now(timezone.utc)).astimezone(ZoneInfo("Asia/Kolkata")).date().isoformat()


def enqueue_daily_report(broker: AlpacaPaperClient) -> None:
    slot = report_slot()
    enqueue_system_alert("daily_account_report", account_report(broker), slot)


def operational_snapshot() -> dict:
    conn = get_connection()
    try:
        jobs = [dict(row) for row in conn.execute(
            "SELECT name, slot, status, started_at, finished_at, error_type "
            "FROM auto_trade_job_runs ORDER BY started_at DESC LIMIT 25")]
        outbox = {row["status"]: row["n"] for row in conn.execute(
            "SELECT status, COUNT(*) n FROM notification_outbox GROUP BY status")}
        audit = [dict(row) for row in conn.execute(
            "SELECT action, actor, created_at FROM auto_trade_control_audit "
            "ORDER BY id DESC LIMIT 10")]
    finally:
        conn.close()
    pairs = list_pairs()
    closed = [p for p in pairs if p["state"] == "CLOSED"]
    wins = sum(1 for p in closed if float(p.get("realized_pnl") or 0) > 0)
    realized = sum(float(p.get("realized_pnl") or 0) for p in closed)
    unrealized = sum(float(p.get("unrealized_pnl") or 0) for p in pairs if p["state"] == "OPEN")
    return {
        "jobs": jobs, "notification_outbox": outbox, "control_audit": audit,
        "performance": {
            "closed_pairs": len(closed), "open_pairs": sum(p["state"] == "OPEN" for p in pairs),
            "win_rate_pct": round(wins / len(closed) * 100, 2) if closed else None,
            "realized_pnl": round(realized, 2), "unrealized_pnl": round(unrealized, 2),
        },
    }


def broker_snapshot(broker: AlpacaPaperClient) -> dict:
    account = broker.get_account()
    clock = broker.get_clock()
    positions = [dict(p) for p in broker.list_positions().items]
    orders = [dict(o) for o in broker.list_orders(status="open").items]
    return {
        "account": {"status": account.status, "equity": account.equity, "cash": account.cash,
                    "buying_power": account.buying_power, "portfolio_value": account.portfolio_value,
                    "trading_blocked": account.trading_blocked or account.account_blocked},
        "market": {"is_open": clock.is_open, "timestamp": clock.timestamp,
                   "next_open": clock.next_open, "next_close": clock.next_close},
        "positions": positions, "orders": orders,
    }


def run_today_workflow(broker: AlpacaPaperClient) -> dict:
    """Manual equivalent of the automatic scan and guarded entry jobs."""
    from .pair_execution import get_control, submit_pair_entry
    from .strategy_v4_live import StrategyV4DryScanner

    clock = broker.get_clock()
    market_now = datetime.fromisoformat(clock.timestamp.replace("Z", "+00:00")).astimezone(
        ZoneInfo("America/New_York"))
    if not clock.is_open:
        scan = StrategyV4DryScanner(broker=broker).run()
        summary = scan.get("summary") or {}
        return {
            "stage": "finalized_for_open",
            "run_id": scan.get("run_id"),
            "session_date": summary.get("session_date"),
            "qualified_pairs": int(summary.get("qualified_pairs") or 0),
            "submitted_pairs": 0,
            "message": "Today's Strategy 4 decisions are finalized; qualified pairs will enter during the guarded market-open window.",
            "scan": scan,
        }
    if (market_now.hour, market_now.minute) < (9, 30) or (market_now.hour, market_now.minute) >= (9, 45):
        raise ValueError("Manual entry is allowed only from 09:30 through 09:44 New York time")
    control = get_control()
    if not control["armed"] or control["kill_switch"]:
        raise ValueError("Automatic paper execution must be armed and the kill switch must be off")
    drafts = [p for p in list_pairs() if p["state"] == "DRAFT"
              and p["session_date"] == market_now.date().isoformat()]
    submitted = [submit_pair_entry(p["pair_trade_id"], broker) for p in drafts]
    return {
        "stage": "orders_submitted", "session_date": market_now.date().isoformat(),
        "qualified_pairs": len(drafts), "submitted_pairs": len(submitted),
        "message": f"Submitted {len(submitted)} qualified Strategy 4 pair(s) to Alpaca paper trading.",
    }
