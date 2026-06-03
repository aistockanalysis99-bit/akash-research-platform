"""Tests for exit logic: stops, trailing, breakeven, partial TP, soft exits."""
from __future__ import annotations

from datetime import datetime, timezone

from engine.core.types import Position, StrategyParams
from engine.strategy.exits import (
    breakeven_stop_long,
    composite_stop_long,
    initial_stop_long,
    partial_tp_price_long,
    should_soft_exit_long,
    trail_stop_long,
)


def _make_pos(avg_price=100.0, initial_stop=95.0, trail_high=100.0, bars_in_trade=0) -> Position:
    return Position(
        symbol="TEST",
        qty=10,
        avg_price=avg_price,
        entry_time=datetime(2024, 1, 1, tzinfo=timezone.utc),
        initial_stop=initial_stop,
        initial_risk_dist=avg_price - initial_stop,
        trail_high=trail_high,
        bars_in_trade=bars_in_trade,
    )


def test_initial_stop_long():
    p = StrategyParams(stop_atr=2.5)
    s = initial_stop_long(entry_price=100, atr_value=2.0, p=p)
    assert s == 95.0


def test_trail_stop_uses_high_minus_multiple():
    p = StrategyParams(trail_atr=3.0)
    pos = _make_pos(trail_high=110.0)
    t = trail_stop_long(pos, atr_value=2.0, p=p)
    assert t == 104.0  # 110 - 3*2


def test_breakeven_kicks_in_after_threshold():
    p = StrategyParams(breakeven_rr=1.0)
    pos = _make_pos(avg_price=100, initial_stop=95)  # R = 5
    # Below threshold: 100 + 1*5 = 105. Price 104 -> no breakeven
    assert breakeven_stop_long(pos, current_high_since_entry=104, p=p) is None
    # At/above threshold -> breakeven (entry price)
    assert breakeven_stop_long(pos, current_high_since_entry=106, p=p) == 100.0


def test_composite_stop_takes_max():
    """Composite stop is max of base, trail, and breakeven."""
    p = StrategyParams(stop_atr=2.5, trail_atr=3.0, breakeven_rr=1.0)
    pos = _make_pos(avg_price=100, initial_stop=95, trail_high=120)
    # trail_stop = 120 - 3*2 = 114, breakeven (since high_since_entry=120 > 105) = 100, base=95
    # composite = max(95, 114, 100) = 114
    s = composite_stop_long(pos, atr_value=2.0, high_since_entry=120, p=p)
    assert s == 114.0


def test_composite_never_goes_below_initial():
    p = StrategyParams(trail_atr=3.0)
    pos = _make_pos(avg_price=100, initial_stop=95, trail_high=99)
    # trail = 99 - 3*2 = 93 (below initial); composite must take initial (95)
    s = composite_stop_long(pos, atr_value=2.0, high_since_entry=99, p=p)
    assert s == 95.0


def test_partial_tp_at_2r():
    p = StrategyParams(take_profit_rr=2.0)
    pos = _make_pos(avg_price=100, initial_stop=95)  # R = 5
    assert partial_tp_price_long(pos, p) == 110.0


def test_soft_exit_on_max_bars():
    p = StrategyParams(max_bars_in_trade=10)
    pos = _make_pos(bars_in_trade=10)
    should, reason = should_soft_exit_long(pos, mom_score=0.5, ema_slow=90, close_price=100, p=p)
    assert should and reason == "time_exit"


def test_soft_exit_on_score_decay():
    p = StrategyParams(exit_threshold=0.0, max_bars_in_trade=999)
    pos = _make_pos(bars_in_trade=5)
    should, reason = should_soft_exit_long(pos, mom_score=-0.1, ema_slow=90, close_price=100, p=p)
    assert should and reason == "soft_exit"


def test_soft_exit_on_close_below_slow_ema():
    p = StrategyParams(exit_threshold=-100.0, max_bars_in_trade=999)  # disable score check
    pos = _make_pos(bars_in_trade=5)
    should, reason = should_soft_exit_long(pos, mom_score=0.5, ema_slow=110, close_price=100, p=p)
    assert should and reason == "soft_exit"


def test_no_soft_exit_when_all_healthy():
    p = StrategyParams()
    pos = _make_pos(bars_in_trade=5)
    should, _ = should_soft_exit_long(pos, mom_score=0.5, ema_slow=90, close_price=100, p=p)
    assert not should
