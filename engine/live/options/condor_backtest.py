"""Layer 2 for R2 — historical iron-condor simulation on real option prices.

For each of a symbol's recent earnings events: build the condor the live rule
would have built (shorts at ± the ENTRY-DAY implied move — estimated from the
real ATM straddle price that day — wings the configured % beyond), enter N
trading days before the event, exit at the close the day AFTER the print
(the crush is the edge; the exit eats the realized gap). Every price is a
real Polygon expired-contract bar; nothing is simulated from a model.

Point-in-time correct: strike selection uses only entry-day information.
Honest skips: an event with any unpriceable SHORT leg is skipped, never
guessed. A LONG wing with no exit print is valued 0 (worthless assumption —
conservative for the P&L of a net-credit structure only at exit).
"""
from __future__ import annotations

import logging
import statistics
from datetime import date, timedelta
from typing import Any, Optional

from .. import settings as live_settings
from . import returns_math as rm
from .backtest import (IMPLIED_MOVE_ARTIFACT_CEILING, MIN_TRAILING_EVENTS,
                       _trading_day_index)
from .polygon_client import PolygonOptionsClient

log = logging.getLogger(__name__)

MAX_TRAILING = 12
EXIT_OFFSET_AFTER = 1     # trading day AFTER earnings — through the print


async def condor_backtest_symbol(symbol: str, entry_days: int = 5,
                                 max_events: int = 8) -> dict[str, Any]:
    from ...data.fmp_client import FMPClient
    from ..data.fmp_research import FMPResearchClient

    async with FMPClient() as fmp:
        research = FMPResearchClient(fmp)
        bars = await fmp.fetch_daily(symbol)
        if bars is None or bars.empty:
            return {"symbol": symbol, "error": "no price history", "events": []}
        earn = await research.fetch_earnings(symbol,
                                             limit=max_events + MAX_TRAILING + 2)
        past: list[date] = []
        for row in (earn.data or []):
            try:
                d = date.fromisoformat(row.get("date") or "")
            except ValueError:
                continue
            if d < date.today() and row.get("epsActual") is not None:
                past.append(d)
        past.sort()

    if len(past) < MIN_TRAILING_EVENTS + 1:
        return {"symbol": symbol,
                "error": f"only {len(past)} past earnings on record",
                "events": []}

    trading_dates = [str(ts)[:10] for ts in bars["timestamp"]]
    close_by_date = dict(zip(trading_dates,
                             bars["close"].astype(float).tolist()))
    simulate = past[MIN_TRAILING_EVENTS:][-max_events:]
    events: list[dict[str, Any]] = []
    async with PolygonOptionsClient() as poly:
        for ed in simulate:
            prior = [d for d in past if d < ed][-MAX_TRAILING:]
            try:
                row = await _simulate_event(symbol, ed, prior, trading_dates,
                                            close_by_date, entry_days, poly)
            except Exception as e:  # noqa: BLE001
                log.warning("condor backtest %s %s failed: %s", symbol, ed, e)
                row = None
            if row:
                events.append(row)
    return _summarize(symbol, entry_days, events)


