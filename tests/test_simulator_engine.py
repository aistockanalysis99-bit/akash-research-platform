"""Unit & Integration Tests for Point-in-Time Simulator & Forward Evaluator.

Verifies:
  1. Constraint 1: Zero lookahead leakage (identical results to live scanner on Date T).
  2. Constraint 2: Stop-loss takes strict priority over target reversion if both occur on the same day.
  3. Evaluator accurately determines WIN, LOSS, and NEUTRAL outcomes.
  4. Integration scan on real cached 5-year Parquet dataset.
"""

from __future__ import annotations

import math
from datetime import datetime
from pathlib import Path
from typing import Tuple

import numpy as np
import pandas as pd
import pytest

from engine.simulator_engine import (
    DayBatchScorecard,
    ForwardEvaluationResult,
    ForwardOutcomeEvaluator,
    PointInTimeEngine,
    PointInTimeSetup,
)


def create_synthetic_market_data(
    num_days: int = 180,
    seed: int = 42,
    base_date: str = "2024-01-02",
) -> Tuple[pd.DataFrame, pd.Timestamp]:
    """Generate deterministic synthetic 2-stock cointegrated market data.
    
    Generates 90 days of cointegrated history (t <= T), then 90 days of future bars (t > T).
    """
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range(start=base_date, periods=num_days)
    target_idx = 90
    target_date = dates[target_idx - 1]

    # Common random walk
    common_trend = 100.0 + np.cumsum(rng.normal(0.05, 0.8, num_days))

    # Stationary Ornstein-Uhlenbeck spread component
    spread = np.zeros(num_days)
    spread[0] = 0.0
    theta = 0.15  # mean reversion speed
    for i in range(1, num_days):
        spread[i] = spread[i - 1] - theta * spread[i - 1] + rng.normal(0, 0.4)

    # Force a calibrated dislocation at target_idx - 1 (Date T)
    # Target entry around z = -2.3 (active setup: |z| >= 2.0, well within stop barrier of -3.5)
    spread[target_idx - 1] = -1.65

    beta = 1.2
    pb = common_trend
    pa = 10.0 + beta * pb + spread

    # Create MultiIndex DataFrame matching universe Parquet schema
    cols = pd.MultiIndex.from_tuples([
        ("Adj Close", "SYM_A"),
        ("Adj Close", "SYM_B"),
        ("Close", "SYM_A"),
        ("Close", "SYM_B"),
        ("High", "SYM_A"),
        ("High", "SYM_B"),
        ("Low", "SYM_A"),
        ("Low", "SYM_B"),
        ("Open", "SYM_A"),
        ("Open", "SYM_B"),
        ("Volume", "SYM_A"),
        ("Volume", "SYM_B"),
    ])

    data = np.column_stack([
        pa, pb,                      # Adj Close
        pa, pb,                      # Close
        pa + 0.5, pb + 0.5,          # High
        pa - 0.5, pb - 0.5,          # Low
        pa + 0.1, pb + 0.1,          # Open
        np.full(num_days, 1000000),  # Volume A
        np.full(num_days, 1000000),  # Volume B
    ])

    df = pd.DataFrame(data, index=dates, columns=cols)
    return df, target_date


# =========================================================================== #
# Test 1: Constraint 1 - Zero Lookahead Leakage
# =========================================================================== #
def test_temporal_slicing_zero_lookahead():
    """Verify that history sliced to Date T contains ZERO data timestamped after T."""
    df, target_date = create_synthetic_market_data(num_days=180)
    engine = PointInTimeEngine(df=df)

    history = engine.slice_history(target_date)
    assert not history.empty
    assert history.index.max() <= target_date
    assert len(history) == 90
    assert len(history) < len(df)


