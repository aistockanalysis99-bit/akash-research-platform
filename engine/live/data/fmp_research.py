"""FMP /stable/ fundamental + news endpoint methods for Phase 2 agents.

Wraps the existing FMPClient with a thin layer that:
    - uses validated paths/params from fmp_constants
    - applies sensible TTL caching to disk (JSON files)
    - normalizes return shapes (always returns dict or list[dict])
    - degrades gracefully on premium-only endpoints (returns None instead of raising)

All endpoint methods are async and safe to await concurrently — the underlying
FMPClient already handles rate-limiting and retry.
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional

from ...config import DATA_CACHE_DIR
from ...data.fmp_client import FMPClient, FMPError
from . import fmp_constants as C

log = logging.getLogger(__name__)


# Per-endpoint cache TTLs (hours). Picked to balance freshness vs API cost.
CACHE_TTL_HOURS: dict[str, int] = {
    "profile": 168,             # 7 days — sector/industry barely change
    "income_q": 168,
    "balance_q": 168,
    "cashflow_q": 168,
    "ratios_annual": 168,
    "ratios_ttm": 24,           # TTM rolls every day
    "key_metrics_annual": 168,
    "key_metrics_ttm": 24,
    "earnings": 168,
    "earnings_calendar": 24,
    "analyst_estimates": 168,
    "news": 12,                 # 2 refreshes per day
    "grades": 24,
    "sec_filings": 24,
    "insider_trades": 24,
    "press_releases": 12,
}


@dataclass
class FetchResult:
    """A typed wrapper so callers can distinguish 'no data' from 'unavailable'."""

    data: Optional[Any]   # the parsed JSON (dict, list[dict], or None)
    available: bool        # False = endpoint not on current plan
    cached: bool
    source_path: str       # for audit trail
    fetched_at: str        # ISO timestamp


class FMPResearchClient:
    """High-level fundamental + news fetcher backed by FMPClient.

    Usage:
        async with FMPClient() as raw:
            research = FMPResearchClient(raw)
            profile = await research.fetch_profile("NVDA")
            news = await research.fetch_news("NVDA", limit=15)
    """

    def __init__(
        self,
        client: FMPClient,
        cache_dir: Optional[Path] = None,
    ) -> None:
        self.client = client
        self.cache_dir = (cache_dir or DATA_CACHE_DIR) / "research"

    # ----------------------------------------------------------------------- #
    # Cache helpers
    # ----------------------------------------------------------------------- #

    def _cache_path(self, symbol: str, endpoint_key: str, suffix: str = "") -> Path:
        # Date in the filename gives us natural rotation + audit.
        day = date.today().isoformat()
        name = f"{endpoint_key}_{day}{suffix}.json"
        return self.cache_dir / symbol.upper() / name

    async def _cached(
        self,
        symbol: str,
        endpoint_key: str,
        fetcher: Callable[[], Awaitable[Any]],
        suffix: str = "",
    ) -> FetchResult:
        ttl_h = CACHE_TTL_HOURS.get(endpoint_key, 24)
        path = self._cache_path(symbol, endpoint_key, suffix)
        now_iso = datetime.utcnow().isoformat()

        # Cache hit?
        if path.exists():
            age_h = (time.time() - path.stat().st_mtime) / 3600
            if age_h < ttl_h:
                try:
                    raw = json.loads(path.read_text(encoding="utf-8"))
                    return FetchResult(
                        data=raw.get("data"),
                        available=raw.get("available", True),
                        cached=True,
                        source_path=raw.get("source_path", ""),
                        fetched_at=raw.get("fetched_at", now_iso),
                    )
                except (json.JSONDecodeError, KeyError):
                    log.warning("corrupt cache at %s, refetching", path)

        # Miss — fetch live, then cache.
        try:
            data = await fetcher()
            result = FetchResult(
                data=data,
                available=True,
                cached=False,
                source_path=endpoint_key,
                fetched_at=now_iso,
            )
        except FMPError as e:
            msg = str(e)
            # Treat both "not on this plan" (402) and "endpoint missing" (404)
            # as graceful absences. The pipeline keeps going with what it has.
            if ("402" in msg or "404" in msg or
                    "Premium" in msg or "Restricted" in msg):
                log.info("endpoint %s not available (plan or path): %s",
                          endpoint_key, msg[:120])
                result = FetchResult(
                    data=None,
                    available=False,
                    cached=False,
                    source_path=endpoint_key,
                    fetched_at=now_iso,
                )
            else:
                raise

        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "data": result.data,
                    "available": result.available,
                    "source_path": result.source_path,
                    "fetched_at": result.fetched_at,
                },
                default=str,
            ),
            encoding="utf-8",
        )
        return result

    # ----------------------------------------------------------------------- #
    # Profile + statements
    # ----------------------------------------------------------------------- #

    async def fetch_profile(self, symbol: str) -> FetchResult:
        async def f() -> Optional[dict]:
            data = await self.client._get(C.PATH_PROFILE, {C.PARAM_PROFILE: symbol})
            if isinstance(data, list) and data:
                return data[0]
            return None
        return await self._cached(symbol, "profile", f)

    async def fetch_income_quarterly(self, symbol: str, limit: int = 8) -> FetchResult:
        async def f() -> list[dict]:
            data = await self.client._get(
                C.PATH_INCOME_Q,
                {C.PARAM_INCOME_Q: symbol, "period": "quarter", "limit": limit},
            )
            return data if isinstance(data, list) else []
        return await self._cached(symbol, "income_q", f)

    async def fetch_balance_quarterly(self, symbol: str, limit: int = 4) -> FetchResult:
        async def f() -> list[dict]:
            data = await self.client._get(
                C.PATH_BALANCE_Q,
                {C.PARAM_BALANCE_Q: symbol, "period": "quarter", "limit": limit},
            )
            return data if isinstance(data, list) else []
        return await self._cached(symbol, "balance_q", f)

    async def fetch_cashflow_quarterly(self, symbol: str, limit: int = 4) -> FetchResult:
        async def f() -> list[dict]:
            data = await self.client._get(
                C.PATH_CASHFLOW_Q,
                {C.PARAM_CASHFLOW_Q: symbol, "period": "quarter", "limit": limit},
            )
            return data if isinstance(data, list) else []
        return await self._cached(symbol, "cashflow_q", f)

    # ----------------------------------------------------------------------- #
    # Ratios + key metrics
    # On Starter plan, period=quarter is blocked. Use annual + TTM as substitute.
    # ----------------------------------------------------------------------- #

    async def fetch_ratios_annual(self, symbol: str, limit: int = 5) -> FetchResult:
        async def f() -> list[dict]:
            data = await self.client._get(
                C.PATH_RATIOS_ANNUAL,
                {C.PARAM_RATIOS_ANNUAL: symbol,
                 "period": C.RATIOS_PERIOD_FALLBACK, "limit": limit},
            )
            return data if isinstance(data, list) else []
        return await self._cached(symbol, "ratios_annual", f)

    async def fetch_ratios_ttm(self, symbol: str) -> FetchResult:
        async def f() -> Optional[dict]:
            data = await self.client._get(
                C.PATH_RATIOS_TTM, {C.PARAM_RATIOS_TTM: symbol}
            )
            if isinstance(data, list) and data:
                return data[0]
            return data if isinstance(data, dict) else None
        return await self._cached(symbol, "ratios_ttm", f)

    async def fetch_key_metrics_annual(self, symbol: str, limit: int = 5) -> FetchResult:
        async def f() -> list[dict]:
            data = await self.client._get(
                C.PATH_KEY_METRICS_ANNUAL,
                {C.PARAM_KEY_METRICS_ANNUAL: symbol,
                 "period": C.KEY_METRICS_PERIOD_FALLBACK, "limit": limit},
            )
            return data if isinstance(data, list) else []
        return await self._cached(symbol, "key_metrics_annual", f)

    async def fetch_key_metrics_ttm(self, symbol: str) -> FetchResult:
        async def f() -> Optional[dict]:
            data = await self.client._get(
                C.PATH_KEY_METRICS_TTM, {C.PARAM_KEY_METRICS_TTM: symbol}
            )
            if isinstance(data, list) and data:
                return data[0]
            return data if isinstance(data, dict) else None
        return await self._cached(symbol, "key_metrics_ttm", f)

    # ----------------------------------------------------------------------- #
    # Earnings + estimates
    # ----------------------------------------------------------------------- #

    async def fetch_earnings(self, symbol: str, limit: int = 8) -> FetchResult:
        """Past + future earnings rows in one endpoint."""
        async def f() -> list[dict]:
            data = await self.client._get(
                C.PATH_EARNINGS, {C.PARAM_EARNINGS: symbol, "limit": limit}
            )
            return data if isinstance(data, list) else []
        return await self._cached(symbol, "earnings", f)

    async def fetch_next_earnings_date(self, symbol: str) -> Optional[date]:
        """Derive next earnings date from /earnings. Returns None if not scheduled."""
        result = await self.fetch_earnings(symbol, limit=16)
        rows = result.data or []
        today = date.today()
        future = []
        for row in rows:
            d_str = row.get("date")
            if not d_str:
                continue
            try:
                d = date.fromisoformat(d_str)
            except ValueError:
                continue
            if d >= today and row.get("epsActual") is None:
                future.append(d)
        return min(future) if future else None

    async def fetch_analyst_estimates(
        self, symbol: str, period: str = "annual", limit: int = 10
    ) -> FetchResult:
        async def f() -> list[dict]:
            data = await self.client._get(
                C.PATH_ANALYST_ESTIMATES,
                {C.PARAM_ANALYST_ESTIMATES: symbol,
                 "period": period, "page": 0, "limit": limit},
            )
            return data if isinstance(data, list) else []
        return await self._cached(symbol, "analyst_estimates", f)

    # ----------------------------------------------------------------------- #
    # News + market signals
    # ----------------------------------------------------------------------- #

    async def fetch_news(self, symbol: str, limit: int = 15, hours: int = 48) -> FetchResult:
        """Last N hours of news for a ticker."""
        async def f() -> list[dict]:
            data = await self.client._get(
                C.PATH_NEWS_STOCK,
                {C.PARAM_NEWS_STOCK: symbol, "limit": limit},
            )
            if not isinstance(data, list):
                return []
            cutoff = datetime.utcnow() - timedelta(hours=hours)
            out = []
            for row in data:
                pub = row.get("publishedDate")
                if not pub:
                    continue
                try:
                    pub_dt = datetime.fromisoformat(pub.replace("Z", "+00:00"))
                except ValueError:
                    # FMP sometimes returns "YYYY-MM-DD HH:MM:SS"
                    try:
                        pub_dt = datetime.strptime(pub, "%Y-%m-%d %H:%M:%S")
                    except ValueError:
                        continue
                if pub_dt.replace(tzinfo=None) >= cutoff:
                    out.append(row)
            return out
        return await self._cached(symbol, "news", f)

    async def fetch_grades(self, symbol: str, days: int = 30) -> FetchResult:
        """Analyst upgrades/downgrades, filtered to last N days."""
        async def f() -> list[dict]:
            data = await self.client._get(
                C.PATH_GRADES, {C.PARAM_GRADES: symbol}
            )
            if not isinstance(data, list):
                return []
            cutoff = date.today() - timedelta(days=days)
            out = []
            for row in data:
                d_str = row.get(C.FIELD_GRADES_DATE)
                if not d_str:
                    continue
                try:
                    d = date.fromisoformat(d_str[:10])
                except ValueError:
                    continue
                if d >= cutoff:
                    out.append(row)
            return out
        return await self._cached(symbol, "grades", f)

    async def fetch_sec_filings(self, symbol: str, days: int = 60) -> FetchResult:
        """SEC filings list. from/to date params are required by FMP."""
        async def f() -> list[dict]:
            from_str = (date.today() - timedelta(days=days)).isoformat()
            to_str = date.today().isoformat()
            data = await self.client._get(
                C.PATH_SEC_FILINGS,
                {C.PARAM_SEC_FILINGS: symbol, "from": from_str, "to": to_str,
                 "page": 0, "limit": 50},
            )
            return data if isinstance(data, list) else []
        return await self._cached(symbol, "sec_filings", f)

    async def fetch_insider_trades(
        self, symbol: str, min_value_usd: float = 1_000_000.0, days: int = 60
    ) -> FetchResult:
        """Insider transactions filtered to (price * shares) >= min_value_usd."""
        async def f() -> list[dict]:
            data = await self.client._get(
                C.PATH_INSIDER_TRADES,
                {C.PARAM_INSIDER_TRADES: symbol, "page": 0, "limit": 100},
            )
            if not isinstance(data, list):
                return []
            cutoff = date.today() - timedelta(days=days)
            out = []
            for row in data:
                price = row.get("price") or 0
                shares = row.get("securitiesTransacted") or 0
                if not (isinstance(price, (int, float)) and isinstance(shares, (int, float))):
                    continue
                value = abs(price * shares)
                if value < min_value_usd:
                    continue
                d_str = row.get("transactionDate") or row.get("filingDate")
                if not d_str:
                    continue
                try:
                    d = date.fromisoformat(d_str[:10])
                except ValueError:
                    continue
                if d < cutoff:
                    continue
                # Attach the computed value for downstream display.
                row = dict(row)
                row["_value_usd"] = value
                out.append(row)
            return out
        return await self._cached(symbol, "insider_trades", f)

    async def fetch_press_releases(self, symbol: str, limit: int = 30) -> FetchResult:
        """Premium-only on Starter plan. Returns FetchResult(available=False) if blocked."""
        if not C.PRESS_RELEASES_AVAILABLE:
            return FetchResult(
                data=None, available=False, cached=False,
                source_path=C.PATH_PRESS_RELEASES,
                fetched_at=datetime.utcnow().isoformat(),
            )

        async def f() -> list[dict]:
            data = await self.client._get(
                C.PATH_PRESS_RELEASES,
                {C.PARAM_PRESS_RELEASES: symbol, "limit": limit},
            )
            return data if isinstance(data, list) else []
        return await self._cached(symbol, "press_releases", f)

    # ----------------------------------------------------------------------- #
    # Tier 1 — M17 (graceful degrade if plan-locked)
    # ----------------------------------------------------------------------- #

    async def fetch_revenue_segments_product(self, symbol: str) -> FetchResult:
        """Product/business-line revenue split (e.g. NVDA: data_center 85%, gaming 8%)."""
        async def f() -> Optional[list]:
            data = await self.client._get(
                C.PATH_REVENUE_SEGMENT_PRODUCT, {"symbol": symbol},
            )
            if isinstance(data, list) and data:
                return data
            if isinstance(data, dict):
                return [data]
            return None
        return await self._cached(symbol, "revenue_segments_product", f)

    async def fetch_revenue_segments_geographic(self, symbol: str) -> FetchResult:
        """Geographic revenue split (e.g. NVDA: US 47%, China 17%)."""
        async def f() -> Optional[list]:
            data = await self.client._get(
                C.PATH_REVENUE_SEGMENT_GEO, {"symbol": symbol},
            )
            if isinstance(data, list) and data:
                return data
            if isinstance(data, dict):
                return [data]
            return None
        return await self._cached(symbol, "revenue_segments_geo", f)

    async def fetch_earnings_transcript(
        self, symbol: str, year: Optional[int] = None, quarter: Optional[int] = None,
    ) -> FetchResult:
        """Most recent earnings call transcript.

        Premium endpoint requires year AND quarter. We walk backwards from
        current quarter until we find one with content (handles companies
        whose latest quarter hasn't been called yet).
        """
        async def f() -> Optional[dict]:
            from datetime import date
            today = date.today()
            current_year = today.year
            current_q = (today.month - 1) // 3 + 1

            if year is not None and quarter is not None:
                attempts = [(year, quarter)]
            else:
                # Walk back up to 6 quarters
                attempts = []
                y, q = current_year, current_q
                for _ in range(6):
                    attempts.append((y, q))
                    q -= 1
                    if q < 1:
                        q = 4
                        y -= 1

            for y, q in attempts:
                try:
                    data = await self.client._get(
                        C.PATH_EARNINGS_TRANSCRIPT,
                        {"symbol": symbol, "year": y, "quarter": q},
                    )
                except FMPError as e:
                    if "400" in str(e) or "404" in str(e):
                        continue
                    raise
                if isinstance(data, list) and data:
                    return data[0]
                if isinstance(data, dict) and data:
                    return data
            return None
        return await self._cached(symbol, "earnings_transcript", f)

    async def fetch_price_target_summary(self, symbol: str) -> FetchResult:
        """Aggregated analyst price-target distribution."""
        async def f() -> Optional[dict]:
            data = await self.client._get(
                C.PATH_PRICE_TARGET_SUMMARY, {"symbol": symbol},
            )
            if isinstance(data, list) and data:
                return data[0]
            if isinstance(data, dict):
                return data
            return None
        return await self._cached(symbol, "price_target_summary", f)

    async def fetch_price_target_news(
        self, symbol: str, limit: int = 25,
    ) -> FetchResult:
        """Recent price-target revisions (analyst, firm, old PT, new PT, date)."""
        async def f() -> list[dict]:
            data = await self.client._get(
                C.PATH_PRICE_TARGET_NEWS,
                {"symbol": symbol, "limit": limit, "page": 0},
            )
            return data if isinstance(data, list) else []
        return await self._cached(symbol, "price_target_news", f)

    async def fetch_institutional_holders(
        self, symbol: str, limit: int = 50,
    ) -> FetchResult:
        """13F-derived institutional ownership rows for this symbol.

        FMP path naming has varied historically. Try a few known variants
        before giving up. All variants degrade gracefully on 404 via
        the broadened error handler in _cached.
        """
        async def f() -> list[dict]:
            # Premium endpoint expects year + quarter params.
            from datetime import date
            today = date.today()
            quarter = (today.month - 1) // 3 + 1
            # Try current quarter, then previous (filings lag 45-90 days)
            attempts = [
                (today.year, quarter),
                (today.year, max(1, quarter - 1)),
                (today.year - 1, 4),
            ]
            candidate_paths = [
                "/institutional-ownership/symbol-positions-summary",
                "/institutional-ownership/symbol-ownership",
                "/institutional-ownership/positions",
                "/institutional-holder",
                "/institutional-holders",
            ]
            last_err: Optional[Exception] = None
            for y, q in attempts:
                for path in candidate_paths:
                    try:
                        data = await self.client._get(
                            path,
                            {"symbol": symbol, "year": y, "quarter": q,
                             "page": 0, "limit": limit},
                        )
                        if isinstance(data, list) and data:
                            return data
                    except FMPError as e:
                        last_err = e
                        if "404" in str(e) or "400" in str(e):
                            continue
                        raise
            if last_err is not None:
                raise last_err
            return []
        return await self._cached(symbol, "institutional_holders", f)
