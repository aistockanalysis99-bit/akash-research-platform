"""Phase 3 — per-ticker historical straddle backtest.

Answers: "if we had run this exact strategy on THIS stock's last N earnings,
using only the information available at the time, what would have happened?"

Uses REAL historical option prices (Polygon: daily OHLCV bars for expired
option contracts, verified back to at least 2024 on the $79 Developer tier).
Polygon has NO historical IV/greeks endpoint (confirmed: snapshot queries
with a past `date` 404 — IV is computed live, for today, only) — but we don't
need IV for this: the implied-move metric is straddle_cost / spot, both of
which ARE available historically. IV-curve visuals would need us to derive
IV ourselves via Black-Scholes; that's a future nice-to-have, not built here.

Point-in-time correctness: the cheapness ratio for a past event only uses
the median realized move of the earnings BEFORE it (never looks ahead).
"""
from __future__ import annotations

import logging
import statistics
from datetime import date, timedelta
from typing import Any, Optional

from . import earnings_vol as ev
from .polygon_client import PolygonOptionsClient

log = logging.getLogger(__name__)

MIN_TRAILING_EVENTS = 4     # need at least this many PRIOR events for a median
MAX_TRAILING_EVENTS = 12
EXIT_OFFSET_DAYS = 1        # exit the trading day before earnings (mirrors positions.py)


def _trading_day_index(dates: list[str], target: str) -> Optional[int]:
    """Index of the trading day on/after `target` in an ascending date list."""
    for i, d in enumerate(dates):
        if d >= target:
            return i
    return None


async def backtest_symbol(symbol: str, entry_days: int = 10,
                          max_events: int = 12) -> dict[str, Any]:
    """Simulate the straddle strategy on `symbol`'s last `max_events` earnings.

    entry_days: trading days before earnings to "buy" (default 10 — the
    research-favored middle of the 5-14 day window).
    """
    from ...data.fmp_client import FMPClient
    from ..data.fmp_research import FMPResearchClient

    async with FMPClient() as fmp:
        research = FMPResearchClient(fmp)
        bars = await fmp.fetch_daily(symbol)
        if bars is None or bars.empty:
            return {"symbol": symbol, "error": "no price history available", "events": []}

        earn = await research.fetch_earnings(symbol, limit=max_events + MAX_TRAILING_EVENTS + 2)
        past_earnings: list[date] = []
        for row in (earn.data or []):
            try:
                d = date.fromisoformat(row.get("date") or "")
            except ValueError:
                continue
            if d < date.today() and row.get("epsActual") is not None:
                past_earnings.append(d)
        past_earnings.sort()  # oldest -> newest

    if len(past_earnings) < MIN_TRAILING_EVENTS + 1:
        return {"symbol": symbol,
                "error": f"only {len(past_earnings)} past earnings on record — "
                         f"need at least {MIN_TRAILING_EVENTS + 1}",
                "events": []}

    trading_dates = [str(ts)[:10] for ts in bars["timestamp"]]
    closes = bars["close"].astype(float).tolist()
    close_by_date = dict(zip(trading_dates, closes))

    # Simulate the most recent `max_events`, each needing >= MIN_TRAILING_EVENTS
    # of REAL PRIOR history for its point-in-time cheapness baseline.
    eligible = past_earnings[MIN_TRAILING_EVENTS:]
    simulate = eligible[-max_events:]
    events_out: list[dict[str, Any]] = []

    async with PolygonOptionsClient() as poly:
        for ed in simulate:
            prior = [d for d in past_earnings if d < ed][-MAX_TRAILING_EVENTS:]
            if len(prior) < MIN_TRAILING_EVENTS:
                continue
            row = await _simulate_one_event(symbol, ed, prior, trading_dates,
                                            close_by_date, entry_days, poly)
            if row:
                events_out.append(row)

    return _summarize(symbol, entry_days, events_out)


