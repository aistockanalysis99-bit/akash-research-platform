"""tests/test_simulator_regimes.py
=============================================================================
Phase 6: Walk-Forward Multi-Regime Stress Test & Mathematical Audit
=============================================================================

Objectives & Constraints:
  1. Regime A: High Volatility Bear Market (Q1–Q2 2022)
  2. Regime B: Mega-Cap Tech Dispersal (Q3–Q4 2023)
  3. Regime C: Choppy Consolidation (Summer 2024)
  - Constraint 1: Simulation loop latency to advance 1 day and evaluate all pairs < 300ms.
  - Constraint 2: Mathematical audit of >= 2 WIN trades and >= 2 LOSS trades proving:
                  WIN never breached |z| >= 3.5 stop-loss before reverting.
                  LOSS breached |z| >= 3.5 stop-loss before reverting.
  - Constraint 3: Test suite passes 100% with formatted console regime summary table.
"""

import time
import pytest
import numpy as np
import pandas as pd
from typing import List, Dict, Any, Tuple

from engine.simulator_engine import (
    PointInTimeEngine,
    ForwardOutcomeEvaluator,
    PointInTimeSetup,
    ForwardEvaluationResult,
    DayBatchScorecard,
)


@pytest.fixture(scope="module")
def warm_engine_and_evaluator():
    """Shared pre-warmed PointInTimeEngine and ForwardOutcomeEvaluator instances."""
    engine = PointInTimeEngine()
    df = engine.load_data()
    evaluator = ForwardOutcomeEvaluator(df=df)
    return engine, evaluator, df


# =========================================================================== #
# Constraint 1: Simulation Loop Latency Benchmark (< 300ms)
# =========================================================================== #
def test_simulation_loop_latency_under_300ms(warm_engine_and_evaluator):
    """Verify Constraint 1: Slicing, scanning all 165 pairs, and evaluating forward outcomes

    must execute in strictly under 300ms per simulated day.
    """
    engine, evaluator, df = warm_engine_and_evaluator
    test_dates = ["2022-03-22", "2023-07-10", "2024-06-14", "2024-07-22"]
    latencies: List[float] = []

    for dt in test_dates:
        t0 = time.perf_counter()

        # Step 1: Point-in-Time Scan (t <= Date T)
        setups = engine.scan_date(dt, top_n=10, only_active_setups=True)

        # Step 2: Forward Outcome Evaluation (t > Date T)
        scorecard = evaluator.evaluate_batch(setups, max_horizon_days=30)

        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        latencies.append(elapsed_ms)

    avg_latency = float(np.mean(latencies))
    max_latency = float(np.max(latencies))

    print(f"\n[Constraint 1 Benchmark] Latency per day: Avg={avg_latency:.1f}ms, Max={max_latency:.1f}ms across {len(test_dates)} dates.")
    assert max_latency < 300.0, f"Constraint 1 Failure: Max single-day cycle ({max_latency:.1f}ms) exceeded 300ms limit!"
    assert avg_latency < 280.0, f"Constraint 1 Failure: Avg cycle ({avg_latency:.1f}ms) exceeded 280ms threshold!"


# =========================================================================== #
# Task 2: Three Market Regimes Walk-Forward Simulations
# =========================================================================== #
def run_regime_simulation(
    regime_name: str,
    start_date: str,
    end_date: str,
    step_stride: int,
    engine: PointInTimeEngine,
    evaluator: ForwardOutcomeEvaluator,
) -> Tuple[DayBatchScorecard, List[PointInTimeSetup], float]:
    """Walk forward through a regime, aggregate setups, and compute batch scorecard."""
    trading_dates = engine.get_trading_dates()
    regime_dates = [
        d.strftime("%Y-%m-%d")
        for d in trading_dates
        if start_date <= d.strftime("%Y-%m-%d") <= end_date
    ][::step_stride]

    assert len(regime_dates) > 0, f"No trading dates found in range {start_date} to {end_date}"

    t0 = time.perf_counter()
    all_setups: List[PointInTimeSetup] = []

    for dt in regime_dates:
        day_setups = engine.scan_date(dt, top_n=10, only_active_setups=True)
        all_setups.extend(day_setups)

    scorecard = evaluator.evaluate_batch(all_setups, max_horizon_days=30)
    total_time_ms = (time.perf_counter() - t0) * 1000.0
    avg_day_ms = total_time_ms / len(regime_dates)

    return scorecard, all_setups, avg_day_ms


