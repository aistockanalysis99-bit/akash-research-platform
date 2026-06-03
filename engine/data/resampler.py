"""Resample daily bars to weekly. Intraday timeframes come directly from FMP."""
from __future__ import annotations

import pandas as pd


def resample_to_weekly(daily_df: pd.DataFrame) -> pd.DataFrame:
    """Aggregate daily bars to weekly Friday-close bars (W-FRI)."""
    if daily_df.empty:
        return daily_df.copy()
    df = daily_df.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.set_index("timestamp").sort_index()
    weekly = df.resample("W-FRI").agg({
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
        "volume": "sum",
        "adj_close": "last",
    }).dropna(how="any")
    weekly = weekly.reset_index()
    return weekly


def get_bars_for_timeframe(daily_or_native_df: pd.DataFrame, timeframe: str) -> pd.DataFrame:
    """Return the right DataFrame for the requested timeframe.

    For 1D and intraday: return as-is (cache stores at native timeframe).
    For 1W: resample from daily.
    """
    if timeframe == "1W":
        return resample_to_weekly(daily_or_native_df)
    return daily_or_native_df.copy()
