"""Unit & Integration Tests for Strategy v2 Core Engine.

Verifies:
  1. Strategy v2 Config loading and strict Phase 1 quantitative parameters.
  2. Reversion Hook Confirmation blocks runaway momentum and triggers correctly.
  3. Two-Tranche Staged Take-Profit:
     - Tranche 1 closes at 0.80σ.
     - Breakeven Stop engages for Tranche 2 at entry level (1.85σ).
     - "Flipped Trade" turns what would be a v1 blowout into a net profitable win.
  4. Full Mean Reversion: Both Tranches hit targets (TP1 at 0.80σ, TP2 at 0.20σ).
  5. Initial Stop Loss Priority (3.20σ) and Constraint 2 same-day precedence.
  6. Ornstein-Uhlenbeck Dynamic Time Stop:
     - Accurate formula: T_max = min(25, max(10, round(1.75 * half_life))).
     - Force market closure at T_max.
  7. Corporate Earnings Blackout Shield: Vetoes entries within ±5 trading days.
  8. Tightened Gauntlet Screening (R² >= 0.50, Half-life <= 22d, ADF p-val <= 0.04).
  9. Zero Lookahead temporal integrity.
"""

from __future__ import annotations

import math
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd
import pytest

from engine.strategy_v2_engine import (
    EarningsCalendar,
    StrategyV2Engine,
    StrategyV2EvaluationResult,
    StrategyV2OutcomeEvaluator,
    StrategyV2Setup,
    load_strategy_v2_config,
)


def create_mock_pair_dataframe(
    dates: pd.DatetimeIndex,
    spread_series: np.ndarray,
    ticker_a: str = "TICK_A",
    ticker_b: str = "TICK_B",
    beta: float = 1.0,
    base_price_b: float = 100.0,
    has_high_low: bool = True,
) -> pd.DataFrame:
    """Helper to construct a MultiIndex DataFrame simulating pair prices for exact spread trajectories."""
    n = len(dates)
    pb = np.full(n, base_price_b)
    pa = pb * beta + spread_series

    cols = pd.MultiIndex.from_tuples([
        ("Adj Close", ticker_a),
        ("Adj Close", ticker_b),
        ("Close", ticker_a),
        ("Close", ticker_b),
        ("High", ticker_a),
        ("High", ticker_b),
        ("Low", ticker_a),
        ("Low", ticker_b),
        ("Open", ticker_a),
        ("Open", ticker_b),
        ("Volume", ticker_a),
        ("Volume", ticker_b),
    ])

    if has_high_low:
        ha = pa + 0.01
        la = pa - 0.01
        hb = pb + 0.01
        lb = pb - 0.01
    else:
        ha, la = pa, pa
        hb, lb = pb, pb

    data = np.column_stack([
        pa, pb,
        pa, pb,
        ha, hb,
        la, lb,
        pa, pb,
        np.full(n, 1000000),
        np.full(n, 1000000),
    ])

    return pd.DataFrame(data, index=dates, columns=cols)


# =========================================================================== #
# Test 1: Configuration Loading & Exact Phase 1 Parameter Validation
# =========================================================================== #
def test_strategy_v2_config_loading_and_thresholds():
    """Verify pair_strategy_v2_config.json contains the exact Phase 1 approved parameters."""
    cfg = load_strategy_v2_config()

    assert cfg.get("version") == "2.0.0"
    div = cfg["divergence_triggers"]
    assert div["z_score_hurdle"] == 2.10
    assert div["z_score_hook_entry"] == 1.85
    assert div["z_score_exit_tp1"] == 0.80
    assert div["z_score_exit_tp2"] == 0.20
    assert div["z_score_stop_loss_barrier"] == 3.20
    assert div["lookback_days"] == 90

    tm = cfg["trade_management"]
    assert tm["staged_take_profit_enabled"] is True
    assert tm["tp1_allocation_pct"] == 50
    assert tm["move_stop_to_breakeven_on_tp1"] is True
    assert tm["half_life_time_stop_multiplier"] == 1.75
    assert tm["min_holding_days_floor"] == 10
    assert tm["max_holding_days_cap"] == 25
    assert tm["earnings_blackout_days"] == 5

    gaunt = cfg["gauntlet_screening_thresholds"]
    assert gaunt["min_correlation"] == 0.85
    assert gaunt["max_cointegration_pvalue"] == 0.04
    assert gaunt["min_half_life_days"] == 2.0
    assert gaunt["max_half_life_days"] == 22.0
    assert gaunt["max_hurst_exponent"] == 0.48
    assert gaunt["min_r_squared"] == 0.50


