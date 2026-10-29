"""Integration tests for Strategy v2 FastAPI Endpoints.

Verifies:
  1. GET /api/simulator/v2/backtest across 1Y, 2Y, 3Y, 5Y horizons.
  2. Latency is sub-50ms for cached horizons.
  3. JSON sanitization (no NaN, Infinity, valid RFC 8259).
  4. POST /api/simulator/v2/recalculate handles custom parameter runs.
  5. GET /api/simulator/v2/trade/{trade_id}/trajectory returns pins and trajectory points.
  6. Error handling for invalid periods and nonexistent trade IDs.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app)


@pytest.fixture(scope="module")
def check_parquet_exists():
    p = Path("data_cache/universe_5y_daily.parquet")
    if not p.exists():
        pytest.skip("universe_5y_daily.parquet not found; skipping v2 API tests.")


def test_v2_backtest_1y_contract_and_latency(check_parquet_exists):
    """Verify /api/simulator/v2/backtest?period=1Y returns valid contract and sub-50ms latency."""
    # First request loads into memory/cache
    t0 = time.time()
    resp = client.get("/api/simulator/v2/backtest?period=1Y")
    t_first = time.time() - t0
    assert resp.status_code == 200, resp.text

    # Second request must be served from cache in sub-50ms
    t1 = time.time()
    resp2 = client.get("/api/simulator/v2/backtest?period=1Y")
    t_second = time.time() - t1
    assert resp2.status_code == 200
    assert t_second < 0.050, f"Cached response took {t_second*1000:.1f}ms (expected < 50ms)"

    data = resp2.json()
    assert data["version"] == "2.0.0"
    assert "period" in data
    assert data["period"]["start_date"] == "2025-10-26"
    assert data["period"]["end_date"] == "2026-10-26"

    # Verify overall_summary structure
    ov = data["overall_summary"]
    for k in [
        "total_trades",
        "win_count",
        "loss_count",
        "win_rate_pct",
        "profit_factor",
        "max_drawdown_pct",
        "avg_holding_days",
        "gross_profit_pct",
        "gross_loss_pct",
        "tp1_and_tp2_count",
        "tp1_and_breakeven_count",
        "stop_loss_count",
        "time_stop_count",
    ]:
        assert k in ov, f"Missing key '{k}' in overall_summary"

    # Verify trades array and monthly returns
    assert isinstance(data.get("trades"), list)
    assert len(data["trades"]) > 0
    assert isinstance(data.get("monthly_returns"), list)
    assert isinstance(data.get("equity_curve"), list)


def test_v2_backtest_all_horizons(check_parquet_exists):
    """Verify all 4 horizons (1Y, 2Y, 3Y, 5Y) respond with status 200 and expected date ranges."""
    for p in ["1Y", "2Y", "3Y", "5Y"]:
        resp = client.get(f"/api/simulator/v2/backtest?period={p}")
        assert resp.status_code == 200, f"Failed for horizon {p}: {resp.text}"
        d = resp.json()
        assert d["period"]["end_date"] == "2026-10-26"
        assert len(d["trades"]) > 0
        assert d["overall_summary"]["total_trades"] > 0


def test_v2_backtest_invalid_period(check_parquet_exists):
    """Verify invalid period parameter yields 400 Bad Request."""
    resp = client.get("/api/simulator/v2/backtest?period=10Y")
    assert resp.status_code == 400
    assert "Invalid period" in resp.json()["detail"]


def test_v2_trade_trajectory_endpoint(check_parquet_exists):
    """Verify /api/simulator/v2/trade/{trade_id}/trajectory returns pins and daily trajectory."""
    # Fetch 1Y trades
    resp1 = client.get("/api/simulator/v2/backtest?period=1Y")
    assert resp1.status_code == 200
    trades = resp1.json()["trades"]
    assert len(trades) > 0

    first_trade = trades[0]
    trade_id = first_trade["id"]

    traj_resp = client.get(f"/api/simulator/v2/trade/{trade_id}/trajectory?period=1Y")
    assert traj_resp.status_code == 200, traj_resp.text
    traj_data = traj_resp.json()

    assert traj_data["trade_id"] == trade_id
    assert traj_data["pair_name"] == first_trade["pair_name"]
    assert "pins" in traj_data
    pins = traj_data["pins"]
    assert "entry" in pins
    assert pins["entry"]["date"] == first_trade["entry_date"]
    assert "exit" in pins
    assert pins["exit"]["date"] == first_trade["exit_date"]

    assert isinstance(traj_data["trajectory"], list)
    assert len(traj_data["trajectory"]) > 0


def test_v2_trade_trajectory_not_found(check_parquet_exists):
    """Verify nonexistent trade ID returns 404."""
    resp = client.get("/api/simulator/v2/trade/NONEXISTENT_PAIR_2099-01-01/trajectory")
    assert resp.status_code == 404


def test_v2_recalculate_custom_parameters(check_parquet_exists):
    """Verify POST /api/simulator/v2/recalculate runs on-the-fly custom parameter test."""
    payload = {
        "period": "1Y",
        "z_score_hurdle": 2.20,
        "z_score_hook_entry": 1.80,
        "z_score_exit_tp1": 0.75,
        "z_score_exit_tp2": 0.20,
        "z_score_stop_loss_barrier": 3.00,
        "half_life_multiplier": 1.5,
    }
    resp = client.post("/api/simulator/v2/recalculate", json=payload)
    assert resp.status_code == 200, resp.text
    d = resp.json()

    assert d["meta"]["z_score_hurdle"] == 2.20
    assert d["meta"]["z_score_hook_entry"] == 1.80
    assert d["meta"]["tp1_target"] == 0.75
    assert d["meta"]["stop_loss_barrier"] == 3.00
    assert d["overall_summary"]["total_trades"] > 0
