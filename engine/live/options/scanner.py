"""Earnings-straddle scanner.

Daily pass over the platform's universe (watchlist + held stocks):
  1. Which have CONFIRMED earnings inside the entry window (default 3-14 days)?
  2. For those: price the ATM straddle on the first expiry after the event
     (Polygon), compute the implied move, and compare it with the stock's
     REAL last 8-12 earnings moves (FMP) -> cheapness ratio.
  3. Apply the gates (cheapness <= max, OI >= min, spread <= max when known).
  4. Persist every scanned name (qualified or not, with the reject reason),
     snapshot ATM IV into our own history, and Telegram a digest when
     something qualifies.

Suggest-only: nothing is ever traded automatically.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime
from typing import Any, Optional

from .. import settings as live_settings
from ..watchlist import list_enabled_symbols
from . import earnings_vol as ev
from . import store
from .polygon_client import PolygonOptionsClient

log = logging.getLogger(__name__)


async def _universe() -> list[str]:
    """Watchlist (enabled) + held equity symbols + the configured broad
    universe (default S&P 500, live-fetched + weekly-cached), deduped."""
    syms = {s.upper() for s in list_enabled_symbols()}
    try:
        from ..portfolio import VirtualPortfolio
        p = VirtualPortfolio()
        try:
            for pos in p.list_open():
                if (pos.get("instrument_type") or "stock") == "stock":
                    syms.add(pos["symbol"].upper())
        finally:
            p.close_conn()
    except Exception as e:  # noqa: BLE001
        log.warning("options scan: portfolio read failed: %s", e)

    broad = live_settings.get_options_universe()
    if broad and broad != "none":
        try:
            from ...data.universe import get_universe_async
            extra = await get_universe_async(broad)
            syms.update(s.upper() for s in extra)
        except Exception as e:  # noqa: BLE001
            log.warning("options scan: broad universe '%s' fetch failed: %s", broad, e)
    return sorted(syms)


def _latest_convictions() -> dict[str, int]:
    """symbol -> latest AI conviction (for the dual-signal badge)."""
    try:
        from api.ai_jobs import list_decisions_on_disk
        best: dict[str, tuple[str, int]] = {}
        for d in list_decisions_on_disk():
            sym = (d.get("symbol") or "").upper()
            dt = d.get("date") or ""
            conv = d.get("conviction")
            if not sym or conv is None:
                continue
            if sym not in best or dt > best[sym][0]:
                best[sym] = (dt, int(conv))
        return {s: c for s, (_, c) in best.items()}
    except Exception as e:  # noqa: BLE001
        log.warning("options scan: conviction lookup failed: %s", e)
        return {}


async def _scan_symbol(sym: str, research, fmp, poly: PolygonOptionsClient,
                       convictions: dict[str, int]) -> Optional[dict[str, Any]]:
    today = date.today()
    min_d = live_settings.get_options_entry_min_days()
    max_d = live_settings.get_options_entry_max_days()

    nxt = await research.fetch_next_earnings_date(sym)
    if nxt is None:
        return None
    days_out = (nxt - today).days
    if not (min_d <= days_out <= max_d):
        return None

    bars = await fmp.fetch_daily(sym)
    if bars is None or bars.empty:
        return None
    spot = float(bars["close"].iloc[-1])

    # realized history from the same earnings feed
    earn = await research.fetch_earnings(sym, limit=16)
    past_dates: list[date] = []
    for row in earn.data or []:
        try:
            d = date.fromisoformat(row.get("date") or "")
        except ValueError:
            continue
        if d < today and row.get("epsActual") is not None:
            past_dates.append(d)
    moves = ev.realized_earnings_moves(bars, past_dates)
    hist_median = ev.median_move(moves)

    expiry = await poly.first_expiry_after(sym, nxt.isoformat())
    if not expiry:
        return _row(sym, nxt, days_out, spot, None, None, hist_median,
                    len(moves), None, None, "no option expiry found", convictions)
    straddle = await poly.atm_straddle(sym, expiry, spot)
    if not straddle:
        return _row(sym, nxt, days_out, spot, None, None, hist_median,
                    len(moves), None, None, "could not price ATM straddle", convictions)

    implied = ev.implied_move_pct(straddle["straddle_cost"], spot)
    cheap = ev.cheapness_ratio(implied, hist_median)

    # accumulate our own IV history (Polygon has no historical IV endpoint)
    store.save_iv_snapshot(sym, today.isoformat(), expiry,
                           straddle.get("atm_iv"), implied)

    # ---- gates ----
    reject = None
    if hist_median is None:
        reject = "not enough earnings history (need 4+ past events)"
    elif cheap is None:
        reject = "could not compute cheapness ratio"
    elif cheap > live_settings.get_options_cheapness_max():
        reject = (f"cheapness {cheap:.2f} — event not underpriced "
                  f"(max {live_settings.get_options_cheapness_max():.2f})")
    elif (straddle.get("min_oi") or 0) < live_settings.get_options_min_oi():
        reject = f"open interest {straddle.get('min_oi')} below minimum"
    else:
        sp = straddle.get("max_leg_spread_pct")
        if sp is not None and sp > live_settings.get_options_max_spread_pct():
            reject = f"bid-ask spread {sp:.1f}% too wide"

    return _row(sym, nxt, days_out, spot, straddle, implied, hist_median,
                len(moves), cheap, straddle.get("atm_iv"), reject, convictions)


def _row(sym, nxt, days_out, spot, straddle, implied, hist_median,
         n_events, cheap, atm_iv, reject, convictions) -> dict[str, Any]:
    s = straddle or {}
    return {
        "scan_date": date.today().isoformat(),
        "symbol": sym,
        "earnings_date": nxt.isoformat(),
        "days_to_earnings": days_out,
        "spot": round(spot, 2),
        "strike": s.get("strike"),
        "expiry": s.get("expiry"),
        "straddle_cost": s.get("straddle_cost"),
        "implied_move_pct": implied,
        "hist_median_move_pct": hist_median,
        "hist_events": n_events,
        "cheapness": cheap,
        "atm_iv": atm_iv,
        "min_oi": s.get("min_oi"),
        "max_leg_spread_pct": s.get("max_leg_spread_pct"),
        "avg_theta": s.get("avg_theta"),
        "avg_vega": s.get("avg_vega"),
        "qualified": 1 if reject is None else 0,
        "reject_reason": reject,
        "dual_signal": 1 if (convictions.get(sym) or 0) >= 7 else 0,
        "created_at": datetime.utcnow().isoformat(),
    }


async def run_scan(notify: bool = True) -> dict[str, Any]:
    """Full scan. Returns {scanned, qualified, candidates}."""
    from ...data.fmp_client import FMPClient
    from ..data.fmp_research import FMPResearchClient

    universe = await _universe()
    convictions = _latest_convictions()
    results: list[dict[str, Any]] = []

    async with FMPClient() as fmp, PolygonOptionsClient() as poly:
        research = FMPResearchClient(fmp)
        # Bigger universe (S&P 500) needs more concurrency to finish in a
        # reasonable window, but still gentle on FMP/Polygon rate limits.
        sem = asyncio.Semaphore(10)

        async def one(sym: str):
            async with sem:
                try:
                    return await _scan_symbol(sym, research, fmp, poly, convictions)
                except Exception as e:  # noqa: BLE001
                    log.warning("options scan %s failed: %s", sym, e)
                    return None

        rows = await asyncio.gather(*[one(s) for s in universe])
        results = [r for r in rows if r]

    for r in results:
        store.save_candidate(r)

    qualified = [r for r in results if r["qualified"]]
    if notify and qualified:
        await _send_digest(qualified)

    log.info("options scan: %d in window, %d qualified (universe %d)",
             len(results), len(qualified), len(universe))
    return {"scanned": len(results), "qualified": len(qualified),
            "universe": len(universe), "candidates": results}


async def _send_digest(qualified: list[dict[str, Any]]) -> None:
    try:
        from ..telegram import telegram as _telegram
        client = _telegram()
        lines = [f"🎯 Straddle Scanner — {len(qualified)} candidate(s) today", ""]
        for c in qualified[:6]:
            star = " ⭐ Also a 7+ AI pick." if c.get("dual_signal") else ""
            cost = c.get("straddle_cost") or 0
            lines.append(
                f"{c['symbol']} — earnings {c['earnings_date']} "
                f"({c['days_to_earnings']} days). Market prices a "
                f"±{c['implied_move_pct']}% move; it normally moves "
                f"±{c['hist_median_move_pct']}% → underpriced "
                f"({c['cheapness']}). Straddle ≈ ${cost * 100:,.0f}/contract."
                f"{star}"
            )
            lines.append("")
        lines.append("Nothing is bought automatically — open Options → "
                      "Scanner to track any of these as a paper trade.")
        await client.send_message("\n".join(lines), kind="options_digest")
    except Exception as e:  # noqa: BLE001
        log.warning("options digest send failed: %s", e)
