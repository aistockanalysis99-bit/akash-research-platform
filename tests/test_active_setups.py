"""Verification tests for Live Divergence Detection Engine and API endpoint."""
import pytest
from fastapi.testclient import TestClient
from api.main import app
from engine.detect_setups import calculate_pair_divergence
import pandas as pd
import numpy as np


def test_calculate_pair_divergence_no_lookahead():
    """Verify that calculate_pair_divergence only uses the historical window and produces correct outputs."""
    np.random.seed(42)
    # Generate 150 bars of synthetic cointegrated series
    n = 150
    b_prices = 100.0 + np.cumsum(np.random.normal(0, 1, n))
    beta_true = 1.5
    spread_noise = np.random.normal(0, 0.5, n)
    a_prices = beta_true * b_prices + spread_noise

    # Induce divergence in the last bar
    a_prices[-1] += 5.0  # Make spread spike up

    dates = pd.date_range("2024-01-01", periods=n, freq="B")
    s_a = pd.Series(a_prices, index=dates)
    s_b = pd.Series(b_prices, index=dates)

    # 90-day lookback
    res = calculate_pair_divergence(s_a, s_b, lookback_days=90)
    assert res is not None
    assert res["window_bars"] == 90
    assert abs(res["hedge_ratio"] - beta_true) < 0.2
    assert res["current_z_score"] > 2.0  # Spiked up


def test_calculate_pair_divergence_nan_handling():
    """Verify NaN and insufficient data handling (Constraint 1)."""
    # Too short series
    s_a = pd.Series([10.0, 11.0, 12.0])
    s_b = pd.Series([20.0, 21.0, 22.0])
    assert calculate_pair_divergence(s_a, s_b, lookback_days=90) is None

    # Series with NaNs
    dates = pd.date_range("2024-01-01", periods=100, freq="B")
    s_a = pd.Series(np.random.normal(100, 5, 100), index=dates)
    s_b = pd.Series(np.random.normal(100, 5, 100), index=dates)
    s_a.iloc[:40] = np.nan  # Leaves 60 common bars
    res = calculate_pair_divergence(s_a, s_b, lookback_days=90)
    assert res is not None
    assert res["window_bars"] == 60


def test_api_active_setups_endpoint():
    """Verify /api/pairs/active-setups returns 200 OK with correct JSON schema and setups (Constraint 3)."""
    client = TestClient(app)
    response = client.get("/api/pairs/active-setups")
    assert response.status_code == 200

    payload = response.json()
    assert "metadata" in payload
    assert "setups" in payload
    assert payload["metadata"]["threshold"] == 2.0

    setups = payload["setups"]
    assert len(setups) >= 1, "Must contain at least 1 active setup"

    required_keys = ["ticker_a", "ticker_b", "current_z_score", "hedge_ratio", "trade_direction"]
    for s in setups:
        for k in required_keys:
            assert k in s, f"Missing key {k} in setup"
        z = s["current_z_score"]
        assert abs(z) >= 2.0, f"Expected |Z| >= 2.0, got {z}"
        if z >= 2.0:
            assert "Short" in s["trade_direction"] and "Long" in s["trade_direction"]
        elif z <= -2.0:
            assert "Long" in s["trade_direction"] and "Short" in s["trade_direction"]


def test_api_active_setups_with_filtering():
    """Test filtering by threshold and sector."""
    client = TestClient(app)
    response = client.get("/api/pairs/active-setups?threshold=2.5")
    assert response.status_code == 200
    data = response.json()
    for s in data["setups"]:
        assert abs(s["current_z_score"]) >= 2.5


def test_api_pair_history_endpoint():
    """Test 5-year history endpoint for TradingView-style charts."""
    client = TestClient(app)
    response = client.get("/pairs/FTV/ODFL/history")
    assert response.status_code == 200
    data = response.json()
    assert data["ticker_a"] == "FTV"
    assert data["ticker_b"] == "ODFL"
    assert "bars" in data
    assert len(data["bars"]) >= 60
    assert "current_z_score" in data
    assert "hedge_ratio" in data
    assert "relative_spread_vol_pct" in data
    assert "spread_tier" in data
    assert "return_5y_a" in data
    assert "return_5y_b" in data
    assert "trend_a" in data
    assert "trend_b" in data
    assert "trend_co_movement_score" in data
    # Verify bar structure
    bar = data["bars"][-1]
    assert "price_a" in bar
    assert "price_b" in bar
    assert "price_b_overlay" in bar
    assert "return_pct_a" in bar
    assert "return_pct_b" in bar
    assert "spread" in bar
    assert "z_score" in bar


