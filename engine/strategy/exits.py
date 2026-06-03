"""Exit management: stops (initial, breakeven, trailing), partial TP, soft exits.

All exits are computed as price levels; the engine decides which one was hit
during the bar by comparing to bar's high/low.
"""
from __future__ import annotations

from ..core.types import Position, StrategyParams


def initial_stop_long(entry_price: float, atr_value: float, p: StrategyParams) -> float:
    return entry_price - p.stop_atr * atr_value


def trail_stop_long(position: Position, atr_value: float, p: StrategyParams) -> float:
    """Trailing stop: highest_close_since_entry - trailATR * ATR."""
    return position.trail_high - p.trail_atr * atr_value


def breakeven_stop_long(position: Position, current_high_since_entry: float, p: StrategyParams) -> float | None:
    """Returns the entry price (breakeven) once price has moved breakevenRR * R favorably."""
    threshold = position.avg_price + p.breakeven_rr * position.initial_risk_dist
    if current_high_since_entry >= threshold:
        return position.avg_price
    return None


def composite_stop_long(
    position: Position,
    atr_value: float,
    high_since_entry: float,
    p: StrategyParams,
) -> float:
    """The actual stop price the engine should use this bar (max of base/trail/BE).

    Stops only ratchet up, never down: result is max(initial_stop, ...).
    """
    stops = [position.initial_stop, trail_stop_long(position, atr_value, p)]
    be = breakeven_stop_long(position, high_since_entry, p)
    if be is not None:
        stops.append(be)
    return max(stops)


def partial_tp_price_long(position: Position, p: StrategyParams) -> float:
    """Long take-profit at takeProfitRR * R above avg entry."""
    return position.avg_price + p.take_profit_rr * position.initial_risk_dist


def should_soft_exit_long(
    position: Position,
    mom_score: float | None,
    ema_slow: float | None,
    close_price: float,
    p: StrategyParams,
) -> tuple[bool, str]:
    """Return (should_exit, reason) for soft-exit conditions on a long."""
    if position.bars_in_trade >= p.max_bars_in_trade:
        return True, "time_exit"
    if mom_score is not None and mom_score < p.exit_threshold:
        return True, "soft_exit"
    if ema_slow is not None and close_price < ema_slow:
        return True, "soft_exit"
    return False, ""


def next_add_price_long(entry_price: float, atr_value: float, p: StrategyParams) -> float:
    return entry_price + p.add_atr * atr_value