async def _simulate_one_event(symbol: str, earnings_date: date, prior_events: list[date],
                              trading_dates: list[str], close_by_date: dict[str, float],
                              entry_days: int, poly: PolygonOptionsClient) -> Optional[dict[str, Any]]:
    # point-in-time realized-move baseline: only events strictly before this one
    prior_moves: list[float] = []
    for pe in prior_events:
        i = _trading_day_index(trading_dates, pe.isoformat())
        if i is None or i < 1 or i + 1 >= len(trading_dates):
            continue
        c_before, c_after = close_by_date.get(trading_dates[i - 1]), close_by_date.get(trading_dates[i])
        c_after2 = close_by_date.get(trading_dates[i + 1]) if i + 1 < len(trading_dates) else None
        gaps = []
        if c_before:
            gaps.append(abs(c_after / c_before - 1) * 100)
        if c_after and c_after2:
            gaps.append(abs(c_after2 / c_after - 1) * 100)
        if gaps:
            prior_moves.append(max(gaps))
    hist_median = round(statistics.median(prior_moves), 2) if len(prior_moves) >= MIN_TRAILING_EVENTS else None

    # this event's ACTUAL realized move (for grading the trade + the filter)
    ei = _trading_day_index(trading_dates, earnings_date.isoformat())
    if ei is None or ei < 1:
        return None
    actual_gaps = []
    if close_by_date.get(trading_dates[ei - 1]) and close_by_date.get(trading_dates[ei]):
        actual_gaps.append(abs(close_by_date[trading_dates[ei]] / close_by_date[trading_dates[ei - 1]] - 1) * 100)
    if ei + 1 < len(trading_dates) and close_by_date.get(trading_dates[ei]):
        actual_gaps.append(abs(close_by_date[trading_dates[ei + 1]] / close_by_date[trading_dates[ei]] - 1) * 100)
    actual_move = round(max(actual_gaps), 2) if actual_gaps else None

    entry_idx = ei - entry_days
    exit_idx = ei - EXIT_OFFSET_DAYS
    if entry_idx < 0 or exit_idx < 0 or entry_idx >= len(trading_dates):
        return None
    entry_date, exit_date = trading_dates[entry_idx], trading_dates[exit_idx]
    # FMP close is FULLY split+dividend adjusted. That's correct for realized
    # MOVE %s above (they're ratios of adjacent bars, so adjustment cancels),
    # but WRONG as an absolute price level to compare against raw option
    # strikes/prices. We only keep it as a fallback for the level basis.
    spot_adj = close_by_date.get(entry_date)
    if not spot_adj:
        return None

    expiry = await poly.first_expiry_after_historical(symbol, earnings_date.isoformat())
    if not expiry:
        return {"earnings_date": earnings_date.isoformat(), "actual_move_pct": actual_move,
                "hist_median_move_pct": hist_median, "error": "no option expiry found"}

    strikes = await poly.strikes_available(symbol, expiry)
    if not strikes:
        return {"earnings_date": earnings_date.isoformat(), "actual_move_pct": actual_move,
                "hist_median_move_pct": hist_median, "error": "no strikes listed"}

    # Price-LEVEL comparisons (ATM-strike selection, implied-move denominator)
    # must use a spot in the SAME basis as Polygon's contemporaneous option
    # strikes/prices — i.e. the RAW, unadjusted underlying close for that date,
    # NOT FMP's fully-adjusted close. Otherwise any split/dividend between this
    # past event and today shifts spot away from the strikes and inflates
    # implied move. Fall back to FMP's adjusted spot only if Polygon has no raw
    # stock bar for the window.
    spot_from = (date.fromisoformat(entry_date) - timedelta(days=6)).isoformat()
    poly_spot = await poly.underlying_close(symbol, spot_from, entry_date, entry_date)
    spot_entry = poly_spot or spot_adj

    atm_strike = min(strikes, key=lambda k: abs(k - spot_entry))

    # Sanity backstop: with a correct same-basis spot the nearest listed strike
    # is essentially always within a strike-increment of spot. If it's >25% off,
    # the reference data is internally inconsistent for this date (or we fell
    # back to the adjusted FMP spot across a split) — skip rather than emit a
    # wrong number.
    if abs(atm_strike - spot_entry) / spot_entry > 0.25:
        return {"earnings_date": earnings_date.isoformat(), "actual_move_pct": actual_move,
                "hist_median_move_pct": hist_median,
                "error": (f"nearest strike ${atm_strike} is >25% from the raw spot "
                          f"${spot_entry:.2f} for this date -- inconsistent option "
                          f"reference data (possible unhandled corporate action); "
                          f"skipped rather than produce a wrong number")}

    lo, hi = min(entry_date, exit_date), max(entry_date, exit_date)
    pad_lo = (date.fromisoformat(lo) - timedelta(days=5)).isoformat()
    pad_hi = (date.fromisoformat(hi) + timedelta(days=2)).isoformat()

    call_bars = await poly.historical_leg_bars(symbol, expiry, atm_strike, "call", pad_lo, pad_hi)
    put_bars = await poly.historical_leg_bars(symbol, expiry, atm_strike, "put", pad_lo, pad_hi)
    call_entry = poly.nearest_bar_close(call_bars, entry_date)
    put_entry = poly.nearest_bar_close(put_bars, entry_date)
    call_exit = poly.nearest_bar_close(call_bars, exit_date)
    put_exit = poly.nearest_bar_close(put_bars, exit_date)

    if not (call_entry and put_entry and call_exit and put_exit):
        return {"earnings_date": earnings_date.isoformat(), "actual_move_pct": actual_move,
                "hist_median_move_pct": hist_median,
                "error": "no historical option price found for this strike/expiry"}

    entry_cost = round(call_entry + put_entry, 4)
    exit_cost = round(call_exit + put_exit, 4)
    implied_move = ev.implied_move_pct(entry_cost, spot_entry)
    # Pure data-artifact backstop (NOT a volatility filter). Now that spot and
    # the straddle share one raw basis, a genuinely high-vol name can legitimately
    # print a 2-week ATM straddle worth 30-50% of spot — we must NOT reject those,
    # they're the whole point. Only a cost above ~60% of spot is essentially
    # always a broken quote / unhandled corporate action rather than a real trade.
    if implied_move is not None and implied_move > 60.0:
        return {"earnings_date": earnings_date.isoformat(), "actual_move_pct": actual_move,
                "hist_median_move_pct": hist_median,
                "error": (f"computed implied move {implied_move}% exceeds the 60% "
                          f"data-artifact ceiling -- almost certainly a broken quote "
                          f"or unhandled corporate action; skipped")}
    cheapness = ev.cheapness_ratio(implied_move, hist_median)
    trade_pnl_pct = round((exit_cost / entry_cost - 1) * 100, 2) if entry_cost else None

    return {
        "earnings_date": earnings_date.isoformat(),
        "entry_date": entry_date, "exit_date": exit_date,
        "spot_entry": round(spot_entry, 2), "strike": atm_strike, "expiry": expiry,
        "entry_cost": entry_cost, "exit_cost": exit_cost,
        "implied_move_pct": implied_move,
        "hist_median_move_pct": hist_median,
        "actual_move_pct": actual_move,
        "cheapness": cheapness,
        "would_qualify": cheapness is not None and cheapness <= 0.80,
        "trade_pnl_pct": trade_pnl_pct,
        "error": None,
    }


