"""Tests for momentum signal computation."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from engine.core.types import StrategyParams
from engine.strategy.signal import compute_signal_columns, required_warmup_bars


def test_warmup_grows_with_lookback():
    p1 = StrategyParams(mom_long_len=126)
    p2 = StrategyParams(mom_long_len=252)
    assert required_warmup_bars(p2) > required_warmup_bars(p1)


def test_signal_positive_in_uptrend(synthetic_uptrend_df):
    p = StrategyParams()
    out = compute_signal_columns(synthetic_uptrend_df, p)
    # At end of warmup, momentum score should be positive in an uptrend
    score_after_warmup = out["mom_score"].iloc[200:].dropna()
    assert score_after_warmup.median() > 0


def test_signal_negative_in_downtrend(synthetic_downtrend_df):
    p = StrategyParams()
    out = compute_signal_columns(synthetic_downtrend_df, p)
    score = out["mom_score"].iloc[200:].dropna()
    assert score.median() < 0


def test_bull_state_only_when_above_emas(synthetic_uptrend_df):
    p = StrategyParams()
    out = compute_signal_columns(synthetic_uptrend_df, p)
    bulls = out[out["bull_state"]]
    if len(bulls) > 0:
        # Whenever bull_state is True, fast EMA must exceed slow EMA
        assert (bulls["ema_fast"] > bulls["ema_slow"]).all()
        assert (bulls["mom_score"] > p.entry_threshold).all()


def test_breakout_long_requires_prior_close_below_high():
    """Construct a simple series where exactly one bar should breakout."""
    p = StrategyParams(breakout_len=5)
    closes = pd.Series([100, 100, 100, 100, 100, 100, 105.0])
    df = pd.DataFrame({
        "timestamp": pd.date_range("2024-01-01", periods=len(closes), tz="UTC"),
        "open": closes,
        "high": closes,
        "low": closes - 0.5,
        "close": closes,
        "volume": [1.0] * len(closes),
        "adj_close": closes,
    })
    out = compute_signal_columns(df, p)
    # breakout_long can only be True if prior close was at/below the prior high
    # Last bar: close=105, prior high (max of bars 1..5) = 100 → breakout
    # But mom_score may be NaN due to insufficient warmup; just check the breakout column
    assert out["breakout_long"].iloc[-1] == True  # noqa: E712


def test_signal_no_lookahead(synthetic_uptrend_df):
    """Truncating the series at bar t must give same signal at bar t as the full series."""
    p = StrategyParams()
    full = compute_signal_columns(synthetic_uptrend_df, p)
    cutoff = 250
    truncated = compute_signal_columns(synthetic_uptrend_df.iloc[: cutoff + 1].copy(), p)
    # The score at the cutoff index must match between full and truncated
    full_score = full["mom_score"].iloc[cutoff]
    trunc_score = truncated["mom_score"].iloc[cutoff]
    if pd.isna(full_score) and pd.isna(trunc_score):
        return
    assert abs(full_score - trunc_score) < 1e-9
