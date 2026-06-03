"""Shared fixtures for tests."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest


@pytest.fixture
def synthetic_uptrend_df() -> pd.DataFrame:
    """A 400-bar gentle uptrend with low noise."""
    n = 400
    rng = np.random.default_rng(42)
    drift = np.linspace(0, 0.30, n)  # 30% over the period
    noise = rng.normal(0, 0.005, n)
    log_rets = drift / n + noise
    closes = 100 * np.exp(np.cumsum(log_rets))
    highs = closes * (1 + np.abs(rng.normal(0, 0.002, n)))
    lows = closes * (1 - np.abs(rng.normal(0, 0.002, n)))
    opens = np.concatenate([[100.0], closes[:-1]])
    volumes = rng.integers(1_000_000, 5_000_000, n).astype(float)
    timestamps = pd.date_range(start="2024-01-01", periods=n, freq="B", tz="UTC")
    return pd.DataFrame({
        "timestamp": timestamps,
        "open": opens,
        "high": highs,
        "low": lows,
        "close": closes,
        "volume": volumes,
        "adj_close": closes,
    })


@pytest.fixture
def synthetic_downtrend_df() -> pd.DataFrame:
    n = 400
    rng = np.random.default_rng(7)
    drift = np.linspace(0, -0.30, n)
    noise = rng.normal(0, 0.005, n)
    log_rets = drift / n + noise
    closes = 100 * np.exp(np.cumsum(log_rets))
    highs = closes * (1 + np.abs(rng.normal(0, 0.002, n)))
    lows = closes * (1 - np.abs(rng.normal(0, 0.002, n)))
    opens = np.concatenate([[100.0], closes[:-1]])
    volumes = rng.integers(1_000_000, 5_000_000, n).astype(float)
    timestamps = pd.date_range(start="2024-01-01", periods=n, freq="B", tz="UTC")
    return pd.DataFrame({
        "timestamp": timestamps,
        "open": opens, "high": highs, "low": lows, "close": closes,
        "volume": volumes, "adj_close": closes,
    })


@pytest.fixture
def synthetic_sideways_df() -> pd.DataFrame:
    n = 400
    rng = np.random.default_rng(13)
    log_rets = rng.normal(0, 0.005, n)
    closes = 100 * np.exp(np.cumsum(log_rets))
    highs = closes * (1 + np.abs(rng.normal(0, 0.002, n)))
    lows = closes * (1 - np.abs(rng.normal(0, 0.002, n)))
    opens = np.concatenate([[100.0], closes[:-1]])
    volumes = rng.integers(1_000_000, 5_000_000, n).astype(float)
    timestamps = pd.date_range(start="2024-01-01", periods=n, freq="B", tz="UTC")
    return pd.DataFrame({
        "timestamp": timestamps,
        "open": opens, "high": highs, "low": lows, "close": closes,
        "volume": volumes, "adj_close": closes,
    })