async def _simulate_event(symbol: str, earnings_date: date,
                          prior_events: list[date], trading_dates: list[str],
                          close_by_date: dict[str, float], entry_days: int,
                          poly: PolygonOptionsClient) -> Optional[dict[str, Any]]:
    ei = _trading_day_index(trading_dates, earnings_date.isoformat())
    if ei is None or ei < 1:
        return None
    entry_idx = ei - entry_days
    exit_idx = ei + EXIT_OFFSET_AFTER
    if entry_idx < 0 or exit_idx >= len(trading_dates):
        return None  # event too old for bars, or too recent to have exited
    entry_date, exit_date = trading_dates[entry_idx], trading_dates[exit_idx]

    # realized event move (for context + the "sold into what" narrative)
    gaps = []
    if close_by_date.get(trading_dates[ei - 1]) and close_by_date.get(trading_dates[ei]):
        gaps.append(abs(close_by_date[trading_dates[ei]] /
                        close_by_date[trading_dates[ei - 1]] - 1) * 100)
    if ei + 1 < len(trading_dates) and close_by_date.get(trading_dates[ei]):
        gaps.append(abs(close_by_date[trading_dates[ei + 1]] /
                        close_by_date[trading_dates[ei]] - 1) * 100)
    actual_move = round(max(gaps), 2) if gaps else None

    expiry = await poly.first_expiry_after_historical(
        symbol, earnings_date.isoformat())
    if not expiry:
        return _skip(earnings_date, actual_move, "no option expiry found")

    # RAW same-basis spot for strike work (the straddle backtest lesson)
    spot_from = (date.fromisoformat(entry_date) - timedelta(days=6)).isoformat()
    spot = await poly.underlying_close(symbol, spot_from, entry_date, entry_date)
    if not spot:
        spot = close_by_date.get(entry_date)
    if not spot:
        return None

    strikes = await poly.strikes_available(symbol, expiry)
    if not strikes:
        return _skip(earnings_date, actual_move, "no strikes listed")
    atm = min(strikes, key=lambda k: abs(k - spot))
    if abs(atm - spot) / spot > 0.25:
        return _skip(earnings_date, actual_move,
                     "strike/spot basis mismatch — skipped")

    pad_lo = (date.fromisoformat(entry_date) - timedelta(days=5)).isoformat()
    pad_hi = (date.fromisoformat(exit_date) + timedelta(days=2)).isoformat()

    # entry-day implied move from the REAL ATM straddle price that day
    atm_call = await poly.historical_leg_bars(symbol, expiry, atm, "call",
                                              pad_lo, pad_hi)
    atm_put = await poly.historical_leg_bars(symbol, expiry, atm, "put",
                                             pad_lo, pad_hi)
    ce = poly.nearest_bar_close(atm_call, entry_date)
    pe = poly.nearest_bar_close(atm_put, entry_date)
    if not ce or not pe:
        return _skip(earnings_date, actual_move,
                     "ATM straddle not priceable at entry")
    implied_move = (ce + pe) / spot * 100
    if implied_move > IMPLIED_MOVE_ARTIFACT_CEILING:
        return _skip(earnings_date, actual_move,
                     f"implied move {round(implied_move, 1)}% exceeds the "
                     f"{IMPLIED_MOVE_ARTIFACT_CEILING:.0f}% data-artifact "
                     f"ceiling — broken quote or corporate action; skipped")

    # point-in-time cheapness context (same construction as the live scanner)
    prior_moves = []
    for pd in prior_events:
        i = _trading_day_index(trading_dates, pd.isoformat())
        if i is None or i < 1 or i + 1 >= len(trading_dates):
            continue
        g = []
        cb, ca = close_by_date.get(trading_dates[i - 1]), close_by_date.get(trading_dates[i])
        ca2 = close_by_date.get(trading_dates[i + 1])
        if cb and ca:
            g.append(abs(ca / cb - 1) * 100)
        if ca and ca2:
            g.append(abs(ca2 / ca - 1) * 100)
        if g:
            prior_moves.append(max(g))
    hist_median = (round(statistics.median(prior_moves), 2)
                   if len(prior_moves) >= MIN_TRAILING_EVENTS else None)
    cheapness = (round(implied_move / hist_median, 2)
                 if hist_median and hist_median > 0 else None)

    # strikes the live rule would pick with no greeks: ± implied move, wings
    wing = max(spot * live_settings.get_options_condor_wing_pct() / 100, 0.5)
    lo_puts = [k for k in strikes if k < spot]
    hi_calls = [k for k in strikes if k > spot]
    if not lo_puts or not hi_calls:
        return _skip(earnings_date, actual_move, "one-sided strike list")
    sp = min(lo_puts, key=lambda k: abs(k - spot * (1 - implied_move / 100)))
    sc = min(hi_calls, key=lambda k: abs(k - spot * (1 + implied_move / 100)))
    lp_c = [k for k in strikes if k < sp]
    lc_c = [k for k in strikes if k > sc]
    if not lp_c or not lc_c:
        return _skip(earnings_date, actual_move, "no wing strikes listed")
    lp = min(lp_c, key=lambda k: abs((sp - wing) - k))
    lc = min(lc_c, key=lambda k: abs((sc + wing) - k))

    async def _bars(strike: float, typ: str) -> list[dict]:
        if strike == atm and typ == "call":
            return atm_call
        if strike == atm and typ == "put":
            return atm_put
        return await poly.historical_leg_bars(symbol, expiry, strike, typ,
                                              pad_lo, pad_hi)

    spec = [(1, lp, "put"), (-1, sp, "put"), (-1, sc, "call"), (1, lc, "call")]
    legs_entry, legs_exit = [], []
    for side, strike, typ in spec:
        b = await _bars(strike, typ)
        e = poly.nearest_bar_close(b, entry_date)
        # Exit must be the exit day's OWN bar (the first post-print session).
        # Without the floor the lookup walks back to a stale pre-crush close
        # and the skip/zero rules below become dead code (review HIGH).
        x = poly.nearest_bar_close(b, exit_date, not_before_date=exit_date)
        if e is None:
            return _skip(earnings_date, actual_move,
                         f"{typ} {strike} unpriced at entry")
        if x is None:
            if side < 0:  # a short leg's buyback price can't be guessed
                return _skip(earnings_date, actual_move,
                             f"short {typ} {strike} unpriced at exit")
            x = 0.0       # long wing with no print: assume worthless
        common = {"contract_type": typ, "strike": strike, "expiry": expiry,
                  "qty": 1, "delta": None}
        legs_entry.append({**common, "side": side, "price": e})
        legs_exit.append({**common, "side": side, "price": x})

    entry_value = rm.package_value(legs_entry)
    exit_value = rm.package_value(legs_exit)
    if entry_value is None or entry_value >= 0:
        return _skip(earnings_date, actual_move,
                     "no net credit at entry (stale quotes)")
    stats = rm.payoff_stats(legs_entry, entry_value, spot=spot)
    if stats["max_loss"] >= 0:
        return _skip(earnings_date, actual_move, "degenerate payoff — skipped")
    credit = -entry_value
    max_loss = -stats["max_loss"]
    pnl = round((exit_value - entry_value) * 100, 2)
    inside_range = None
    if actual_move is not None:
        put_room = (spot - sp) / spot * 100
        call_room = (sc - spot) / spot * 100
        inside_range = bool(actual_move < min(put_room, call_room))
    return {
        "earnings_date": earnings_date.isoformat(),
        "entry_date": entry_date, "exit_date": exit_date,
        "spot_entry": round(spot, 2),
        "short_put": sp, "short_call": sc, "long_put": lp, "long_call": lc,
        "expiry": expiry,
        "credit": round(credit, 4), "max_loss": round(max_loss, 4),
        "implied_move_pct": round(implied_move, 2),
        "hist_median_move_pct": hist_median,
        "cheapness": cheapness,
        "actual_move_pct": actual_move,
        "inside_range": inside_range,
        "trade_pnl_usd": pnl,
        "return_on_risk_pct": round(pnl / (max_loss * 100) * 100, 1),
        "would_fire": (cheapness is not None and cheapness >=
                       live_settings.get_options_condor_min_cheapness()),
        "error": None,
    }


