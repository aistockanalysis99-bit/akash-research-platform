#!/usr/bin/env python3
"""Multi-Horizon Walkforward Backtest Runner for Strategy v2.

Ingests sanitized historical daily market data from universe_5y_daily.parquet,
applies Strategy v2 quantitative gates (Confirmed Reversion Hook, Two-Tranche Staged Sizing,
Breakeven Stop Trailing, Ornstein-Uhlenbeck Time Stop, and Earnings Blackout Shield),
tracks non-overlapping active positions per pair, and exports pre-computed datasets for:
  - 1-Year: 2025-10-26 to 2026-10-26 (~252 trading days)
  - 2-Year: 2024-10-26 to 2026-10-26 (~504 trading days)
  - 3-Year: 2023-10-26 to 2026-10-26 (~756 trading days)
  - 5-Year: 2021-10-26 to 2026-10-26 (~1,260 trading days)

Outputs:
  - data/backtest_v2_1y_results.json
  - data/backtest_v2_2y_results.json
  - data/backtest_v2_3y_results.json
  - data/backtest_v2_5y_results.json
"""

from __future__ import annotations

import json
import logging
import math
import os
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

# Ensure UTF-8 output encoding for Windows command line
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import numpy as np
import pandas as pd

from engine.strategy_v2_engine import (
    EarningsCalendar,
    StrategyV2Engine,
    StrategyV2OutcomeEvaluator,
    StrategyV2Setup,
    load_strategy_v2_config,
)

logger = logging.getLogger("backtest_v2")

DATA_DIR = ROOT_DIR / "data"
V2_CACHE_DIR = DATA_DIR / "backtest_v2_runs_cache"

HORIZON_CONFIGS = {
    "1Y": {
        "label": "1 Year (2025-2026)",
        "start_date": "2025-10-26",
        "end_date": "2026-10-26",
        "output_file": DATA_DIR / "backtest_v2_1y_results.json",
    },
    "2Y": {
        "label": "2 Years (2024-2026)",
        "start_date": "2024-10-26",
        "end_date": "2026-10-26",
        "output_file": DATA_DIR / "backtest_v2_2y_results.json",
    },
    "3Y": {
        "label": "3 Years (2023-2026)",
        "start_date": "2023-10-26",
        "end_date": "2026-10-26",
        "output_file": DATA_DIR / "backtest_v2_3y_results.json",
    },
    "5Y": {
        "label": "5 Years (2021-2026)",
        "start_date": "2021-10-26",
        "end_date": "2026-10-26",
        "output_file": DATA_DIR / "backtest_v2_5y_results.json",
    },
}

# Warm singleton cache
_WARM_V2_ENGINE: Optional[StrategyV2Engine] = None
_WARM_V2_EVALUATOR: Optional[StrategyV2OutcomeEvaluator] = None
_WARM_LOCK = threading.Lock()


def get_warm_v2_components() -> Tuple[StrategyV2Engine, StrategyV2OutcomeEvaluator]:
    """Retrieve shared in-memory Strategy v2 engine and outcome evaluator."""
    global _WARM_V2_ENGINE, _WARM_V2_EVALUATOR
    if _WARM_V2_ENGINE is None or _WARM_V2_EVALUATOR is None:
        with _WARM_LOCK:
            if _WARM_V2_ENGINE is None:
                _WARM_V2_ENGINE = StrategyV2Engine()
                df = _WARM_V2_ENGINE.load_data()
                _WARM_V2_EVALUATOR = StrategyV2OutcomeEvaluator(df=df)
    return _WARM_V2_ENGINE, _WARM_V2_EVALUATOR


def clean_nan(val: Any, default: float = 0.0) -> Any:
    """Sanitize float values for strict RFC 8259 JSON compliance."""
    if val is None:
        return default
    if isinstance(val, (int, bool, str)):
        return val
    try:
        f = float(val)
        if math.isnan(f) or math.isinf(f):
            return default
        return f
    except (ValueError, TypeError):
        return default


