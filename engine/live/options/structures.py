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
        # lightweight migrations
        for col, decl in (("exit_alerted", "INTEGER DEFAULT 0"),
                          ("stock_covered", "INTEGER DEFAULT 0"),
                          ("coverage_alerted", "INTEGER DEFAULT 0"),
                          ("real_entry_value", "REAL"),
                          ("real_exit_value", "REAL")):
            try:
                conn.execute(f"ALTER TABLE options_multi_positions "
                             f"ADD COLUMN {col} {decl}")
            except Exception:  # noqa: BLE001 — column already exists
                pass
        for col in ("current_theta", "current_vega"):
            try:
                conn.execute(f"ALTER TABLE options_multi_legs "
                             f"ADD COLUMN {col} REAL")
            except Exception:  # noqa: BLE001 — column already exists
                pass
        conn.commit()
        _ensured = True
    finally:
        conn.close()


class StructureError(ValueError):
    """Raised when a structure violates the rulebook (e.g. unbounded risk)."""


def _committed_covered_shares(symbol: str) -> int:
    """Shares already backing OPEN covered calls on this symbol."""
    ensure_tables()
    conn = get_connection()
    try:
        r = conn.execute(
            "SELECT COALESCE(SUM(l.qty),0)*100 AS n FROM options_multi_legs l "
            "JOIN options_multi_positions p ON p.id=l.position_id "
            "WHERE p.status='open' AND p.stock_covered=1 "
            "AND UPPER(p.symbol)=? AND l.side<0 AND l.contract_type='call'",
            (symbol.upper(),)).fetchone()
        return int(r["n"] or 0)
    finally:
        conn.close()


