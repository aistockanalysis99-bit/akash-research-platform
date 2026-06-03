"""Tests for metrics computation."""
from __future__ import annotations

import numpy as np
import pandas as pd

from engine.core.types import EquityPoint, ExitReason, Trade
from datetime import datetime, timezone

from engine.metrics.returns import cagr, daily_returns, equity_to_series, total_return
from engine.metrics.risk import (
    annualized_vol,
    drawdown_series,
    max_drawdown,
    sharpe_ratio,
    sortino_ratio,
)
from engine.metrics.trade_stats import trade_stats


def _eq_pt(ts, equity):
    return EquityPoint(timestamp=ts, equity=equity, cash=equity, gross_exposure=0, open_positions=0)


def test_total_return_simple():
    pts = [
        _eq_pt(datetime(2024, 1, 1, tzinfo=timezone.utc), 100),
        _eq_pt(datetime(2024, 1, 2, tzinfo=timezone.utc), 110),
    ]
    assert abs(total_return(equity_to_series(pts)) - 0.10) < 1e-9


def test_max_drawdown_known():
    """Equity goes 100 -> 120 -> 90 -> 110: max DD = (90-120)/120 = -25%."""
    eq = pd.Series(
        [100, 110, 120, 100, 90, 100, 110],
        index=pd.date_range("2024-01-01", periods=7, tz="UTC"),
    )
    mdd = max_drawdown(eq)
    assert abs(mdd - (-0.25)) < 1e-9


def test_drawdown_series_is_nonpositive():
    rng = np.random.default_rng(0)
    vals = 100 + np.cumsum(rng.normal(0, 1, 100))
    eq = pd.Series(vals, index=pd.date_range("2024-01-01", periods=100, tz="UTC"))
    dd = drawdown_series(eq)
    assert (dd <= 0).all()


def test_sharpe_zero_for_zero_returns():
    eq = pd.Series([100.0] * 30, index=pd.date_range("2024-01-01", periods=30, tz="UTC"))
    dr = daily_returns(eq)
    assert sharpe_ratio(dr) == 0.0


def test_sharpe_positive_for_positive_drift():
    rng = np.random.default_rng(0)
    log_rets = rng.normal(0.001, 0.01, 252)
    eq_vals = 100 * np.exp(np.cumsum(log_rets))
    eq = pd.Series(eq_vals, index=pd.date_range("2024-01-01", periods=252, tz="UTC"))
    dr = daily_returns(eq)
    assert sharpe_ratio(dr) > 0


def test_sortino_higher_or_equal_to_sharpe_in_skew_up():
    rng = np.random.default_rng(0)
    # Right-skewed returns: more up than down magnitude
    log_rets = np.where(rng.random(500) < 0.5, 0.005, -0.002)
    eq_vals = 100 * np.exp(np.cumsum(log_rets))
    eq = pd.Series(eq_vals, index=pd.date_range("2024-01-01", periods=500, tz="UTC"))
    dr = daily_returns(eq)
    s = sharpe_ratio(dr)
    so = sortino_ratio(dr)
    # When drift is positive and downside is small, Sortino >= Sharpe
    assert so >= s - 1e-6


def test_annualized_vol_positive_for_noisy_returns():
    rng = np.random.default_rng(0)
    rets = pd.Series(rng.normal(0, 0.01, 252))
    assert annualized_vol(rets) > 0


def _make_trade(symbol, pnl, bars=5):
    return Trade(
        symbol=symbol,
        entry_time=datetime(2024, 1, 1, tzinfo=timezone.utc),
        exit_time=datetime(2024, 1, 2, tzinfo=timezone.utc),
        entry_price=100,
        exit_price=100 + pnl / 10,
        qty=10, pnl=pnl, pnl_pct=pnl / 1000,
        exit_reason=ExitReason.STOP, bars_held=bars,
        mae=0, mfe=0, commission_total=1.0,
    )


def test_trade_stats_empty():
    s = trade_stats([])
    assert s["total_trades"] == 0
    assert s["win_rate"] == 0.0


def test_trade_stats_basic():
    trades = [_make_trade("A", 100), _make_trade("B", -50), _make_trade("C", 200)]
    s = trade_stats(trades)
    assert s["total_trades"] == 3
    assert s["winners"] == 2
    assert s["losers"] == 1
    assert abs(s["win_rate"] - 2 / 3) < 1e-9
    assert s["largest_win"] == 200
    assert s["largest_loss"] == -50
    # Profit factor: 300 / 50 = 6.0
    assert abs(s["profit_factor"] - 6.0) < 1e-9
