"""Integration tests for FastAPI Simulator Router.

Tests all simulator endpoints using FastAPI TestClient:
  - POST /api/simulator/init
  - GET  /api/simulator/scan (Latency and schema validation)
  - GET  /api/simulator/step
  - GET  /api/simulator/pair-chart (Constraint 1: Zero future leakage when reveal=False)
  - POST /api/simulator/reveal
  - GET  /api/simulator/batch-scorecard
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app)

TEST_SIM_DATE = "2024-03-15"
TEST_PAIR_A = "MS"
TEST_PAIR_B = "RF"


@pytest.fixture(scope="module")
def check_parquet_exists():
    parquet_path = Path("data_cache/universe_5y_daily.parquet")
    if not parquet_path.exists():
        pytest.skip("universe_5y_daily.parquet not found; skipping API simulator tests.")


def test_init_endpoint(check_parquet_exists):
    """Verify /api/simulator/init initializes anchor date and parameters."""
    payload = {
        "anchor_date": TEST_SIM_DATE,
        "lookback_days": 90,
        "min_z_score": 2.0,
        "max_adf_pvalue": 0.05,
        "min_correlation": 0.85,
        "max_horizon_days": 30,
    }
    response = client.post("/api/simulator/init", json=payload)
    assert response.status_code == 200, response.text
    data = response.json()

    assert data["status"] == "initialized"
    assert data["anchor_date"] == TEST_SIM_DATE
    assert data["current_date"] == TEST_SIM_DATE
    assert data["total_trading_days"] >= 1000
    assert data["intact_pairs_count"] > 0
    assert data["parameters"]["lookback_days"] == 90


def test_scan_endpoint_latency_and_schema(check_parquet_exists):
    """Constraint 3: /api/simulator/scan must return 200 OK with correct schema and < 100ms response."""
    # Warm up first call
    _ = client.get(f"/api/simulator/scan?current_date={TEST_SIM_DATE}&top_n=10&only_active_setups=false")

    # Measure latency on second call
    t0 = time.perf_counter()
    response = client.get(f"/api/simulator/scan?current_date={TEST_SIM_DATE}&top_n=10&only_active_setups=false")
    duration_ms = (time.perf_counter() - t0) * 1000.0

    assert response.status_code == 200, response.text
    data = response.json()

    assert data["current_date"] == TEST_SIM_DATE
    assert "setups" in data
    assert isinstance(data["setups"], list)
    assert len(data["setups"]) > 0

    # Verify JSON Schema of first setup
    first_setup = data["setups"][0]
    required_keys = [
        "ticker_a", "ticker_b", "pair_name", "target_date", "direction",
        "hedge_ratio", "alpha", "r_squared", "correlation", "current_z_score",
        "abs_z_score", "current_spread", "spread_mean", "spread_std",
        "target_spread_mean", "target_spread_80pct", "stop_loss_spread",
        "price_a_entry", "price_b_entry", "adf_tstat", "adf_pvalue",
        "half_life_days", "zero_crossings", "relative_spread_vol_pct",
        "spread_tier", "composite_score", "is_setup", "window_bars"
    ]
    for k in required_keys:
        assert k in first_setup, f"Missing key '{k}' in setup schema"

    # Verify Constraint 2: No NaN or Infinity in raw text
    raw_text = response.text
    assert "NaN" not in raw_text
    assert "Infinity" not in raw_text

    # Verify Constraint 3: Sub-100ms response time
    assert duration_ms < 100.0, f"Latency violation: {duration_ms:.2f}ms >= 100ms"


def test_step_endpoint(check_parquet_exists):
    """Verify /api/simulator/step advances/reverses the simulated date."""
    response = client.get(f"/api/simulator/step?current_date={TEST_SIM_DATE}&direction=+1")
    assert response.status_code == 200, response.text
    data = response.json()

    assert data["previous_date"] == TEST_SIM_DATE
    assert data["current_date"] > TEST_SIM_DATE
    assert data["direction"] == "+1"
    assert data["current_index"] > 0

    # Step backward
    next_date = data["current_date"]
    resp_back = client.get(f"/api/simulator/step?current_date={next_date}&direction=-1")
    assert resp_back.status_code == 200
    assert resp_back.json()["current_date"] == TEST_SIM_DATE


def test_pair_chart_constraint_1_no_future_leakage_when_unrevealed(check_parquet_exists):
    """Constraint 1: When reveal=False, /api/simulator/pair-chart MUST NOT send ANY future data."""
    url = f"/api/simulator/pair-chart?ticker_a={TEST_PAIR_A}&ticker_b={TEST_PAIR_B}&current_date={TEST_SIM_DATE}&reveal=false"
    response = client.get(url)
    assert response.status_code == 200, response.text
    data = response.json()

    assert data["reveal"] is False
    # CRITICAL: forward data MUST BE None / Null
    assert data["forward_bars"] is None, "Constraint 1 Violation: forward_bars sent when reveal=false"
    assert data["forward_outcome"] is None, "Constraint 1 Violation: forward_outcome sent when reveal=false"

    # Verify every historical bar is strictly t <= current_date
    assert len(data["historical_bars"]) > 0
    for bar in data["historical_bars"]:
        assert bar["date"] <= TEST_SIM_DATE, (
            f"Constraint 1 Violation: Historical bar date {bar['date']} > current_date {TEST_SIM_DATE}"
        )


def test_pair_chart_revealed(check_parquet_exists):
    """Verify /api/simulator/pair-chart returns forward bars and outcome when reveal=true."""
    url = f"/api/simulator/pair-chart?ticker_a={TEST_PAIR_A}&ticker_b={TEST_PAIR_B}&current_date={TEST_SIM_DATE}&reveal=true"
    response = client.get(url)
    assert response.status_code == 200, response.text
    data = response.json()

    assert data["reveal"] is True
    assert data["forward_bars"] is not None
    assert len(data["forward_bars"]) > 0
    assert data["forward_outcome"] is not None
    assert data["forward_outcome"]["outcome"] in ("WIN", "LOSS", "NEUTRAL")

    # Forward bar dates must be strictly > current_date
    for fb in data["forward_bars"]:
        assert fb["date"] > TEST_SIM_DATE


def test_reveal_endpoint(check_parquet_exists):
    """Verify POST /api/simulator/reveal returns valid forward evaluation result."""
    payload = {
        "ticker_a": TEST_PAIR_A,
        "ticker_b": TEST_PAIR_B,
        "target_date": TEST_SIM_DATE,
        "max_horizon_days": 30,
        "lookback_days": 90,
    }
    response = client.post("/api/simulator/reveal", json=payload)
    assert response.status_code == 200, response.text
    data = response.json()

    assert data["pair_name"] == f"{TEST_PAIR_A}/{TEST_PAIR_B}"
    assert data["outcome"] in ("WIN", "LOSS", "NEUTRAL")
    assert data["exit_days_held"] > 0
    assert "path" in data
    assert len(data["path"]) > 0


def test_batch_scorecard_endpoint(check_parquet_exists):
    """Verify GET /api/simulator/batch-scorecard returns aggregate metrics and clean RFC JSON."""
    url = f"/api/simulator/batch-scorecard?target_date={TEST_SIM_DATE}&top_n=5&max_horizon_days=30"
    response = client.get(url)
    assert response.status_code == 200, response.text
    data = response.json()

    assert data["target_date"] == TEST_SIM_DATE
    assert data["total_setups"] > 0
    assert "win_rate_pct" in data
    assert "profit_factor" in data
    assert "avg_return_pct" in data
    assert isinstance(data["evaluations"], list)

    # Constraint 2 check: Zero raw NaN/Infinity in nested response text
    raw_text = response.text
    assert "NaN" not in raw_text
    assert "Infinity" not in raw_text


def test_validation_identical_tickers_returns_400(check_parquet_exists):
    """Verify requesting identical tickers (A == B) returns HTTP 400 Bad Request."""
    url = f"/api/simulator/pair-chart?ticker_a=AAPL&ticker_b=AAPL&current_date={TEST_SIM_DATE}"
    resp = client.get(url)
    assert resp.status_code == 400
    assert "identical" in resp.json()["detail"].lower()


def test_validation_out_of_bounds_date_returns_400(check_parquet_exists):
    """Verify requesting a date outside 5Y history range returns HTTP 400."""
    url = "/api/simulator/scan?current_date=1999-01-01"
    resp = client.get(url)
    assert resp.status_code == 400
    assert "out of bounds" in resp.json()["detail"].lower()


def test_api_prefix_stripping_middleware_compatibility(check_parquet_exists):
    """Verify both /api/simulator/scan and /simulator/scan resolve cleanly via middleware."""
    resp_with_prefix = client.get(f"/api/simulator/scan?current_date={TEST_SIM_DATE}&top_n=5&only_active_setups=false")
    assert resp_with_prefix.status_code == 200

    resp_direct = client.get(f"/simulator/scan?current_date={TEST_SIM_DATE}&top_n=5&only_active_setups=false")
    assert resp_direct.status_code == 200
    assert resp_with_prefix.json()["total_setups_found"] == resp_direct.json()["total_setups_found"]