def _verify_stock_coverage(symbol: str, contracts: int) -> None:
    """A covered call is only 'covered' if the fund ACTUALLY holds the shares
    — IN AGGREGATE. Verified here, inside the gate, against the live
    portfolio minus shares already committed to open covered calls on the
    same symbol; otherwise tracking the same card twice would book more
    short calls than the holding backs, each passing individually
    (review HIGH). 1 contract = 100 shares."""
    needed = contracts * 100
    held = 0.0
    try:
        from ..portfolio import VirtualPortfolio
        p = VirtualPortfolio()
        try:
            for pos in p.list_open():
                if (pos.get("instrument_type") or "stock") == "stock" \
                        and pos["symbol"].upper() == symbol.upper():
                    held += float(pos.get("units") or 0)
        finally:
            p.close_conn()
    except Exception as e:  # noqa: BLE001
        raise StructureError(f"could not verify share coverage: {e}")
    committed = _committed_covered_shares(symbol)
    free = held - committed
    if free < needed:
        raise StructureError(
            f"covered call needs {needed} free {symbol.upper()} shares — "
            f"portfolio holds {held:.0f}, {committed} already committed to "
            f"open covered calls, {max(free, 0):.0f} free. Refused.")


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
                     stock_covered: bool = False,
                     capital_override: Optional[float] = None,
                     earnings_date: Optional[str] = None,
                     exit_deadline: Optional[str] = None,
                     notes: str = "") -> int:
    """Create an open paper structure. Legs must carry entry `price` (and
    ideally `delta`). Refuses unbounded-risk structures outright.

    `stock_covered` is the NARROW covered-call exception: exactly one short
    call leg, and the gate itself verifies the portfolio holds 100 shares per
    contract before accepting. `capital_override` (per share-set, like
    entry_value) sets the honest capital denominator — for a covered call
    that's the stock value backing it, since the option leg alone would
    otherwise look like free money."""
    if not legs or len(legs) > 4:
        raise StructureError("a structure needs 1-4 legs")
    for leg in legs:
        if leg.get("price") is None:
            raise StructureError(f"leg {leg.get('contract_type')} "
                                 f"{leg.get('strike')} has no price")
    if cash_secured and stock_covered:
        raise StructureError("a structure is cash_secured OR stock_covered, "
                             "never both")

    if stock_covered:
        shorts = [l for l in legs if l["side"] < 0]
        if len(legs) != 1 or not shorts \
                or shorts[0]["contract_type"] != "call":
            raise StructureError("stock_covered applies only to a single "
                                 "short call")
        _verify_stock_coverage(symbol, int(shorts[0].get("qty", 1)))
    else:
        _validate_covered(legs, cash_secured)

    entry_value = rm.package_value(legs)
    stats = rm.payoff_stats(legs, entry_value)
    if stats["unbounded_loss"] and not (cash_secured or stock_covered):
        raise StructureError(
            "structure has UNLIMITED loss potential (naked short exposure) — "
            "refused by the defined-risk rule. Add a protective long leg.")
    if stock_covered:
        if not capital_override or capital_override <= 0:
            raise StructureError("covered call requires capital_override = "
                                 "backing stock value per share-set")
        capital = round(capital_override, 4)
    elif cash_secured:
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
    if dte is not None and dte < 0:
        raise StructureError("legs are already expired — refusing to open "
                             "(stale card or bad expiry)")
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
                 exit_deadline, cash_secured, stock_covered, current_value,
                 pnl_usd, pnl_pct_on_risk, notes, created_at)
            VALUES (?,?,'open',?,?,?,?,?,?,?,?,?,?,?,?,?,?,0,0,?,?)
            """, (strategy_key, symbol.upper(), date.today().isoformat(),
                  entry_value, capital, stats["max_profit"], stats["max_loss"],
                  json.dumps(stats["breakevens"]), rm.pop_estimate_pct(legs),
                  quoted_ann, dte, earnings_date, exit_deadline,
                  1 if cash_secured else 0, 1 if stock_covered else 0,
                  entry_value, notes, datetime.utcnow().isoformat()))
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
                        "current_delta=?, current_theta=?, current_vega=? "
                        "WHERE id=?",
                        (q.get("price"), q.get("delta"), q.get("theta"),
                         q.get("vega"), db_leg["id"]))
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


async def check_exit_alerts(notify: bool = True) -> int:
    """One-time exit SUGGESTION for open structures on their exit-deadline
    DAY (e.g. condors: the morning after earnings). Never closes anything.

    Two deliberate semantics, both review findings:
    * MORNING-OF, not moment-after: the 09:20 ET sweep must warn before a
      10:00 ET deadline, so the trigger is calendar-day based — a strict
      `now < deadline` skip would push every alert to the NEXT day's run.
    * Flag AFTER delivery: exit_alerted is only set once Telegram confirms
      the send. Flag-first would burn the once-only alert on a failed send
      and the suggestion would be lost forever. With notify=False nothing is
      flagged — detection defers to the next notifying run.
    """
    from zoneinfo import ZoneInfo
    et = ZoneInfo("America/New_York")
    now = datetime.now(et)
    pending = []
    for pos in list_structures("open"):
        deadline_raw = pos.get("exit_deadline")
        if not deadline_raw or pos.get("exit_alerted"):
            continue
        try:
            deadline = datetime.fromisoformat(deadline_raw)
        except ValueError:
            continue
        if deadline.tzinfo is None:
            deadline = deadline.replace(tzinfo=et)
        if now.date() < deadline.date():
            continue
        pnl = pos.get("pnl_usd")
        pnl_txt = (f" Current P&L {pnl:+,.0f} USD "
                   f"({pos.get('pnl_pct_on_risk') or 0:+.1f}% on risk).") \
            if pnl is not None else ""
        pending.append({
            "id": pos["id"],
            "symbol": pos["symbol"], "kind": "options_exit",
            "text": (f"⏰ {pos['symbol']} {pos['strategy_key'].replace('_', ' ')} "
                     f"#{pos['id']} — exit point is "
                     f"{deadline.strftime('%b %d %H:%M ET')}.{pnl_txt}\n"
                     f"Suggestion: close it in your account and mark it closed "
                     f"on the platform. Nothing was changed — your call."),
        })
    if not pending:
        return 0
    if not notify:
        log.info("structure exit alerts: %d due, deferred (notify=False)",
                 len(pending))
        return 0

    sent = 0
    try:
        from ..telegram import telegram as _telegram
        client = _telegram()
    except Exception as e:  # noqa: BLE001
        log.warning("structure exit alerts: telegram unavailable: %s", e)
        return 0
    for a in pending:
        try:
            ok = await client.send_message(a["text"], kind=a["kind"],
                                           symbol=a.get("symbol"))
        except Exception as e:  # noqa: BLE001
            log.warning("structure exit alert send failed for #%d: %s",
                        a["id"], e)
            ok = False
        if ok:
            conn = get_connection()
            try:
                conn.execute("UPDATE options_multi_positions SET "
                             "exit_alerted=1 WHERE id=?", (a["id"],))
                conn.commit()
            finally:
                conn.close()
            sent += 1
    return sent


async def check_coverage_alerts(notify: bool = True) -> int:
    """Daily watchdog: a covered call is only covered while the shares are
    still held. If the equity side sold/trimmed the backing position, the
    short call is now effectively naked — alert ONCE (flag only after
    confirmed delivery), never auto-close. Review HIGH: without this, a
    stock_covered flag set at creation would stay true forever."""
    open_cc = [p for p in list_structures("open")
               if p.get("stock_covered") and not p.get("coverage_alerted")]
    if not open_cc:
        return 0
    pending = []
    for pos in open_cc:
        qty = sum(int(l.get("qty", 1)) for l in pos["legs"] if l["side"] < 0)
        # Exclude this position's own commitment from the aggregate check:
        # verify the holding still covers EVERYTHING currently open.
        try:
            _verify_stock_coverage(pos["symbol"], 0)
            still_ok = True
        except StructureError:
            still_ok = False
        if still_ok:
            continue
        pending.append({
            "id": pos["id"], "symbol": pos["symbol"],
            "text": (f"🚨 {pos['symbol']} covered call #{pos['id']} has LOST "
                     f"its share backing — the portfolio no longer holds "
                     f"enough {pos['symbol']} to cover {qty} contract(s). "
                     f"The short call is now effectively naked.\n"
                     f"Suggestion: close the call in your account (and mark "
                     f"it closed here) or restore the shares. Nothing was "
                     f"changed — your call."),
        })
    if not pending:
        return 0
    if not notify:
        return 0
    sent = 0
    try:
        from ..telegram import telegram as _telegram
        client = _telegram()
    except Exception as e:  # noqa: BLE001
        log.warning("coverage alerts: telegram unavailable: %s", e)
        return 0
    for a in pending:
        try:
            ok = await client.send_message(a["text"], kind="options_alert",
                                           symbol=a["symbol"])
        except Exception as e:  # noqa: BLE001
            log.warning("coverage alert send failed for #%d: %s", a["id"], e)
            ok = False
        if ok:
            conn = get_connection()
            try:
                conn.execute("UPDATE options_multi_positions SET "
                             "coverage_alerted=1 WHERE id=?", (a["id"],))
                conn.commit()
            finally:
                conn.close()
            sent += 1
    return sent


def greeks_rollup() -> dict[str, Any]:
    """Portfolio-level Greeks across OPEN multi-leg structures, from the last
    mark. Share-equivalents: net delta × 100 per contract. Honest about
    coverage — positions never marked (no greeks yet) are counted and named,
    not silently treated as zero."""
    open_pos = list_structures("open")
    by_symbol: dict[str, dict[str, float]] = {}
    unmarked: list[str] = []
    for pos in open_pos:
        legs = pos["legs"]
        if any(l.get("current_delta") is None for l in legs):
            unmarked.append(f"{pos['symbol']}#{pos['id']}")
            continue
        agg = by_symbol.setdefault(pos["symbol"],
                                   {"delta": 0.0, "theta": 0.0, "vega": 0.0})
        for l in legs:
            mult = l["side"] * l["qty"] * 100
            agg["delta"] += (l.get("current_delta") or 0) * mult
            agg["theta"] += (l.get("current_theta") or 0) * mult
            agg["vega"] += (l.get("current_vega") or 0) * mult
    totals = {k: round(sum(s[k] for s in by_symbol.values()), 1)
              for k in ("delta", "theta", "vega")}
    return {
        "totals": totals,
        "per_symbol": {sym: {k: round(v, 1) for k, v in s.items()}
                       for sym, s in by_symbol.items()},
        "positions_counted": len(open_pos) - len(unmarked),
        "unmarked": unmarked,
        "note": ("Share-equivalents: delta +100 ≈ owning 100 shares' worth of "
                 "direction. Theta is $/day for the whole book; vega is $ per "
                 "1-point IV move. Multi-leg structures only; straddles are "
                 "tracked separately on the Positions page."),
    }


def record_real_fill(position_id: int, *, entry: Optional[float] = None,
                     exit_: Optional[float] = None) -> None:
    """Log what the broker ACTUALLY filled (per share-set, signed like
    entry_value). Slippage vs the paper mid decides the live-data upgrade."""
    fields = {}
    if entry is not None:
        fields["real_entry_value"] = float(entry)
    if exit_ is not None:
        fields["real_exit_value"] = float(exit_)
    if not fields:
        return
    ensure_tables()
    conn = get_connection()
    try:
        sets = ", ".join(f"{k}=?" for k in fields)
        conn.execute(f"UPDATE options_multi_positions SET {sets} WHERE id=?",
                     (*fields.values(), position_id))
        conn.commit()
    finally:
        conn.close()


def slippage_report() -> dict[str, Any]:
    """Paper mid vs real fill, per family. The live-data upgrade trigger:
    median entry slippage > 10% of the credit/debit means delayed quotes are
    costing real money and the $199 feed pays for itself."""
    ensure_tables()
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT strategy_key, entry_value, real_entry_value, exit_value, "
            "real_exit_value FROM options_multi_positions "
            "WHERE real_entry_value IS NOT NULL "
            "OR real_exit_value IS NOT NULL").fetchall()
    finally:
        conn.close()
    fams: dict[str, list[float]] = {}
    for r in rows:
        if r["real_entry_value"] is not None and r["entry_value"]:
            slip = abs(r["real_entry_value"] - r["entry_value"]) \
                / abs(r["entry_value"]) * 100
            fams.setdefault(r["strategy_key"], []).append(slip)
        if r["real_exit_value"] is not None and r["exit_value"]:
            slip = abs(r["real_exit_value"] - r["exit_value"]) \
                / abs(r["exit_value"]) * 100
            fams.setdefault(r["strategy_key"], []).append(slip)
    import statistics as _st
    out = {}
    all_slips: list[float] = []
    for fam, slips in fams.items():
        all_slips.extend(slips)
        out[fam] = {"fills": len(slips),
                    "median_slippage_pct": round(_st.median(slips), 2)}
    overall = round(_st.median(all_slips), 2) if all_slips else None
    return {
        "families": out,
        "fills_recorded": len(all_slips),
        "median_slippage_pct": overall,
        "upgrade_trigger_pct": 10.0,
        "upgrade_recommended": bool(overall is not None and overall > 10.0),
        "note": "record the broker's real fills when tracking/closing — this "
                "number, not a feeling, decides the real-time data upgrade",
    }


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
