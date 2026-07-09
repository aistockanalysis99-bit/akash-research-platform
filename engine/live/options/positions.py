"""Paper straddle positions — tracking, daily marks, alerts, closing.

Rules enforced here (notify-only, never auto-traded):
  * HARD EXIT DEADLINE: FMP doesn't tell us BMO vs AMC, so we use the
    conservative rule — exit by 15:45 ET on the LAST TRADING DAY BEFORE the
    earnings date. Worst case we give up one day of run-up; we can never
    accidentally hold through a print.
  * Date-revision watcher: every mark re-checks the earnings date; if the
    company moved it, the deadline is recomputed and an alert fires.
  * P&L attribution: each mark decomposes P&L into IV run-up (vega), time
    decay (theta) and movement (residual/gamma) — estimates, clearly labeled.

This module NEVER touches the equity portfolio or its cash balance.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, time, timedelta
from typing import Any, Optional
from zoneinfo import ZoneInfo

from . import store
from .polygon_client import PolygonOptionsClient

log = logging.getLogger(__name__)

ET = ZoneInfo("America/New_York")
EXIT_TIME = time(15, 45)          # ET
FINAL_ALERT_MINUTES = 75          # final warning window before deadline
DRIFT_ALERT = 0.20                # |net delta| per straddle → re-center alert


def _prev_trading_day(d: date) -> date:
    d = d - timedelta(days=1)
    while d.weekday() >= 5:  # Sat/Sun
        d -= timedelta(days=1)
    return d


def exit_deadline_for(earnings_date: date) -> datetime:
    """Conservative: 15:45 ET on the last trading day BEFORE the earnings date."""
    return datetime.combine(_prev_trading_day(earnings_date), EXIT_TIME, tzinfo=ET)


# --------------------------------------------------------------------------- #
# Tracking
# --------------------------------------------------------------------------- #

def track_candidate(candidate_id: int, contracts: int = 1) -> Optional[int]:
    """Create a paper position from a scanner candidate."""
    c = store.get_candidate(candidate_id)
    if not c or not c.get("straddle_cost"):
        return None
    earnings = date.fromisoformat(c["earnings_date"])
    deadline = exit_deadline_for(earnings)
    pos_id = store.insert_position({
        "symbol": c["symbol"],
        "contracts": max(1, int(contracts)),
        "strike": c["strike"],
        "expiry": c["expiry"],
        "earnings_date": c["earnings_date"],
        "exit_deadline": deadline.isoformat(),
        "entry_date": date.today().isoformat(),
        "entry_spot": c["spot"],
        "entry_cost": c["straddle_cost"],
        "entry_iv": c.get("atm_iv"),
        "entry_theta": c.get("avg_theta"),
        "entry_vega": c.get("avg_vega"),
        "notes": f"cheapness {c.get('cheapness')} · implied ±{c.get('implied_move_pct')}% "
                 f"vs hist ±{c.get('hist_median_move_pct')}%",
        "created_at": datetime.utcnow().isoformat(),
    })
    log.info("options: tracking %s straddle #%d (%d contract(s))",
             c["symbol"], pos_id, contracts)
    return pos_id


# --------------------------------------------------------------------------- #
# Marking + attribution
# --------------------------------------------------------------------------- #

async def _price_position(poly: PolygonOptionsClient, pos: dict) -> Optional[dict]:
    """Price the position's EXACT strike/expiry pair."""
    strike = float(pos["strike"])
    contracts = await poly.chain_for_expiry(
        pos["symbol"], pos["expiry"], strike - 0.01, strike + 0.01)
    call = put = None
    for c in contracts:
        det = c.get("details") or {}
        if abs(float(det.get("strike_price") or -1) - strike) > 0.001:
            continue
        if det.get("contract_type") == "call":
            call = c
        elif det.get("contract_type") == "put":
            put = c
    if not call or not put:
        return None
    cp, pp = poly.leg_price(call), poly.leg_price(put)
    if not cp or not pp:
        return None
    ivs = [v for v in (call.get("implied_volatility"),
                       put.get("implied_volatility")) if v]
    cg, pg = call.get("greeks") or {}, put.get("greeks") or {}

    def _avg(a, b):
        vals = [v for v in (a, b) if v is not None]
        return sum(vals) / len(vals) if vals else None

    net_delta = None
    if cg.get("delta") is not None and pg.get("delta") is not None:
        net_delta = cg["delta"] + pg["delta"]
    und = (call.get("underlying_asset") or {}).get("price")
    return {
        "value": round(cp + pp, 4),
        "iv": round(sum(ivs) / len(ivs), 4) if ivs else None,
        "theta": _avg(cg.get("theta"), pg.get("theta")),
        "vega": _avg(cg.get("vega"), pg.get("vega")),
        "net_delta": net_delta,
        "spot": und,
    }


