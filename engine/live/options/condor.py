"""R2 — earnings iron condor builder.

Given a symbol, expiry, and spot, build the defined-risk condor the rulebook
describes: short put + short call near the configured |delta| band, protective
wings a configured % of spot further out. ONE chain snapshot prices all four
legs (rate-limit discipline).

Returns None-with-reason instead of a bad structure: every failure mode
(missing legs, unpriced wings, inverted credit) is reported, never guessed
around. The board shows WHY a candidate produced no card, same philosophy as
the scanner's reject reasons.
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Any, Optional

from .. import settings as live_settings
from . import returns_math as rm
from .polygon_client import PolygonOptionsClient

log = logging.getLogger(__name__)

# Widest strike band we ever need: short strikes can sit ~10-12% out on a
# high-vol name, wings a few % beyond. 20% each side covers it in one call.
CHAIN_BAND_PCT = 0.20


def _leg(side: int, contract: dict, expiry: str,
         poly: PolygonOptionsClient) -> Optional[dict[str, Any]]:
    det = contract.get("details") or {}
    greeks = contract.get("greeks") or {}
    price = poly.leg_price(contract)
    if price is None or price <= 0:
        return None
    return {
        "side": side,
        "contract_type": det.get("contract_type"),
        "strike": float(det.get("strike_price")),
        "expiry": expiry,
        "qty": 1,
        "price": price,
        "delta": greeks.get("delta"),
        "oi": contract.get("open_interest") or 0,
        "spread_pct": poly.leg_spread_pct(contract),
    }


async def build_condor(poly: PolygonOptionsClient, symbol: str, expiry: str,
                       spot: float,
                       expected_move_pct: Optional[float] = None
                       ) -> dict[str, Any]:
    """Build the rulebook condor. Returns {"ok": True, ...card fields} or
    {"ok": False, "reason": str}."""
    target_delta = live_settings.get_options_condor_short_delta()
    wing_pct = live_settings.get_options_condor_wing_pct()

    band = spot * CHAIN_BAND_PCT
    chain = await poly.chain_for_expiry(symbol, expiry, spot - band, spot + band)
    puts: dict[float, dict] = {}
    calls: dict[float, dict] = {}
    for c in chain:
        det = c.get("details") or {}
        k, typ = det.get("strike_price"), det.get("contract_type")
        if k is None:
            continue
        (puts if typ == "put" else calls if typ == "call" else {})[float(k)] = c

    if not puts or not calls:
        return {"ok": False, "reason": "chain snapshot has no strikes in band"}

    def _short_strike(side_book: dict[float, dict], is_put: bool) -> Optional[float]:
        # Prefer delta targeting; fall back to expected-move distance.
        scored = []
        for k, c in side_book.items():
            if (is_put and k >= spot) or (not is_put and k <= spot):
                continue  # shorts must be out-of-the-money
            d = (c.get("greeks") or {}).get("delta")
            if d is not None:
                scored.append((abs(abs(float(d)) - target_delta), k))
        if scored:
            return min(scored)[1]
        if expected_move_pct:
            tgt = spot * (1 - expected_move_pct / 100) if is_put \
                else spot * (1 + expected_move_pct / 100)
            otm = [k for k in side_book if (k < spot if is_put else k > spot)]
            return min(otm, key=lambda k: abs(k - tgt)) if otm else None
        return None

    sp = _short_strike(puts, is_put=True)
    sc = _short_strike(calls, is_put=False)
    if sp is None or sc is None:
        return {"ok": False, "reason": "no delta data and no expected move to "
                                       "place short strikes"}

    wing = max(spot * wing_pct / 100, 0.5)
    lp_candidates = [k for k in puts if k <= sp - wing * 0.5 and k < sp]
    lc_candidates = [k for k in calls if k >= sc + wing * 0.5 and k > sc]
    if not lp_candidates or not lc_candidates:
        return {"ok": False, "reason": "no listed wing strikes beyond the shorts"}
    lp = min(lp_candidates, key=lambda k: abs((sp - wing) - k))
    lc = min(lc_candidates, key=lambda k: abs((sc + wing) - k))

    legs = []
    for side, book, strike in ((1, puts, lp), (-1, puts, sp),
                               (-1, calls, sc), (1, calls, lc)):
        leg = _leg(side, book[strike], expiry, poly)
        if leg is None:
            return {"ok": False,
                    "reason": f"leg {'put' if book is puts else 'call'} "
                              f"{strike} not priceable"}
        legs.append(leg)

    entry_value = rm.package_value(legs)
    if entry_value is None or entry_value >= 0:
        return {"ok": False, "reason": "structure does not net a credit — "
                                       "quotes likely stale/crossed"}
    credit = -entry_value
    stats = rm.payoff_stats(legs, entry_value, spot=spot)
    # Guard on the SIGNED value: a non-negative minimum payoff means "no way
    # to lose" — a fantasy arbitrage manufactured by stale/crossed fallback
    # quotes (day-close/last-trade legs), never a real market. abs() here
    # would mask exactly that case.
    if stats["max_loss"] >= 0:
        return {"ok": False, "reason": "degenerate payoff (no loss side) — "
                                       "quotes likely stale/crossed"}
    max_loss = -stats["max_loss"]

    dte = (date.fromisoformat(expiry) - date.today()).days
    min_oi = min(l["oi"] for l in legs)
    spreads = [l["spread_pct"] for l in legs if l["spread_pct"] is not None]
    return {
        "ok": True,
        "symbol": symbol.upper(),
        "expiry": expiry,
        "spot": round(spot, 2),
        "legs": legs,
        "credit": round(credit, 4),
        "max_profit": stats["max_profit"],
        "max_loss": stats["max_loss"],
        "breakevens": stats["breakevens"],
        "pop_est": rm.pop_estimate_pct(legs),
        "return_on_risk_pct": rm.return_on_risk_pct(credit, stats["max_loss"]),
        "annualized_pct": rm.annualized_yield_pct(credit, max_loss, dte)
        if dte > 0 else None,
        "dte": dte,
        "min_oi": min_oi,
        "max_leg_spread_pct": round(max(spreads), 2) if spreads else None,
    }
