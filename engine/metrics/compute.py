"""Compose all metrics into a single dict for storage and display."""
from __future__ import annotations

from typing import Any

from ..core.types import BacktestConfig, EquityPoint, Trade
from .returns import (
    cagr,
    daily_returns,
    equity_to_series,
    monthly_returns,
    rolling_12m_return,
    total_return,
)
from .risk import (
    annualized_vol,
    calmar_ratio,
    drawdown_series,
    mar_ratio,
    max_drawdown,
    max_drawdown_duration_days,
    sharpe_ratio,
    sortino_ratio,
)
from .trade_stats import (
    concentration_stats,
    exit_reason_breakdown,
    trade_stats,
)


def compute_all_metrics(
    equity_curve: list[EquityPoint],
    trades: list[Trade],
    config: BacktestConfig,
) -> dict[str, Any]:
    """Compute the full metrics dict — what UI / DB / API all consume."""
    eq = equity_to_series(equity_curve)
    dr = daily_returns(eq)
    mr = monthly_returns(eq)
    r12 = rolling_12m_return(eq)
    dd = drawdown_series(eq)

    tot_ret = total_return(eq)
    cagr_v = cagr(eq)
    max_dd = max_drawdown(eq)
    vol = annualized_vol(dr)
    sharpe = sharpe_ratio(dr)
    sortino = sortino_ratio(dr)
    calmar = calmar_ratio(cagr_v, max_dd)
    mar = mar_ratio(cagr_v, max_dd)
    dd_days = max_drawdown_duration_days(eq)

    ts = trade_stats(trades)
    conc = concentration_stats(trades)
    exits = exit_reason_breakdown(trades)

    final_equity = float(eq.iloc[-1]) if not eq.empty else config.initial_capital
    total_commission = ts.get("total_commission", 0.0)

    monthly_dict = {ts_k.strftime("%Y-%m"): float(v) for ts_k, v in mr.items()}
    rolling12_dict = {ts_k.strftime("%Y-%m"): float(v) for ts_k, v in r12.items()}

    return {
        # Returns
        "initial_capital": float(config.initial_capital),
        "final_equity": final_equity,
        "total_return": float(tot_ret),
        "cagr": float(cagr_v),
        "annualized_vol": float(vol),

        # Risk
        "max_drawdown": float(max_dd),
        "max_drawdown_duration_days": int(dd_days),

        # Risk-adjusted
        "sharpe": float(sharpe),
        "sortino": float(sortino),
        "calmar": float(calmar),
        "mar": float(mar),

        # Trades
        **{f"trades.{k}": v for k, v in ts.items()},
        **{f"concentration.{k}": v for k, v in conc.items()},
        "exit_reasons": exits,

        # Cost diagnostics
        "total_commission": float(total_commission),
        "cost_pct_of_pnl": float(total_commission / max(abs(final_equity - config.initial_capital), 1.0)),

        # Time series (for UI charts)
        "monthly_returns": monthly_dict,
        "rolling_12m_returns": rolling12_dict,
    }