def _attribution(pos: dict, cur: dict) -> dict[str, Optional[float]]:
    """Split P&L into vega / theta / movement (estimates)."""
    contracts = int(pos["contracts"] or 1)
    mult = 100 * contracts
    total = (cur["value"] - pos["entry_cost"]) * mult

    days = max(0, (date.today() - date.fromisoformat(pos["entry_date"])).days)
    theta_pnl = None
    if pos.get("entry_theta") is not None and cur.get("theta") is not None:
        theta_pnl = ((pos["entry_theta"] + cur["theta"]) / 2) * days * mult
    vega_pnl = None
    if (pos.get("entry_vega") is not None and cur.get("vega") is not None
            and pos.get("entry_iv") is not None and cur.get("iv") is not None):
        vega_pnl = ((pos["entry_vega"] + cur["vega"]) / 2) * \
                   (cur["iv"] - pos["entry_iv"]) * mult
    move_pnl = None
    if theta_pnl is not None and vega_pnl is not None:
        move_pnl = total - theta_pnl - vega_pnl
    return {
        "pnl_usd": round(total, 2),
        "pnl_pct": round((cur["value"] / pos["entry_cost"] - 1) * 100, 2)
                   if pos["entry_cost"] else None,
        "theta_pnl": round(theta_pnl, 2) if theta_pnl is not None else None,
        "vega_pnl": round(vega_pnl, 2) if vega_pnl is not None else None,
        "move_pnl": round(move_pnl, 2) if move_pnl is not None else None,
    }


async def mark_open_positions(notify: bool = True) -> dict[str, Any]:
    """Refresh every open position: price, P&L attribution, drift check,
    earnings-date revision watch. Returns a summary."""
    open_pos = store.list_positions("open")
    if not open_pos:
        return {"marked": 0}

    marked, alerts = 0, []
    async with PolygonOptionsClient() as poly:
        for pos in open_pos:
            try:
                cur = await _price_position(poly, pos)
            except Exception as e:  # noqa: BLE001
                log.warning("mark %s #%d failed: %s", pos["symbol"], pos["id"], e)
                continue
            if not cur:
                continue
            att = _attribution(pos, cur)
            fields = {
                "current_value": cur["value"], "current_iv": cur["iv"],
                "current_theta": cur["theta"], "current_vega": cur["vega"],
                "current_spot": cur["spot"],
                "last_marked": datetime.utcnow().isoformat(), **att,
            }
            # delta-drift (re-center) alert — once per position
            if (cur.get("net_delta") is not None
                    and abs(cur["net_delta"]) >= DRIFT_ALERT
                    and not pos.get("drift_alerted")):
                fields["drift_alerted"] = 1
                alerts.append(_drift_msg(pos, cur, att))
            store.update_position(pos["id"], fields)
            marked += 1

    # earnings-date revision watch (FMP)
    try:
        await _check_date_revisions(open_pos, alerts)
    except Exception as e:  # noqa: BLE001
        log.warning("date revision check failed: %s", e)

    if notify:
        await _send_alerts(alerts)
    return {"marked": marked, "alerts": len(alerts)}


def _drift_msg(pos, cur, att) -> dict:
    lean = "bullish" if (cur.get("net_delta") or 0) > 0 else "bearish"
    return {
        "symbol": pos["symbol"], "kind": "options_alert",
        "text": (f"⚠ {pos['symbol']} straddle — position drift\n\n"
                 f"The stock has moved and your straddle is now leaning "
                 f"{abs(cur['net_delta'])*100:.0f}% {lean}. P&L "
                 f"{att['pnl_pct']:+.1f}%.\n"
                 f"Consider re-centering to the current ATM strike to stay "
                 f"direction-neutral.\n\nNothing was changed — your call."),
    }


async def _check_date_revisions(open_pos: list[dict], alerts: list) -> None:
    from ...data.fmp_client import FMPClient
    from ..data.fmp_research import FMPResearchClient
    async with FMPClient() as fmp:
        research = FMPResearchClient(fmp)
        for pos in open_pos:
            nxt = await research.fetch_next_earnings_date(pos["symbol"])
            if nxt is None:
                continue
            if nxt.isoformat() != pos["earnings_date"]:
                new_deadline = exit_deadline_for(nxt)
                store.update_position(pos["id"], {
                    "earnings_date": nxt.isoformat(),
                    "exit_deadline": new_deadline.isoformat(),
                    "exit_alerted_morning": 0, "exit_alerted_final": 0,
                })
                alerts.append({
                    "symbol": pos["symbol"], "kind": "options_alert",
                    "text": (f"🔴 {pos['symbol']} EARNINGS DATE MOVED: "
                             f"{pos['earnings_date']} → {nxt.isoformat()}.\n"
                             f"New exit deadline: "
                             f"{new_deadline.strftime('%b %d, %H:%M ET')}. "
                             f"Adjust your plan accordingly."),
                })


# --------------------------------------------------------------------------- #
# Exit alerts (the non-negotiable)
# --------------------------------------------------------------------------- #

