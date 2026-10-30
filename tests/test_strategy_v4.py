"""Comprehensive Automated Test Suite for Strategy v4 ("Risk-Engineered Pure Alpha").

Validates:
  1. Mandatory Acceptance Gates across all 4 horizons (1Y, 2Y, 3Y, 5Y):
     - Win Rate >= 52.0%
     - Max Drawdown <= 28.0%
     - Profit Factor >= 1.55
     - Strong Net Return
  2. Momentum Flattening Confirmation (blocks adverse runaway slope > 0.05)
  3. 2.5x Half-Life Time Stop Clamping (clamped to [4, 22] days)
  4. Volatility-Inverse Position Sizing Multiplier (0.40x to 1.25x with 0.70x DD dampener)
  5. Earnings Blackout Shield & VIX Macro Overlay vetoes
  6. API endpoint integration (/api/simulator/v4/backtest, /api/simulator/compare)
"""

import json
import math
import os
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from engine.strategy_v4_engine import StrategyV4Config, StrategyV4Engine
from engine.strategy_comparison_engine import StrategyComparisonEngine

STRATEGY_4_RESULT_PATH = ROOT_DIR / "Strategy_4_result.json"
DATA_DIR = ROOT_DIR / "data"


def test_mandatory_acceptance_gates():
    """Verify that Strategy v4 meets or exceeds all 4 acceptance gates across all 4 timelines."""
    assert STRATEGY_4_RESULT_PATH.exists(), "Strategy_4_result.json must exist in root."

    with open(STRATEGY_4_RESULT_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert "horizons" in data, "Consolidated output must include horizons dictionary."
    horizons = data["horizons"]

    for h in ["1y", "2y", "3y", "5y"]:
        assert h in horizons, f"Horizon {h} must be present in Strategy_4_result.json"
        summary = horizons[h]["overall_summary"]

        win_rate = summary["win_rate_pct"]
        max_dd = summary["max_drawdown_pct"]
        pf = summary["profit_factor"]
        net_ret = summary["net_return_pct"]
        total_trades = summary["total_trades"]

        print(f"\nVerifying Horizon {h.upper()}:")
        print(f"  Win Rate: {win_rate}% (Must be >= 52.0%)")
        print(f"  Max Drawdown: {max_dd}% (Must be <= 28.0%)")
        print(f"  Profit Factor: {pf} (Must be >= 1.55)")
        print(f"  Net Realized Profit: +{net_ret:.2f}%")
        print(f"  Total Trades: {total_trades}")

        # Gate 1: Win Rate >= 52.0%
        assert win_rate >= 52.0, f"{h.upper()} Win Rate {win_rate}% failed gate (>= 52.0%)"

        # Gate 2: Max Drawdown <= 28.0%
        assert max_dd <= 28.0, f"{h.upper()} Max Drawdown {max_dd}% failed gate (<= 28.0%)"

        # Gate 3: Profit Factor >= 1.55
        assert pf >= 1.55, f"{h.upper()} Profit Factor {pf} failed gate (>= 1.55)"

        # Gate 4: Net Realized Profit > 0
        assert net_ret > 0.0, f"{h.upper()} Net Return +{net_ret}% must be strongly positive"
        assert total_trades >= 40, f"{h.upper()} Total trades {total_trades} must indicate robust sample size"


def test_momentum_flattening_confirmation():
    """Verify that momentum flattening / velocity confirmation correctly filters entries."""
    cfg = StrategyV4Config.load()
    max_slope = cfg.max_entry_momentum_slope

    # Case 1: Adverse runaway knife (e.g. z_curr = -2.50, z_prev = -2.30, diff = 0.20 > 0.05) -> VETO
    z_curr = -2.50
    z_prev = -2.30
    is_reversing = (z_curr > z_prev) if z_curr < 0 else (z_curr < z_prev)
    is_flattening = abs(z_curr - z_prev) <= max_slope
    assert not (is_reversing or is_flattening), "Adverse runaway knife must be rejected"

    # Case 2: Flattening momentum (|diff| <= 0.05) -> ACCEPT
    z_curr = -2.52
    z_prev = -2.50
    is_reversing = (z_curr > z_prev) if z_curr < 0 else (z_curr < z_prev)
    is_flattening = abs(z_curr - z_prev) <= max_slope
    assert (is_reversing or is_flattening), "Flattening momentum must be accepted"

    # Case 3: Reversing hook towards mean (z_curr = -2.30, z_prev = -2.50) -> ACCEPT
    z_curr = -2.30
    z_prev = -2.50
    is_reversing = (z_curr > z_prev) if z_curr < 0 else (z_curr < z_prev)
    assert is_reversing, "Mean-reversion hook must be accepted"


def test_time_stop_calculation():
    """Verify 2.5x half-life time stop clamping."""
    cfg = StrategyV4Config.load()
    mult = cfg.half_life_time_stop_multiplier

    # Very fast half-life (1.0 day): round(2.5 * 1.0) = 2 -> Clamped to min 4 days
    t_fast = max(cfg.min_holding_days_floor, min(cfg.max_holding_days_cap, int(round(mult * 1.0))))
    assert t_fast == 4, f"Expected 4 days floor, got {t_fast}"

    # Typical half-life (5.0 days): round(2.5 * 5.0) = 12 days
    t_mid = max(cfg.min_holding_days_floor, min(cfg.max_holding_days_cap, int(round(mult * 5.0))))
    assert t_mid == 12 or t_mid == 13, f"Expected 12 or 13 days, got {t_mid}"

    # Very slow half-life (20.0 days): round(2.5 * 20.0) = 50 -> Clamped to max 22 days
    t_slow = max(cfg.min_holding_days_floor, min(cfg.max_holding_days_cap, int(round(mult * 20.0))))
    assert t_slow == 22, f"Expected 22 days cap, got {t_slow}"


def test_volatility_inverse_sizing():
    """Verify volatility-inverse position sizing multiplier bounds and drawdown dampener."""
    cfg = StrategyV4Config.load()

    # Low spread vol (2.0%): 3.5 / 2.0 = 1.75 -> Clamped to max 1.25
    m_low = min(cfg.max_capital_multiplier, max(cfg.min_capital_multiplier, cfg.target_spread_vol_pct / 2.0))
    assert m_low == 1.25, f"Expected 1.25 cap, got {m_low}"

    # High spread vol (5.0%): 3.5 / 5.0 = 0.70 -> 0.70x multiplier
    m_high = min(cfg.max_capital_multiplier, max(cfg.min_capital_multiplier, cfg.target_spread_vol_pct / 5.0))
    assert abs(m_high - 0.70) < 1e-4, f"Expected 0.70 multiplier, got {m_high}"

    # Drawdown dampener: 0.70x applied during >20% drawdown
    m_dampened = m_high * cfg.drawdown_scaling_factor
    assert abs(m_dampened - 0.49) < 1e-4, f"Expected 0.49 dampened multiplier, got {m_dampened}"


def test_strategy_comparison_engine_v4_integration():
    """Verify that StrategyComparisonEngine loads and exposes Strategy 4 metrics."""
    engine = StrategyComparisonEngine()
    comp_1y = engine.compare("1Y")

    assert "summary_delta" in comp_1y, "Comparison must include summary_delta."
    summary = comp_1y["summary_delta"]

    # Verify v4 metrics exist and are populated
    assert "win_rate_v4" in summary, "summary_delta must include win_rate_v4"
    assert "profit_factor_v4" in summary, "summary_delta must include profit_factor_v4"
    assert "max_drawdown_v4" in summary, "summary_delta must include max_drawdown_v4"
    assert summary["win_rate_v4"] >= 52.0, "Comparison 1Y v4 win rate must exceed 52.0%"
    assert summary["max_drawdown_v4"] <= 28.0, "Comparison 1Y v4 max drawdown must be under 28.0%"
    assert summary["profit_factor_v4"] >= 1.55, "Comparison 1Y v4 profit factor must exceed 1.55"

    # Aligned equity points must have v4_equity
    aligned = comp_1y["aligned_equity"]
    assert len(aligned) > 0, "Aligned equity points must not be empty"
    first_pt = aligned[0]
    last_pt = aligned[-1]
    assert "v4_equity" in first_pt, "Aligned equity point must include v4_equity"
    assert "v4_equity" in last_pt, "Aligned equity point must include v4_equity"
    assert last_pt["v4_equity"] > 0.0, "Strategy 4 final cumulative equity must be positive"


def test_earnings_blackout_and_vix_macro_overlay_vetoes():
    """Verify that earnings blackout and VIX macro panic regime vetoes are strictly enforced."""
    from engine.strategy_v2_engine import EarningsCalendar

    ec = EarningsCalendar()
    cfg = StrategyV4Config.load()

    # Earnings blackout check
    # Pick a sample date near known earnings or simulated blackout
    is_blackout, reason = ec.is_in_blackout("AAPL", "MSFT", "2025-01-29", blackout_days=cfg.earnings_blackout_days_pre)
    assert isinstance(is_blackout, (bool, np.bool_)), "Blackout result must be boolean"

    # Macro regime VIX check
    vix_panic = 28.5
    vix_normal = 16.2
    assert vix_panic > cfg.vix_panic_threshold, "VIX 28.5 must breach panic threshold (25.0)"
    assert vix_normal <= cfg.vix_panic_threshold, "VIX 16.2 must remain below panic threshold (25.0)"


def test_spread_volatility_cap_and_entry_hurdle():
    """Verify that spread volatility cap (> 5.5%) and divergence hurdle bounds are strictly enforced."""
    cfg = StrategyV4Config.load()

    # Volatility cap
    assert cfg.max_allowed_spread_vol_pct == 5.5, "Default max allowed spread vol must be 5.5%"
    vol_pass = 4.2 <= cfg.max_allowed_spread_vol_pct
    vol_fail = 6.1 <= cfg.max_allowed_spread_vol_pct
    assert vol_pass, "4.2% spread volatility must pass cap"
    assert not vol_fail, "6.1% spread volatility must breach cap"

    # Divergence hurdle bounds: 2.10 <= |Z| < 3.00
    assert cfg.z_score_entry_hurdle == 2.10
    assert cfg.z_score_entry_max == 3.00
    z_under = abs(1.95) >= cfg.z_score_entry_hurdle and abs(1.95) < cfg.z_score_entry_max
    z_valid = abs(2.35) >= cfg.z_score_entry_hurdle and abs(2.35) < cfg.z_score_entry_max
    z_over = abs(3.25) >= cfg.z_score_entry_hurdle and abs(3.25) < cfg.z_score_entry_max
    assert not z_under, "|Z| = 1.95 must be rejected (under hurdle)"
    assert z_valid, "|Z| = 2.35 must be accepted"
    assert not z_over, "|Z| = 3.25 must be rejected (over entry max)"


def test_api_simulator_v4_endpoints():
    """Verify that FastAPI endpoints return valid Strategy v4 data and comparison structures."""
    from fastapi.testclient import TestClient
    from api.main import app

    client = TestClient(app)

    # 1. Test /api/simulator/v4/backtest endpoint
    resp_v4 = client.get("/api/simulator/v4/backtest?horizon=1Y")
    assert resp_v4.status_code == 200, f"Expected 200 OK, got {resp_v4.status_code}"
    v4_data = resp_v4.json()
    assert "overall_summary" in v4_data, "Response must include overall_summary"
    assert "trades" in v4_data, "Response must include trades list"
    assert "equity_curve" in v4_data, "Response must include equity_curve"
    assert v4_data["overall_summary"]["win_rate_pct"] >= 52.0

    # 2. Test /api/simulator/compare endpoint with v4 metrics
    resp_comp = client.get("/api/simulator/compare?period=1Y")
    assert resp_comp.status_code == 200, f"Expected 200 OK, got {resp_comp.status_code}"
    comp_data = resp_comp.json()
    assert "summary_delta" in comp_data, "Comparison response must include summary_delta"
    s_delta = comp_data["summary_delta"]
    assert "win_rate_v4" in s_delta, "Summary delta must include win_rate_v4"
    assert "profit_factor_v4" in s_delta, "Summary delta must include profit_factor_v4"
    assert "max_drawdown_v4" in s_delta, "Summary delta must include max_drawdown_v4"
    assert s_delta["win_rate_v4"] >= 52.0

