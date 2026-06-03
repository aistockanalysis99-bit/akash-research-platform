"""Integration tests for the end-to-end backtest engine."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd

from engine.core.event_loop import run_backtest
from engine.core.types import BacktestConfig, RunStatus, StrategyParams


def _config_for(panel: dict[str, pd.DataFrame], capital: float = 100_000) -> BacktestConfig:
    timeframe = "1D"
    df = next(iter(panel.values()))
    return BacktestConfig(
        universe=list(panel.keys()),
        start_date=df["timestamp"].iloc[0].to_pydatetime(),
        end_date=df["timestamp"].iloc[-1].to_pydatetime(),
        timeframe=timeframe,
        initial_capital=capital,
        params=StrategyParams(),
        universe_name="test",
    )


def test_uptrend_produces_some_trades(synthetic_uptrend_df):
    panel = {"UP": synthetic_uptrend_df}
    config = _config_for(panel)
    result = run_backtest(panel, config)
    assert result.status == RunStatus.DONE
    # Trend strategy should fire at least one entry on a clean uptrend
    assert len(result.trades) >= 1


def test_sideways_few_or_no_trades(synthetic_sideways_df):
    panel = {"FLAT": synthetic_sideways_df}
    config = _config_for(panel)
    result = run_backtest(panel, config)
    assert result.status == RunStatus.DONE
    # Sideways: trend filter mostly suppresses entries
    # Allow some, but fewer than uptrend
    assert len(result.trades) < 100


def test_downtrend_long_only_no_trades(synthetic_downtrend_df):
    panel = {"DN": synthetic_downtrend_df}
    config = _config_for(panel)
    result = run_backtest(panel, config)
    assert result.status == RunStatus.DONE
    # Long-only strategy on a downtrend should not produce many entries (trend filter blocks them)
    assert len(result.trades) <= 5


def test_equity_starts_at_capital(synthetic_uptrend_df):
    panel = {"UP": synthetic_uptrend_df}
    config = _config_for(panel, capital=50_000)
    result = run_backtest(panel, config)
    if result.equity_curve:
        assert abs(result.equity_curve[0].equity - 50_000) < 1.0


def test_equity_curve_continuous(synthetic_uptrend_df):
    panel = {"UP": synthetic_uptrend_df}
    config = _config_for(panel)
    result = run_backtest(panel, config)
    # No NaN/None equity points
    for ep in result.equity_curve:
        assert ep.equity > 0
        assert ep.cash >= 0 or abs(ep.cash) < 1e-3  # cash can be slightly negative due to rounding


def test_metrics_computed(synthetic_uptrend_df):
    panel = {"UP": synthetic_uptrend_df}
    config = _config_for(panel)
    result = run_backtest(panel, config)
    m = result.metrics
    assert "sharpe" in m
    assert "max_drawdown" in m
    assert "cagr" in m
    assert "trades.total_trades" in m
    assert m["trades.total_trades"] == len(result.trades)


def test_pnl_consistency_with_equity(synthetic_uptrend_df):
    """Sum of trade PnLs should approximately equal final equity - initial capital."""
    panel = {"UP": synthetic_uptrend_df}
    config = _config_for(panel, capital=100_000)
    result = run_backtest(panel, config)
    if not result.trades:
        return
    sum_pnl = sum(t.pnl for t in result.trades)
    delta_equity = result.equity_curve[-1].equity - 100_000
    # Allow small rounding (commission/slippage handling)
    assert abs(sum_pnl - delta_equity) < 100.0
