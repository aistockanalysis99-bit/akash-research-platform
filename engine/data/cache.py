"""Local Parquet cache for OHLCV data.

One file per (symbol, timeframe). Incremental refresh fetches only bars newer
than the latest cached timestamp.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import pandas as pd

from ..config import DATA_CACHE_DIR
from ..logging_setup import get_logger
from .fmp_client import FMPClient, INTRADAY_TIMEFRAMES

log = get_logger("data.cache")


@dataclass
class CacheStatus:
    symbol: str
    timeframe: str
    bars: int
    first_ts: Optional[datetime]
    last_ts: Optional[datetime]
    file_path: Path


def _cache_path(symbol: str, timeframe: str) -> Path:
    safe = symbol.replace("/", "_").replace(".", "_")
    return DATA_CACHE_DIR / f"{safe}_{timeframe}.parquet"


def load_bars(symbol: str, timeframe: str) -> pd.DataFrame:
    """Load cached bars for a symbol/timeframe. Empty DataFrame if missing."""
    path = _cache_path(symbol, timeframe)
    if not path.exists():
        return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume", "adj_close"])
    df = pd.read_parquet(path)
    if "timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    return df.sort_values("timestamp").reset_index(drop=True)


def save_bars(symbol: str, timeframe: str, df: pd.DataFrame) -> Path:
    """Persist bars to Parquet."""
    path = _cache_path(symbol, timeframe)
    if not df.empty:
        df = df.sort_values("timestamp").drop_duplicates(subset=["timestamp"], keep="last")
    df.to_parquet(path, index=False)
    return path


def cache_status(symbol: str, timeframe: str) -> CacheStatus:
    df = load_bars(symbol, timeframe)
    if df.empty:
        return CacheStatus(symbol, timeframe, 0, None, None, _cache_path(symbol, timeframe))
    return CacheStatus(
        symbol=symbol,
        timeframe=timeframe,
        bars=len(df),
        first_ts=df["timestamp"].iloc[0].to_pydatetime(),
        last_ts=df["timestamp"].iloc[-1].to_pydatetime(),
        file_path=_cache_path(symbol, timeframe),
    )


async def refresh_symbol(
    client: FMPClient,
    symbol: str,
    timeframe: str,
    years_back: int = 5,
    incremental: bool = True,
) -> CacheStatus:
    """Refresh one symbol/timeframe in cache. Incremental if cache exists."""
    existing = load_bars(symbol, timeframe)
    end_date = datetime.now(tz=timezone.utc)

    if incremental and not existing.empty:
        # Fetch from the last cached date forward
        from_date = existing["timestamp"].iloc[-1].to_pydatetime() - timedelta(days=2)
    else:
        from_date = end_date - timedelta(days=365 * years_back)

    if timeframe == "1D":
        new_df = await client.fetch_daily(symbol, from_date=from_date, to_date=end_date)
    elif timeframe in INTRADAY_TIMEFRAMES:
        new_df = await client.fetch_intraday(symbol, timeframe, from_date=from_date, to_date=end_date)
    else:
        raise ValueError(f"Unsupported timeframe for direct fetch: {timeframe}")

    if new_df.empty:
        log.warning("Refresh got 0 bars for %s %s", symbol, timeframe)
        return cache_status(symbol, timeframe)

    if existing.empty:
        merged = new_df
    else:
        merged = pd.concat([existing, new_df], ignore_index=True)
        merged = merged.drop_duplicates(subset=["timestamp"], keep="last").sort_values("timestamp")

    save_bars(symbol, timeframe, merged)
    log.info("Cached %s %s: %d total bars", symbol, timeframe, len(merged))
    return cache_status(symbol, timeframe)


async def refresh_universe(
    symbols: list[str],
    timeframe: str,
    years_back: int = 5,
    incremental: bool = True,
    max_concurrent: int = 8,
    progress_cb=None,
) -> list[CacheStatus]:
    """Refresh many symbols. Returns status list."""
    async with FMPClient(max_concurrent=max_concurrent) as client:
        results: list[CacheStatus] = []

        async def _one(sym: str, idx: int) -> None:
            try:
                status = await refresh_symbol(client, sym, timeframe, years_back, incremental)
                results.append(status)
            except Exception as e:  # noqa: BLE001
                log.error("Failed to refresh %s %s: %s", sym, timeframe, e)
                results.append(CacheStatus(sym, timeframe, 0, None, None, _cache_path(sym, timeframe)))
            if progress_cb is not None:
                progress_cb(idx + 1, len(symbols), sym)

        await asyncio.gather(*[_one(s, i) for i, s in enumerate(symbols)])
    return results


def list_cached() -> list[CacheStatus]:
    """List all cache entries on disk."""
    out: list[CacheStatus] = []
    for f in sorted(DATA_CACHE_DIR.glob("*.parquet")):
        stem = f.stem
        # Format: SYMBOL_TIMEFRAME (timeframe may be e.g. 1D, 4h)
        parts = stem.rsplit("_", 1)
        if len(parts) != 2:
            continue
        symbol, tf = parts
        # Replace back '_' to '.' if symbol had it (e.g. BRK_B -> BRK.B)
        # We use '.' -> '_' on save; reverse safely (only for known suffixes)
        if symbol.endswith("_B") or symbol.endswith("_A"):
            symbol = symbol[:-2] + "." + symbol[-1]
        out.append(cache_status(symbol, tf))
    return out