def test_regime_a_high_volatility_bear_market(warm_engine_and_evaluator):
    """Regime A: High Volatility Bear Market (Q1–Q2 2022).

    During rapid macro rate hikes and equity deleveraging, spreads experience extreme dislocation.
    """
    engine, evaluator, _ = warm_engine_and_evaluator
    scorecard, setups, avg_ms = run_regime_simulation(
        regime_name="Regime A (Bear Market 2022)",
        start_date="2022-03-15",
        end_date="2022-06-30",
        step_stride=3,
        engine=engine,
        evaluator=evaluator,
    )

    print(f"\n[Regime A: Q1-Q2 2022 Bear Market] Setups={scorecard.total_setups}, "
          f"Wins={scorecard.win_count}, Losses={scorecard.loss_count}, WinRate={scorecard.win_rate_pct:.1f}%, "
          f"AvgPnL={scorecard.avg_return_pct:.2f}%, AvgDaysHeld={scorecard.avg_days_held:.1f}d, Latency/Day={avg_ms:.1f}ms")

    assert scorecard.total_setups > 0, "Regime A should identify active divergence candidates."
    assert scorecard.win_count + scorecard.loss_count + scorecard.neutral_count == scorecard.total_setups
    assert avg_ms < 300.0, f"Average per-day latency ({avg_ms:.1f}ms) in Regime A must be < 300ms"


def test_regime_b_mega_cap_tech_dispersal(warm_engine_and_evaluator):
    """Regime B: Mega-Cap Tech Dispersal (Q3–Q4 2023).

    Selective dispersion among tech and financial equities creates mean-reverting dislocations.
    """
    engine, evaluator, _ = warm_engine_and_evaluator
    scorecard, setups, avg_ms = run_regime_simulation(
        regime_name="Regime B (Tech Dispersal 2023)",
        start_date="2023-07-03",
        end_date="2023-11-30",
        step_stride=3,
        engine=engine,
        evaluator=evaluator,
    )

    print(f"\n[Regime B: Q3-Q4 2023 Tech Dispersal] Setups={scorecard.total_setups}, "
          f"Wins={scorecard.win_count}, Losses={scorecard.loss_count}, WinRate={scorecard.win_rate_pct:.1f}%, "
          f"AvgPnL={scorecard.avg_return_pct:.2f}%, AvgDaysHeld={scorecard.avg_days_held:.1f}d, Latency/Day={avg_ms:.1f}ms")

    assert scorecard.total_setups > 0, "Regime B should identify active divergence setups."
    assert scorecard.win_count > 0, "Regime B must register successful mean-reverting wins."
    assert avg_ms < 300.0, f"Average per-day latency ({avg_ms:.1f}ms) in Regime B must be < 300ms"


def test_regime_c_choppy_consolidation(warm_engine_and_evaluator):
    """Regime C: Choppy Consolidation (Summer 2024).

    Range-bound market conditions provide high statistical mean-reversion success rates.
    """
    engine, evaluator, _ = warm_engine_and_evaluator
    scorecard, setups, avg_ms = run_regime_simulation(
        regime_name="Regime C (Consolidation 2024)",
        start_date="2024-06-03",
        end_date="2024-08-30",
        step_stride=3,
        engine=engine,
        evaluator=evaluator,
    )

    print(f"\n[Regime C: Summer 2024 Consolidation] Setups={scorecard.total_setups}, "
          f"Wins={scorecard.win_count}, Losses={scorecard.loss_count}, WinRate={scorecard.win_rate_pct:.1f}%, "
          f"AvgPnL={scorecard.avg_return_pct:.2f}%, AvgDaysHeld={scorecard.avg_days_held:.1f}d, Latency/Day={avg_ms:.1f}ms")

    assert scorecard.total_setups > 0, "Regime C should identify active divergence setups."
    assert scorecard.win_count > 0, "Regime C must register mean-reversion wins."
    assert scorecard.win_rate_pct > 25.0, f"Consolidation regime win rate ({scorecard.win_rate_pct:.1f}%) should be healthy (>25%)."
    assert avg_ms < 300.0, f"Average per-day latency ({avg_ms:.1f}ms) in Regime C must be < 300ms"


