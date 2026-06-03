"""Trade-level statistics."""
from __future__ import annotations

from typing import Any

from ..core.types import Trade


def trade_stats(trades: list[Trade]) -> dict[str, Any]:
    if not trades:
        return {
            "total_trades": 0,
            "winners": 0,
            "losers": 0,
            "win_rate": 0.0,
            "avg_win": 0.0,
            "avg_loss": 0.0,
            "avg_trade": 0.0,
            "profit_factor": 0.0,
            "expectancy": 0.0,
            "largest_win": 0.0,
            "largest_loss": 0.0,
            "avg_bars_held": 0.0,
            "avg_bars_held_winners": 0.0,
            "avg_bars_held_losers": 0.0,
            "max_consec_winners": 0,
            "max_consec_losers": 0,
            "total_commission": 0.0,
        }

    wins = [t for t in trades if t.pnl > 0]
    losses = [t for t in trades if t.pnl <= 0]

    total_wins = sum(t.pnl for t in wins)
    total_losses = abs(sum(t.pnl for t in losses))
    profit_factor = total_wins / total_losses if total_losses > 0 else float("inf") if total_wins > 0 else 0.0

    win_rate = len(wins) / len(trades)
    avg_win = total_wins / len(wins) if wins else 0.0
    avg_loss = -total_losses / len(losses) if losses else 0.0
    avg_trade = sum(t.pnl for t in trades) / len(trades)
    expectancy = win_rate * avg_win + (1 - win_rate) * avg_loss

    # Consecutive streaks
    max_w_streak = max_l_streak = 0
    cur_w = cur_l = 0
    for t in trades:
        if t.pnl > 0:
            cur_w += 1
            cur_l = 0
            max_w_streak = max(max_w_streak, cur_w)
        else:
            cur_l += 1
            cur_w = 0
            max_l_streak = max(max_l_streak, cur_l)

    return {
        "total_trades": len(trades),
        "winners": len(wins),
        "losers": len(losses),
        "win_rate": float(win_rate),
        "avg_win": float(avg_win),
        "avg_loss": float(avg_loss),
        "avg_trade": float(avg_trade),
        "profit_factor": float(profit_factor) if profit_factor != float("inf") else 999.0,
        "expectancy": float(expectancy),
        "largest_win": float(max((t.pnl for t in trades), default=0.0)),
        "largest_loss": float(min((t.pnl for t in trades), default=0.0)),
        "avg_bars_held": float(sum(t.bars_held for t in trades) / len(trades)),
        "avg_bars_held_winners": float(sum(t.bars_held for t in wins) / len(wins)) if wins else 0.0,
        "avg_bars_held_losers": float(sum(t.bars_held for t in losses) / len(losses)) if losses else 0.0,
        "max_consec_winners": int(max_w_streak),
        "max_consec_losers": int(max_l_streak),
        "total_commission": float(sum(t.commission_total for t in trades)),
    }


def concentration_stats(trades: list[Trade]) -> dict[str, Any]:
    if not trades:
        return {"top5_share": 0.0, "top1_symbol_share": 0.0}
    total_pnl = sum(t.pnl for t in trades)
    if total_pnl == 0:
        return {"top5_share": 0.0, "top1_symbol_share": 0.0}
    sorted_trades = sorted(trades, key=lambda t: t.pnl, reverse=True)
    top5 = sum(t.pnl for t in sorted_trades[:5])
    by_sym: dict[str, float] = {}
    for t in trades:
        by_sym[t.symbol] = by_sym.get(t.symbol, 0.0) + t.pnl
    top_sym = max(by_sym.values()) if by_sym else 0.0
    return {
        "top5_share": float(top5 / total_pnl),
        "top1_symbol_share": float(top_sym / total_pnl),
    }


def exit_reason_breakdown(trades: list[Trade]) -> dict[str, int]:
    out: dict[str, int] = {}
    for t in trades:
        key = t.exit_reason.value if hasattr(t.exit_reason, "value") else str(t.exit_reason)
        out[key] = out.get(key, 0) + 1
    return out
