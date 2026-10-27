#!/usr/bin/env python3
"""1-Year Walkforward Backtest Engine for Elite Pairs.

Scans all trading days across the last 1 year (2025-10-26 to 2026-10-26),
identifies entry triggers (|Z| >= 2.0), tracks non-overlapping trade episodes per pair,
evaluates forward outcomes (WIN/LOSS/NEUTRAL) with stop-loss priority,
and computes institutional performance metrics with 10/10 quality check breakdowns.
"""

from __future__ import annotations

import json
import logging
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import numpy as np
import pandas as pd

from engine.detect_setups import load_pairs
from engine.simulator_engine import ForwardOutcomeEvaluator, PointInTimeEngine

logger = logging.getLogger("backtest_1y")


def run_1y_walkforward_backtest(
    start_date: str = "2025-10-26",
    end_date: str = "2026-10-26",
    entry_z: float = 2.0,
    stop_z: float = 3.5,
    max_horizon_days: int = 30,
) -> Dict[str, Any]:
    t0 = time.time()
    engine = PointInTimeEngine()
    df = engine.load_data()
    evaluator = ForwardOutcomeEvaluator(df=df)
    pairs_df = load_pairs()

    fields = df.columns.levels[0].tolist() if isinstance(df.columns, pd.MultiIndex) else []
    price_matrix = df["Adj Close"] if "Adj Close" in fields else (df["Close"] if "Close" in fields else df)

    start_ts = pd.to_datetime(start_date).tz_localize(None).normalize()
    end_ts = pd.to_datetime(end_date).tz_localize(None).normalize()

    trading_days = [d for d in price_matrix.index if start_ts <= d <= end_ts]
    print(f"Loaded dataset: {len(trading_days)} trading days, {len(pairs_df)} pairs.")

    trades: List[Dict[str, Any]] = []
    # Track active trade positions: pair_name -> exit_timestamp
    active_positions: Dict[str, pd.Timestamp] = {}

    for dt in trading_days:
        dt_str = dt.strftime("%Y-%m-%d")

        # Expire closed positions
        closed = [p for p, exit_ts in active_positions.items() if exit_ts <= dt]
        for p in closed:
            del active_positions[p]

        # Scan candidate pairs using ultra-fast scan_date
        active_setups = engine.scan_date(target_date=dt, top_n=50, only_active_setups=True)
        for setup in active_setups:
            orig_a = setup.ticker_a
            orig_b = setup.ticker_b
            pname = setup.pair_name

            if pname in active_positions:
                continue

            if abs(setup.current_z_score) >= entry_z:
                # Trigger trade entry
                fwd = evaluator.evaluate_setup(
                    setup,
                    max_horizon_days=max_horizon_days,
                    use_intraday_extremes=False,
                )

                exit_ts = (
                    pd.to_datetime(fwd.exit_date).normalize()
                    if fwd.exit_date
                    else dt + pd.Timedelta(days=max_horizon_days)
                )
                active_positions[pname] = exit_ts

                # Determine 10/10 check status
                passed_checks = getattr(setup, "passed_checks_count", 0)
                is_perfect = getattr(setup, "is_perfect", False) or passed_checks == 10

                trade_data = {
                    "id": f"{orig_a}_{orig_b}_{dt_str}",
                    "pair_name": pname,
                    "ticker_a": orig_a,
                    "ticker_b": orig_b,
                    "sector": setup.sector or "Equities",
                    "entry_date": dt_str,
                    "exit_date": fwd.exit_date,
                    "direction": setup.direction,
                    "direction_label": (
                        f"Long {orig_a} / Short {orig_b}"
                        if (setup.direction == "LONG_A_SHORT_B" or setup.current_z_score < 0)
                        else f"Short {orig_a} / Long {orig_b}"
                    ),
                    "entry_z": round(setup.current_z_score, 3),
                    "abs_entry_z": round(abs(setup.current_z_score), 3),
                    "exit_z": round(fwd.exit_z_score, 3) if fwd.exit_z_score is not None else None,
                    "hedge_ratio": round(setup.hedge_ratio, 4),
                    "entry_price_a": round(setup.price_a_entry, 2),
                    "entry_price_b": round(setup.price_b_entry, 2),
                    "exit_price_a": round(fwd.exit_price_a, 2) if fwd.exit_price_a is not None else None,
                    "exit_price_b": round(fwd.exit_price_b, 2) if fwd.exit_price_b is not None else None,
                    "outcome": fwd.outcome,  # "WIN", "LOSS", "NEUTRAL", "OPEN"
                    "status_reason": fwd.status_reason,
                    "realized_return_pct": round(fwd.realized_pnl_pct, 2),
                    "holding_days": fwd.exit_days_held,
                    "max_favorable_z": round(fwd.max_favorable_z, 3),
                    "max_adverse_z": round(fwd.max_adverse_z, 3),
                    "is_perfect_10": bool(is_perfect),
                    "passed_checks_count": int(passed_checks),
                    "checks": setup.checks if hasattr(setup, "checks") else {},
                    "adf_pvalue": round(setup.adf_pvalue, 4),
                    "correlation": round(setup.correlation, 3),
                    "half_life_days": round(setup.half_life_days, 1),
                    "spread_tier": setup.spread_tier,
                    "relative_spread_vol_pct": round(setup.relative_spread_vol_pct, 2),
                    "composite_score": round(setup.composite_score, 1),
                }
                trades.append(trade_data)

    elapsed = time.time() - t0
    print(f"Simulation completed in {elapsed:.2f}s. Total trades recorded: {len(trades)}")

    # Compute aggregate KPI metrics
    def summarize_trades(trade_list: List[Dict[str, Any]]) -> Dict[str, Any]:
        total = len(trade_list)
        if total == 0:
            return {
                "total_trades": 0,
                "win_count": 0,
                "loss_count": 0,
                "neutral_count": 0,
                "win_rate_pct": 0.0,
                "avg_return_pct": 0.0,
                "median_return_pct": 0.0,
                "avg_holding_days": 0.0,
                "profit_factor": 0.0,
                "gross_profit_pct": 0.0,
                "gross_loss_pct": 0.0,
                "max_drawdown_pct": 0.0,
            }

        wins = [t for t in trade_list if t["outcome"] == "WIN"]
        losses = [t for t in trade_list if t["outcome"] == "LOSS"]
        neutrals = [t for t in trade_list if t["outcome"] in ("NEUTRAL", "OPEN")]

        decisive = len(wins) + len(losses)
        win_rate = round((len(wins) / decisive * 100.0), 1) if decisive > 0 else 0.0

        returns = [t["realized_return_pct"] for t in trade_list]
        avg_ret = round(float(np.mean(returns)), 2)
        med_ret = round(float(np.median(returns)), 2)

        holding = [t["holding_days"] for t in trade_list]
        avg_hold = round(float(np.mean(holding)), 1)

        win_returns = [t["realized_return_pct"] for t in wins if t["realized_return_pct"] > 0]
        loss_returns = [abs(t["realized_return_pct"]) for t in losses if t["realized_return_pct"] < 0]
        gross_profit = float(np.sum(win_returns)) if win_returns else 0.0
        gross_loss = float(np.sum(loss_returns)) if loss_returns else 0.0
        profit_factor = round(gross_profit / max(1e-4, gross_loss), 2) if gross_loss > 0 else (99.0 if gross_profit > 0 else 1.0)

        # Max drawdown across realized trade equity curve sorted chronologically by exit_date
        exit_sorted_trades = sorted(trade_list, key=lambda t: t.get("exit_date") or t.get("entry_date", ""))
        exit_returns = [t["realized_return_pct"] for t in exit_sorted_trades]
        cum = np.cumsum(exit_returns) if exit_returns else np.array([0.0])
        peak = np.maximum.accumulate(cum)
        dd = peak - cum
        max_dd = round(float(np.max(dd)), 2) if len(dd) > 0 else 0.0

        return {
            "total_trades": total,
            "win_count": len(wins),
            "loss_count": len(losses),
            "neutral_count": len(neutrals),
            "win_rate_pct": win_rate,
            "avg_return_pct": avg_ret,
            "median_return_pct": med_ret,
            "avg_holding_days": avg_hold,
            "profit_factor": profit_factor,
            "gross_profit_pct": round(gross_profit, 2),
            "gross_loss_pct": round(gross_loss, 2),
            "max_drawdown_pct": max_dd,
        }

    overall_metrics = summarize_trades(trades)
    perfect_10_trades = [t for t in trades if t["is_perfect_10"]]
    perfect_10_metrics = summarize_trades(perfect_10_trades)
    checks_8plus_trades = [t for t in trades if t["passed_checks_count"] >= 8]
    checks_8plus_metrics = summarize_trades(checks_8plus_trades)

    result = {
        "period": {
            "start_date": start_date,
            "end_date": end_date,
            "trading_days_evaluated": len(trading_days),
            "pairs_universe_count": len(pairs_df),
        },
        "overall_summary": overall_metrics,
        "perfect_10_summary": perfect_10_metrics,
        "checks_8plus_summary": checks_8plus_metrics,
        "trades": trades,
        "meta": {
            "entry_z": entry_z,
            "stop_z": stop_z,
            "max_horizon_days": max_horizon_days,
            "computed_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "latency_seconds": round(elapsed, 2),
        },
    }

    # Cache result atomically to disk for instant sub-5ms loading
    import tempfile
    import os
    cache_file = ROOT_DIR / "data" / "backtest_1y_results.json"
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", dir=str(cache_file.parent), delete=False, encoding="utf-8") as tf:
        json.dump(result, tf, indent=2)
        temp_name = tf.name
    os.replace(temp_name, cache_file)
    print(f"Saved 1-year backtest results cache to {cache_file}")

    return result


if __name__ == "__main__":
    res = run_1y_walkforward_backtest()
    o = res["overall_summary"]
    p = res["perfect_10_summary"]
    print("=" * 70)
    print("1-YEAR STATISTICAL ARBITRAGE WALKFORWARD BACKTEST RESULTS")
    print("=" * 70)
    print(f"Overall Trades: {o['total_trades']} | Wins: {o['win_count']} | Losses: {o['loss_count']} | Neutral: {o['neutral_count']}")
    print(f"Overall Win Rate: {o['win_rate_pct']}% | Avg Return: {o['avg_return_pct']}% | Profit Factor: {o['profit_factor']}")
    print("-" * 70)
    print(f"10/10 Perfect Trades: {p['total_trades']} | Wins: {p['win_count']} | Losses: {p['loss_count']}")
    print(f"10/10 Win Rate: {p['win_rate_pct']}% | Avg Return: {p['avg_return_pct']}% | Profit Factor: {p['profit_factor']}")
    print("=" * 70)