def _skip(ed: date, actual_move, reason: str) -> dict[str, Any]:
    return {"earnings_date": ed.isoformat(), "actual_move_pct": actual_move,
            "error": reason}


def _summarize(symbol: str, entry_days: int,
               events: list[dict[str, Any]]) -> dict[str, Any]:
    priced = [e for e in events if not e.get("error")]
    fired = [e for e in priced if e.get("would_fire")]
    wins = [e for e in fired if e["trade_pnl_usd"] > 0]

    def _avg(rows, key):
        vals = [r[key] for r in rows if r.get(key) is not None]
        return round(sum(vals) / len(vals), 1) if vals else None

    return {
        "symbol": symbol.upper(), "entry_days": entry_days,
        "events": sorted(events, key=lambda e: e["earnings_date"],
                         reverse=True),
        "summary": {
            "events_simulated": len(events),
            "events_priced": len(priced),
            "rule_fired_events": len(fired),
            "fired_win_rate_pct": (round(len(wins) / len(fired) * 100)
                                   if fired else None),
            "fired_avg_return_on_risk_pct": _avg(fired, "return_on_risk_pct"),
            "all_avg_return_on_risk_pct": _avg(priced, "return_on_risk_pct"),
        },
        "note": ("Real historical option prices (Polygon expired contracts). "
                 "Shorts placed at the entry-day implied move exactly as the "
                 "live rule's no-greeks fallback does; wings per settings. "
                 "Exit = close the day AFTER earnings — through the print. "
                 "Cheapness uses only earnings BEFORE each event."),
    }