async def check_exit_alerts(notify: bool = True) -> int:
    """Fire the morning-of and final exit warnings. Never closes anything."""
    now = datetime.now(ET)
    alerts = []
    for pos in store.list_positions("open"):
        try:
            deadline = datetime.fromisoformat(pos["exit_deadline"])
        except (TypeError, ValueError):
            continue
        if deadline.tzinfo is None:
            deadline = deadline.replace(tzinfo=ET)
        val = pos.get("current_value") or pos["entry_cost"]
        pnl_pct = (val / pos["entry_cost"] - 1) * 100 if pos["entry_cost"] else 0

        if now.date() == deadline.date() and not pos.get("exit_alerted_morning"):
            store.update_position(pos["id"], {"exit_alerted_morning": 1})
            alerts.append({
                "symbol": pos["symbol"], "kind": "options_exit",
                "text": (f"🚨 EXIT {pos['symbol']} STRADDLE TODAY — before "
                         f"{deadline.strftime('%H:%M ET')}\n\n"
                         f"Earnings is imminent (report dated "
                         f"{pos['earnings_date']}). Current value ≈ "
                         f"${val:.2f}/share → {pnl_pct:+.1f}%.\n"
                         f"Holding through the announcement risks the IV "
                         f"crush. This alert IS the strategy — please close "
                         f"it in your account, then mark it closed on the "
                         f"platform."),
            })
        elif (timedelta(0) <= (deadline - now)
              <= timedelta(minutes=FINAL_ALERT_MINUTES)
              and not pos.get("exit_alerted_final")):
            store.update_position(pos["id"], {"exit_alerted_final": 1})
            alerts.append({
                "symbol": pos["symbol"], "kind": "options_exit",
                "text": (f"🚨 FINAL WARNING — {pos['symbol']} straddle exit "
                         f"deadline {deadline.strftime('%H:%M ET')} (under "
                         f"{FINAL_ALERT_MINUTES} min).\n"
                         f"Value ≈ ${val:.2f}/share → {pnl_pct:+.1f}%. "
                         f"Close it now."),
            })
    if notify:
        await _send_alerts(alerts)
    return len(alerts)


async def _send_alerts(alerts: list[dict]) -> None:
    if not alerts:
        return
    try:
        from ..telegram import telegram as _telegram
        client = _telegram()
        for a in alerts:
            await client.send_message(a["text"], kind=a["kind"],
                                      symbol=a.get("symbol"))
    except Exception as e:  # noqa: BLE001
        log.warning("options alert send failed: %s", e)


# --------------------------------------------------------------------------- #
# Closing
# --------------------------------------------------------------------------- #

async def close_position(position_id: int, reason: str = "manual",
                         notify: bool = True) -> Optional[dict[str, Any]]:
    """Close a paper straddle at the freshest obtainable value."""
    pos = store.get_position(position_id)
    if not pos or pos["status"] != "open":
        return None
    exit_value = pos.get("current_value") or pos["entry_cost"]
    try:
        async with PolygonOptionsClient() as poly:
            cur = await _price_position(poly, pos)
            if cur:
                exit_value = cur["value"]
    except Exception as e:  # noqa: BLE001
        log.warning("close mark failed for #%d (using last mark): %s",
                    position_id, e)

    mult = 100 * int(pos["contracts"] or 1)
    pnl_usd = round((exit_value - pos["entry_cost"]) * mult, 2)
    pnl_pct = round((exit_value / pos["entry_cost"] - 1) * 100, 2) \
        if pos["entry_cost"] else None
    store.update_position(position_id, {
        "status": "closed", "exit_date": date.today().isoformat(),
        "exit_value": exit_value, "exit_reason": reason,
        "final_pnl_usd": pnl_usd, "final_pnl_pct": pnl_pct,
    })

    if notify:
        s = store.stats()
        days = (date.today() - date.fromisoformat(pos["entry_date"])).days
        att_bits = []
        if pos.get("vega_pnl") is not None:
            att_bits.append(f"anticipation build-up {pos['vega_pnl']:+,.0f} 💨")
        if pos.get("move_pnl") is not None:
            att_bits.append(f"stock movement {pos['move_pnl']:+,.0f} 🎢")
        if pos.get("theta_pnl") is not None:
            att_bits.append(f"time decay {pos['theta_pnl']:+,.0f} ⏳")
        att = ("\nWhere it came from (est.): " + " · ".join(att_bits)) if att_bits else ""
        emoji = "✅" if (pnl_usd or 0) >= 0 else "🔻"
        text = (f"{emoji} {pos['symbol']} straddle closed: {pnl_usd:+,.0f} "
                f"({pnl_pct:+.1f}%) in {days} day(s) — {reason}{att}\n"
                f"Scanner record: {s['trades']} trades, "
                f"{s['win_rate_pct'] or 0}% winners, total "
                f"${s['total_pnl_usd']:+,.0f} (paper).")
        await _send_alerts([{"symbol": pos["symbol"],
                             "kind": "options_exit", "text": text}])
    return store.get_position(position_id)