def _summarize(symbol: str, entry_days: int, events: list[dict[str, Any]]) -> dict[str, Any]:
    priced = [e for e in events if not e.get("error") and e.get("trade_pnl_pct") is not None]
    qualified = [e for e in priced if e.get("would_qualify")]
    wins = [e for e in qualified if e["trade_pnl_pct"] > 0]

    def _avg(rows, key):
        vals = [r[key] for r in rows if r.get(key) is not None]
        return round(sum(vals) / len(vals), 1) if vals else None

    summary = {
        "events_simulated": len(events),
        "events_priced": len(priced),
        "qualifying_events": len(qualified),
        "qualifying_win_rate_pct": round(len(wins) / len(qualified) * 100) if qualified else None,
        "qualifying_avg_pnl_pct": _avg(qualified, "trade_pnl_pct"),
        "all_events_avg_pnl_pct": _avg(priced, "trade_pnl_pct"),
        "avg_implied_vs_actual": (
            round(statistics.mean(
                e["implied_move_pct"] / e["actual_move_pct"] for e in priced
                if e.get("actual_move_pct")), 2)
            if any(e.get("actual_move_pct") for e in priced) else None
        ),
    }
    return {
        "symbol": symbol.upper(), "entry_days": entry_days,
        "events": sorted(events, key=lambda e: e["earnings_date"], reverse=True),
        "summary": summary,
        "note": ("Historical option PRICES are real (Polygon expired-contract "
                 "data). Historical IV is NOT available from Polygon (only "
                 "computed live for today) — implied move is derived directly "
                 "from historical straddle cost / spot, so no IV estimate was "
                 "needed or used. Each event's cheapness ratio uses only the "
                 "earnings BEFORE it (no look-ahead)."),
    }