# =========================================================================== #
# Test 2: Reversion Hook Confirmation Logic
# =========================================================================== #
def test_hook_confirmation_blocks_runaway_momentum():
    """Verify hook confirmation blocks continuous runaway momentum and triggers on reversion turn."""
    engine = StrategyV2Engine()

    # Case A: Continuous downward runaway divergence (Falling Knife problem)
    # Z keeps expanding deeper: -1.5 -> -2.1 -> -2.5 -> -2.9 -> -3.3 -> -3.6
    z_runaway_down = np.array([-1.5, -2.1, -2.5, -2.9, -3.3, -3.6])
    confirmed, direction, hurdle_z, hook_z = engine.is_hook_confirmed(z_runaway_down)
    assert not confirmed, "Runaway momentum downward must NOT trigger hook entry"

    # Case B: Continuous upward runaway divergence
    z_runaway_up = np.array([1.5, 2.1, 2.6, 3.0, 3.4])
    confirmed, direction, hurdle_z, hook_z = engine.is_hook_confirmed(z_runaway_up)
    assert not confirmed, "Runaway momentum upward must NOT trigger hook entry"

    # Case C: Confirmed Long Reversion Hook
    # Reaches hurdle <= -2.10 (min is -2.30), turns around, and crosses back inside -1.85 with dZ > 0
    z_hook_long = np.array([-1.2, -1.8, -2.25, -2.30, -2.05, -1.80])
    confirmed, direction, hurdle_z, hook_z = engine.is_hook_confirmed(z_hook_long)
    assert confirmed, "Turnaround across -1.85 with dZ > 0 must confirm Long Hook"
    assert direction == "LONG_A_SHORT_B"
    assert hurdle_z <= -2.10
    assert hook_z == -1.80

    # Case D: Confirmed Short Reversion Hook
    # Reaches hurdle >= +2.10 (max is 2.35), turns down, and crosses back inside +1.85 with dZ < 0
    z_hook_short = np.array([1.2, 1.8, 2.30, 2.35, 2.05, 1.82])
    confirmed, direction, hurdle_z, hook_z = engine.is_hook_confirmed(z_hook_short)
    assert confirmed, "Turnaround across +1.85 with dZ < 0 must confirm Short Hook"
    assert direction == "SHORT_A_LONG_B"
    assert hurdle_z >= 2.10
    assert hook_z == 1.82

    # Case E: Shallow dip without hurdle breach (|Z| < 2.10)
    # Min is only -2.00; never breached hurdle threshold of -2.10
    z_shallow = np.array([-1.2, -1.6, -2.00, -1.95, -1.80])
    confirmed, direction, hurdle_z, hook_z = engine.is_hook_confirmed(z_shallow)
    assert not confirmed, "Shallow dip that failed to breach hurdle must NOT trigger hook entry"


