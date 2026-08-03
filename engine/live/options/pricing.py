"""Pricing source abstraction — the seam for the future live-data upgrade.

Everything in the options module prices legs through `get_pricing()`, never
through PolygonOptionsClient directly. Today that returns DelayedPolygonPricing
(15-min delayed snapshots, the $79 tier). When measured slippage justifies the
real-time tier, a LivePolygonPricing class implements the same one method and
this factory is the only line that changes.

Contract: quote_legs() fills price/delta/oi/iv onto copies of the given legs
(None where the market has no quote — callers treat a partially-priced
structure as unpriced; see returns_math.package_value).
"""
from __future__ import annotations

import logging
from typing import Any

from .polygon_client import PolygonOptionsClient

log = logging.getLogger(__name__)


class DelayedPolygonPricing:
    """Prices legs from Polygon chain snapshots (delayed ~15 min).

    Groups legs by (symbol, expiry) so a 4-leg condor costs ONE chain call,
    not four — this matters against the per-minute rate limit.
    """

    def __init__(self, poly: PolygonOptionsClient) -> None:
        self._poly = poly

    async def quote_legs(self, symbol: str,
                         legs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        out = [dict(l) for l in legs]
        by_expiry: dict[str, list[int]] = {}
        for i, leg in enumerate(out):
            by_expiry.setdefault(leg["expiry"], []).append(i)

        for expiry, idxs in by_expiry.items():
            strikes = [out[i]["strike"] for i in idxs]
            lo, hi = min(strikes) - 0.01, max(strikes) + 0.01
            try:
                chain = await self._poly.chain_for_expiry(symbol, expiry, lo, hi)
            except Exception as e:  # noqa: BLE001
                log.warning("pricing: chain %s %s failed: %s", symbol, expiry, e)
                chain = []
            book: dict[tuple[float, str], dict] = {}
            for c in chain:
                det = c.get("details") or {}
                k, typ = det.get("strike_price"), det.get("contract_type")
                if k is not None and typ in ("call", "put"):
                    book[(float(k), typ)] = c

            for i in idxs:
                leg = out[i]
                c = book.get((float(leg["strike"]), leg["contract_type"]))
                if not c:
                    leg.update(price=None, delta=None, oi=None, iv=None,
                               spread_pct=None)
                    continue
                greeks = c.get("greeks") or {}
                leg["price"] = self._poly.leg_price(c)
                leg["delta"] = greeks.get("delta")
                leg["oi"] = c.get("open_interest")
                leg["iv"] = c.get("implied_volatility")
                leg["spread_pct"] = self._poly.leg_spread_pct(c)
        return out


def get_pricing(poly: PolygonOptionsClient) -> DelayedPolygonPricing:
    """The single switch point for the live-data upgrade."""
    return DelayedPolygonPricing(poly)