def test_bit_for_bit_identical_pit_calculation():
    """Constraint 1: PIT calculation on full 180-day dataset sliced at T must yield
    identical results to running on a 90-day dataset that physically ends at T.
    """
    df_full, target_date = create_synthetic_market_data(num_days=180)
    df_truncated = df_full.loc[:target_date].copy()

    engine_full = PointInTimeEngine(df=df_full)
    engine_trunc = PointInTimeEngine(df=df_truncated)

    setup_full = engine_full.calculate_pair_pit("SYM_A", "SYM_B", target_date=target_date)
    setup_trunc = engine_trunc.calculate_pair_pit("SYM_A", "SYM_B", target_date=target_date)

    assert setup_full is not None
    assert setup_trunc is not None

    # Verify all statistical metrics match exactly
    assert math.isclose(setup_full.hedge_ratio, setup_trunc.hedge_ratio, abs_tol=1e-6)
    assert math.isclose(setup_full.alpha, setup_trunc.alpha, abs_tol=1e-6)
    assert math.isclose(setup_full.correlation, setup_trunc.correlation, abs_tol=1e-6)
    assert math.isclose(setup_full.current_z_score, setup_trunc.current_z_score, abs_tol=1e-6)
    assert math.isclose(setup_full.current_spread, setup_trunc.current_spread, abs_tol=1e-6)
    assert math.isclose(setup_full.spread_mean, setup_trunc.spread_mean, abs_tol=1e-6)
    assert math.isclose(setup_full.spread_std, setup_trunc.spread_std, abs_tol=1e-6)
    assert math.isclose(setup_full.adf_pvalue, setup_trunc.adf_pvalue, abs_tol=1e-6)
    assert setup_full.direction == setup_trunc.direction
    assert setup_full.composite_score == setup_trunc.composite_score
    assert setup_full.is_setup == setup_trunc.is_setup


# =========================================================================== #
# Test 2: Forward Outcome Evaluator - Target Mean Reversion (WIN)
# =========================================================================== #
def test_forward_evaluator_win_mean_reversion():
    """Verify that a setup whose spread reverts to z = 0 prior to stop loss is marked WIN."""
    df, target_date = create_synthetic_market_data(num_days=120)
    engine = PointInTimeEngine(df=df)
    setup = engine.calculate_pair_pit("SYM_A", "SYM_B", target_date=target_date)
    assert setup is not None

    # Inject clean mean reversion in future days (t > T)
    # Day 1: z = -1.5, Day 2: z = -0.8, Day 3: z = 0.1 (Target hit)
    future_dates = df.index[df.index > target_date]
    beta = setup.hedge_ratio
    mu = setup.spread_mean
    sigma = setup.spread_std

    # Construct clean reversion path
    for i, target_z in enumerate([-1.5, -0.8, 0.1]):
        d = future_dates[i]
        target_s = mu + target_z * sigma
        pb_val = float(df.loc[d, ("Adj Close", "SYM_B")])
        pa_val = target_s + beta * pb_val
        for col_name in ["Adj Close", "Close", "High", "Low", "Open"]:
            df.loc[d, (col_name, "SYM_A")] = pa_val

    evaluator = ForwardOutcomeEvaluator(df=df)
    result = evaluator.evaluate_setup(setup, max_horizon_days=30, use_intraday_extremes=False)

    assert result.outcome == "WIN"
    assert result.exit_days_held == 3
    assert result.exit_date == future_dates[2].strftime("%Y-%m-%d")
    assert result.realized_pnl_pct > 0.0


def test_forward_evaluator_win_80pct_reversion():
    """Verify that achieving 80% reversion towards the mean also triggers a WIN."""
    df, target_date = create_synthetic_market_data(num_days=120)
    engine = PointInTimeEngine(df=df)
    setup = engine.calculate_pair_pit("SYM_A", "SYM_B", target_date=target_date)
    assert setup is not None

    future_dates = df.index[df.index > target_date]
    beta = setup.hedge_ratio
    mu = setup.spread_mean
    sigma = setup.spread_std
    z0 = setup.current_z_score

    # Revert to 82% of initial dislocation: z = z0 * 0.18
    target_z = z0 * 0.18
    d = future_dates[1]
    target_s = mu + target_z * sigma
    pb_val = float(df.loc[d, ("Adj Close", "SYM_B")])
    pa_val = target_s + beta * pb_val
    for col_name in ["Adj Close", "Close", "High", "Low", "Open"]:
        df.loc[d, (col_name, "SYM_A")] = pa_val

    evaluator = ForwardOutcomeEvaluator(df=df)
    result = evaluator.evaluate_setup(setup, max_horizon_days=30, use_intraday_extremes=False)

    assert result.outcome == "WIN"
    assert result.exit_days_held in (1, 2)
    assert result.realized_pnl_pct > 0.0