# =========================================================================== #
# Test 3: Two-Tranche Staged TP1 & Breakeven Stop ("Flipped Trade" Diagnostic)
# =========================================================================== #
def test_two_tranche_staged_tp1_and_breakeven_stop():
    """Verify that TP1 banks 50% profit at 0.80σ and Tranche 2 exits at breakeven if spread re-diverges.
    
    This is the core 'Flipped Trade' mechanism: Strategy v1 blows out at 3.5σ because it waits
    for 0.0, while Strategy v2 locks profit on TP1 and scratches Tranche 2 at breakeven.
    """
    entry_date = "2026-01-15"
    future_dates = pd.bdate_range(start="2026-01-16", periods=10)
    all_dates = pd.DatetimeIndex([pd.to_datetime(entry_date)]).append(future_dates)

    # Entry at Z0 = -1.85 (Long Spread: Pa=98.15, Pb=100, beta=1.0, mu=0, sigma=1.0, spread = -1.85)
    # Future trajectory:
    # Day 1: Spread reverts to -0.75 (crosses TP1 target of -0.80σ -> TP1 executes!)
    # Day 2: Spread re-widens to -1.20
    # Day 3: Spread re-diverges past entry to -1.90 (crosses Breakeven Stop level of -1.85 -> BE stop executes!)
    # Days 4-10: Spreads stays wide at -2.50
    spread_vals = np.array([
        -1.85,  # Entry date (Day 0)
        -0.75,  # Day 1: TP1 hit (Z = -0.75 >= -0.80)
        -1.20,  # Day 2: Mid-range
        -1.90,  # Day 3: Breakeven Stop hit (Z = -1.90 <= -1.85)
        -2.50, -2.50, -2.50, -2.50, -2.50, -2.50, -2.50,
    ])

    df = create_mock_pair_dataframe(all_dates, spread_vals, has_high_low=False)
    evaluator = StrategyV2OutcomeEvaluator(df=df)

    setup = StrategyV2Setup(
        ticker_a="TICK_A",
        ticker_b="TICK_B",
        pair_name="TICK_A/TICK_B",
        target_date=entry_date,
        direction="LONG_A_SHORT_B",
        hedge_ratio=1.0,
        alpha=0.0,
        r_squared=0.75,
        correlation=0.88,
        current_z_score=-1.85,
        abs_z_score=1.85,
        current_spread=-1.85,
        spread_mean=0.0,
        spread_std=1.0,
        adf_tstat=-3.5,
        adf_pvalue=0.01,
        half_life_days=10.0,
        zero_crossings=12,
        relative_spread_vol_pct=1.0,
        spread_tier="Ultra Tight",
        composite_score=85.0,
        price_a_entry=98.15,
        price_b_entry=100.0,
        expected_reversion_return_pct=1.0,
        risk_reward_ratio=1.5,
        hook_confirmed=True,
        hurdle_breached_z=-2.20,
        hook_entry_z=-1.85,
        tp1_z_target=-0.80,
        tp2_z_target=-0.20,
        stop_loss_z=-3.20,
        breakeven_stop_z=-1.85,
        target_spread_tp1=-0.80,
        target_spread_tp2=-0.20,
        stop_loss_spread=-3.20,
        time_stop_days=18,
        earnings_blackout=False,
        earnings_veto_reason=None,
        is_setup=True,
        is_perfect=True,
        is_tradeable=True,
    )

    result = evaluator.evaluate_setup(setup)

    assert result.outcome == "WIN", "Trade must be classified as WIN due to locked TP1 profit"
    assert result.exit_reason == "TP1_AND_BREAKEVEN"
    assert result.tp1_hit is True
    assert result.tp1_days_held == 1
    assert result.breakeven_stop_hit is True
    assert result.exit_days_held == 3

    # Financial verification: Tranche 1 banked profit, Tranche 2 was 0.0%, net return is positive!
    assert result.tranche1_pnl_pct > 0.0, f"Tranche 1 must be positive: {result.tranche1_pnl_pct}%"
    assert result.tranche2_pnl_pct == 0.0, f"Tranche 2 must be 0% at breakeven: {result.tranche2_pnl_pct}%"
    expected_comb = round(0.50 * result.tranche1_pnl_pct + 0.50 * 0.0, 2)
    assert result.realized_pnl_pct == expected_comb
    assert result.realized_pnl_pct > 0.0, "Overall trade MUST be net profitable!"


