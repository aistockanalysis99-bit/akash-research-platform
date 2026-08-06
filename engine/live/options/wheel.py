"""Phase 4 — the wheel, as a state machine with a ledger.

A wheel is one capital commitment cycling through states:

    CASH ──sell CSP──▶ CSP_OPEN ──expired──▶ CASH        (premium banked, repeat)
                            └───assigned──▶ HOLDING       (own stock at strike)
    HOLDING ──sell CC──▶ CC_OPEN ──expired──▶ HOLDING     (premium banked, repeat)
                              └─called away─▶ COMPLETE    (cycle closed, ROI booked)

Every leg's premium lands in the ledger; TRUE COST BASIS = assigned price
minus every premium banked since the cycle started. The user confirms what
actually happened in the broker (assigned / expired / called away) — the
platform never assumes an outcome, it only *suggests* one on expiry day by
comparing the close to the strike.

Wheels are self-contained paper positions: legs live in this module's own
ledger (not options_multi_positions), because a wheel's covered call is
backed by the wheel's OWN assigned shares — not the equity portfolio — so
the stock_covered gate deliberately does not apply here. Capital at risk is
recorded once at cycle start (the secured cash) and never changes silently.
"""
from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any, Optional

from ...db.schema import get_connection

log = logging.getLogger(__name__)

_ensured = False

STATES = ("CASH", "CSP_OPEN", "HOLDING", "CC_OPEN", "COMPLETE", "ABANDONED")
LEG_KINDS = ("csp", "cc")
OUTCOMES = ("expired", "assigned", "called_away", "closed_early")


def ensure_tables() -> None:
    global _ensured
    if _ensured:
        return
    conn = get_connection()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS options_wheels (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT, state TEXT DEFAULT 'CASH',
                qty INTEGER DEFAULT 1,
                capital_per_share REAL,
                assigned_price REAL,
                premiums_net REAL DEFAULT 0,
                exit_price REAL,
                cycle_roi_pct REAL,
                started_at TEXT, completed_at TEXT, notes TEXT
            )""")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS options_wheel_legs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                wheel_id INTEGER, seq INTEGER,
                kind TEXT, strike REAL, expiry TEXT,
                premium REAL, qty INTEGER,
                outcome TEXT, close_price REAL,
                opened_at TEXT, closed_at TEXT
            )""")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_wheel_legs "
                     "ON options_wheel_legs(wheel_id)")
        conn.commit()
        _ensured = True
    finally:
        conn.close()


class WheelError(ValueError):
    """State-machine rule violated (wrong leg for the state, bad outcome…)."""


def _wheel_row(conn, wheel_id: int) -> dict[str, Any]:
    r = conn.execute("SELECT * FROM options_wheels WHERE id=?",
                     (wheel_id,)).fetchone()
    if not r:
        raise WheelError(f"wheel #{wheel_id} not found")
    return dict(r)


def start_wheel(symbol: str, qty: int = 1, notes: str = "") -> int:
    """A new wheel in CASH state. qty = contracts (100-share lots)."""
    ensure_tables()
    conn = get_connection()
    try:
        cur = conn.execute(
            "INSERT INTO options_wheels (symbol, state, qty, started_at, notes) "
            "VALUES (?,?,?,?,?)",
            (symbol.upper(), "CASH", max(1, int(qty)),
             datetime.utcnow().isoformat(), notes))
        conn.commit()
        return int(cur.lastrowid)
    finally:
        conn.close()


