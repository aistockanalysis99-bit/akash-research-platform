"""Unusual Whales REST client — institutional/dark-pool/options flow data.

Independent of any MCP integration. Talks to api.unusualwhales.com directly
with an Authorization: Bearer header and the same FetchResult /
graceful-degrade pattern used by FMPResearchClient.

Endpoint set (validated empirically against the openapi spec on 2026-05-30):
    GET /api/institution/{ticker}/ownership          — 13F top holders + Q-o-Q
    GET /api/darkpool/{ticker}                       — dark pool prints
    GET /api/stock/{ticker}/flow-alerts              — UOA flow alerts
    GET /api/stock/{ticker}/options-volume           — daily call/put + premium
    (bonus) GET /api/stock/{ticker}/insider-buy-sells — net insider $ flow

Each method returns a FetchResult so the pipeline can degrade gracefully
when an endpoint is plan-locked or the symbol has no data.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional

import httpx

from ...config import DATA_CACHE_DIR

log = logging.getLogger(__name__)

UW_BASE_URL = "https://api.unusualwhales.com"

# Cache TTLs in hours — UW data is real-time but we don't need second-level freshness.
# Institutional ownership rolls quarterly; everything else updates intraday.
CACHE_TTL_HOURS: dict[str, int] = {
    "uw_inst_ownership":    72,   # 13F filings — quarterly, 3-day cache fine
    "uw_darkpool":          1,    # intraday, want fresh-ish
    "uw_flow_alerts":       1,
    "uw_options_volume":    6,
    "uw_insider":           24,
    # M19 additions
    "uw_greek_exposure":    4,    # dealer hedge updates intraday
    "uw_max_pain":          4,
    "uw_vol_term":          4,
    "uw_short_interest":    24,   # short interest reports bi-monthly
    "uw_sector_etfs":       1,
    "uw_market_tide":       1,
    "uw_econ_calendar":     12,
}


class UWError(Exception):
    pass


@dataclass
class FetchResult:
    """Match FMPResearchClient.FetchResult shape so callers stay uniform."""
    data: Optional[Any]
    available: bool
    cached: bool
    source_path: str
    fetched_at: str


class UnusualWhalesClient:
    """Async client for the Unusual Whales REST API.

    Usage:
        async with UnusualWhalesClient() as uw:
            holders = await uw.fetch_institutional_ownership("AAPL")
            dp      = await uw.fetch_dark_pool("AAPL")
            flow    = await uw.fetch_options_flow("AAPL")
            ov      = await uw.fetch_options_volume("AAPL")
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: str = UW_BASE_URL,
        max_concurrent: int = 4,
        rate_limit_per_min: int = 120,
        timeout: float = 30.0,
        cache_dir: Optional[Path] = None,
    ) -> None:
        self.api_key = api_key or os.getenv("UW_API_KEY", "")
        if not self.api_key:
            raise UWError("UW_API_KEY not set in environment.")
        self.base_url = base_url.rstrip("/")
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._min_interval = 60.0 / max(rate_limit_per_min, 1)
        self._last_request_time = 0.0
        self._lock = asyncio.Lock()
        self._client = httpx.AsyncClient(
            timeout=timeout,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Accept": "application/json",
            },
        )
        self.cache_dir = (cache_dir or DATA_CACHE_DIR) / "uw"

    async def __aenter__(self) -> "UnusualWhalesClient":
        return self

    async def __aexit__(self, *args) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()

    # ------------------------------------------------------------------ #
    # HTTP plumbing
    # ------------------------------------------------------------------ #

    async def _throttle(self) -> None:
        async with self._lock:
            now = asyncio.get_event_loop().time()
            wait = self._min_interval - (now - self._last_request_time)
            if wait > 0:
                await asyncio.sleep(wait)
            self._last_request_time = asyncio.get_event_loop().time()

    async def _get(self, path: str, params: Optional[dict] = None) -> Any:
        url = f"{self.base_url}{path}"
        async with self._semaphore:
            await self._throttle()
            log.debug("UW GET %s params=%s", url, params)
            r = await self._client.get(url, params=params or {})
            if r.status_code == 200:
                return r.json()
            if r.status_code in (401, 403):
                raise UWError(f"UW auth failed ({r.status_code}) on {path}")
            if r.status_code == 404:
                raise UWError(f"UW 404 on {path}")
            if r.status_code == 429:
                raise UWError(f"UW rate limited (429) on {path}")
            raise UWError(f"UW {r.status_code} on {path}: {r.text[:200]}")

    # ------------------------------------------------------------------ #
    # Cache wrapper — mirrors FMPResearchClient._cached
    # ------------------------------------------------------------------ #

    def _cache_path(self, symbol: str, key: str) -> Path:
        day = date.today().isoformat()
        return self.cache_dir / symbol.upper() / f"{key}_{day}.json"

    async def _cached(
        self,
        symbol: str,
        key: str,
        source_path: str,
        fetcher: Callable[[], Awaitable[Any]],
    ) -> FetchResult:
        ttl_h = CACHE_TTL_HOURS.get(key, 6)
        path = self._cache_path(symbol, key)
        now_iso = datetime.utcnow().isoformat()

        if path.exists():
            age_h = (time.time() - path.stat().st_mtime) / 3600
            if age_h < ttl_h:
                try:
                    raw = json.loads(path.read_text(encoding="utf-8"))
                    return FetchResult(
                        data=raw.get("data"),
                        available=raw.get("available", True),
                        cached=True,
                        source_path=raw.get("source_path", source_path),
                        fetched_at=raw.get("fetched_at", now_iso),
                    )
                except (json.JSONDecodeError, KeyError):
                    log.warning("corrupt UW cache at %s, refetching", path)

        try:
            data = await fetcher()
            result = FetchResult(
                data=data, available=True, cached=False,
                source_path=source_path, fetched_at=now_iso,
            )
        except UWError as e:
            msg = str(e)
            # 404 / 401 / 403 / Premium-locked → graceful absence (None data)
            log.info("UW endpoint %s not available: %s", source_path, msg[:120])
            result = FetchResult(
                data=None, available=False, cached=False,
                source_path=source_path, fetched_at=now_iso,
            )

        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({
                "data": result.data,
                "available": result.available,
                "source_path": result.source_path,
                "fetched_at": result.fetched_at,
            }, default=str),
            encoding="utf-8",
        )
        return result

    # ------------------------------------------------------------------ #
    # Public fetch methods — the 4 (+1 bonus) we wire into the pipeline
    # ------------------------------------------------------------------ #

    async def fetch_institutional_ownership(
        self, symbol: str, limit: int = 50,
    ) -> FetchResult:
        """13F holders of `symbol` with units_changed (Q-o-Q delta) and 8q history.

        Response rows include: name, value, units, units_changed,
        historical_units (list[8]), avg_price, filing_date, report_date,
        first_buy. Sorted by `value` desc by UW.
        """
        path = f"/api/institution/{symbol.upper()}/ownership"

        async def f() -> list[dict]:
            data = await self._get(path, {"limit": limit})
            rows = (data or {}).get("data") or []
            return rows[:limit] if isinstance(rows, list) else []

        return await self._cached(symbol, "uw_inst_ownership", path, f)

    async def fetch_dark_pool(
        self, symbol: str, limit: int = 200,
    ) -> FetchResult:
        """Recent dark-pool prints for `symbol`.

        Each row: size, price, executed_at, premium, nbbo_bid, nbbo_ask,
        sale_cond_codes, ext_hour_sold_codes, volume (cumulative day).
        Newest first.
        """
        path = f"/api/darkpool/{symbol.upper()}"

        async def f() -> list[dict]:
            data = await self._get(path, {"limit": limit})
            rows = (data or {}).get("data") or []
            return rows[:limit] if isinstance(rows, list) else []

        return await self._cached(symbol, "uw_darkpool", path, f)

    async def fetch_options_flow(
        self, symbol: str, limit: int = 100,
    ) -> FetchResult:
        """Unusual options activity (UOA) alerts for `symbol`.

        Each row: type (call/put), price, expiry, strike, volume,
        open_interest, underlying_price, total_premium, trade_count,
        iv_end, created_at.
        """
        path = f"/api/stock/{symbol.upper()}/flow-alerts"

        async def f() -> list[dict]:
            data = await self._get(path, {"limit": limit})
            rows = (data or {}).get("data") or []
            return rows[:limit] if isinstance(rows, list) else []

        return await self._cached(symbol, "uw_flow_alerts", path, f)

    async def fetch_options_volume(
        self, symbol: str,
    ) -> FetchResult:
        """Daily options volume & premium for `symbol`.

        Each row (1 per day, ~20 days): call_volume, put_volume,
        call_volume_ask_side, call_volume_bid_side, net_call_premium,
        net_put_premium.
        """
        path = f"/api/stock/{symbol.upper()}/options-volume"

        async def f() -> list[dict]:
            data = await self._get(path)
            rows = (data or {}).get("data") or []
            return rows if isinstance(rows, list) else []

        return await self._cached(symbol, "uw_options_volume", path, f)

    async def fetch_insider_flow(
        self, symbol: str,
    ) -> FetchResult:
        """Daily insider buy/sell totals (notional $) for `symbol`."""
        path = f"/api/stock/{symbol.upper()}/insider-buy-sells"

        async def f() -> list[dict]:
            data = await self._get(path)
            rows = (data or {}).get("data") or []
            return rows if isinstance(rows, list) else []

        return await self._cached(symbol, "uw_insider", path, f)

    # ------------------------------------------------------------------ #
    # M19 — Options Structure + Macro Regime + Short Interest
    # ------------------------------------------------------------------ #

    async def fetch_greek_exposure(self, symbol: str) -> FetchResult:
        """Daily aggregate dealer gamma/delta/charm/vanna exposure.

        Each row (1 per day): call_gamma, put_gamma, call_delta, put_delta,
        call_charm, put_charm, call_vanna, put_vanna. Used to derive the
        gamma flip line (where call_gamma + put_gamma cross zero).
        """
        path = f"/api/stock/{symbol.upper()}/greek-exposure"

        async def f() -> list[dict]:
            data = await self._get(path)
            rows = (data or {}).get("data") or []
            return rows if isinstance(rows, list) else []
        return await self._cached(symbol, "uw_greek_exposure", path, f)

    async def fetch_max_pain(self, symbol: str) -> FetchResult:
        """Max-pain price by expiry — where option holders lose the most.

        Each row: expiry, close, max_pain, next_upper_strike, next_lower_strike.
        """
        path = f"/api/stock/{symbol.upper()}/max-pain"

        async def f() -> list[dict]:
            data = await self._get(path)
            rows = (data or {}).get("data") or []
            return rows if isinstance(rows, list) else []
        return await self._cached(symbol, "uw_max_pain", path, f)

    async def fetch_vol_term_structure(self, symbol: str) -> FetchResult:
        """Implied volatility term structure (IV by expiry)."""
        path = f"/api/stock/{symbol.upper()}/volatility/term-structure"

        async def f() -> list[dict]:
            data = await self._get(path)
            rows = (data or {}).get("data") or []
            return rows if isinstance(rows, list) else []
        return await self._cached(symbol, "uw_vol_term", path, f)

    async def fetch_short_interest(self, symbol: str) -> FetchResult:
        """Short interest, days to cover, % of float."""
        path = f"/api/shorts/{symbol.upper()}/interest-float/v2"

        async def f() -> dict:
            data = await self._get(path)
            return (data or {}).get("data") or {}
        return await self._cached(symbol, "uw_short_interest", path, f)

    async def fetch_sector_etfs(self) -> FetchResult:
        """SPDR sector ETF flow + performance — for macro regime."""
        path = "/api/market/sector-etfs"

        async def f() -> list[dict]:
            data = await self._get(path)
            rows = (data or {}).get("data") or []
            return rows if isinstance(rows, list) else []
        # Single market-wide cache, keyed on symbol="MARKET"
        return await self._cached("MARKET", "uw_sector_etfs", path, f)

    async def fetch_market_tide(self) -> FetchResult:
        """Market-wide net call/put premium tide (institutional sentiment)."""
        path = "/api/market/market-tide"

        async def f() -> list[dict]:
            data = await self._get(path)
            rows = (data or {}).get("data") or []
            return rows if isinstance(rows, list) else []
        return await self._cached("MARKET", "uw_market_tide", path, f)

    async def fetch_option_quote(
        self, underlying: str, expiry: str, strike: float, option_type: str,
    ) -> Optional[float]:
        """Live premium for a specific option contract via the expiry chain.

        Builds the OCC symbol (e.g. AMZN261218C00220000) and returns the last
        traded price (falling back to the bid/ask mid). Returns None if not found.
        Not cached on disk — option marks move fast.
        """
        u = underlying.upper()
        exp = expiry[:10]
        yy, mm, dd = exp[2:4], exp[5:7], exp[8:10]
        cp = "C" if option_type.lower().startswith("c") else "P"
        occ = f"{u}{yy}{mm}{dd}{cp}{int(round(strike * 1000)):08d}"
        path = f"/api/stock/{u}/option-contracts"
        try:
            data = await self._get(path, {"expiry": exp})
        except UWError as e:
            log.info("option chain fetch failed for %s %s: %s", u, exp, e)
            return None
        rows = (data or {}).get("data") or []
        match = next((c for c in rows if c.get("option_symbol") == occ), None)
        if not match:
            return None
        for key in ("last_price",):
            v = match.get(key)
            if v not in (None, "", "0", 0):
                try:
                    return float(v)
                except (TypeError, ValueError):
                    pass
        # Fall back to NBBO mid
        try:
            bid = float(match.get("nbbo_bid") or 0)
            ask = float(match.get("nbbo_ask") or 0)
            if bid > 0 and ask > 0:
                return round((bid + ask) / 2, 4)
        except (TypeError, ValueError):
            pass
        return None

    async def fetch_economic_calendar(self) -> FetchResult:
        """Upcoming macro events (FOMC, CPI, NFP, etc.)."""
        path = "/api/market/economic-calendar"

        async def f() -> list[dict]:
            data = await self._get(path)
            rows = (data or {}).get("data") or []
            return rows if isinstance(rows, list) else []
        return await self._cached("MARKET", "uw_econ_calendar", path, f)