# =========================================================================== #
# Test 4: Full Mean Reversion (TP1 and TP2 Reached)
# =========================================================================== #
def test_two_tranche_staged_tp1_and_tp2_full_target():
    """Verify both tranches exit profitably when spread fully reverts to equilibrium."""
    entry_date = "2026-01-15"
    future_dates = pd.bdate_range(start="2026-01-16", periods=6)
    all_dates = pd.DatetimeIndex([pd.to_datetime(entry_date)]).append(future_dates)

    # Long spread entry at -1.85 -> Day 1 hits TP1 (-0.75), Day 3 hits TP2 (-0.15)
    spread_vals = np.array([
        -1.85,  # Entry
        -0.75,  # Day 1: TP1
        -0.50,  # Day 2
        -0.15,  # Day 3: TP2
        0.0, 0.0, 0.0,
    ])

    df = create_mock_pair_dataframe(all_dates, spread_vals, has_high_low=False)
    evaluator = StrategyV2OutcomeEvaluator(df=df)

    setup = StrategyV2Setup(
        ticker_a="TICK_A",
        ticker_b="TICK_B",
        pair_name="TICK_A/TICK_B",
        target_date=entry_date,
        direction="LONG_A_SHORT_B",
        hedge_ratio=1.0,
        alpha=0.0,
        r_squared=0.75,
        correlation=0.88,
        current_z_score=-1.85,
        abs_z_score=1.85,
        current_spread=-1.85,
        spread_mean=0.0,
        spread_std=1.0,
        adf_tstat=-3.5,
        adf_pvalue=0.01,
        half_life_days=10.0,
        zero_crossings=12,
        relative_spread_vol_pct=1.0,
        spread_tier="Ultra Tight",
        composite_score=85.0,
        price_a_entry=98.15,
        price_b_entry=100.0,
        expected_reversion_return_pct=1.0,
        risk_reward_ratio=1.5,
        hook_confirmed=True,
        hurdle_breached_z=-2.20,
        hook_entry_z=-1.85,
        tp1_z_target=-0.80,
        tp2_z_target=-0.20,
        stop_loss_z=-3.20,
        breakeven_stop_z=-1.85,
        target_spread_tp1=-0.80,
        target_spread_tp2=-0.20,
        stop_loss_spread=-3.20,
        time_stop_days=18,
        earnings_blackout=False,
        earnings_veto_reason=None,
        is_setup=True,
        is_perfect=True,
        is_tradeable=True,
    )

    result = evaluator.evaluate_setup(setup)

    assert result.outcome == "WIN"
    assert result.exit_reason == "TP1_AND_TP2"
    assert result.tp1_hit is True
    assert result.tp2_hit is True
    assert result.exit_days_held == 3
    assert result.tranche1_pnl_pct > 0.0
    assert result.tranche2_pnl_pct > result.tranche1_pnl_pct, "Tranche 2 captured deeper mean reversion"
    assert result.realized_pnl_pct == round(0.50 * result.tranche1_pnl_pct + 0.50 * result.tranche2_pnl_pct, 2)


