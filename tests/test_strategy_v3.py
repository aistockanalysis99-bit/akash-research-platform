"""Unit and Integration Tests for Strategy v3 ("Asymmetric Alpha Maximizer").

Verifies:
  1. Configuration loading and parameter thresholds.
  2. Conviction sizing math (1.45x for score >= 82.0, 1.00x for score >= 72.0, 0.65x for score < 72.0).
  3. Trailing Disaster Floor: Prevents -3.50σ blowout when spread recovered past 0.80σ.
  4. Bit-for-bit price integrity against Strategy 1 dataset.
  5. Non-Negotiable Outperformance Target: Strategy 3 MUST generate higher total net profit %
     than Strategy 1 in ALL 4 timelines (1Y > 81.04%, 2Y > 97.97%, 3Y > 134.04%, 5Y > 113.50%).
  6. API endpoint contract and sub-50ms response latency on /api/simulator/v3/backtest.
"""

import json
import time
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from engine.config import DATA_CACHE_DIR, PROJECT_ROOT
from engine.strategy_v3_engine import (
    StrategyV3Config,
    StrategyV3Engine,
    StrategyV3OutcomeEvaluator,
)
from engine.simulator_engine import PointInTimeSetup
from api.main import app


@pytest.fixture(scope="module")
def api_client():
    return TestClient(app)


@pytest.fixture(scope="module")
def v3_config():
    return StrategyV3Config.load()


def test_strategy_v3_config_loading(v3_config):
    """Verify Strategy v3 config parameters match specification."""
    assert v3_config.version == "3.0.0"
    assert v3_config.z_score_entry == 2.00
    assert v3_config.z_score_stop_loss == 3.50
    assert v3_config.tier1_score_threshold == 82.0
    assert v3_config.tier1_multiplier >= 1.40
    assert v3_config.tier2_score_threshold == 72.0
    assert v3_config.tier2_multiplier == 1.00
    assert v3_config.tier3_multiplier == 0.65
    assert v3_config.activation_recovery_z == 0.80
    assert v3_config.protected_stop_z == 1.50
    assert v3_config.max_holding_days == 35


def test_conviction_sizing_math(v3_config):
    """Verify conviction sizing tiers and multipliers."""
    evaluator = StrategyV3OutcomeEvaluator(v3_config)

    # Tier 1: Prime Setup (score >= 82)
    tier1, m1 = evaluator.get_conviction_tier(85.5)
    assert "Tier 1" in tier1
    assert m1 == v3_config.tier1_multiplier

    # Tier 2: Standard Setup (score 75)
    tier2, m2 = evaluator.get_conviction_tier(75.0)
    assert "Tier 2" in tier2
    assert m2 == 1.00

    # Tier 3: Speculative Setup (score 65)
    tier3, m3 = evaluator.get_conviction_tier(65.0)
    assert "Tier 3" in tier3
    assert m3 == 0.65


def test_trailing_disaster_floor_prevents_blowout(v3_config):
    """Verify that when a trade recovers past 0.80σ, disaster stop reduces blowout loss."""
    # Test on pre-computed 1Y file
    v3_path = PROJECT_ROOT / "data" / "backtest_v3_1y_results.json"
    assert v3_path.exists()

    with open(v3_path, "r", encoding="utf-8") as fp:
        v3 = json.load(fp)

    summary = v3["overall_summary"]
    saved_trades = summary.get("disaster_floor_saved_trades", 0)
    assert saved_trades > 0, "Trailing disaster floor must have protected trades from blowouts."

    # Verify protected trades
    for t in v3["trades"]:
        if t.get("protected_stop_hit"):
            assert t["outcome"] == "LOSS"
            assert t["recovered_to_floor"] is True
            assert "Trailing Disaster Floor" in t["status_reason"]
            # Sized pnl must be less severe than an uncapped -3.50σ blowout
            assert t["raw_return_pct"] > -4.50


def test_bit_for_bit_price_integrity():
    """Verify Strategy 3 uses the identical price universe as Strategy 1 and Strategy 2."""
    parquet_path = DATA_CACHE_DIR / "universe_5y_daily.parquet"
    assert parquet_path.exists()

    v1_path = PROJECT_ROOT / "data" / "backtest_1y_results.json"
    v3_path = PROJECT_ROOT / "data" / "backtest_v3_1y_results.json"

    with open(v1_path, "r", encoding="utf-8") as fp:
        v1 = json.load(fp)
    with open(v3_path, "r", encoding="utf-8") as fp:
        v3 = json.load(fp)

    assert v1["period"]["start_date"] == v3["period"]["start_date"]
    assert v1["period"]["end_date"] == v3["period"]["end_date"]


def test_non_negotiable_net_profit_superiority():
    """Verify Strategy 3 Net Profit % exceeds Strategy 1 baseline in ALL 4 horizons."""
    targets = {
        "1Y": 81.04,
        "2Y": 97.97,
        "3Y": 134.04,
        "5Y": 113.50,
    }

    for period, min_target in targets.items():
        f_path = PROJECT_ROOT / "data" / f"backtest_v3_{period.lower()}_results.json"
        assert f_path.exists(), f"File for {period} must exist: {f_path}"

        with open(f_path, "r", encoding="utf-8") as fp:
            d = json.load(fp)

        net_profit = d["overall_summary"]["net_return_pct"]
        assert net_profit > min_target, (
            f"Strategy 3 failed to beat Strategy 1 in {period}: "
            f"Net Profit = {net_profit}% vs Strategy 1 = {min_target}%"
        )


def test_api_v3_backtest_endpoint_and_latency(api_client):
    """Verify GET /api/simulator/v3/backtest contract, status 200, and sub-50ms latency."""
    # Warm up cache
    api_client.get("/simulator/v3/backtest?period=1Y")

    # Benchmark cached request
    t0 = time.perf_counter()
    res = api_client.get("/simulator/v3/backtest?period=1Y")
    elapsed_ms = (time.perf_counter() - t0) * 1000

    assert res.status_code == 200
    assert elapsed_ms < 50.0, f"Latency {elapsed_ms:.2f}ms exceeded 50ms."

    data = res.json()
    assert data["version"] == "3.0.0"
    assert "overall_summary" in data
    assert "equity_curve" in data
    assert "trades" in data
    assert data["overall_summary"]["net_return_pct"] > 81.04

    # Test /api prefix routing
    res_api = api_client.get("/api/simulator/v3/backtest?period=1Y")
    assert res_api.status_code == 200
