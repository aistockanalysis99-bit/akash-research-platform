"""Tests for the hybrid portfolio layer."""
from __future__ import annotations

from datetime import datetime, timezone

from engine.core.types import Position, StrategyParams
from engine.portfolio.hybrid import EntryCandidate, filter_candidates


def _cand(sym, score, qty=10, price=100, rv=0.20):
    return EntryCandidate(
        symbol=sym, score=score, ref_price=price,
        atr_value=2.0, realized_vol=rv, initial_qty_proposed=qty,
    )


def _pos(sym, qty=10, price=100):
    return Position(
        symbol=sym, qty=qty, avg_price=price,
        entry_time=datetime(2024, 1, 1, tzinfo=timezone.utc),
        initial_stop=price * 0.95,
        initial_risk_dist=price * 0.05,
        trail_high=price,
    )


def test_drops_existing_open_positions():
    p = StrategyParams(max_concurrent_positions=10)
    open_pos = {"AAPL": _pos("AAPL")}
    cands = [_cand("AAPL", 1.0), _cand("MSFT", 0.5)]
    out = filter_candidates(cands, open_pos, equity=100_000, p=p)
    assert all(c.symbol != "AAPL" for c in out)


def test_takes_top_n_by_score_when_capped():
    p = StrategyParams(max_concurrent_positions=2, portfolio_vol_target=10.0,  # very loose
                       max_portfolio_gross=10.0)
    cands = [_cand("A", 0.1), _cand("B", 0.5), _cand("C", 0.9)]
    out = filter_candidates(cands, open_positions={}, equity=100_000, p=p)
    chosen = {c.symbol for c in out}
    assert chosen == {"B", "C"}


def test_respects_concurrent_cap_with_existing_positions():
    p = StrategyParams(max_concurrent_positions=3, portfolio_vol_target=10.0,
                       max_portfolio_gross=10.0)
    open_pos = {"X": _pos("X"), "Y": _pos("Y")}
    cands = [_cand("A", 0.5), _cand("B", 0.4)]
    out = filter_candidates(cands, open_pos, equity=100_000, p=p)
    # Only 1 slot left
    assert len(out) == 1
    assert out[0].symbol == "A"


def test_gross_cap_scales_down():
    """Large candidates should be scaled down by gross cap."""
    p = StrategyParams(
        max_concurrent_positions=10,
        portfolio_vol_target=10.0,  # not binding
        max_portfolio_gross=0.5,    # 50% of equity max
        fractional_shares=True,     # avoid floor zeroing
    )
    # 3 candidates, 1000 shares each at $100 = $100k each, $300k total
    cands = [_cand("A", 1, qty=1000), _cand("B", 0.9, qty=1000), _cand("C", 0.8, qty=1000)]
    out = filter_candidates(cands, {}, equity=100_000, p=p)
    total_notional = sum(c.initial_qty_proposed * c.ref_price for c in out)
    # Should be at or below 50% of equity = $50k
    assert total_notional <= 50_000 + 1


def test_whole_shares_drops_sub_one():
    p = StrategyParams(
        max_concurrent_positions=10,
        portfolio_vol_target=0.001,  # forces aggressive scaling down
        fractional_shares=False,
    )
    cands = [_cand("A", 0.5, qty=1, price=100, rv=0.30)]
    out = filter_candidates(cands, {}, equity=100_000, p=p)
    # After vol scaling, qty < 1; floor → 0; dropped
    assert all(c.initial_qty_proposed >= 1 for c in out)
