#!/usr/bin/env python3
"""Walkforward Backtest Engine for Elite Pairs with Parameter Caching & Multi-Year Support.

Scans trading days across a configurable window (6 months to 5 years),
identifies entry triggers (|Z| >= entry_z), tracks non-overlapping trade episodes per pair,
evaluates forward outcomes (WIN/LOSS/NEUTRAL) with stop-loss priority,
and caches results persistently by configuration settings so repeated views are instant (sub-5ms).
"""

from __future__ import annotations

import json
import logging
import os
import sys
import tempfile
import time
from pathlib import Path
import threading
from typing import Any, Dict, List, Optional, Set, Tuple

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import numpy as np
import pandas as pd

from engine.detect_setups import load_pairs
from engine.simulator_engine import ForwardOutcomeEvaluator, PointInTimeEngine

logger = logging.getLogger("backtest_1y")

RUNS_CACHE_DIR = ROOT_DIR / "data" / "backtest_runs_cache"
MANIFEST_FILE = RUNS_CACHE_DIR / "manifest.json"

# Thread-safe in-memory warm singletons to eliminate repeated disk parquet reads and prevent data re-downloads
_WARM_ENGINE: Optional[PointInTimeEngine] = None
_WARM_EVALUATOR: Optional[ForwardOutcomeEvaluator] = None
_WARM_PAIRS_DF: Optional[pd.DataFrame] = None
_WARM_LOCK = threading.Lock()


def get_warm_components() -> Tuple[PointInTimeEngine, ForwardOutcomeEvaluator, pd.DataFrame]:
    """Retrieve warm in-memory engine, evaluator, and pairs dataframe with zero parquet reloads."""
    global _WARM_ENGINE, _WARM_EVALUATOR, _WARM_PAIRS_DF
    if _WARM_ENGINE is None or _WARM_EVALUATOR is None or _WARM_PAIRS_DF is None:
        with _WARM_LOCK:
            if _WARM_ENGINE is None:
                _WARM_ENGINE = PointInTimeEngine()
                df = _WARM_ENGINE.load_data()
                _WARM_EVALUATOR = ForwardOutcomeEvaluator(df=df)
                _WARM_PAIRS_DF = load_pairs()
    return _WARM_ENGINE, _WARM_EVALUATOR, _WARM_PAIRS_DF


def get_run_key(
    start_date: str,
    end_date: str,
    entry_z: float,
    stop_z: float,
    max_horizon_days: int,
) -> str:
    """Generate a clean, deterministic cache key from strategy settings."""
    s = pd.to_datetime(start_date).strftime("%Y-%m-%d")
    e = pd.to_datetime(end_date).strftime("%Y-%m-%d")
    ez = round(float(entry_z), 2)
    sz = round(float(stop_z), 2)
    h = int(max_horizon_days)
    return f"{s}_{e}_ez{ez:.1f}_sz{sz:.1f}_h{h}"


