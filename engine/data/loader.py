"""Load cached bars for a backtest, with timeframe handling and date filtering."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

import pandas as pd

from ..logging_setup import get_logger
from .cache import load_bars
from .resampler import get_bars_for_timeframe

log = get_logger("data.loader")


def load_for_backtest(
    symbol: str,
    timeframe: str,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
) -> pd.DataFrame:
    """Load bars for one symbol, in the requested timeframe, filtered by dates.

    Cache stores either daily (for 1D / 1W) or native intraday timeframes.
    """
    if timeframe == "1W":
        df = load_bars(symbol, "1D")
    else:
        df = load_bars(symbol, timeframe)

    if df.empty:
        return df

    df = get_bars_for_timeframe(df, timeframe)

    if start is not None:
        start_utc = pd.Timestamp(start).tz_convert("UTC") if pd.Timestamp(start).tz is not None else pd.Timestamp(start, tz="UTC")
        df = df[df["timestamp"] >= start_utc]
    if end is not None:
        end_utc = pd.Timestamp(end).tz_convert("UTC") if pd.Timestamp(end).tz is not None else pd.Timestamp(end, tz="UTC")
        df = df[df["timestamp"] <= end_utc]

    return df.reset_index(drop=True)


def load_universe_panel(
    symbols: list[str],
    timeframe: str,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
) -> dict[str, pd.DataFrame]:
    """Load all symbols. Returns dict[symbol, DataFrame]. Symbols with no cache are skipped."""
    out: dict[str, pd.DataFrame] = {}
    for s in symbols:
        df = load_for_backtest(s, timeframe, start, end)
        if df.empty:
            log.warning("No cached data for %s @ %s", s, timeframe)
            continue
        out[s] = df
    return out