# =========================================================================== #
# Constraint 2: Mathematical Audit of >= 2 WIN and >= 2 LOSS Trades
# =========================================================================== #
def test_constraint_2_audit_win_and_loss_trades(warm_engine_and_evaluator):
    """Verify Constraint 2:

    Confirm mathematically that:
      - At least 2 "WIN" trades NEVER breached the |z| >= 3.5 stop-loss before reverting.
      - At least 2 "LOSS" trades breached |z| >= 3.5 stop-loss before reverting.
    """
    engine, evaluator, _ = warm_engine_and_evaluator

    # 1. Audit WIN Trade 1: BNY/IBKR on 2023-07-06 (Long Spread)
    s_win1 = engine.calculate_pair_pit("BNY", "IBKR", "2023-07-06")
    assert s_win1 is not None, "BNY/IBKR setup on 2023-07-06 must exist"
    res_win1 = evaluator.evaluate_setup(s_win1, max_horizon_days=30, use_intraday_extremes=False)

    assert res_win1.outcome == "WIN", f"Expected WIN, got {res_win1.outcome}"
    # Verify mathematically that every path bar prior to reversion had |z| < 3.5
    for bar in res_win1.path:
        assert abs(bar["z_score"]) < 3.5, f"WIN violation: bar on {bar['date']} had |z|={abs(bar['z_score']):.2f} >= 3.5!"
    # Verify reversion target was achieved
    exit_bar_win1 = res_win1.path[-1]
    assert exit_bar_win1["z_score"] >= -0.50 or exit_bar_win1["z_score"] >= 0.0, "Reversion target achieved"

    # 2. Audit WIN Trade 2: BEN/PFG on 2023-07-12 (Short Spread)
    s_win2 = engine.calculate_pair_pit("BEN", "PFG", "2023-07-12")
    assert s_win2 is not None, "BEN/PFG setup on 2023-07-12 must exist"
    res_win2 = evaluator.evaluate_setup(s_win2, max_horizon_days=30, use_intraday_extremes=False)

    assert res_win2.outcome == "WIN", f"Expected WIN, got {res_win2.outcome}"
    for bar in res_win2.path:
        assert abs(bar["z_score"]) < 3.5, f"WIN violation: bar on {bar['date']} had |z|={abs(bar['z_score']):.2f} >= 3.5!"
    exit_bar_win2 = res_win2.path[-1]
    assert exit_bar_win2["z_score"] <= 0.40 or exit_bar_win2["z_score"] <= 0.0, "Reversion target achieved"

    # 3. Audit LOSS Trade 1: BX/KKR on 2023-07-03 (Short Spread)
    s_loss1 = engine.calculate_pair_pit("BX", "KKR", "2023-07-03")
    assert s_loss1 is not None, "BX/KKR setup on 2023-07-03 must exist"
    res_loss1 = evaluator.evaluate_setup(s_loss1, max_horizon_days=30, use_intraday_extremes=False)

    assert res_loss1.outcome == "LOSS", f"Expected LOSS, got {res_loss1.outcome}"
    # Prior bars never reached mean target
    for bar in res_loss1.path[:-1]:
        assert bar["z_score"] > 0.50, "Prior bars must not have reverted before stop"
    # Exit bar breached |z| >= 3.5
    exit_bar_loss1 = res_loss1.path[-1]
    assert abs(exit_bar_loss1["z_score"]) >= 3.5, f"LOSS violation: exit bar {exit_bar_loss1['z_score']} did not breach 3.5!"

    # 4. Audit LOSS Trade 2: IBKR/STT on 2023-07-06 (Short Spread)
    s_loss2 = engine.calculate_pair_pit("IBKR", "STT", "2023-07-06")
    assert s_loss2 is not None, "IBKR/STT setup on 2023-07-06 must exist"
    res_loss2 = evaluator.evaluate_setup(s_loss2, max_horizon_days=30, use_intraday_extremes=False)

    assert res_loss2.outcome == "LOSS", f"Expected LOSS, got {res_loss2.outcome}"
    for bar in res_loss2.path[:-1]:
        assert bar["z_score"] > 0.50, "Prior bars must not have reverted before stop"
    exit_bar_loss2 = res_loss2.path[-1]
    assert abs(exit_bar_loss2["z_score"]) >= 3.5, f"LOSS violation: exit bar {exit_bar_loss2['z_score']} did not breach 3.5!"

    print("\n[Constraint 2 Audit] 4/4 Verified:")
    print(f"  [OK] WIN 1: {s_win1.pair_name} ({s_win1.target_date}) held {res_win1.exit_days_held}d, max |z|={max(abs(b['z_score']) for b in res_win1.path):.2f} < 3.5, exit z={res_win1.exit_z_score:.2f}")
    print(f"  [OK] WIN 2: {s_win2.pair_name} ({s_win2.target_date}) held {res_win2.exit_days_held}d, max |z|={max(abs(b['z_score']) for b in res_win2.path):.2f} < 3.5, exit z={res_win2.exit_z_score:.2f}")
    print(f"  [OK] LOSS 1: {s_loss1.pair_name} ({s_loss1.target_date}) held {res_loss1.exit_days_held}d, breached z={res_loss1.exit_z_score:.2f} >= 3.5 before reverting")
    print(f"  [OK] LOSS 2: {s_loss2.pair_name} ({s_loss2.target_date}) held {res_loss2.exit_days_held}d, breached z={res_loss2.exit_z_score:.2f} >= 3.5 before reverting")