def sanitize_dict(d: Any) -> Any:
    """Recursively clean dictionaries and lists of NaN / Inf values."""
    if isinstance(d, dict):
        return {k: sanitize_dict(v) for k, v in d.items()}
    if isinstance(d, list):
        return [sanitize_dict(x) for x in d]
    if isinstance(d, float):
        return clean_nan(d)
    return d


def run_strategy_v2_backtest(
    start_date: str = "2025-10-26",
    end_date: str = "2026-10-26",
    config: Optional[Dict[str, Any]] = None,
    engine: Optional[StrategyV2Engine] = None,
    evaluator: Optional[StrategyV2OutcomeEvaluator] = None,
) -> Dict[str, Any]:
    """Execute walkforward Strategy v2 backtest across given historical dates.
    
    Guarantees:
      - Point-in-time scanning strictly at t <= T (Zero Lookahead).
      - Reversion Hook Confirmation required for entry.
      - Two-Tranche Staged Sizing & Breakeven Stop Trailing.
      - Non-overlapping active positions per pair.
      - Dynamic Ornstein-Uhlenbeck Time Stop.
      - Corporate Earnings Blackout Vetoes.
    """
    t0 = time.time()
    if engine is None or evaluator is None:
        warm_eng, warm_eval = get_warm_v2_components()
        engine = engine or warm_eng
        evaluator = evaluator or warm_eval

    if config:
        engine.apply_config(config)
        evaluator.config = config

    df = engine.load_data()
    start_ts = pd.to_datetime(start_date).tz_localize(None).normalize()
    end_ts = pd.to_datetime(end_date).tz_localize(None).normalize()

    if end_ts <= start_ts:
        raise ValueError(f"end_date ({end_date}) must be after start_date ({start_date})")

    # Available trading days in slice
    trading_days = [d for d in df.index if start_ts <= d <= end_ts]
    if not trading_days:
        raise ValueError(f"No trading days found between {start_date} and {end_date}")

    pairs = engine.get_pairs()
    trades: List[Dict[str, Any]] = []
    # Active positions mapping: pair_name -> exit_timestamp
    active_positions: Dict[str, pd.Timestamp] = {}

    for dt in trading_days:
        dt_str = dt.strftime("%Y-%m-%d")

        # Expire closed positions
        closed = [p for p, exit_ts in active_positions.items() if exit_ts <= dt]
        for p in closed:
            del active_positions[p]

        # Scan active setups for Date T using fast-filter, excluding pairs in active trade
        active_setups = engine.scan_date(
            target_date=dt,
            top_n=50,
            only_active_setups=True,
            exclude_pairs=set(active_positions.keys()),
        )

        for setup in active_setups:
            pname = setup.pair_name
            if pname in active_positions:
                continue

            # Forward evaluation with 2-tranche staged execution
            fwd = evaluator.evaluate_setup(setup, use_intraday_extremes=False)

            exit_ts = (
                pd.to_datetime(fwd.exit_date).normalize()
                if fwd.exit_date
                else dt + pd.Timedelta(days=setup.time_stop_days)
            )
            active_positions[pname] = exit_ts

            trade_record = {
                "id": f"{setup.ticker_a}_{setup.ticker_b}_{dt_str}",
                "pair_name": pname,
                "ticker_a": setup.ticker_a,
                "ticker_b": setup.ticker_b,
                "sector": setup.sector,
                "entry_date": dt_str,
                "exit_date": fwd.exit_date,
                "direction": setup.direction,
                "direction_label": (
                    f"Long {setup.ticker_a} / Short {setup.ticker_b}"
                    if (setup.direction == "LONG_A_SHORT_B" or setup.current_z_score < 0)
                    else f"Short {setup.ticker_a} / Long {setup.ticker_b}"
                ),
                "entry_z": round(setup.current_z_score, 3),
                "abs_entry_z": round(abs(setup.current_z_score), 3),
                "hurdle_breached_z": round(setup.hurdle_breached_z, 3),
                "hook_entry_z": round(setup.hook_entry_z, 3),
                "exit_z": round(fwd.exit_z_score, 3) if fwd.exit_z_score is not None else None,
                "hedge_ratio": round(setup.hedge_ratio, 4),
                "entry_price_a": round(setup.price_a_entry, 2),
                "entry_price_b": round(setup.price_b_entry, 2),
                "exit_price_a": round(fwd.exit_price_a, 2) if fwd.exit_price_a is not None else None,
                "exit_price_b": round(fwd.exit_price_b, 2) if fwd.exit_price_b is not None else None,
                "outcome": fwd.outcome,
                "exit_reason": fwd.exit_reason,
                "status_reason": fwd.status_reason,
                "realized_return_pct": round(fwd.realized_pnl_pct, 2),
                "holding_days": fwd.exit_days_held,
                "time_stop_days": setup.time_stop_days,
                "max_favorable_z": round(fwd.max_favorable_z, 3),
                "max_adverse_z": round(fwd.max_adverse_z, 3),

                # Staged Tranche Details
                "tp1_hit": fwd.tp1_hit,
                "tp1_date": fwd.tp1_date,
                "tp1_days_held": fwd.tp1_days_held,
                "tp1_z_score": fwd.tp1_z_score,
                "tranche1_pnl_pct": fwd.tranche1_pnl_pct,
                "tp2_hit": fwd.tp2_hit,
                "tp2_date": fwd.tp2_date,
                "tp2_days_held": fwd.tp2_days_held,
                "tp2_z_score": fwd.tp2_z_score,
                "tranche2_pnl_pct": fwd.tranche2_pnl_pct,
                "breakeven_stop_hit": fwd.breakeven_stop_hit,
                "time_stop_hit": fwd.time_stop_hit,
                "stop_loss_hit": fwd.stop_loss_hit,

                # Institutional checks & scoring
                "is_perfect": setup.is_perfect,
                "passed_checks_count": setup.passed_checks_count,
                "is_tradeable": setup.is_tradeable,
                "checks": setup.checks,
                "adf_pvalue": round(setup.adf_pvalue, 4),
                "correlation": round(setup.correlation, 3),
                "r_squared": round(setup.r_squared, 3),
                "half_life_days": round(setup.half_life_days, 1),
                "spread_tier": setup.spread_tier,
                "relative_spread_vol_pct": round(setup.relative_spread_vol_pct, 2),
                "composite_score": round(setup.composite_score, 1),
                "trajectory": fwd.path,
            }
            trades.append(trade_record)

    elapsed = round(time.time() - t0, 2)

    # Compile Aggregate KPI Summary
    def compute_summary(t_list: List[Dict[str, Any]]) -> Dict[str, Any]:
        total = len(t_list)
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
                "tp1_and_tp2_count": 0,
                "tp1_and_breakeven_count": 0,
                "stop_loss_count": 0,
                "time_stop_count": 0,
            }

        wins = [t for t in t_list if t["outcome"] == "WIN"]
        losses = [t for t in t_list if t["outcome"] == "LOSS"]
        neutrals = [t for t in t_list if t["outcome"] in ("NEUTRAL", "OPEN")]

        decisive = len(wins) + len(losses)
        win_rate = round((len(wins) / decisive * 100.0), 1) if decisive > 0 else 0.0

        returns = [t["realized_return_pct"] for t in t_list]
        avg_ret = round(float(np.mean(returns)), 2)
        med_ret = round(float(np.median(returns)), 2)

        holding = [t["holding_days"] for t in t_list]
        avg_hold = round(float(np.mean(holding)), 1)

        win_rets = [t["realized_return_pct"] for t in wins if t["realized_return_pct"] > 0]
        loss_rets = [abs(t["realized_return_pct"]) for t in losses if t["realized_return_pct"] < 0]
        gross_profit = round(float(np.sum(win_rets)), 2) if win_rets else 0.0
        gross_loss = round(float(np.sum(loss_rets)), 2) if loss_rets else 0.0
        pf = (
            round(gross_profit / max(1e-4, gross_loss), 2)
            if gross_loss > 0
            else (99.0 if gross_profit > 0 else 1.0)
        )

        # Max drawdown across trade equity curve sorted chronologically by exit_date
        exit_sorted = sorted(t_list, key=lambda t: t.get("exit_date") or t.get("entry_date", ""))
        exit_returns = [t["realized_return_pct"] for t in exit_sorted]
        cum = np.cumsum(exit_returns) if exit_returns else np.array([0.0])
        peak = np.maximum.accumulate(cum)
        dd = peak - cum
        max_dd = round(float(np.max(dd)), 2) if len(dd) > 0 else 0.0

        # Staged exit breakdown
        tp1_tp2 = sum(1 for t in t_list if t.get("exit_reason") == "TP1_AND_TP2")
        tp1_be = sum(1 for t in t_list if t.get("exit_reason") == "TP1_AND_BREAKEVEN")
        stop_cnt = sum(1 for t in t_list if t.get("exit_reason") == "STOP_LOSS")
        time_cnt = sum(1 for t in t_list if t.get("exit_reason") == "TIME_STOP")

        return {
            "total_trades": total,
            "win_count": len(wins),
            "loss_count": len(losses),
            "neutral_count": len(neutrals),
            "win_rate_pct": win_rate,
            "avg_return_pct": avg_ret,
            "median_return_pct": med_ret,
            "avg_holding_days": avg_hold,
            "profit_factor": pf,
            "gross_profit_pct": gross_profit,
            "gross_loss_pct": gross_loss,
            "max_drawdown_pct": max_dd,
            "tp1_and_tp2_count": tp1_tp2,
            "tp1_and_breakeven_count": tp1_be,
            "stop_loss_count": stop_cnt,
            "time_stop_count": time_cnt,
        }

    overall_summary = compute_summary(trades)
    perfect_trades = [t for t in trades if t.get("is_perfect")]
    perfect_summary = compute_summary(perfect_trades)
    tradeable_trades = [t for t in trades if t.get("is_tradeable")]
    tradeable_summary = compute_summary(tradeable_trades)

    # Monthly Returns Matrix
    monthly_dict: Dict[str, List[float]] = {}
    for t in trades:
        d_key = (t.get("exit_date") or t.get("entry_date", ""))[:7]
        if d_key:
            if d_key not in monthly_dict:
                monthly_dict[d_key] = []
            monthly_dict[d_key].append(t["realized_return_pct"])

    monthly_returns: List[Dict[str, Any]] = []
    cum_ret = 0.0
    for m in sorted(monthly_dict.keys()):
        m_rets = monthly_dict[m]
        m_tot = round(float(np.sum(m_rets)), 2)
        cum_ret = round(cum_ret + m_tot, 2)
        m_wins = sum(1 for r in m_rets if r > 0)
        m_wr = round((m_wins / len(m_rets) * 100.0), 1) if m_rets else 0.0
        monthly_returns.append({
            "month": m,
            "trades_count": len(m_rets),
            "win_rate_pct": m_wr,
            "return_pct": m_tot,
            "cumulative_return_pct": cum_ret,
        })

    # Equity Curve Points
    equity_curve: List[Dict[str, Any]] = []
    cum_eq = 0.0
    eq_peak = 0.0
    exit_sorted = sorted(trades, key=lambda t: t.get("exit_date") or t.get("entry_date", ""))
    for t in exit_sorted:
        cum_eq = round(cum_eq + t["realized_return_pct"], 2)
        eq_peak = max(eq_peak, cum_eq)
        dd = round(eq_peak - cum_eq, 2)
        equity_curve.append({
            "date": t.get("exit_date") or t.get("entry_date"),
            "trade_id": t["id"],
            "return_pct": t["realized_return_pct"],
            "cumulative_equity_pct": cum_eq,
            "drawdown_pct": dd,
        })

    result = {
        "version": "2.0.0",
        "strategy_name": "Cointegrated Stat-Arb v2 (Confirmed Reversion & Staged Exits)",
        "period": {
            "start_date": start_date,
            "end_date": end_date,
            "trading_days_evaluated": len(trading_days),
            "pairs_universe_count": len(pairs),
        },
        "overall_summary": overall_summary,
        "perfect_summary": perfect_summary,
        "tradeable_summary": tradeable_summary,
        "monthly_returns": monthly_returns,
        "equity_curve": equity_curve,
        "trades": trades,
        "meta": {
            "strategy_version": "v2",
            "z_score_hurdle": engine.z_hurdle,
            "z_score_hook_entry": engine.z_hook,
            "tp1_target": engine.tp1_z,
            "tp2_target": engine.tp2_z,
            "stop_loss_barrier": engine.stop_loss_z,
            "half_life_multiplier": engine.hl_mult,
            "computed_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "latency_seconds": elapsed,
        },
    }

    return sanitize_dict(result)