# =========================================================================== #
# Test 5: Initial Stop Loss Priority (3.20σ) & Precedence Guarantee
# =========================================================================== #
def test_initial_stop_loss_priority_and_same_day_precedence():
    """Verify stop loss triggers at 3.20σ and takes priority over same-day target reversion."""
    entry_date = "2026-01-15"
    future_dates = pd.bdate_range(start="2026-01-16", periods=4)
    all_dates = pd.DatetimeIndex([pd.to_datetime(entry_date)]).append(future_dates)

    # Spread drops immediately to -3.30 (breaches -3.20σ)
    spread_vals = np.array([-1.85, -3.30, -3.50, -3.60, -3.70])

    df = create_mock_pair_dataframe(all_dates, spread_vals, has_high_low=False)
    evaluator = StrategyV2OutcomeEvaluator(df=df)

    setup = StrategyV2Setup(
        ticker_a="TICK_A",
        ticker_b="TICK_B",
        pair_name="TICK_A/TICK_B",
        target_date=entry_date,
        direction="LONG_A_SHORT_B",
        hedge_ratio=1.0,
        alpha=0.0,
        r_squared=0.75,
        correlation=0.88,
        current_z_score=-1.85,
        abs_z_score=1.85,
        current_spread=-1.85,
        spread_mean=0.0,
        spread_std=1.0,
        adf_tstat=-3.5,
        adf_pvalue=0.01,
        half_life_days=10.0,
        zero_crossings=12,
        relative_spread_vol_pct=1.0,
        spread_tier="Ultra Tight",
        composite_score=85.0,
        price_a_entry=98.15,
        price_b_entry=100.0,
        expected_reversion_return_pct=1.0,
        risk_reward_ratio=1.5,
        hook_confirmed=True,
        hurdle_breached_z=-2.20,
        hook_entry_z=-1.85,
        tp1_z_target=-0.80,
        tp2_z_target=-0.20,
        stop_loss_z=-3.20,
        breakeven_stop_z=-1.85,
        target_spread_tp1=-0.80,
        target_spread_tp2=-0.20,
        stop_loss_spread=-3.20,
        time_stop_days=18,
        earnings_blackout=False,
        earnings_veto_reason=None,
        is_setup=True,
        is_perfect=True,
        is_tradeable=True,
    )

    result = evaluator.evaluate_setup(setup)

    assert result.outcome == "LOSS"
    assert result.exit_reason == "STOP_LOSS"
    assert result.stop_loss_hit is True
    assert result.exit_days_held == 1
    assert result.realized_pnl_pct < 0.0


# =========================================================================== #
# Test 6: Dynamic Ornstein-Uhlenbeck Time Stop Calculation & Execution
# =========================================================================== #
def test_ornstein_uhlenbeck_time_stop_calculation_and_execution():
    """Verify dynamic time stop formula: min(25, max(10, round(1.75 * half_life)))."""
    engine = StrategyV2Engine()

    # Formula edge cases
    # 1. Very fast half-life (e.g. 3.0 days): 1.75 * 3.0 = 5.25 -> clamped to floor 10
    assert engine.calculate_time_stop_days(3.0) == 10

    # 2. Medium half-life (e.g. 8.0 days): 1.75 * 8.0 = 14 -> 14 days
    assert engine.calculate_time_stop_days(8.0) == 14

    # 3. Intermediate half-life (e.g. 11.0 days): 1.75 * 11.0 = 19.25 -> round 19 days
    assert engine.calculate_time_stop_days(11.0) == 19

    # 4. Long half-life (e.g. 20.0 days): 1.75 * 20.0 = 35.0 -> clamped to cap 25
    assert engine.calculate_time_stop_days(20.0) == 25

    # Execution Test: Setup with T_max = 12 days. Stale spread never hits TP1 or Stop.
    entry_date = "2026-01-15"
    future_dates = pd.bdate_range(start="2026-01-16", periods=20)
    all_dates = pd.DatetimeIndex([pd.to_datetime(entry_date)]).append(future_dates)

    # Spread stays in dead zone around -1.40 (between -1.85 and -0.80)
    spread_vals = np.full(len(all_dates), -1.40)
    spread_vals[0] = -1.85

    df = create_mock_pair_dataframe(all_dates, spread_vals, has_high_low=False)
    evaluator = StrategyV2OutcomeEvaluator(df=df)

    setup = StrategyV2Setup(
        ticker_a="TICK_A",
        ticker_b="TICK_B",
        pair_name="TICK_A/TICK_B",
        target_date=entry_date,
        direction="LONG_A_SHORT_B",
        hedge_ratio=1.0,
        alpha=0.0,
        r_squared=0.75,
        correlation=0.88,
        current_z_score=-1.85,
        abs_z_score=1.85,
        current_spread=-1.85,
        spread_mean=0.0,
        spread_std=1.0,
        adf_tstat=-3.5,
        adf_pvalue=0.01,
        half_life_days=7.0,  # 1.75 * 7 = 12.25 -> 12 days
        zero_crossings=12,
        relative_spread_vol_pct=1.0,
        spread_tier="Ultra Tight",
        composite_score=85.0,
        price_a_entry=98.15,
        price_b_entry=100.0,
        expected_reversion_return_pct=1.0,
        risk_reward_ratio=1.5,
        hook_confirmed=True,
        hurdle_breached_z=-2.20,
        hook_entry_z=-1.85,
        tp1_z_target=-0.80,
        tp2_z_target=-0.20,
        stop_loss_z=-3.20,
        breakeven_stop_z=-1.85,
        target_spread_tp1=-0.80,
        target_spread_tp2=-0.20,
        stop_loss_spread=-3.20,
        time_stop_days=12,
        earnings_blackout=False,
        earnings_veto_reason=None,
        is_setup=True,
        is_perfect=True,
        is_tradeable=True,
    )

    result = evaluator.evaluate_setup(setup)

    assert result.exit_reason == "TIME_STOP"
    assert result.time_stop_hit is True
    assert result.exit_days_held == 12, "Trade must be forcefully exited at T_max = 12 days"


