"""Async client around Financial Modeling Prep's REST API.

Uses the new /stable/ endpoints (post-2025 API). Daily prices are fetched from
the dividend-adjusted endpoint so OHLC are fully adjusted for splits + dividends.

- Throttling (250 req/min — leaves headroom under Starter's 300/min cap)
- Retry on 429 / 5xx with exponential backoff
- Both daily (adjusted) and intraday (raw) endpoints
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Optional

import httpx
import pandas as pd
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from ..config import FMP_API_KEY
from ..logging_setup import get_logger

log = get_logger("data.fmp")

FMP_STABLE = "https://financialmodelingprep.com/stable"

TIMEFRAME_TO_FMP = {
    "15m": "15min",
    "30m": "30min",
    "1h": "1hour",
    "4h": "4hour",
}
INTRADAY_TIMEFRAMES = set(TIMEFRAME_TO_FMP.keys())


class FMPError(Exception):
    pass


class FMPClient:
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: str = FMP_STABLE,
        max_concurrent: int = 6,
        rate_limit_per_min: int = 250,
        timeout: float = 30.0,
    ) -> None:
        self.api_key = api_key or FMP_API_KEY
        if not self.api_key:
            raise FMPError("FMP_API_KEY not set in environment.")
        self.base_url = base_url.rstrip("/")
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._min_interval = 60.0 / max(rate_limit_per_min, 1)
        self._last_request_time = 0.0
        self._lock = asyncio.Lock()
        self._client = httpx.AsyncClient(timeout=timeout)

    async def __aenter__(self) -> "FMPClient":
        return self

    async def __aexit__(self, *args) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _throttle(self) -> None:
        async with self._lock:
            now = asyncio.get_event_loop().time()
            wait = self._min_interval - (now - self._last_request_time)
            if wait > 0:
                await asyncio.sleep(wait)
            self._last_request_time = asyncio.get_event_loop().time()

    async def _get(self, path: str, params: Optional[dict] = None) -> list | dict:
        params = dict(params or {})
        params["apikey"] = self.api_key
        url = f"{self.base_url}{path}"

        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=1, min=1, max=10),
            retry=retry_if_exception_type((httpx.HTTPStatusError, httpx.ReadTimeout, FMPError)),
            reraise=True,
        ):
            with attempt:
                async with self._semaphore:
                    await self._throttle()
                    safe = {k: v for k, v in params.items() if k != "apikey"}
                    log.debug("GET %s params=%s", url, safe)
                    r = await self._client.get(url, params=params)
                    if r.status_code == 429 or 500 <= r.status_code < 600:
                        log.warning("FMP %d on %s: %s", r.status_code, path, r.text[:200])
                        r.raise_for_status()
                    if r.status_code != 200:
                        raise FMPError(f"FMP {r.status_code} on {path}: {r.text[:300]}")
                    return r.json()
        raise FMPError("retry loop exhausted")

    async def fetch_daily(
        self,
        symbol: str,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None,
    ) -> pd.DataFrame:
        """Fetch daily fully-adjusted (splits + dividends) OHLCV bars."""
        params: dict[str, str] = {"symbol": symbol}
        if from_date:
            params["from"] = from_date.strftime("%Y-%m-%d")
        if to_date:
            params["to"] = to_date.strftime("%Y-%m-%d")
        data = await self._get("/historical-price-eod/dividend-adjusted", params)

        if not isinstance(data, list) or not data:
            log.warning("No daily data for %s", symbol)
            return _empty_df()

        df = pd.DataFrame(data).sort_values("date").reset_index(drop=True)
        df["timestamp"] = pd.to_datetime(df["date"], utc=True)
        out = pd.DataFrame({
            "timestamp": df["timestamp"],
            "open": df["adjOpen"].astype(float),
            "high": df["adjHigh"].astype(float),
            "low": df["adjLow"].astype(float),
            "close": df["adjClose"].astype(float),
            "volume": df["volume"].astype(float),
            "adj_close": df["adjClose"].astype(float),
        })
        return out

    async def fetch_intraday(
        self,
        symbol: str,
        timeframe: str,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None,
    ) -> pd.DataFrame:
        """Fetch intraday OHLCV bars. NOTE: not split/dividend adjusted."""
        if timeframe not in TIMEFRAME_TO_FMP:
            raise ValueError(f"Bad intraday timeframe: {timeframe}")
        fmp_interval = TIMEFRAME_TO_FMP[timeframe]
        params: dict[str, str] = {"symbol": symbol}
        if from_date:
            params["from"] = from_date.strftime("%Y-%m-%d")
        if to_date:
            params["to"] = to_date.strftime("%Y-%m-%d")
        data = await self._get(f"/historical-chart/{fmp_interval}", params)

        if not isinstance(data, list) or not data:
            return _empty_df()
        df = pd.DataFrame(data).sort_values("date").reset_index(drop=True)
        df["timestamp"] = pd.to_datetime(df["date"], utc=True)
        out = pd.DataFrame({
            "timestamp": df["timestamp"],
            "open": df["open"].astype(float),
            "high": df["high"].astype(float),
            "low": df["low"].astype(float),
            "close": df["close"].astype(float),
            "volume": df.get("volume", pd.Series([0] * len(df))).astype(float),
            "adj_close": df["close"].astype(float),
        })
        return out


def _empty_df() -> pd.DataFrame:
    return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume", "adj_close"])


def utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)
