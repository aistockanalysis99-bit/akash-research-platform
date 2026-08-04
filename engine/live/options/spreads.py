"""Phase 5 — directional credit spreads from AI verdicts.

R5 bull put spread: collect premium betting a high-conviction BUY simply
won't fall through the AI's own stop level — the stop IS the short strike.
R6 bear call spread: the mirror on AVOID/SELL verdicts — collect premium
betting the stock won't rally past the AI's invalidation level.

Both are defined-risk by construction (the wing is mandatory) and the
structures gate re-verifies that anyway. Levels come from the AI's parsed
message; when a level can't be parsed there is NO trade — a spread struck
at a guessed level isn't a monetized opinion, it's a coin flip with extra
steps.
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Any, Optional

from .. import settings as live_settings
from . import returns_math as rm
from .income import _earnings_inside, _friday_expiry
from .polygon_client import PolygonOptionsClient

log = logging.getLogger(__name__)


def _book(chain: list[dict], contract_type: str) -> dict[float, dict]:
    return {float((c.get("details") or {}).get("strike_price") or 0): c
            for c in chain
            if (c.get("details") or {}).get("contract_type") == contract_type}


async def _build_vertical(poly: PolygonOptionsClient, research, symbol: str,
                          spot: float, level: float, *,
                          bullish: bool) -> dict[str, Any]:
    """Shared engine: sell the strike at/beyond the AI's level, buy the wing
    one width further out. bullish=True → put side below; False → call side
    above."""
    min_dte = live_settings.get_options_income_min_dte()
    max_dte = live_settings.get_options_income_max_dte()
    expiry = await _friday_expiry(poly, symbol, min_dte, max_dte)
    if not expiry:
        return {"ok": False, "reason": "no expiry in the window"}
    if await _earnings_inside(research, symbol, expiry):
        return {"ok": False, "reason": "earnings inside expiry — spreads skip "
                                       "event weeks (the condor owns those)"}
    if bullish and level >= spot:
        return {"ok": False, "reason": f"AI stop ${level:,.2f} is above spot "
                                       f"${spot:,.2f} — no room to sell under it"}
    if not bullish and level <= spot:
        return {"ok": False, "reason": f"AI ceiling ${level:,.2f} is below spot "
                                       f"${spot:,.2f} — thesis already broken"}

    side = "put" if bullish else "call"
    lo, hi = (spot * 0.60, spot) if bullish else (spot, spot * 1.40)
    chain = await poly.chain_for_expiry(symbol, expiry, lo, hi)
    book = _book(chain, side)
    priced = {k: c for k, c in book.items() if poly.leg_price(c) is not None}
    if not priced:
        return {"ok": False, "reason": f"no priced {side}s in band"}

    if bullish:
        candidates = [k for k in priced if k <= level]
        short_strike = max(candidates) if candidates else None
    else:
        candidates = [k for k in priced if k >= level]
        short_strike = min(candidates) if candidates else None
    if short_strike is None:
        return {"ok": False,
                "reason": f"no priced strike at/beyond the AI level ${level:,.2f}"}

    wing = max(spot * live_settings.get_options_condor_wing_pct() / 100, 0.5)
    if bullish:
        wings = [k for k in priced if k < short_strike]
        long_strike = min(wings, key=lambda k: abs((short_strike - wing) - k)) \
            if wings else None
    else:
        wings = [k for k in priced if k > short_strike]
        long_strike = min(wings, key=lambda k: abs((short_strike + wing) - k)) \
            if wings else None
    if long_strike is None:
        return {"ok": False, "reason": "no wing strike listed beyond the short"}

    legs = []
    for s, k in ((-1, short_strike), (1, long_strike)):
        c = priced[k]
        legs.append({"side": s, "contract_type": side, "strike": k,
                     "expiry": expiry, "qty": 1,
                     "price": poly.leg_price(c),
                     "delta": (c.get("greeks") or {}).get("delta"),
                     "oi": c.get("open_interest") or 0})

    entry_value = rm.package_value(legs)
    if entry_value is None or entry_value >= 0:
        return {"ok": False, "reason": "no net credit — quotes stale/crossed"}
    stats = rm.payoff_stats(legs, entry_value, spot=spot)
    if stats["max_loss"] >= 0:
        return {"ok": False, "reason": "degenerate payoff — skipped"}
    credit = -entry_value
    max_loss = -stats["max_loss"]
    dte = (date.fromisoformat(expiry) - date.today()).days
    min_oi = min(l["oi"] for l in legs)
    return {
        "ok": True, "symbol": symbol.upper(), "expiry": expiry, "dte": dte,
        "spot": round(spot, 2), "level": level,
        "short_strike": short_strike, "long_strike": long_strike,
        "legs": legs,
        "credit": round(credit, 4),
        "max_loss": stats["max_loss"],
        "breakevens": stats["breakevens"],
        "pop_est": rm.pop_estimate_pct(legs),
        "return_on_risk_pct": rm.return_on_risk_pct(credit, stats["max_loss"]),
        "annualized_pct": rm.annualized_yield_pct(credit, max_loss, dte)
        if dte > 0 else None,
        "min_oi": min_oi,
    }


async def build_bull_put(poly: PolygonOptionsClient, research, symbol: str,
                         spot: float, ai_stop: float) -> dict[str, Any]:
    """R5: short put at/below the AI's stop, wing below. Wins unless the
    stock falls through the level the AI itself said invalidates the thesis."""
    return await _build_vertical(poly, research, symbol, spot, ai_stop,
                                 bullish=True)


async def build_bear_call(poly: PolygonOptionsClient, research, symbol: str,
                          spot: float, ai_ceiling: float) -> dict[str, Any]:
    """R6: short call at/above the AI's invalidation level, wing above."""
    return await _build_vertical(poly, research, symbol, spot, ai_ceiling,
                                 bullish=False)