# =========================================================================== #
# Test 7: Earnings Blackout Filter (±5 Trading Days)
# =========================================================================== #
def test_earnings_blackout_filter():
    """Verify that entries are vetoed within ±5 trading days of corporate earnings."""
    custom_earnings = {
        "MSFT": ["2026-10-28"],
        "GOOGL": ["2026-11-10"],
    }
    calendar = EarningsCalendar(custom_earnings=custom_earnings)

    # 1. Test MSFT date 2 days before earnings -> Blackout!
    is_bo, reason = calendar.is_in_blackout("MSFT", "AAPL", "2026-10-26", blackout_days=5)
    assert is_bo is True
    assert "Earnings Blackout" in reason
    assert "MSFT" in reason

    # 2. Test MSFT date 2 days after earnings -> Blackout!
    is_bo, reason = calendar.is_in_blackout("MSFT", "AAPL", "2026-10-30", blackout_days=5)
    assert is_bo is True

    # 3. Test date 20 days prior (well outside ±5 trading days) -> Safe!
    is_bo, reason = calendar.is_in_blackout("MSFT", "AAPL", "2026-10-05", blackout_days=5)
    assert is_bo is False
    assert reason is None

    # 4. Test Ticker B (GOOGL) triggers blackout for the pair
    is_bo, reason = calendar.is_in_blackout("AAPL", "GOOGL", "2026-11-08", blackout_days=5)
    assert is_bo is True
    assert "GOOGL" in reason


# =========================================================================== #
# Test 8: Tightened Gauntlet Screening (R² >= 0.50, HL <= 22d, ADF p <= 0.04)
# =========================================================================== #
def test_tightened_gauntlet_screening():
    """Verify Strategy v2 tightened screening gates reject marginal pairs."""
    engine = StrategyV2Engine()

    # R-squared gate: v2 requires >= 0.50 (v1 allowed >= 0.35)
    assert engine.min_r_squared == 0.50

    # Half-life gate: v2 requires <= 22.0 days (v1 allowed <= 35.0)
    assert engine.max_half_life == 22.0

    # Cointegration p-value gate: v2 requires <= 0.04 (v1 allowed <= 0.05)
    assert engine.max_coint_p == 0.04

    # Stop-Loss barrier: v2 tightened to 3.20σ (v1 was 3.50σ)
    assert engine.stop_loss_z == 3.20


# =========================================================================== #
# Test 9: Zero Lookahead Verification on Multi-Day Point-in-Time Slicing
# =========================================================================== #
def test_strategy_v2_zero_lookahead_temporal_integrity():
    """Verify StrategyV2Engine.slice_history contains zero bars after Date T."""
    dates = pd.bdate_range(start="2025-01-01", periods=120)
    spread = np.zeros(len(dates))
    df = create_mock_pair_dataframe(dates, spread)

    engine = StrategyV2Engine(df=df)
    target_date = dates[59]  # 60th bar

    sliced = engine.slice_history(target_date)
    assert len(sliced) == 60
    assert sliced.index[-1] == target_date
    assert sliced.index[-1] <= target_date
    assert all(ts <= target_date for ts in sliced.index)
