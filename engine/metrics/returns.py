"""Return-related metrics: total return, CAGR, monthly, rolling."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

import numpy as np
import pandas as pd

from ..core.types import EquityPoint


def equity_to_series(equity_curve: list[EquityPoint]) -> pd.Series:
    if not equity_curve:
        return pd.Series(dtype=float)
    idx = pd.to_datetime([e.timestamp for e in equity_curve], utc=True)
    vals = [e.equity for e in equity_curve]
    return pd.Series(vals, index=idx, name="equity").sort_index()


def total_return(equity: pd.Series) -> float:
    if equity.empty or equity.iloc[0] <= 0:
        return 0.0
    return float(equity.iloc[-1] / equity.iloc[0] - 1.0)


def cagr(equity: pd.Series) -> float:
    if equity.empty or len(equity) < 2 or equity.iloc[0] <= 0:
        return 0.0
    days = (equity.index[-1] - equity.index[0]).days
    if days <= 0:
        return 0.0
    years = days / 365.25
    if years <= 0:
        return 0.0
    return float((equity.iloc[-1] / equity.iloc[0]) ** (1 / years) - 1.0)


def daily_returns(equity: pd.Series) -> pd.Series:
    if equity.empty:
        return pd.Series(dtype=float)
    return equity.pct_change().dropna()


def monthly_returns(equity: pd.Series) -> pd.Series:
    if equity.empty:
        return pd.Series(dtype=float)
    monthly = equity.resample("ME").last()
    return monthly.pct_change().dropna()


def rolling_12m_return(equity: pd.Series) -> pd.Series:
    if equity.empty:
        return pd.Series(dtype=float)
    monthly = equity.resample("ME").last()
    return monthly.pct_change(12).dropna()
