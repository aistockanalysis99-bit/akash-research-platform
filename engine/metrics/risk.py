"""Risk metrics: volatility, drawdown, Sharpe, Sortino, Calmar/MAR."""
from __future__ import annotations

import numpy as np
import pandas as pd


def annualized_vol(daily_returns: pd.Series, annualization: int = 252) -> float:
    if daily_returns.empty:
        return 0.0
    return float(daily_returns.std() * np.sqrt(annualization))


def drawdown_series(equity: pd.Series) -> pd.Series:
    if equity.empty:
        return pd.Series(dtype=float)
    running_peak = equity.cummax()
    return (equity / running_peak - 1.0)


def max_drawdown(equity: pd.Series) -> float:
    dd = drawdown_series(equity)
    if dd.empty:
        return 0.0
    return float(dd.min())


def max_drawdown_duration_days(equity: pd.Series) -> int:
    """Longest stretch of being below the running peak."""
    if equity.empty:
        return 0
    running_peak = equity.cummax()
    underwater = equity < running_peak
    if not underwater.any():
        return 0
    longest = 0
    current = 0
    last_peak_ts = equity.index[0]
    for ts, is_uw in underwater.items():
        if is_uw:
            current = (ts - last_peak_ts).days
            longest = max(longest, current)
        else:
            last_peak_ts = ts
            current = 0
    return int(longest)


def sharpe_ratio(daily_returns: pd.Series, rf: float = 0.0, annualization: int = 252) -> float:
    if daily_returns.empty:
        return 0.0
    excess = daily_returns - rf / annualization
    sd = excess.std()
    if sd == 0 or np.isnan(sd):
        return 0.0
    return float((excess.mean() / sd) * np.sqrt(annualization))


def sortino_ratio(daily_returns: pd.Series, rf: float = 0.0, annualization: int = 252) -> float:
    if daily_returns.empty:
        return 0.0
    excess = daily_returns - rf / annualization
    downside = excess[excess < 0]
    if downside.empty:
        return 0.0
    dd = downside.std()
    if dd == 0 or np.isnan(dd):
        return 0.0
    return float((excess.mean() / dd) * np.sqrt(annualization))


def calmar_ratio(cagr_value: float, max_dd: float) -> float:
    """CAGR / |MaxDD|. Same as MAR for daily-data backtests."""
    if max_dd == 0:
        return 0.0
    return float(cagr_value / abs(max_dd))


def mar_ratio(cagr_value: float, max_dd: float) -> float:
    return calmar_ratio(cagr_value, max_dd)