# =========================================================================== #
# Test 3: Forward Outcome Evaluator - Stop Loss Hit (LOSS)
# =========================================================================== #
def test_forward_evaluator_loss_stop_hit():
    """Verify that spread expansion to |z| >= 3.5 prior to reversion is marked LOSS."""
    df, target_date = create_synthetic_market_data(num_days=120)
    engine = PointInTimeEngine(df=df)
    setup = engine.calculate_pair_pit("SYM_A", "SYM_B", target_date=target_date)
    assert setup is not None

    future_dates = df.index[df.index > target_date]
    beta = setup.hedge_ratio
    mu = setup.spread_mean
    sigma = setup.spread_std

    # Day 1: worsens to z = -2.8; Day 2: blows out to z = -3.8 (Stop Loss triggered)
    for i, target_z in enumerate([-2.8, -3.8]):
        d = future_dates[i]
        target_s = mu + target_z * sigma
        pb_val = float(df.loc[d, ("Adj Close", "SYM_B")])
        pa_val = target_s + beta * pb_val
        for col_name in ["Adj Close", "Close", "High", "Low", "Open"]:
            df.loc[d, (col_name, "SYM_A")] = pa_val

    evaluator = ForwardOutcomeEvaluator(df=df)
    result = evaluator.evaluate_setup(setup, max_horizon_days=30, use_intraday_extremes=False)

    assert result.outcome == "LOSS"
    assert result.exit_days_held == 2
    assert result.exit_date == future_dates[1].strftime("%Y-%m-%d")
    assert result.realized_pnl_pct < 0.0


# =========================================================================== #
# Test 4: Constraint 2 - Stop-Loss Priority on Same Day
# =========================================================================== #
def test_stop_loss_takes_strict_priority_on_same_day():
    """Constraint 2 Verification:
    If on the SAME future day both stop-loss (|z| >= 3.5) and target reversion (z = 0)
    occur (e.g. wide intraday range), STOP-LOSS MUST TAKE PRECEDENCE (outcome = LOSS).
    """
    df, target_date = create_synthetic_market_data(num_days=120)
    engine = PointInTimeEngine(df=df)
    setup = engine.calculate_pair_pit("SYM_A", "SYM_B", target_date=target_date)
    assert setup is not None

    future_dates = df.index[df.index > target_date]
    conflict_day = future_dates[0]

    beta = setup.hedge_ratio
    mu = setup.spread_mean
    sigma = setup.spread_std

    # On conflict_day, create an extreme intraday bar:
    # High price gives target reversion (z >= 0.0)
    # Low price gives stop loss breach (z <= -3.6)
    pb_val = 100.0
    s_target = mu + 0.2 * sigma       # z = +0.2 (Target hit)
    s_stop = mu - 3.8 * sigma         # z = -3.8 (Stop loss hit)

    df.loc[conflict_day, ("Adj Close", "SYM_B")] = pb_val
    df.loc[conflict_day, ("High", "SYM_B")] = pb_val
    df.loc[conflict_day, ("Low", "SYM_B")] = pb_val

    # Stock A High allows spread to touch s_target; Low causes spread to touch s_stop
    df.loc[conflict_day, ("High", "SYM_A")] = s_target + beta * pb_val
    df.loc[conflict_day, ("Low", "SYM_A")] = s_stop + beta * pb_val
    df.loc[conflict_day, ("Adj Close", "SYM_A")] = s_target + beta * pb_val  # Close was positive!

    evaluator = ForwardOutcomeEvaluator(df=df)
    result = evaluator.evaluate_setup(setup, max_horizon_days=30, use_intraday_extremes=True)

    # Constraint 2 Assertion: Stop loss must win over target reversion on same day
    assert result.outcome == "LOSS", (
        f"Constraint 2 Failed: Outcome was {result.outcome} instead of LOSS. "
        "Stop loss must override target on same-day conflict."
    )
    assert "Stop Loss" in result.status_reason
    assert result.exit_days_held == 1
    # CR-01 Assertion: Stopped-out trade must realize a negative return
    assert result.realized_pnl_pct < 0.0, f"Expected negative PnL on stop-out, got {result.realized_pnl_pct}%"


