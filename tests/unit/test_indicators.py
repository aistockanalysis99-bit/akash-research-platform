"""Tests for indicator helpers (EMA, ATR, rolling extremes, vol, skip-adjusted return)."""
from __future__ import annotations

import numpy as np
import pandas as pd

from engine.strategy.indicators import (
    atr,
    ema,
    realized_vol,
    rolling_highest,
    rolling_lowest,
    skip_adjusted_return,
    true_range,
)


def test_ema_first_value_equals_first_close():
    s = pd.Series([10.0, 11, 12, 13, 14, 15])
    e = ema(s, 3)
    assert e.iloc[0] == 10.0


def test_ema_converges_to_constant():
    s = pd.Series([100.0] * 50)
    e = ema(s, 10)
    assert abs(e.iloc[-1] - 100.0) < 1e-9


def test_true_range_handles_gap():
    df = pd.DataFrame({
        "high": [10, 12, 14],
        "low": [9, 11, 13],
        "close": [9.5, 11.5, 13.5],
    })
    tr = true_range(df)
    # First row: prev_close NaN -> TR is high-low only = 1
    assert tr.iloc[0] == 1
    # Second row: max(12-11, |12-9.5|, |11-9.5|) = max(1, 2.5, 1.5) = 2.5
    assert abs(tr.iloc[1] - 2.5) < 1e-9


def test_atr_positive_for_volatile_data():
    n = 100
    rng = np.random.default_rng(0)
    closes = 100 + np.cumsum(rng.normal(0, 1, n))
    df = pd.DataFrame({
        "high": closes + 1,
        "low": closes - 1,
        "close": closes,
    })
    a = atr(df, 14)
    valid = a.dropna()
    assert (valid > 0).all()


def test_rolling_highest_excludes_current_bar():
    s = pd.Series([1, 2, 3, 4, 5, 6])
    rh = rolling_highest(s, 3)
    # At index 3, prior 3 bars are 1, 2, 3 -> max is 3
    assert rh.iloc[3] == 3
    # At index 5, prior 3 bars are 3, 4, 5 -> max is 5
    assert rh.iloc[5] == 5


def test_rolling_lowest_excludes_current_bar():
    s = pd.Series([10, 9, 8, 7, 6, 5])
    rl = rolling_lowest(s, 3)
    assert rl.iloc[3] == 8
    assert rl.iloc[5] == 6


def test_skip_adjusted_return_basic():
    # Simple geometric series
    closes = pd.Series([100.0, 110.0, 121.0, 133.1, 146.41, 161.05])
    # Lookback 2, skip 0: r = P[t] / P[t-2] - 1 = (closes_now / closes_2bars_ago) - 1
    r = skip_adjusted_return(closes, lookback=2, skip=0)
    # At index 2: 121/100 - 1 = 0.21
    assert abs(r.iloc[2] - 0.21) < 1e-9


def test_realized_vol_higher_for_noisier_series():
    n = 200
    rng = np.random.default_rng(1)
    quiet = pd.Series(100 + np.cumsum(rng.normal(0, 0.001, n)))
    loud = pd.Series(100 + np.cumsum(rng.normal(0, 0.05, n)))
    rv_quiet = realized_vol(quiet, 20).dropna()
    rv_loud = realized_vol(loud, 20).dropna()
    assert rv_loud.mean() > rv_quiet.mean()