def load_cached_backtest_run(
    start_date: str,
    end_date: str,
    entry_z: float,
    stop_z: float,
    max_horizon_days: int,
) -> Optional[Dict[str, Any]]:
    """Retrieve cached backtest result for exact settings if present on disk."""
    key = get_run_key(start_date, end_date, entry_z, stop_z, max_horizon_days)
    run_file = RUNS_CACHE_DIR / f"{key}.json"
    if run_file.exists():
        try:
            with open(run_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data
        except Exception as err:
            logger.warning(f"Failed to read cache file {run_file}: {err}")

    # Fallback for canonical 1Y baseline
    is_canonical_1y = (
        start_date == "2025-10-26"
        and end_date == "2026-10-26"
        and abs(float(entry_z) - 2.0) < 1e-4
        and abs(float(stop_z) - 3.5) < 1e-4
        and int(max_horizon_days) == 30
    )
    if is_canonical_1y:
        legacy_file = ROOT_DIR / "data" / "backtest_1y_results.json"
        if legacy_file.exists():
            try:
                with open(legacy_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as err:
                logger.warning(f"Failed to read legacy cache {legacy_file}: {err}")

    return None


def generate_auto_test_name(
    start_date: str,
    end_date: str,
    entry_z: float,
    stop_z: float,
    max_horizon_days: int,
) -> str:
    """Generate an automatic, descriptive, institutional test label for a backtest run."""
    s = pd.to_datetime(start_date)
    e = pd.to_datetime(end_date)
    cal_days = (e - s).days

    if cal_days <= 210:
        tf_label = "6M"
    elif cal_days <= 400:
        tf_label = "1Y"
    elif cal_days <= 760:
        tf_label = "2Y"
    elif cal_days <= 1150:
        tf_label = "3Y"
    elif cal_days <= 1500:
        tf_label = "4Y"
    else:
        tf_label = "5Y"

    # Strategy flavor based on parameters
    if abs(entry_z - 2.0) < 0.05 and abs(stop_z - 3.5) < 0.05 and max_horizon_days >= 30:
        strat = "Institutional Baseline"
    elif entry_z >= 2.5 and max_horizon_days >= 30:
        strat = f"High Conviction (|Z| ≥ {entry_z:.1f}σ)"
    elif max_horizon_days <= 5:
        strat = f"Fast Mean-Reversion (≤{max_horizon_days}d Hold)"
    elif max_horizon_days <= 15:
        strat = f"Medium Swing (≤{max_horizon_days}d Hold)"
    elif stop_z <= 3.0:
        strat = f"Tight Stop Guard ({stop_z:.1f}σ)"
    elif stop_z >= 4.0:
        strat = f"Wide Tail Leeway ({stop_z:.1f}σ)"
    else:
        strat = f"Custom (|Z| ≥ {entry_z:.1f}σ, Stop {stop_z:.1f}σ, {max_horizon_days}d)"

    return f"{tf_label} {strat}"


def update_manifest(key: str, result: Dict[str, Any]) -> None:
    """Atomically update the catalog manifest of saved/cached backtest runs."""
    RUNS_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    manifest: Dict[str, Any] = {"runs": []}
    if MANIFEST_FILE.exists():
        try:
            with open(MANIFEST_FILE, "r", encoding="utf-8") as f:
                manifest = json.load(f)
        except Exception:
            manifest = {"runs": []}

    runs_list: List[Dict[str, Any]] = manifest.get("runs", [])
    # Remove existing entry with same key if present
    runs_list = [r for r in runs_list if r.get("run_id") != key]

    meta = result.get("meta", {})
    period = result.get("period", {})
    ov = result.get("overall_summary", {})
    perf = result.get("perfect_10_summary", {})
    trades = result.get("trades", [])

    s_date = period.get("start_date", "2025-10-26")
    e_date = period.get("end_date", "2026-10-26")
    ez = float(meta.get("entry_z", 2.0))
    sz = float(meta.get("stop_z", 3.5))
    h = int(meta.get("max_horizon_days", 30))

    test_name = generate_auto_test_name(s_date, e_date, ez, sz, h)

    best_trade = None
    worst_trade = None
    net_return = 0.0

    if trades:
        sorted_by_ret = sorted(trades, key=lambda t: t.get("realized_return_pct", 0.0), reverse=True)
        b = sorted_by_ret[0]
        w = sorted_by_ret[-1]
        best_trade = {
            "pair_name": b.get("pair_name"),
            "realized_return_pct": b.get("realized_return_pct"),
            "entry_date": b.get("entry_date"),
            "exit_date": b.get("exit_date"),
            "holding_days": b.get("holding_days"),
        }
        worst_trade = {
            "pair_name": w.get("pair_name"),
            "realized_return_pct": w.get("realized_return_pct"),
            "entry_date": w.get("entry_date"),
            "exit_date": w.get("exit_date"),
            "holding_days": w.get("holding_days"),
        }
        net_return = round(float(sum(t.get("realized_return_pct", 0.0) for t in trades)), 2)

    record = {
        "run_id": key,
        "test_name": test_name,
        "start_date": s_date,
        "end_date": e_date,
        "entry_z": ez,
        "stop_z": sz,
        "max_horizon_days": h,
        "trading_days": period.get("trading_days_evaluated", 0),
        "total_trades": ov.get("total_trades", 0),
        "win_count": ov.get("win_count", 0),
        "loss_count": ov.get("loss_count", 0),
        "win_rate_pct": ov.get("win_rate_pct", 0.0),
        "profit_factor": ov.get("profit_factor", 0.0),
        "avg_return_pct": ov.get("avg_return_pct", 0.0),
        "net_return_pct": net_return,
        "max_drawdown_pct": ov.get("max_drawdown_pct", 0.0),
        "avg_holding_days": ov.get("avg_holding_days", 0.0),
        "best_trade": best_trade,
        "worst_trade": worst_trade,
        "perfect_10_win_rate": perf.get("win_rate_pct", 0.0),
        "perfect_10_trades": perf.get("total_trades", 0),
        "computed_at": meta.get("computed_at", time.strftime("%Y-%m-%d %H:%M:%S")),
        "latency_seconds": meta.get("latency_seconds", 0.0),
    }
    runs_list.insert(0, record)
    manifest["runs"] = runs_list

    with tempfile.NamedTemporaryFile("w", dir=str(RUNS_CACHE_DIR), delete=False, encoding="utf-8") as tf:
        json.dump(manifest, tf, indent=2)
        temp_name = tf.name
    os.replace(temp_name, MANIFEST_FILE)


def save_backtest_run(result: Dict[str, Any]) -> str:
    """Atomically save backtest result to disk keyed by settings."""
    RUNS_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    meta = result.get("meta", {})
    period = result.get("period", {})
    s = period.get("start_date", "2025-10-26")
    e = period.get("end_date", "2026-10-26")
    ez = meta.get("entry_z", 2.0)
    sz = meta.get("stop_z", 3.5)
    h = meta.get("max_horizon_days", 30)

    key = get_run_key(s, e, ez, sz, h)
    run_file = RUNS_CACHE_DIR / f"{key}.json"

    with tempfile.NamedTemporaryFile("w", dir=str(RUNS_CACHE_DIR), delete=False, encoding="utf-8") as tf:
        json.dump(result, tf, indent=2)
        temp_name = tf.name
    os.replace(temp_name, run_file)

    # If canonical 1Y baseline, also save to backtest_1y_results.json
    is_canonical_1y = (
        s == "2025-10-26"
        and e == "2026-10-26"
        and abs(float(ez) - 2.0) < 1e-4
        and abs(float(sz) - 3.5) < 1e-4
        and int(h) == 30
    )
    if is_canonical_1y:
        default_file = ROOT_DIR / "data" / "backtest_1y_results.json"
        with tempfile.NamedTemporaryFile("w", dir=str(default_file.parent), delete=False, encoding="utf-8") as tf:
            json.dump(result, tf, indent=2)
            temp_name = tf.name
        os.replace(temp_name, default_file)

    # Update manifest
    try:
        update_manifest(key, result)
    except Exception as err:
        logger.warning(f"Failed to update manifest: {err}")

    return key


def get_saved_runs_list() -> List[Dict[str, Any]]:
    """Retrieve catalog list of all saved/cached backtest runs."""
    if MANIFEST_FILE.exists():
        try:
            with open(MANIFEST_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("runs", [])
        except Exception as err:
            logger.warning(f"Error reading runs manifest: {err}")
    return []


def run_1y_walkforward_backtest(
    start_date: str = "2025-10-26",
    end_date: str = "2026-10-26",
    entry_z: float = 2.0,
    stop_z: float = 3.5,
    max_horizon_days: int = 30,
    engine: Optional[PointInTimeEngine] = None,
    evaluator: Optional[ForwardOutcomeEvaluator] = None,
    pairs_df: Optional[pd.DataFrame] = None,
    use_cache: bool = True,
    refresh: bool = False,
) -> Dict[str, Any]:
    """Execute walkforward backtest across configurable date window and parameters.
    
    Validations:
      - Minimum date window: 6 months (180 calendar days)
      - Maximum date window: 5 years (1826 calendar days)
    """
    start_ts = pd.to_datetime(start_date).tz_localize(None).normalize()
    end_ts = pd.to_datetime(end_date).tz_localize(None).normalize()

    if end_ts <= start_ts:
        raise ValueError("End date must be strictly after start date.")

    calendar_days = (end_ts - start_ts).days
    if calendar_days < 180:
        raise ValueError(
            f"Backtest period must be at least 6 months (180 days). Provided: {calendar_days} days."
        )
    if calendar_days > 1827:
        raise ValueError(
            f"Backtest period cannot exceed 5 years (1826 days). Provided: {calendar_days} days."
        )

    # Check cache first if not explicitly forcing refresh
    if use_cache and not refresh:
        cached_result = load_cached_backtest_run(
            start_date=start_date,
            end_date=end_date,
            entry_z=entry_z,
            stop_z=stop_z,
            max_horizon_days=max_horizon_days,
        )
        if cached_result is not None:
            logger.info(
                f"Returning cached backtest for {start_date} to {end_date} (Z={entry_z}, Stop={stop_z}, H={max_horizon_days})"
            )
            return cached_result

    t0 = time.time()
    if engine is None or evaluator is None or pairs_df is None:
        warm_eng, warm_eval, warm_pairs = get_warm_components()
        engine = engine or warm_eng
        evaluator = evaluator or warm_eval
        pairs_df = pairs_df or warm_pairs

    df = engine.load_data()

    fields = df.columns.levels[0].tolist() if isinstance(df.columns, pd.MultiIndex) else []
    price_matrix = df["Adj Close"] if "Adj Close" in fields else (df["Close"] if "Close" in fields else df)

    # Restrict to available dataset boundaries
    trading_days = [d for d in price_matrix.index if start_ts <= d <= end_ts]
    if len(trading_days) == 0:
        raise ValueError(f"No trading days found between {start_date} and {end_date}.")

    logger.info(f"Loaded dataset: {len(trading_days)} trading days, {len(pairs_df)} pairs.")

    trades: List[Dict[str, Any]] = []
    # Track active trade positions: pair_name -> exit_timestamp
    active_positions: Dict[str, pd.Timestamp] = {}

    for dt in trading_days:
        dt_str = dt.strftime("%Y-%m-%d")

        # Expire closed positions
        closed = [p for p, exit_ts in active_positions.items() if exit_ts <= dt]
        for p in closed:
            del active_positions[p]

        # Scan candidate pairs using ultra-fast scan_date, excluding pairs already in active positions
        active_setups = engine.scan_date(
            target_date=dt,
            top_n=50,
            only_active_setups=True,
            exclude_pairs=set(active_positions.keys()),
        )
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
                    "is_tradeable": bool(getattr(setup, "is_tradeable", False) or (abs(setup.current_z_score) >= entry_z and setup.relative_spread_vol_pct <= 7.0)),
                    "is_ready_to_take": bool(is_perfect or (setup.relative_spread_vol_pct <= 7.0 and int(passed_checks) >= 8)),
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
    logger.info(f"Simulation completed in {elapsed:.2f}s. Total trades recorded: {len(trades)}")

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
        profit_factor = (
            round(gross_profit / max(1e-4, gross_loss), 2)
            if gross_loss > 0
            else (99.0 if gross_profit > 0 else 1.0)
        )

        # Max drawdown across realized trade equity curve sorted chronologically by exit_date
        exit_sorted_trades = sorted(
            trade_list, key=lambda t: t.get("exit_date") or t.get("entry_date", "")
        )
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

    # Save to persistent runs cache
    save_backtest_run(result)

    return result


if __name__ == "__main__":
    res = run_1y_walkforward_backtest(refresh=True)
    o = res["overall_summary"]
    p = res["perfect_10_summary"]
    print("=" * 70)
    print("1-YEAR STATISTICAL ARBITRAGE WALKFORWARD BACKTEST RESULTS")
    print("=" * 70)
    print(
        f"Overall Trades: {o['total_trades']} | Wins: {o['win_count']} | Losses: {o['loss_count']} | Neutral: {o['neutral_count']}"
    )
    print(
        f"Overall Win Rate: {o['win_rate_pct']}% | Avg Return: {o['avg_return_pct']}% | Profit Factor: {o['profit_factor']}"
    )
    print("-" * 70)
    print(
        f"10/10 Perfect Trades: {p['total_trades']} | Wins: {p['win_count']} | Losses: {p['loss_count']}"
    )
    print(
        f"10/10 Win Rate: {p['win_rate_pct']}% | Avg Return: {p['avg_return_pct']}% | Profit Factor: {p['profit_factor']}"
    )
    print("=" * 70)
