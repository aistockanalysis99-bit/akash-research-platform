"""Polygon.io (now "Massive") options client — chains, ATM straddle pricing.

$79 "Options Developer" tier: 15-min delayed, chain snapshots WITH greeks + IV
+ open interest. `last_quote` (NBBO) is usually null on this tier, so leg
pricing falls back: last_quote mid → day close → last trade price.

There is NO historical-IV endpoint on Polygon — the scanner snapshots ATM IV
daily into our own iv_history table so IV-percentile filters become usable
over time.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

import httpx

from ...config import POLYGON_API_KEY

log = logging.getLogger(__name__)

BASE = "https://api.polygon.io"


class PolygonError(RuntimeError):
    pass


class PolygonOptionsClient:
    def __init__(self, api_key: Optional[str] = None) -> None:
        self.api_key = api_key or POLYGON_API_KEY
        if not self.api_key:
            raise PolygonError("POLYGON_API_KEY is not set.")
        self._client: Optional[httpx.AsyncClient] = None

    async def __aenter__(self) -> "PolygonOptionsClient":
        self._client = httpx.AsyncClient(timeout=30.0)
        return self

    async def __aexit__(self, *exc) -> None:
        if self._client:
            await self._client.aclose()

    async def _get(self, path_or_url: str, params: Optional[dict] = None) -> dict:
        assert self._client is not None, "use `async with PolygonOptionsClient()`"
        params = dict(params or {})
        params["apiKey"] = self.api_key
        url = path_or_url if path_or_url.startswith("http") else f"{BASE}{path_or_url}"
        r = await self._client.get(url, params=params)
        if r.status_code != 200:
            raise PolygonError(f"polygon {r.status_code}: {r.text[:150]}")
        return r.json()

    # ------------------------------------------------------------------ #

    async def first_expiry_after(self, underlying: str, after_date: str) -> Optional[str]:
        """First listed option expiration strictly AFTER `after_date` (ISO)."""
        j = await self._get(
            "/v3/reference/options/contracts",
            {
                "underlying_ticker": underlying.upper(),
                "expiration_date.gt": after_date,
                "expired": "false",
                "sort": "expiration_date",
                "order": "asc",
                "limit": 50,
            },
        )
        rows = j.get("results") or []
        for row in rows:
            exp = row.get("expiration_date")
            if exp:
                return exp
        return None

    async def chain_for_expiry(self, underlying: str, expiry: str,
                               strike_lo: float, strike_hi: float) -> list[dict]:
        """Chain snapshot (both types) for one expiry within a strike band.
        Each contract: details, greeks, implied_volatility, open_interest,
        last_quote (often null), last_trade, day, underlying_asset."""
        out: list[dict] = []
        url = f"/v3/snapshot/options/{underlying.upper()}"
        params: Optional[dict] = {
            "expiration_date": expiry,
            "strike_price.gte": strike_lo,
            "strike_price.lte": strike_hi,
            "limit": 250,
        }
        for _ in range(4):  # pagination guard
            j = await self._get(url, params)
            out.extend(j.get("results") or [])
            nxt = j.get("next_url")
            if not nxt:
                break
            url, params = nxt, None
        return out

    # ------------------------------------------------------------------ #

    @staticmethod
    def leg_price(contract: dict) -> Optional[float]:
        """Best-effort per-share price: NBBO mid → day close → last trade."""
        q = contract.get("last_quote") or {}
        bid, ask = q.get("bid"), q.get("ask")
        if bid and ask and bid > 0 and ask > 0:
            return round((bid + ask) / 2, 4)
        day = contract.get("day") or {}
        if day.get("close"):
            return float(day["close"])
        lt = contract.get("last_trade") or {}
        if lt.get("price"):
            return float(lt["price"])
        return None

    @staticmethod
    def leg_spread_pct(contract: dict) -> Optional[float]:
        """Bid-ask spread as % of mid — None when NBBO unavailable (this tier)."""
        q = contract.get("last_quote") or {}
        bid, ask = q.get("bid"), q.get("ask")
        if bid and ask and bid > 0 and ask > 0:
            mid = (bid + ask) / 2
            return round((ask - bid) / mid * 100, 2) if mid > 0 else None
        return None

    async def atm_straddle(self, underlying: str, expiry: str, spot: float) -> Optional[dict[str, Any]]:
        """Price the ATM straddle for `expiry`. Returns strike, per-leg detail,
        combined cost, avg IV/greeks — or None if a priced pair can't be found."""
        band = max(spot * 0.08, 5.0)
        contracts = await self.chain_for_expiry(
            underlying, expiry, spot - band, spot + band)
        by_strike: dict[float, dict[str, dict]] = {}
        for c in contracts:
            det = c.get("details") or {}
            k, typ = det.get("strike_price"), det.get("contract_type")
            if k is None or typ not in ("call", "put"):
                continue
            by_strike.setdefault(float(k), {})[typ] = c

        # nearest strike to spot with BOTH priced legs
        for k in sorted(by_strike.keys(), key=lambda x: abs(x - spot)):
            legs = by_strike[k]
            call, put = legs.get("call"), legs.get("put")
            if not call or not put:
                continue
            cp, pp = self.leg_price(call), self.leg_price(put)
            if not cp or not pp:
                continue
            ivs = [v for v in (call.get("implied_volatility"),
                               put.get("implied_volatility")) if v]
            cg, pg = call.get("greeks") or {}, put.get("greeks") or {}

            def _avg(a, b):
                vals = [v for v in (a, b) if v is not None]
                return round(sum(vals) / len(vals), 5) if vals else None

            spreads = [s for s in (self.leg_spread_pct(call),
                                   self.leg_spread_pct(put)) if s is not None]
            return {
                "strike": k,
                "expiry": expiry,
                "spot": spot,
                "call_price": cp,
                "put_price": pp,
                "straddle_cost": round(cp + pp, 4),
                "atm_iv": round(sum(ivs) / len(ivs), 4) if ivs else None,
                "avg_theta": _avg(cg.get("theta"), pg.get("theta")),
                "avg_vega": _avg(cg.get("vega"), pg.get("vega")),
                "call_delta": cg.get("delta"),
                "put_delta": pg.get("delta"),
                "min_oi": min(call.get("open_interest") or 0,
                              put.get("open_interest") or 0),
                "max_leg_spread_pct": max(spreads) if spreads else None,
            }
        return None