def open_leg(wheel_id: int, kind: str, strike: float, expiry: str,
             premium: float, qty: Optional[int] = None) -> int:
    """Record a sold option leg. CSPs only from CASH; CCs only from HOLDING.
    The state machine — not the UI — enforces the wheel's grammar."""
    if kind not in LEG_KINDS:
        raise WheelError(f"leg kind must be one of {LEG_KINDS}")
    if premium <= 0 or strike <= 0:
        raise WheelError("strike and premium must be positive")
    try:
        date.fromisoformat(expiry)
    except ValueError:
        raise WheelError("expiry must be ISO YYYY-MM-DD")
    ensure_tables()
    conn = get_connection()
    try:
        w = _wheel_row(conn, wheel_id)
        if kind == "csp" and w["state"] != "CASH":
            raise WheelError(f"a CSP can only be sold from CASH "
                             f"(wheel is {w['state']})")
        if kind == "cc" and w["state"] != "HOLDING":
            raise WheelError(f"a covered call can only be sold while HOLDING "
                             f"stock (wheel is {w['state']})")
        try:
            leg_qty = int(qty) if qty is not None else int(w["qty"])
        except (TypeError, ValueError):
            raise WheelError("qty must be an integer")
        # The ledger (premiums_net, capital, basis) is per-share AT WHEEL QTY;
        # a leg with a different qty would silently corrupt every downstream
        # dollar/ROI conversion (review finding). One wheel = one lot size.
        if leg_qty != int(w["qty"]):
            raise WheelError(f"leg qty {leg_qty} must match the wheel's "
                             f"{w['qty']} contract(s) — start a separate "
                             f"wheel for a different size")
        seq = conn.execute(
            "SELECT COALESCE(MAX(seq),0)+1 AS s FROM options_wheel_legs "
            "WHERE wheel_id=?", (wheel_id,)).fetchone()["s"]
        cur = conn.execute(
            "INSERT INTO options_wheel_legs (wheel_id, seq, kind, strike, "
            "expiry, premium, qty, opened_at) VALUES (?,?,?,?,?,?,?,?)",
            (wheel_id, seq, kind, strike, expiry, premium, leg_qty,
             datetime.utcnow().isoformat()))
        new_state = "CSP_OPEN" if kind == "csp" else "CC_OPEN"
        fields = {"state": new_state}
        if kind == "csp" and w["capital_per_share"] is None:
            # capital committed = the FIRST secured strike; recorded once,
            # the honest ROI denominator for the whole cycle.
            fields["capital_per_share"] = strike
        sets = ", ".join(f"{k}=?" for k in fields)
        conn.execute(f"UPDATE options_wheels SET {sets} WHERE id=?",
                     (*fields.values(), wheel_id))
        conn.commit()
        return int(cur.lastrowid)
    finally:
        conn.close()


