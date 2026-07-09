"""Ticker universes. Single source of truth.

S&P 100 is a hard-coded snapshot (verified 2026-04-30). S&P 500 is fetched
LIVE from FMP's /sp500-constituent endpoint (real index membership changes
often — e.g. spinoffs — so a hardcoded 500-ticker list would go stale fast)
and cached to disk with a weekly TTL so we don't refetch on every scan.
"""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

_SP500_CACHE_TTL_SECS = 7 * 24 * 3600  # 1 week


def _sp500_cache_path() -> Path:
    from ..config import DATA_CACHE_DIR
    return Path(DATA_CACHE_DIR) / "universe_sp500.json"


async def fetch_sp500_live(fmp=None) -> list[str]:
    """Fetch current S&P 500 constituents from FMP (uncached network call)."""
    from .fmp_client import FMPClient
    own = fmp is None
    if own:
        fmp = FMPClient()
    try:
        data = await fmp._get("/sp500-constituent")
        tickers = sorted({row["symbol"] for row in data if row.get("symbol")})
        if len(tickers) < 400:  # sanity guard — bad/partial response
            raise ValueError(f"only {len(tickers)} constituents returned — refusing to cache")
        return tickers
    finally:
        if own:
            await fmp.aclose()


async def get_sp500(force_refresh: bool = False) -> list[str]:
    """S&P 500 tickers, cached to disk for a week. Refreshes on demand."""
    path = _sp500_cache_path()
    if not force_refresh and path.exists():
        age = time.time() - path.stat().st_mtime
        if age < _SP500_CACHE_TTL_SECS:
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError) as e:
                log.warning("universe: sp500 cache unreadable (%s) — refetching", e)

    tickers = await fetch_sp500_live()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(tickers), encoding="utf-8")
    except OSError as e:  # noqa: BLE001 — cache write failure is not fatal
        log.warning("universe: failed to write sp500 cache: %s", e)
    log.info("universe: refreshed S&P 500 constituents (%d tickers)", len(tickers))
    return tickers


# S&P 100 tickers (alphabetical), verified 2026-04-30
SP100: list[str] = [
    "AAPL", "ABBV", "ABT", "ACN", "ADBE", "AIG", "AMD", "AMGN", "AMT", "AMZN",
    "AVGO", "AXP", "BA", "BAC", "BK", "BKNG", "BLK", "BMY", "BRK.B", "C",
    "CAT", "CHTR", "CL", "CMCSA", "COF", "COP", "COST", "CRM", "CSCO", "CVS",
    "CVX", "DE", "DHR", "DIS", "DUK", "EMR", "F", "FDX", "GD", "GE",
    "GILD", "GM", "GOOG", "GOOGL", "GS", "HD", "HON", "IBM", "INTC", "INTU",
    "ISRG", "JNJ", "JPM", "KHC", "KO", "LIN", "LLY", "LMT", "LOW", "MA",
    "MCD", "MDLZ", "MDT", "MET", "META", "MMM", "MO", "MRK", "MS", "MSFT",
    "NEE", "NFLX", "NKE", "NVDA", "ORCL", "PEP", "PFE", "PG", "PM", "PYPL",
    "QCOM", "RTX", "SBUX", "SCHW", "SO", "SPG", "T", "TGT", "TMO", "TMUS",
    "TSLA", "TXN", "UNH", "UNP", "UPS", "USB", "V", "VZ", "WFC", "WMT",
]

# Smoke test universe — small but diverse
SMOKE_TEST: list[str] = ["SPY", "AAPL", "MSFT", "GOOGL", "NVDA"]


def get_universe(name: str = "sp100") -> list[str]:
    """Return ticker list for a named universe. Sync — sp100/smoke only.

    Existing callers (backtest CLI, quant scanner, peer metrics, old UI) all
    use this. Left untouched: adding sp500 here would require making it
    async, which would break every one of those call sites.
    """
    name = name.lower()
    if name == "sp100":
        return list(SP100)
    if name == "smoke":
        return list(SMOKE_TEST)
    raise ValueError(f"Unknown universe: {name}. Available: sp100, smoke.")


async def get_universe_async(name: str, force_refresh: bool = False) -> list[str]:
    """Async superset of get_universe — adds "sp500" (live-fetched, cached).
    New callers (e.g. the options scanner) should use this."""
    name = name.lower()
    if name == "sp500":
        return await get_sp500(force_refresh=force_refresh)
    return get_universe(name)


def list_universes() -> list[str]:
    return ["sp100", "smoke"]


def list_universes_async() -> list[str]:
    return ["sp100", "sp500", "smoke"]
