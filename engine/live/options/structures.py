"""Multi-leg paper positions — the container every strategy family shares.

A "structure" is one strategy instance (condor, CSP, covered call, spread,
straddle-v2…) holding 1-4 legs. The straddle module (positions.py) predates
this and stays untouched; new strategy families build on this from Phase 1 on.

House rule enforced HERE, not in UI copy: `create_structure` REFUSES any
structure with unbounded loss (naked short calls). Cash-secured puts pass by
declaring `cash_secured=True`, which also sets the honest capital denominator
(strike − credit). This module never touches the equity portfolio's cash.
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime
from typing import Any, Optional

from ...db.schema import get_connection
from . import returns_math as rm
from .polygon_client import PolygonOptionsClient
from .pricing import get_pricing

log = logging.getLogger(__name__)

_ensured = False


def ensure_tables() -> None:
    global _ensured
    if _ensured:
        return
    conn = get_connection()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS options_multi_positions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                strategy_key TEXT, symbol TEXT, status TEXT DEFAULT 'open',
                entry_date TEXT, entry_value REAL,
                capital_at_risk REAL, max_profit REAL, max_loss REAL,
                breakevens TEXT, pop_est REAL, quoted_annualized_pct REAL,
                dte_at_entry INTEGER, earnings_date TEXT, exit_deadline TEXT,
                cash_secured INTEGER DEFAULT 0,
                current_value REAL, pnl_usd REAL, pnl_pct_on_risk REAL,
                last_marked TEXT,
                exit_date TEXT, exit_value REAL, exit_reason TEXT,
                final_pnl_usd REAL, final_pnl_pct_on_risk REAL,
                notes TEXT, created_at TEXT
            )""")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS options_multi_legs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                position_id INTEGER,
                side INTEGER, contract_type TEXT, strike REAL,
                expiry TEXT, qty INTEGER,
                entry_price REAL, current_price REAL,
                entry_delta REAL, current_delta REAL
            )""")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_multi_legs_pos "
                     "ON options_multi_legs(position_id)")
        conn.commit()
        _ensured = True
    finally:
        conn.close()


class StructureError(ValueError):
    """Raised when a structure violates the rulebook (e.g. unbounded risk)."""


def _validate_covered(legs: list[dict[str, Any]], cash_secured: bool) -> None:
    """Short contracts must be covered ONE-FOR-ONE by long contracts of the
    same type and expiry. A naked short put passes a naive 'bounded loss'
    test (stocks stop at zero) but strike−credit on a $200 name is still
    ruin — bounded is not the same as defined.

    The test is a COUNT per (contract_type, expiry), not a per-leg strike
    comparison, because:
      * counting per short leg lets ONE long be claimed by MANY shorts — a
        put ratio [short 100, short 95, long 90] would pass while being net
        short a put (loses >$10k/contract at spot 0);
      * requiring the long to sit further OTM wrongly refuses every DEBIT
        vertical (long 100C / short 110C is fully capped at the debit paid).
    With equal long/short counts of one type and expiry the payoff slope is
    flat beyond the outermost strike, so the worst case is always finite.
    Multi-expiry structures (calendars) are deliberately refused until the
    payoff engine models time value — it prices all legs at one expiry.
    """
    if cash_secured:
        return
    groups: dict[tuple[str, str], dict[str, int]] = {}
    for leg in legs:
        g = groups.setdefault((leg["contract_type"], leg["expiry"]),
                              {"short": 0, "long": 0})
        g["short" if leg["side"] < 0 else "long"] += int(leg.get("qty", 1))
    for (ctype, expiry), g in groups.items():
        if g["short"] > g["long"]:
            naked = g["short"] - g["long"]
            raise StructureError(
                f"{naked} short {ctype}(s) expiring {expiry} are not covered "
                f"by a protective long of the same type/expiry — refused by "
                f"the defined-risk rule (declare cash_secured for a single "
                f"secured put)")


def create_structure(strategy_key: str, symbol: str, legs: list[dict[str, Any]],
                     *, cash_secured: bool = False,
                     earnings_date: Optional[str] = None,
                     exit_deadline: Optional[str] = None,
                     notes: str = "") -> int:
    """Create an open paper structure. Legs must carry entry `price` (and
    ideally `delta`). Refuses unbounded-risk structures outright."""
    if not legs or len(legs) > 4:
        raise StructureError("a structure needs 1-4 legs")
    for leg in legs:
        if leg.get("price") is None:
            raise StructureError(f"leg {leg.get('contract_type')} "
                                 f"{leg.get('strike')} has no price")

    _validate_covered(legs, cash_secured)
    entry_value = rm.package_value(legs)
    stats = rm.payoff_stats(legs, entry_value)
    if stats["unbounded_loss"] and not cash_secured:
        raise StructureError(
            "structure has UNLIMITED loss potential (naked short exposure) — "
            "refused by the defined-risk rule. Add a protective long leg.")
    if cash_secured:
        shorts = [l for l in legs if l["side"] < 0]
        if len(legs) != 1 or not shorts or shorts[0]["contract_type"] != "put":
            raise StructureError("cash_secured applies only to a single short put")
        capital = rm.capital_at_risk(legs, entry_value,
                                     cash_secured_strike=shorts[0]["strike"])
    else:
        capital = rm.capital_at_risk(legs, entry_value)
    if not capital or capital <= 0:
        raise StructureError("capital at risk computed as zero — refusing")

    dte = None
    try:
        dte = (min(date.fromisoformat(l["expiry"]) for l in legs)
               - date.today()).days
    except ValueError:
        pass
    income = -entry_value if entry_value < 0 else None  # credit received
    quoted_ann = (rm.annualized_yield_pct(income, capital, dte)
                  if income and dte else None)

    ensure_tables()
    conn = get_connection()
    try:
        cur = conn.execute("""
            INSERT INTO options_multi_positions
                (strategy_key, symbol, status, entry_date, entry_value,
                 capital_at_risk, max_profit, max_loss, breakevens, pop_est,
                 quoted_annualized_pct, dte_at_entry, earnings_date,
                 exit_deadline, cash_secured, current_value, pnl_usd,
                 pnl_pct_on_risk, notes, created_at)
            VALUES (?,?,'open',?,?,?,?,?,?,?,?,?,?,?,?,?,0,0,?,?)
            """, (strategy_key, symbol.upper(), date.today().isoformat(),
                  entry_value, capital, stats["max_profit"], stats["max_loss"],
                  json.dumps(stats["breakevens"]), rm.pop_estimate_pct(legs),
                  quoted_ann, dte, earnings_date, exit_deadline,
                  1 if cash_secured else 0, entry_value, notes,
                  datetime.utcnow().isoformat()))
        pos_id = int(cur.lastrowid)
        for leg in legs:
            conn.execute("""
                INSERT INTO options_multi_legs
                    (position_id, side, contract_type, strike, expiry, qty,
                     entry_price, current_price, entry_delta, current_delta)
                VALUES (?,?,?,?,?,?,?,?,?,?)
                """, (pos_id, leg["side"], leg["contract_type"], leg["strike"],
                      leg["expiry"], leg.get("qty", 1), leg["price"],
                      leg["price"], leg.get("delta"), leg.get("delta")))
        conn.commit()
    finally:
        conn.close()
    log.info("structures: opened %s on %s (#%d, capital $%.0f/share-set)",
             strategy_key, symbol, pos_id, capital)
    return pos_id


def _rows_to_position(pos: dict, legs: list[dict]) -> dict[str, Any]:
    pos["legs"] = legs
    try:
        pos["breakevens"] = json.loads(pos.get("breakevens") or "[]")
    except (TypeError, ValueError):
        pos["breakevens"] = []
    return pos


def list_structures(status: Optional[str] = None,
                    limit: int = 200) -> list[dict[str, Any]]:
    ensure_tables()
    conn = get_connection()
    try:
        if status:
            rows = conn.execute(
                "SELECT * FROM options_multi_positions WHERE status=? "
                "ORDER BY id DESC LIMIT ?", (status, limit)).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM options_multi_positions ORDER BY id DESC "
                "LIMIT ?", (limit,)).fetchall()
        out = []
        for r in rows:
            legs = conn.execute(
                "SELECT * FROM options_multi_legs WHERE position_id=? "
                "ORDER BY id", (r["id"],)).fetchall()
            out.append(_rows_to_position(dict(r), [dict(l) for l in legs]))
        return out
    finally:
        conn.close()


def get_structure(position_id: int) -> Optional[dict[str, Any]]:
    ensure_tables()
    conn = get_connection()
    try:
        r = conn.execute("SELECT * FROM options_multi_positions WHERE id=?",
                         (position_id,)).fetchone()
        if not r:
            return None
        legs = conn.execute(
            "SELECT * FROM options_multi_legs WHERE position_id=? ORDER BY id",
            (position_id,)).fetchall()
        return _rows_to_position(dict(r), [dict(l) for l in legs])
    finally:
        conn.close()


async def mark_structures(status: str = "open") -> dict[str, Any]:
    """Re-price every open structure through the pricing interface."""
    positions = list_structures(status)
    if not positions:
        return {"marked": 0}
    marked = 0
    async with PolygonOptionsClient() as poly:
        pricing = get_pricing(poly)
        for pos in positions:
            legs_in = [{"side": l["side"], "contract_type": l["contract_type"],
                        "strike": l["strike"], "expiry": l["expiry"],
                        "qty": l["qty"]} for l in pos["legs"]]
            try:
                quoted = await pricing.quote_legs(pos["symbol"], legs_in)
            except Exception as e:  # noqa: BLE001
                log.warning("mark structure #%d failed: %s", pos["id"], e)
                continue
            value = rm.package_value(quoted)
            if value is None:
                continue
            pnl = rm.pnl_usd(pos["entry_value"], value)
            pnl_pct = (round(pnl / (pos["capital_at_risk"] * rm.MULT) * 100, 2)
                       if pos.get("capital_at_risk") else None)
            conn = get_connection()
            try:
                conn.execute(
                    "UPDATE options_multi_positions SET current_value=?, "
                    "pnl_usd=?, pnl_pct_on_risk=?, last_marked=? WHERE id=?",
                    (value, pnl, pnl_pct, datetime.utcnow().isoformat(),
                     pos["id"]))
                for db_leg, q in zip(pos["legs"], quoted):
                    conn.execute(
                        "UPDATE options_multi_legs SET current_price=?, "
                        "current_delta=? WHERE id=?",
                        (q.get("price"), q.get("delta"), db_leg["id"]))
                conn.commit()
            finally:
                conn.close()
            marked += 1
    return {"marked": marked, "open": len(positions)}


async def close_structure(position_id: int,
                          reason: str = "manual") -> Optional[dict[str, Any]]:
    """Close a paper structure at the freshest obtainable package value."""
    pos = get_structure(position_id)
    if not pos or pos["status"] != "open":
        return None
    exit_value = pos.get("current_value")
    try:
        async with PolygonOptionsClient() as poly:
            pricing = get_pricing(poly)
            legs_in = [{"side": l["side"], "contract_type": l["contract_type"],
                        "strike": l["strike"], "expiry": l["expiry"],
                        "qty": l["qty"]} for l in pos["legs"]]
            quoted = await pricing.quote_legs(pos["symbol"], legs_in)
            fresh = rm.package_value(quoted)
            if fresh is not None:
                exit_value = fresh
    except Exception as e:  # noqa: BLE001
        log.warning("close mark failed for structure #%d (using last mark): %s",
                    position_id, e)

    # Never invent a result: if the structure was never successfully marked AND
    # the closing quote failed, exit_value would silently equal entry_value and
    # book a 0.00 "realized" P&L into the league table forever. Record the close
    # with NULL P&L instead, flagged in the reason, and let family_stats skip it.
    unmarked = exit_value is None or (pos.get("last_marked") is None
                                      and exit_value == pos["entry_value"])
    if unmarked:
        conn = get_connection()
        try:
            conn.execute(
                "UPDATE options_multi_positions SET status='closed', "
                "exit_date=?, exit_value=NULL, exit_reason=?, "
                "final_pnl_usd=NULL, final_pnl_pct_on_risk=NULL WHERE id=?",
                (date.today().isoformat(), f"{reason}:unpriced", position_id))
            conn.commit()
        finally:
            conn.close()
        log.warning("structure #%d closed WITHOUT a price — P&L recorded as "
                    "unknown, excluded from the league table", position_id)
        return get_structure(position_id)

    pnl = rm.pnl_usd(pos["entry_value"], exit_value)
    pnl_pct = (round(pnl / (pos["capital_at_risk"] * rm.MULT) * 100, 2)
               if pos.get("capital_at_risk") else None)
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE options_multi_positions SET status='closed', exit_date=?, "
            "exit_value=?, exit_reason=?, final_pnl_usd=?, "
            "final_pnl_pct_on_risk=? WHERE id=?",
            (date.today().isoformat(), exit_value, reason, pnl, pnl_pct,
             position_id))
        conn.commit()
    finally:
        conn.close()
    return get_structure(position_id)


def family_stats() -> dict[str, dict[str, Any]]:
    """Realized (Layer 3) numbers per strategy family — the league table's
    data source. Return axis: % on capital at risk."""
    ensure_tables()
    conn = get_connection()
    try:
        # Closed-but-unpriced positions carry NULL P&L (see close_structure) —
        # excluded so an unknown never masquerades as a break-even trade.
        rows = conn.execute(
            "SELECT strategy_key, final_pnl_usd, final_pnl_pct_on_risk, "
            "capital_at_risk, entry_date, exit_date FROM "
            "options_multi_positions WHERE status='closed' "
            "AND final_pnl_usd IS NOT NULL").fetchall()
    finally:
        conn.close()
    fams: dict[str, list[dict]] = {}
    for r in rows:
        fams.setdefault(r["strategy_key"], []).append(dict(r))
    out = {}
    for key, trades in fams.items():
        pnls = [t["final_pnl_usd"] for t in trades]
        pcts = [t["final_pnl_pct_on_risk"] for t in trades
                if t["final_pnl_pct_on_risk"] is not None]
        wins = [p for p in pnls if p > 0]
        out[key] = {
            "trades": len(trades),
            "win_rate_pct": round(len(wins) / len(pnls) * 100) if pnls else None,
            "total_pnl_usd": round(sum(pnls), 2),
            "avg_return_on_risk_pct": (round(sum(pcts) / len(pcts), 1)
                                       if pcts else None),
            "worst_trade_usd": round(min(pnls), 2) if pnls else None,
        }
    return out
