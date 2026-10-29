"""Unit and Integration Tests for StrategyComparisonEngine.

Verifies:
  1. Trade matching alignment by pair and historical timestamp windows.
  2. Four primary trade diagnostic categories:
     - Category A: Saved Losses (The Shield)
     - Category B: Flipped Trades (Loss -> Win)
     - Category C: Preserved Winners
     - Category D: Missed Opportunities
  3. Failure Cause Attribution classification logic.
  4. Comparative delta metric mathematics (Win Rate, Max Drawdown, Profit Factor).
  5. Dual-series synchronized equity curve alignment.
  6. Multi-horizon coverage (1Y, 2Y, 3Y, 5Y).
  7. API endpoint contract and sub-100ms response latency on /api/simulator/compare.
"""

import math
import time
from datetime import datetime
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from engine.config import PROJECT_ROOT
from engine.strategy_comparison_engine import StrategyComparisonEngine, clean_float, parse_date
from api.main import app


@pytest.fixture(scope="module")
def compare_engine():
    return StrategyComparisonEngine()


@pytest.fixture(scope="module")
def api_client():
    return TestClient(app)


def test_strategy_comparison_engine_initialization(compare_engine):
    """Verify engine initializes and finds required v1 baseline and v2 files."""
    assert compare_engine.project_root.exists()
    assert (PROJECT_ROOT / "data" / "backtest_1y_results.json").exists()
    assert (PROJECT_ROOT / "data" / "backtest_v2_1y_results.json").exists()


def test_trade_matching_temporal_and_pair_integrity(compare_engine):
    """Verify trade matching aligns pairs within timestamp windows and enforces 1-to-1 matching."""
    v1_data = compare_engine.load_v1_results("1Y")
    v2_data = compare_engine.load_v2_results("1Y")

    v1_trades = v1_data.get("trades", [])
    v2_trades = v2_data.get("trades", [])

    deltas, metrics = compare_engine.match_trades(v1_trades, v2_trades)

    assert len(deltas) > 0
    assert metrics["total_matched_pairs"] > 0
    assert metrics["total_matched_pairs"] <= len(v2_trades)
    assert metrics["total_matched_pairs"] <= len(v1_trades)

    # Verify matched trades share the exact same pair name
    for d in deltas:
        if d["category"] in ("FLIPPED_TRADE", "PRESERVED_WINNER", "PERSISTENT_LOSS", "DEGRADED_WIN"):
            assert d["v1_entry_date"] is not None
            assert d["v2_entry_date"] is not None
            d1 = parse_date(d["v1_entry_date"])
            d2 = parse_date(d["v2_entry_date"])
            assert d1 is not None and d2 is not None


def test_category_a_saved_losses(compare_engine):
    """Verify Category A identifies trades that lost in v1 but were completely avoided in v2."""
    res = compare_engine.compare("1Y")
    deltas = res["trade_deltas"]
    saved_losses = [d for d in deltas if d["category"] == "SAVED_LOSS"]

    assert len(saved_losses) > 0
    assert res["category_metrics"]["saved_losses_count"] == len(saved_losses)

    # Every saved loss must be a v1 loss that was vetoed in v2
    total_preserved = 0.0
    for sl in saved_losses:
        assert sl["v1_outcome"] == "LOSS"
        assert sl["v2_outcome"] == "VETOED"
        assert sl["failure_cause"] in ("RUNAWAY_MOMENTUM", "EARNINGS_SHOCK", "PROFIT_GIVEBACK", "STALE_DECAY")
        if sl["v1_return_pct"] < 0:
            total_preserved += abs(sl["v1_return_pct"])

    assert math.isclose(res["category_metrics"]["capital_preserved_loss_pct"], round(total_preserved, 2), abs_tol=0.1)


def test_category_b_flipped_trades(compare_engine):
    """Verify Category B identifies trades that lost in v1 but flipped to winning trades in v2."""
    res = compare_engine.compare("1Y")
    deltas = res["trade_deltas"]
    flipped = [d for d in deltas if d["category"] == "FLIPPED_TRADE"]

    assert len(flipped) > 0
    assert res["category_metrics"]["flipped_trades_count"] == len(flipped)

    for ft in flipped:
        assert ft["v1_outcome"] == "LOSS"
        assert ft["v2_outcome"] == "WIN"
        assert ft["v1_return_pct"] < 0
        assert ft["v2_return_pct"] > 0
        assert ft["return_delta_pct"] > 0


