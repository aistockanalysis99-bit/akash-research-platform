"""Market-data fetcher for the morning regime agent.

Pulls SPY + a volatility proxy + a handful of sector ETFs from FMP (using the
existing fetch_daily path, which is already cached as Parquet on disk). We
extract compact summary stats — recent returns, vol, drawdown — and hand a
small JSON bundle to the regime LLM. No giant OHLCV arrays in the prompt.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import date
from typing import Any, Optional

import pandas as pd

from ...data.fmp_client import FMPClient

log = logging.getLogger(__name__)


# A short, opinionated set covering the major macro buckets.
SECTOR_ETFS = ["XLK", "XLF", "XLE", "XLY", "XLP", "XLV", "XLI", "XLU"]

# VIX ETF proxy — FMP /stable doesn't always expose ^VIX cleanly; VIXY tracks
# it and works via the standard equity endpoint.
VOLATILITY_PROXY = "VIXY"


async def fetch_market_data() -> dict[str, Any]:
    """Build the regime agent's input bundle."""
    async with FMPClient() as fmp:
        spy, vol = await asyncio.gather(
            _safe_fetch(fmp, "SPY"),
            _safe_fetch(fmp, VOLATILITY_PROXY),
        )
        sector_dfs = await asyncio.gather(
            *[_safe_fetch(fmp, sym) for sym in SECTOR_ETFS]
        )

    sectors: dict[str, Any] = {}
    for sym, df in zip(SECTOR_ETFS, sector_dfs):
        s = _summarize(df, sym, windows=[1, 5, 20])
        if s is not None:
            sectors[sym] = s

    # Rank sectors by 20-day return.
    ranked = sorted(
        sectors.items(),
        key=lambda kv: (kv[1].get("return_20d") or -999),
        reverse=True,
    )

    return {
        "as_of": date.today().isoformat(),
        "spy": _summarize(spy, "SPY", windows=[1, 5, 20, 60]),
        "volatility_proxy": _summarize(vol, VOLATILITY_PROXY, windows=[1, 5, 20]),
        "sectors": sectors,
        "sectors_ranked": [{"symbol": s, "return_20d": d.get("return_20d")}
                            for s, d in ranked],
    }


async def _safe_fetch(fmp: FMPClient, symbol: str) -> Optional[pd.DataFrame]:
    try:
        df = await fmp.fetch_daily(symbol)
        return df if df is not None and not df.empty else None
    except Exception as e:  # noqa: BLE001
        log.warning("market_data fetch failed for %s: %s", symbol, e)
        return None


def _summarize(
    df: Optional[pd.DataFrame], label: str, windows: list[int],
) -> Optional[dict[str, Any]]:
    if df is None or df.empty:
        return None
    closes = df["close"]
    n = len(closes)
    if n < 2:
        return None

    out: dict[str, Any] = {
        "symbol": label,
        "last_close": float(closes.iloc[-1]),
        "last_date": str(df["timestamp"].iloc[-1])[:10] if "timestamp" in df else None,
    }
    for w in windows:
        if n > w:
            try:
                out[f"return_{w}d"] = float(closes.iloc[-1] / closes.iloc[-(w + 1)] - 1)
            except (ZeroDivisionError, ValueError):
                pass
    # Realized vol (last 20 daily returns annualized).
    if n > 21:
        rets = closes.pct_change().dropna().tail(20)
        try:
            out["realized_vol_20d_ann"] = float(rets.std() * (252 ** 0.5))
        except Exception:  # noqa: BLE001
            pass
    # Drawdown from 60-day high.
    if n > 60:
        roll_max = closes.tail(60).max()
        try:
            out["drawdown_from_60d_high"] = float(closes.iloc[-1] / roll_max - 1)
        except (ZeroDivisionError, ValueError):
            pass
    # Above 50-EMA?
    if n > 50:
        try:
            ema50 = closes.ewm(span=50, adjust=False).mean().iloc[-1]
            out["above_50ema"] = bool(closes.iloc[-1] > ema50)
        except Exception:  # noqa: BLE001
            pass
    return out