def resolve_leg(wheel_id: int, leg_id: int, outcome: str,
                close_price: Optional[float] = None) -> dict[str, Any]:
    """The user confirms what happened in the broker. Transitions:
    csp expired → CASH · csp assigned → HOLDING · cc expired → HOLDING ·
    cc called_away → COMPLETE (ROI booked) · closed_early → back to the
    state's resting point with net premium adjusted by the buyback price."""
    if outcome not in OUTCOMES:
        raise WheelError(f"outcome must be one of {OUTCOMES}")
    ensure_tables()
    conn = get_connection()
    try:
        w = _wheel_row(conn, wheel_id)
        leg = conn.execute(
            "SELECT * FROM options_wheel_legs WHERE id=? AND wheel_id=?",
            (leg_id, wheel_id)).fetchone()
        if not leg:
            raise WheelError(f"leg #{leg_id} not on wheel #{wheel_id}")
        leg = dict(leg)
        if leg["outcome"]:
            raise WheelError(f"leg #{leg_id} already resolved ({leg['outcome']})")
        expected_state = "CSP_OPEN" if leg["kind"] == "csp" else "CC_OPEN"
        if w["state"] != expected_state:
            raise WheelError(f"wheel is {w['state']} — leg #{leg_id} can't "
                             f"resolve from here")
        if leg["kind"] == "csp" and outcome == "called_away":
            raise WheelError("a put can't be called away")
        if leg["kind"] == "cc" and outcome == "assigned":
            raise WheelError("use called_away for a covered call that "
                             "exercised")
        if outcome == "closed_early" and (close_price is None
                                          or close_price < 0):
            raise WheelError("closed_early needs the buyback price")

        premium_net = leg["premium"] - (close_price or 0.0
                                        if outcome == "closed_early" else 0.0)
        fields: dict[str, Any] = {
            "premiums_net": (w["premiums_net"] or 0.0) + premium_net}
        if leg["kind"] == "csp":
            if outcome == "assigned":
                fields["state"] = "HOLDING"
                fields["assigned_price"] = leg["strike"]
            else:  # expired / closed_early
                fields["state"] = "CASH"
        else:  # cc
            if outcome == "called_away":
                fields["state"] = "COMPLETE"
                fields["exit_price"] = leg["strike"]
                fields["completed_at"] = datetime.utcnow().isoformat()
                capital = w["capital_per_share"] or leg["strike"]
                stock_pnl = leg["strike"] - (w["assigned_price"]
                                             or leg["strike"])
                total = fields["premiums_net"] + stock_pnl
                fields["cycle_roi_pct"] = round(total / capital * 100, 2)
            else:  # expired / closed_early
                fields["state"] = "HOLDING"

        conn.execute(
            "UPDATE options_wheel_legs SET outcome=?, close_price=?, "
            "closed_at=? WHERE id=?",
            (outcome, close_price, datetime.utcnow().isoformat(), leg_id))
        sets = ", ".join(f"{k}=?" for k in fields)
        conn.execute(f"UPDATE options_wheels SET {sets} WHERE id=?",
                     (*fields.values(), wheel_id))
        conn.commit()
        return get_wheel(wheel_id)
    finally:
        conn.close()


def abandon_wheel(wheel_id: int,
                  exit_price: Optional[float] = None) -> dict[str, Any]:
    """Close a wheel without a called-away exit (user unwound it in the
    broker). Any open leg must be resolved first.

    From CASH the premiums-only ROI is exact. From HOLDING the shares'
    disposal price is REQUIRED — booking a premiums-only "profit" while
    ignoring what the stock actually sold for would flatter every abandoned
    cycle in the league table (review HIGH)."""
    ensure_tables()
    conn = get_connection()
    try:
        w = _wheel_row(conn, wheel_id)
        if w["state"] in ("COMPLETE", "ABANDONED"):
            raise WheelError("wheel already finished")
        if w["state"] in ("CSP_OPEN", "CC_OPEN"):
            raise WheelError("resolve the open leg first (expired / "
                             "closed_early), then abandon")
        capital = w["capital_per_share"]
        holding = w["state"] == "HOLDING" and w["assigned_price"] is not None
        if holding and (exit_price is None or exit_price < 0):
            raise WheelError("this wheel HOLDS stock — the price the shares "
                             "were sold for is required to book an honest ROI")
        total = (w["premiums_net"] or 0.0)
        if holding:
            total += float(exit_price) - float(w["assigned_price"])
        roi = round(total / capital * 100, 2) if capital else None
        conn.execute(
            "UPDATE options_wheels SET state='ABANDONED', completed_at=?, "
            "cycle_roi_pct=?, exit_price=? WHERE id=?",
            (datetime.utcnow().isoformat(), roi,
             float(exit_price) if holding else None, wheel_id))
        conn.commit()
        return get_wheel(wheel_id)
    finally:
        conn.close()


def get_wheel(wheel_id: int) -> dict[str, Any]:
    ensure_tables()
    conn = get_connection()
    try:
        w = _wheel_row(conn, wheel_id)
        legs = [dict(r) for r in conn.execute(
            "SELECT * FROM options_wheel_legs WHERE wheel_id=? ORDER BY seq",
            (wheel_id,)).fetchall()]
    finally:
        conn.close()
    w["legs"] = legs
    if w.get("assigned_price") is not None:
        w["effective_basis"] = round(
            w["assigned_price"] - (w["premiums_net"] or 0), 4)
    else:
        w["effective_basis"] = None
    return w