# =========================================================================== #
# Constraint 3: Comprehensive Multi-Regime Console Summary Table
# =========================================================================== #
def test_cross_regime_summary_report(warm_engine_and_evaluator):
    """Verify Constraint 3: Generate and display the institutional regime summary table."""
    engine, evaluator, _ = warm_engine_and_evaluator

    regimes = [
        ("Regime A: High Vol Bear Market", "2022-03-15", "2022-06-30", 3),
        ("Regime B: Mega-Cap Tech Dispersal", "2023-07-03", "2023-11-30", 3),
        ("Regime C: Choppy Consolidation", "2024-06-03", "2024-08-30", 3),
    ]

    results: List[Dict[str, Any]] = []
    total_setups_all = 0
    total_wins_all = 0
    total_losses_all = 0

    for name, start, end, stride in regimes:
        scorecard, setups, avg_ms = run_regime_simulation(name, start, end, stride, engine, evaluator)
        results.append({
            "name": name,
            "period": f"{start} to {end}",
            "setups": scorecard.total_setups,
            "wins": scorecard.win_count,
            "losses": scorecard.loss_count,
            "neutrals": scorecard.neutral_count,
            "win_rate": f"{scorecard.win_rate_pct:.1f}%",
            "avg_pnl": f"{scorecard.avg_return_pct:+.2f}%",
            "avg_days": f"{scorecard.avg_days_held:.1f}d",
            "latency_ms": f"{avg_ms:.1f}ms",
        })
        total_setups_all += scorecard.total_setups
        total_wins_all += scorecard.win_count
        total_losses_all += scorecard.loss_count

    # Formatted Console Summary
    header = (
        f"{'Market Regime':<35} | {'Period':<23} | {'Setups':<6} | {'W':<4} | {'L':<4} | {'Win Rate':<8} | {'Avg PnL':<8} | {'Hold':<6} | {'Cycle':<7}"
    )
    separator = "-" * len(header)

    print("\n" + separator)
    print("POINT-IN-TIME SIMULATOR: MULTI-REGIME STRESS TEST REPORT")
    print(separator)
    print(header)
    print(separator)

    for r in results:
        print(
            f"{r['name']:<35} | {r['period']:<23} | {r['setups']:<6} | {r['wins']:<4} | {r['losses']:<4} | {r['win_rate']:<8} | {r['avg_pnl']:<8} | {r['avg_days']:<6} | {r['latency_ms']:<7}"
        )

    print(separator)
    overall_wr = (total_wins_all / max(1, total_wins_all + total_losses_all)) * 100.0
    print(f"TOTAL SETUPS AUDITED: {total_setups_all} | TOTAL WINS: {total_wins_all} | TOTAL LOSSES: {total_losses_all} | OVERALL WIN RATE: {overall_wr:.1f}%")
    print(separator + "\n")

    assert total_setups_all > 0, "Multi-regime run must produce aggregate evaluated setups."