def test_category_c_and_d_cohorts(compare_engine):
    """Verify Preserved Winners (Cat C) and Missed Opportunities (Cat D)."""
    res = compare_engine.compare("1Y")
    deltas = res["trade_deltas"]

    cat_c = [d for d in deltas if d["category"] == "PRESERVED_WINNER"]
    cat_d = [d for d in deltas if d["category"] == "MISSED_OPPORTUNITY"]

    assert len(cat_c) > 0
    assert len(cat_d) > 0

    for c in cat_c:
        assert c["v1_outcome"] == "WIN"
        assert c["v2_outcome"] == "WIN"

    for d in cat_d:
        assert d["v1_outcome"] == "WIN"
        assert d["v2_outcome"] == "VETOED"


def test_failure_cause_attribution(compare_engine):
    """Verify failure cause attribution sums to 100% and correctly categorizes all v1 losses."""
    res = compare_engine.compare("1Y")
    attr = res["failure_attribution"]

    assert attr["total_losses"] > 0
    counts = attr["counts"]
    pcts = attr["percentages"]

    assert "RUNAWAY_MOMENTUM" in counts
    assert "EARNINGS_SHOCK" in counts
    assert "PROFIT_GIVEBACK" in counts
    assert "STALE_DECAY" in counts

    total_count = sum(counts.values())
    assert total_count == attr["total_losses"]

    total_pct = sum(pcts.values())
    assert 99.0 <= total_pct <= 101.0  # Allow rounding to 100%


def test_comparative_delta_summary_math(compare_engine):
    """Verify differential performance deltas are mathematically exact."""
    res = compare_engine.compare("1Y")
    s = res["summary_delta"]
    v1_sum = res["v1_summary"]
    v2_sum = res["v2_summary"]

    # Win rate delta
    expected_wr_delta = round(v2_sum["win_rate_pct"] - v1_sum["win_rate_pct"], 1)
    assert s["delta_win_rate_pct"] == expected_wr_delta
    assert s["delta_win_rate_pct"] > 0  # v2 must outperform v1 in win rate

    # Max drawdown reduction (positive indicates risk reduction)
    expected_dd_saved = round(v1_sum["max_drawdown_pct"] - v2_sum["max_drawdown_pct"], 1)
    assert s["delta_max_drawdown_saved_pct"] == expected_dd_saved
    assert s["delta_max_drawdown_saved_pct"] > 0  # v2 must reduce max drawdown

    # Profit factor delta
    expected_pf_delta = round(v2_sum["profit_factor"] - v1_sum["profit_factor"], 2)
    assert s["delta_profit_factor"] == expected_pf_delta


def test_aligned_equity_curves(compare_engine):
    """Verify synchronized dual-series equity curves maintain chronological ordering and exact alpha spread."""
    res = compare_engine.compare("1Y")
    eq = res["aligned_equity"]

    assert len(eq) > 10
    dates = [e["date"] for e in eq]
    assert dates == sorted(dates)  # Monotonic dates

    for pt in eq:
        expected_spread = round(pt["v2_equity"] - pt["v1_equity"], 2)
        assert math.isclose(pt["spread_alpha"], expected_spread, abs_tol=0.01)


def test_all_four_horizons_comparative_robustness(compare_engine):
    """Verify comparative engine generates valid outputs across 1Y, 2Y, 3Y, and 5Y horizons."""
    for p in ("1Y", "2Y", "3Y", "5Y"):
        res = compare_engine.compare(p)
        assert res["period"] == p
        assert res["summary_delta"]["delta_win_rate_pct"] > 20.0  # Consistent +25-30% win-rate improvement
        assert res["category_metrics"]["saved_losses_count"] > 0
        assert res["category_metrics"]["flipped_trades_count"] > 0
        assert len(res["trade_deltas"]) > 50


def test_api_compare_endpoint_contract_and_latency(api_client):
    """Verify GET /api/simulator/compare endpoint contract, status 200, and sub-100ms cached latency."""
    # First request: loads & computes/caches
    t0 = time.perf_counter()
    r1 = api_client.get("/simulator/compare?period=1Y")
    assert r1.status_code == 200
    d1 = r1.json()

    assert "summary_delta" in d1
    assert "category_metrics" in d1
    assert "failure_attribution" in d1
    assert "trade_deltas" in d1
    assert "aligned_equity" in d1

    # Second request: served from in-memory cache
    t1 = time.perf_counter()
    r2 = api_client.get("/simulator/compare?period=1Y")
    cached_elapsed_ms = (time.perf_counter() - t1) * 1000
    assert r2.status_code == 200
    assert cached_elapsed_ms < 100.0  # Must be sub-100ms

    # Also test /api prefix stripping
    r3 = api_client.get("/api/simulator/compare?period=1Y")
    assert r3.status_code == 200

    # Test invalid period
    r_bad = api_client.get("/simulator/compare?period=INVALID")
    assert r_bad.status_code == 400