def test_api_active_setups_low_spread_and_composite_ranking():
    """Verify co-movement, spread tightness metrics, and low spread filtering."""
    client = TestClient(app)
    response = client.get("/api/pairs/active-setups")
    assert response.status_code == 200
    data = response.json()
    setups = data["setups"]
    assert len(setups) >= 1

    # Check spread tightness and co-movement fields
    for s in setups:
        assert "relative_spread_vol_pct" in s
        assert "spread_tier" in s
        assert "composite_score" in s
        assert "co_movement_score" in s
        assert "is_low_spread" in s
        assert "is_medium_to_low_spread" in s
        assert "return_5y_a" in s
        assert "return_5y_b" in s
        assert "trend_a" in s
        assert "trend_b" in s
        assert s["relative_spread_vol_pct"] >= 0.0

    # Top setup should have highest composite score and low spread
    top_setup = setups[0]
    assert top_setup["composite_score"] >= 70.0, "Top setup should have high composite quality score"
    assert top_setup["is_low_spread"] is True, "Top setup should have low spread"
    assert top_setup["relative_spread_vol_pct"] <= 5.0, "Top setup spread volatility should be <= 5%"

    # Test low_spread_only filter
    resp_low_spread = client.get("/api/pairs/active-setups?low_spread_only=true")
    assert resp_low_spread.status_code == 200
    low_setups = resp_low_spread.json()["setups"]
    for s in low_setups:
        assert s["is_low_spread"] is True
        assert s["relative_spread_vol_pct"] <= 5.0

    # Test medium_to_low_spread_only filter (supports <= 7.0% spread vol)
    resp_med_spread = client.get("/api/pairs/active-setups?medium_to_low_spread_only=true")
    assert resp_med_spread.status_code == 200
    med_setups = resp_med_spread.json()["setups"]
    for s in med_setups:
        assert s["is_medium_to_low_spread"] is True
        assert s["relative_spread_vol_pct"] <= 7.0

    # Test max_spread_vol filter
    resp_max_vol = client.get("/api/pairs/active-setups?max_spread_vol=3.0")
    assert resp_max_vol.status_code == 200
    for s in resp_max_vol.json()["setups"]:
        assert s["relative_spread_vol_pct"] <= 3.0


def test_api_active_setups_tradeable_now_and_order_blueprint():
    """Verify that setups report ripe tradeable spread dislocation, target exit, stop loss, and order blueprint."""
    client = TestClient(app)
    response = client.get("/api/pairs/active-setups?tradeable_now_only=true")
    assert response.status_code == 200
    data = response.json()
    setups = data["setups"]
    assert len(setups) >= 1

    for s in setups:
        assert s["is_tradeable_now"] is True
        assert s["is_medium_to_low_spread"] is True
        assert abs(s["current_z_score"]) >= 2.0
        assert s["spread_dislocation"] > 0.0
        assert s["expected_reversion_return_pct"] >= 1.5
        assert s["target_exit_spread"] is not None
        assert s["stop_loss_spread"] is not None
        assert s["risk_reward_ratio"] >= 1.0
        assert s["trade_readiness"] in ["READY TO TRADE NOW", "ACTIVE SETUP"]
        assert "Short" in s["trade_direction"] or "Long" in s["trade_direction"]
        # Verify exact stock buy/sell target and stop loss price blueprints
        assert s["action_a"] in ["BUY LONG", "SELL SHORT"]
        assert s["action_b"] in ["BUY LONG", "SELL SHORT"]
        assert s["exit_action_a"] in ["SELL TO CLOSE", "BUY TO COVER"]
        assert s["exit_action_b"] in ["SELL TO CLOSE", "BUY TO COVER"]
        assert s["target_price_a"] > 0.0
        assert s["target_price_b"] > 0.0
        assert s["stop_loss_price_a"] > 0.0
        assert s["stop_loss_price_b"] > 0.0
        assert s["expected_profit_dollar_a"] >= 0.0
        assert s["expected_profit_dollar_b"] >= 0.0
        assert s["pair_unit_cost"] > 0.0


def test_api_strategy_config_get_and_update():
    """Verify that pair trading strategy configuration can be loaded and dynamically updated via API."""
    client = TestClient(app)
    resp = client.get("/api/pairs/config")
    assert resp.status_code == 200
    cfg = resp.json()
    assert "divergence_triggers" in cfg
    assert "gauntlet_screening_thresholds" in cfg
    assert "spread_volatility_tiers" in cfg
    assert "trade_readiness_conditions" in cfg
    assert cfg["divergence_triggers"]["z_score_entry_threshold"] == 2.0
    assert cfg["spread_volatility_tiers"]["max_allowed_spread_vol_pct"] == 7.0

    # Test updating a parameter with guaranteed rollback in finally block
    update_payload = {
        "divergence_triggers": {
            "z_score_entry_threshold": 2.1
        }
    }
    try:
        update_resp = client.post("/api/pairs/config", json=update_payload)
        assert update_resp.status_code == 200
        updated = update_resp.json()["config"]
        assert updated["divergence_triggers"]["z_score_entry_threshold"] == 2.1
    finally:
        # Revert back to 2.0 to preserve baseline
        client.post("/api/pairs/config", json={"divergence_triggers": {"z_score_entry_threshold": 2.0}})