def list_wheels(active_only: bool = False) -> list[dict[str, Any]]:
    ensure_tables()
    conn = get_connection()
    try:
        q = "SELECT id FROM options_wheels"
        if active_only:
            q += " WHERE state NOT IN ('COMPLETE','ABANDONED')"
        q += " ORDER BY id DESC"
        ids = [r["id"] for r in conn.execute(q).fetchall()]
    finally:
        conn.close()
    return [get_wheel(i) for i in ids]


def wheel_league_row() -> Optional[dict[str, Any]]:
    """Completed cycles as a league-table family (return axis: cycle ROI on
    committed capital — directly comparable to the other families)."""
    done = [w for w in list_wheels()
            if w["state"] in ("COMPLETE", "ABANDONED")
            and w.get("cycle_roi_pct") is not None]
    if not done:
        return None
    rois = [w["cycle_roi_pct"] for w in done]
    pnls = [round((w["cycle_roi_pct"] / 100) * (w["capital_per_share"] or 0)
                  * 100 * (w["qty"] or 1), 2) for w in done]
    wins = [r for r in rois if r > 0]
    return {
        "trades": len(done),
        "win_rate_pct": round(len(wins) / len(rois) * 100),
        "total_pnl_usd": round(sum(pnls), 2),
        "avg_return_on_risk_pct": round(sum(rois) / len(rois), 1),
        "worst_trade_usd": round(min(pnls), 2),
    }


async def expiry_day_suggestions(notify: bool = True) -> int:
    """On/after a leg's expiry, compare the close to the strike and SUGGEST
    the likely outcome on Telegram. Never resolves anything itself — the
    broker's reality, confirmed by the user, is the only source of truth."""
    ensure_tables()
    today = date.today().isoformat()
    pending = []
    for w in list_wheels(active_only=True):
        for leg in w["legs"]:
            # Strictly AFTER expiry: the 09:20 morning job would otherwise
            # announce "expired" 6.5 hours early using YESTERDAY's close.
            # The morning after, fetch_daily's last bar IS the expiry close.
            if leg["outcome"] or leg["expiry"] >= today:
                continue
            try:
                from ...data.fmp_client import FMPClient
                async with FMPClient() as fmp:
                    bars = await fmp.fetch_daily(w["symbol"])
                spot = float(bars["close"].iloc[-1]) if bars is not None \
                    and not bars.empty else None
            except Exception:  # noqa: BLE001
                spot = None
            if spot is None:
                guess = "check your broker"
            elif leg["kind"] == "csp":
                guess = ("likely ASSIGNED — mark it and the wheel moves to "
                         "HOLDING" if spot < leg["strike"]
                         else "likely EXPIRED worthless — premium banked, "
                              "sell the next put")
            else:
                guess = ("likely CALLED AWAY — cycle completes, ROI books"
                         if spot > leg["strike"]
                         else "likely EXPIRED worthless — premium banked, "
                              "sell the next call")
            pending.append({
                "symbol": w["symbol"],
                "text": (f"🎡 {w['symbol']} wheel #{w['id']}: the "
                         f"${leg['strike']} {leg['kind'].upper()} expired "
                         f"{leg['expiry']}"
                         + (f" · close ${spot:,.2f} → {guess}" if spot
                            else f" — {guess}")
                         + ".\nConfirm the outcome on the Wheel page; "
                           "nothing is assumed."),
            })
    if notify and pending:
        try:
            from ..telegram import telegram as _telegram
            client = _telegram()
            for a in pending:
                await client.send_message(a["text"], kind="options_alert",
                                          symbol=a["symbol"])
        except Exception as e:  # noqa: BLE001
            log.warning("wheel expiry suggestions send failed: %s", e)
    return len(pending)