def save_v2_results_atomically(result: Dict[str, Any], output_path: Path) -> None:
    """Save backtest output to disk atomically using temporary file swap."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", dir=str(output_path.parent), delete=False, encoding="utf-8") as tf:
        json.dump(result, tf, indent=2)
        temp_name = tf.name
    os.replace(temp_name, output_path)
    logger.info(f"Saved Strategy v2 results to {output_path} ({len(result.get('trades', []))} trades)")


def main():
    print("=" * 80)
    print("STRATEGY v2: MULTI-HORIZON WALKFORWARD BACKTEST RUNNER (1Y, 2Y, 3Y, 5Y)")
    print("=" * 80)

    t_start = time.time()
    eng, eval_inst = get_warm_v2_components()
    print("Warm Strategy v2 Engine & Evaluator initialized successfully.\n")

    summary_cards = []

    for horizon_key, cfg in HORIZON_CONFIGS.items():
        print(f"[{horizon_key}] Running Backtest: {cfg['label']}")
        print(f"     Window: {cfg['start_date']} -> {cfg['end_date']}")

        t0 = time.time()
        res = run_strategy_v2_backtest(
            start_date=cfg["start_date"],
            end_date=cfg["end_date"],
            engine=eng,
            evaluator=eval_inst,
        )
        elapsed = time.time() - t0

        save_v2_results_atomically(res, cfg["output_file"])

        ov = res["overall_summary"]
        print(f"     ✅ Completed in {elapsed:.2f}s:")
        print(f"        Trades: {ov['total_trades']} | Win Rate: {ov['win_rate_pct']}% | Profit Factor: {ov['profit_factor']}")
        print(f"        Net Return: {ov['gross_profit_pct'] - ov['gross_loss_pct']:+.2f}% | Max DD: -{ov['max_drawdown_pct']}% | Avg Hold: {ov['avg_holding_days']}d")
        print(f"        Exits: TP1+TP2: {ov['tp1_and_tp2_count']} | TP1+Breakeven: {ov['tp1_and_breakeven_count']} | Stops: {ov['stop_loss_count']} | Time: {ov['time_stop_count']}\n")

        summary_cards.append({
            "horizon": horizon_key,
            "period": cfg["label"],
            "trades": ov["total_trades"],
            "win_rate": ov["win_rate_pct"],
            "profit_factor": ov["profit_factor"],
            "net_return": round(ov["gross_profit_pct"] - ov["gross_loss_pct"], 2),
            "max_dd": ov["max_drawdown_pct"],
            "avg_holding": ov["avg_holding_days"],
            "tp1_and_tp2": ov["tp1_and_tp2_count"],
            "tp1_and_breakeven": ov["tp1_and_breakeven_count"],
            "stops": ov["stop_loss_count"],
        })

    total_time = round(time.time() - t_start, 2)
    print("=" * 80)
    print(f"ALL 4 HORIZONS COMPUTED & PERSISTED IN {total_time}s")
    print("=" * 80)


if __name__ == "__main__":
    main()