# =========================================================================== #
# Test 5: Forward Outcome Evaluator - Neutral / Horizon Expiry
# =========================================================================== #
def test_forward_evaluator_neutral_horizon_expiry():
    """Verify that a trade that neither hits target nor stop is marked NEUTRAL."""
    df, target_date = create_synthetic_market_data(num_days=120)
    engine = PointInTimeEngine(df=df)
    setup = engine.calculate_pair_pit("SYM_A", "SYM_B", target_date=target_date)
    assert setup is not None

    future_dates = df.index[df.index > target_date]
    beta = setup.hedge_ratio
    mu = setup.spread_mean
    sigma = setup.spread_std

    # Keep spread hovering around z = -1.8 for 5 days (between target and stop)
    for i in range(5):
        d = future_dates[i]
        target_s = mu - 1.8 * sigma
        pb_val = float(df.loc[d, ("Adj Close", "SYM_B")])
        pa_val = target_s + beta * pb_val
        for col_name in ["Adj Close", "Close", "High", "Low", "Open"]:
            df.loc[d, (col_name, "SYM_A")] = pa_val

    evaluator = ForwardOutcomeEvaluator(df=df)
    result = evaluator.evaluate_setup(setup, max_horizon_days=5, use_intraday_extremes=False)

    assert result.outcome == "NEUTRAL"
    assert result.exit_days_held == 5
    assert "expired" in result.status_reason.lower()


# =========================================================================== #
# Test 6: Day Batch Scorecard Calculation
# =========================================================================== #
def test_day_batch_scorecard_aggregation():
    """Verify that evaluate_batch computes correct aggregate metrics."""
    df, target_date = create_synthetic_market_data(num_days=120)
    engine = PointInTimeEngine(df=df)
    setup1 = engine.calculate_pair_pit("SYM_A", "SYM_B", target_date=target_date)
    assert setup1 is not None

    # Create dummy setup 2
    setup2 = PointInTimeSetup(
        ticker_a="SYM_B",
        ticker_b="SYM_A",
        pair_name="SYM_B/SYM_A",
        target_date=str(target_date.date()),
        direction="SHORT_A_LONG_B",
        hedge_ratio=0.8,
        alpha=0.0,
        r_squared=0.85,
        correlation=0.92,
        current_z_score=2.3,
        abs_z_score=2.3,
        current_spread=5.0,
        spread_mean=2.0,
        spread_std=1.3,
        target_spread_mean=2.0,
        target_spread_80pct=2.6,
        stop_loss_spread=6.55,
        price_a_entry=100.0,
        price_b_entry=120.0,
        adf_tstat=-3.5,
        adf_pvalue=0.01,
        half_life_days=10.0,
        zero_crossings=15,
        relative_spread_vol_pct=1.3,
        spread_tier="Ultra Tight",
        composite_score=85.0,
        is_setup=True,
        window_bars=90,
    )

    evaluator = ForwardOutcomeEvaluator(df=df)
    scorecard = evaluator.evaluate_batch([setup1, setup2], max_horizon_days=20)

    assert isinstance(scorecard, DayBatchScorecard)
    assert scorecard.total_setups == 2
    assert scorecard.total_setups == (scorecard.win_count + scorecard.loss_count + scorecard.neutral_count)
    assert 0.0 <= scorecard.win_rate_pct <= 100.0


# =========================================================================== #
# Test 7: Integration with Live Cached 5-Year Parquet Dataset
# =========================================================================== #
def test_live_parquet_pit_simulation():
    """Verify integration on live cached universe_5y_daily.parquet."""
    parquet_path = Path("data_cache/universe_5y_daily.parquet")
    if not parquet_path.exists():
        pytest.skip("universe_5y_daily.parquet not found; skipping integration test.")

    engine = PointInTimeEngine(parquet_path=parquet_path)
    dates = engine.get_trading_dates()
    assert len(dates) >= 1000

    # Test Date in middle of 5-year history
    test_date = "2024-03-15"
    history = engine.slice_history(test_date)
    assert not history.empty
    assert history.index.max() <= pd.Timestamp(test_date)

    # Scan for setups on this date
    setups = engine.scan_date(test_date, top_n=5, only_active_setups=False)
    assert len(setups) > 0

    first_setup = setups[0]
    assert first_setup.target_date == test_date
    assert first_setup.window_bars >= 30

    # Evaluate forward outcome on live data
    evaluator = ForwardOutcomeEvaluator(parquet_path=parquet_path)
    result = evaluator.evaluate_setup(first_setup, max_horizon_days=30)
    assert result.outcome in ("WIN", "LOSS", "NEUTRAL")
    assert result.exit_days_held > 0
    assert len(result.path) > 0


