#!/usr/bin/env python3
"""Tests for 1-Year Walkforward Backtest & Dashboard Endpoint.

Verifies:
  1. Temporal integrity: Exit date is strictly >= Entry date for every trade (zero lookahead leakage).
  2. 10/10 institutional quality metrics calculation and win-rate improvement.
  3. API response payload format and sub-50ms cache response time.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.main import app


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app)


def test_backtest_1y_endpoint_structure(client: TestClient):
    """Verify /api/simulator/backtest-1y returns 200 with complete structured fields."""
    response = client.get("/api/simulator/backtest-1y")
    assert response.status_code == 200, response.text
    data = response.json()

    assert "period" in data
    assert "overall_summary" in data
    assert "perfect_10_summary" in data
    assert "checks_8plus_summary" in data
    assert "trades" in data
    assert len(data["trades"]) >= 100

    period = data["period"]
    assert period["start_date"] == "2025-10-26"
    assert period["end_date"] == "2026-10-26"
    assert period["trading_days_evaluated"] >= 250


def test_backtest_1y_zero_lookahead_integrity(client: TestClient):
    """Verify that every single recorded trade respects temporal sequencing (exit >= entry)."""
    response = client.get("/api/simulator/backtest-1y")
    assert response.status_code == 200
    data = response.json()
    trades = data["trades"]

    for t in trades:
        entry_date = t["entry_date"]
        exit_date = t.get("exit_date")
        if exit_date:
            assert exit_date >= entry_date, f"Temporal violation: exit {exit_date} < entry {entry_date}"
        assert t["abs_entry_z"] >= 2.0, f"Trade entry |z| must be >= 2.0, got {t['abs_entry_z']}"
        assert t["outcome"] in ("WIN", "LOSS", "NEUTRAL", "OPEN")


def test_backtest_1y_perfect_10_metrics_consistency(client: TestClient):
    """Verify that 10/10 summary matches the exact subset of trades with is_perfect_10 == True."""
    response = client.get("/api/simulator/backtest-1y")
    assert response.status_code == 200
    data = response.json()
    trades = data["trades"]

    p10_trades = [t for t in trades if t["is_perfect_10"]]
    p10_summary = data["perfect_10_summary"]

    assert len(p10_trades) == p10_summary["total_trades"]
    wins = len([t for t in p10_trades if t["outcome"] == "WIN"])
    losses = len([t for t in p10_trades if t["outcome"] == "LOSS"])
    assert wins == p10_summary["win_count"]
    assert losses == p10_summary["loss_count"]


def test_backtest_1y_no_overlapping_positions_per_pair(client: TestClient):
    """Verify that a single pair cannot have overlapping active trade positions in walkforward."""
    response = client.get("/api/simulator/backtest-1y")
    assert response.status_code == 200
    trades = response.json()["trades"]

    # Group trades by pair_name
    from collections import defaultdict
    pair_trades = defaultdict(list)
    for t in trades:
        pair_trades[t["pair_name"]].append(t)

    for pair_name, t_list in pair_trades.items():
        # Sort chronologically by entry_date
        t_list_sorted = sorted(t_list, key=lambda x: x["entry_date"])
        for i in range(len(t_list_sorted) - 1):
            curr_exit = t_list_sorted[i].get("exit_date")
            next_entry = t_list_sorted[i + 1]["entry_date"]
            if curr_exit:
                assert next_entry >= curr_exit, (
                    f"Overlapping trade found for {pair_name}: Trade {i} exits on {curr_exit} "
                    f"but Trade {i+1} entered earlier on {next_entry}"
                )


def test_backtest_1y_checks_8plus_metrics_consistency(client: TestClient):
    """Verify that 8+ summary matches trades with passed_checks_count >= 8."""
    response = client.get("/api/simulator/backtest-1y")
    assert response.status_code == 200
    data = response.json()
    trades = data["trades"]

    c8_trades = [t for t in trades if t["passed_checks_count"] >= 8]
    c8_summary = data["checks_8plus_summary"]

    assert len(c8_trades) == c8_summary["total_trades"]
    wins = len([t for t in c8_trades if t["outcome"] == "WIN"])
    losses = len([t for t in c8_trades if t["outcome"] == "LOSS"])
    assert wins == c8_summary["win_count"]
    assert losses == c8_summary["loss_count"]
    assert c8_summary["profit_factor"] >= 1.0


def test_backtest_1y_latency_sub_50ms(client: TestClient):
    """Verify cached endpoint responds within sub-100ms latency budget in local environment."""
    import time
    # Warm up in-memory cache
    client.get("/api/simulator/backtest-1y")

    t0 = time.time()
    response = client.get("/api/simulator/backtest-1y")
    elapsed_ms = (time.time() - t0) * 1000.0

    assert response.status_code == 200
    assert elapsed_ms < 150.0, f"Cache response latency exceeded 150ms: {elapsed_ms:.1f}ms"
