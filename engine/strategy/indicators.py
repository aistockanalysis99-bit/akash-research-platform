"""Pure-numpy/pandas indicator helpers. No look-ahead, all causal."""
from __future__ import annotations

import numpy as np
import pandas as pd


def ema(series: pd.Series, length: int) -> pd.Series:
    """Standard EMA (adjust=False so it matches Pine/TA-Lib behavior)."""
    return series.ewm(span=length, adjust=False).mean()


def true_range(df: pd.DataFrame) -> pd.Series:
    """Wilder true range from OHLC."""
    prev_close = df["close"].shift(1)
    tr1 = df["high"] - df["low"]
    tr2 = (df["high"] - prev_close).abs()
    tr3 = (df["low"] - prev_close).abs()
    return pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)


def atr(df: pd.DataFrame, length: int = 20) -> pd.Series:
    """ATR using EMA-of-true-range (RMA-style with span=length)."""
    tr = true_range(df)
    return tr.ewm(alpha=1.0 / length, adjust=False).mean()


def rolling_highest(series: pd.Series, length: int) -> pd.Series:
    """Highest of the prior `length` bars (excluding current bar)."""
    return series.shift(1).rolling(window=length, min_periods=length).max()


def rolling_lowest(series: pd.Series, length: int) -> pd.Series:
    return series.shift(1).rolling(window=length, min_periods=length).min()


def realized_vol(close: pd.Series, lookback: int = 20, annualization: int = 252) -> pd.Series:
    """Annualized realized vol from log returns."""
    log_ret = np.log(close / close.shift(1))
    return log_ret.rolling(window=lookback, min_periods=lookback).std() * np.sqrt(annualization)


def skip_adjusted_return(close: pd.Series, lookback: int, skip: int) -> pd.Series:
    """r(L,s) = P[t-s] / P[t-L-s] - 1, computed safely with NaN."""
    p_now = close.shift(skip)
    p_then = close.shift(lookback + skip)
    return p_now / p_then - 1.0