# =========================================================================== #
# Test 8: Short Spread (Z >= +2.0) Forward Reversion & Stop Loss
# =========================================================================== #
def test_forward_evaluator_short_spread_win():
    """Verify that a SHORT_A_LONG_B setup (entered at z >= 2.0) resolves to WIN on downward reversion."""
    df, target_date = create_synthetic_market_data(num_days=120)
    future_dates = df.index[df.index > target_date]

    # Force a positive dislocation at target date: z ~ +2.5
    engine = PointInTimeEngine(df=df)
    setup = engine.calculate_pair_pit("SYM_A", "SYM_B", target_date=target_date)
    assert setup is not None

    # Construct positive dislocation setup manually or test forward evaluator
    short_setup = PointInTimeSetup(
        ticker_a="SYM_A",
        ticker_b="SYM_B",
        pair_name="SYM_A/SYM_B",
        target_date=str(target_date.date()),
        direction="SHORT_A_LONG_B",
        hedge_ratio=setup.hedge_ratio,
        alpha=setup.alpha,
        r_squared=setup.r_squared,
        correlation=setup.correlation,
        current_z_score=2.5,
        abs_z_score=2.5,
        current_spread=setup.spread_mean + 2.5 * setup.spread_std,
        spread_mean=setup.spread_mean,
        spread_std=setup.spread_std,
        target_spread_mean=setup.spread_mean,
        target_spread_80pct=setup.spread_mean + 0.5 * setup.spread_std,
        stop_loss_spread=setup.spread_mean + 3.5 * setup.spread_std,
        price_a_entry=setup.price_a_entry,
        price_b_entry=setup.price_b_entry,
        adf_tstat=setup.adf_tstat,
        adf_pvalue=setup.adf_pvalue,
        half_life_days=setup.half_life_days,
        zero_crossings=setup.zero_crossings,
        relative_spread_vol_pct=setup.relative_spread_vol_pct,
        spread_tier=setup.spread_tier,
        composite_score=85.0,
        is_setup=True,
        window_bars=setup.window_bars,
    )

    # Future: spread falls towards mean (z = 0.1 on Day 2)
    beta = short_setup.hedge_ratio
    mu = short_setup.spread_mean
    sigma = short_setup.spread_std

    for i, target_z in enumerate([1.5, 0.1]):
        d = future_dates[i]
        target_s = mu + target_z * sigma
        pb_val = float(df.loc[d, ("Adj Close", "SYM_B")])
        pa_val = target_s + beta * pb_val
        for col_name in ["Adj Close", "Close", "High", "Low", "Open"]:
            df.loc[d, (col_name, "SYM_A")] = pa_val

    evaluator = ForwardOutcomeEvaluator(df=df)
    res = evaluator.evaluate_setup(short_setup, max_horizon_days=30, use_intraday_extremes=False)

    assert res.outcome == "WIN"
    assert res.realized_pnl_pct > 0.0
    assert res.exit_days_held in (1, 2)


# =========================================================================== #
# Test 9: RFC 8259 JSON Compliance (No Infinity)
# =========================================================================== #
def test_rfc_json_serialization():
    """Verify setup and scorecard serialize to valid RFC 8259 JSON with zero non-standard tokens."""
    import json
    df, target_date = create_synthetic_market_data(num_days=120)
    engine = PointInTimeEngine(df=df)
    setup = engine.calculate_pair_pit("SYM_A", "SYM_B", target_date=target_date)
    assert setup is not None

    setup_dict = setup.to_dict()
    # Must serialize with allow_nan=False without raising ValueError
    serialized = json.dumps(setup_dict, allow_nan=False)
    assert "Infinity" not in serialized
    assert "NaN" not in serialized

    evaluator = ForwardOutcomeEvaluator(df=df)
    res = evaluator.evaluate_setup(setup)
    res_serialized = json.dumps(res.to_dict(), allow_nan=False)
    assert "Infinity" not in res_serialized
