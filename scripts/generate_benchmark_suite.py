#!/usr/bin/env python3
"""Pre-computes and caches a comprehensive benchmark suite across 1Y, 2Y, 3Y, 5Y and 6M timeframes.

Saves each backtest run into data/backtest_runs_cache/ and catalogs them in manifest.json
so they are instantly available on the website without manual calculation.
"""

import sys
import time
from pathlib import Path

# Ensure UTF-8 output encoding for Windows command line
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts.run_1y_backtest import get_warm_components, run_1y_walkforward_backtest

BENCHMARK_CONFIGS = [
    {
        "name": "1Y Institutional Baseline",
        "start_date": "2025-10-26",
        "end_date": "2026-10-26",
        "entry_z": 2.0,
        "stop_z": 3.5,
        "max_horizon_days": 30,
    },
    {
        "name": "1Y High Conviction (|Z| ≥ 2.5σ)",
        "start_date": "2025-10-26",
        "end_date": "2026-10-26",
        "entry_z": 2.5,
        "stop_z": 3.5,
        "max_horizon_days": 30,
    },
    {
        "name": "1Y Fast Mean-Reversion (≤ 5d)",
        "start_date": "2025-10-26",
        "end_date": "2026-10-26",
        "entry_z": 2.2,
        "stop_z": 3.0,
        "max_horizon_days": 5,
    },
    {
        "name": "1Y Medium Swing (≤ 15d)",
        "start_date": "2025-10-26",
        "end_date": "2026-10-26",
        "entry_z": 2.0,
        "stop_z": 3.5,
        "max_horizon_days": 15,
    },
    {
        "name": "2Y Multi-Cycle Standard",
        "start_date": "2024-10-26",
        "end_date": "2026-10-26",
        "entry_z": 2.0,
        "stop_z": 3.5,
        "max_horizon_days": 30,
    },
    {
        "name": "2Y High Conviction (|Z| ≥ 2.5σ)",
        "start_date": "2024-10-26",
        "end_date": "2026-10-26",
        "entry_z": 2.5,
        "stop_z": 3.5,
        "max_horizon_days": 30,
    },
    {
        "name": "3Y Macro Cycle Standard",
        "start_date": "2023-10-26",
        "end_date": "2026-10-26",
        "entry_z": 2.0,
        "stop_z": 3.5,
        "max_horizon_days": 30,
    },
    {
        "name": "3Y Deep Anomaly (|Z| ≥ 2.5σ, Stop 4.0σ)",
        "start_date": "2023-10-26",
        "end_date": "2026-10-26",
        "entry_z": 2.5,
        "stop_z": 4.0,
        "max_horizon_days": 30,
    },
    {
        "name": "5Y Full History Stress Test",
        "start_date": "2021-10-27",
        "end_date": "2026-10-26",
        "entry_z": 2.0,
        "stop_z": 3.5,
        "max_horizon_days": 30,
    },
    {
        "name": "5Y High Conviction (|Z| ≥ 2.5σ)",
        "start_date": "2021-10-27",
        "end_date": "2026-10-26",
        "entry_z": 2.5,
        "stop_z": 3.5,
        "max_horizon_days": 30,
    },
    {
        "name": "6M Recent Market Regime",
        "start_date": "2026-04-26",
        "end_date": "2026-10-26",
        "entry_z": 2.0,
        "stop_z": 3.5,
        "max_horizon_days": 30,
    },
]


def main():
    print("=" * 80)
    print("PRE-COMPUTING BENCHMARK SUITE ACROSS 1Y, 2Y, 3Y, 5Y & 6M TIMEFRAMES")
    print("=" * 80)

    # Pre-warm shared components once
    eng, eval_inst, pairs_df = get_warm_components()
    print(f"Warm singletons ready: {len(pairs_df)} pairs loaded in memory.")

    results_summary = []

    for i, cfg in enumerate(BENCHMARK_CONFIGS, 1):
        print(f"\n[{i}/{len(BENCHMARK_CONFIGS)}] Running: {cfg['name']}")
        print(f"   Period: {cfg['start_date']} -> {cfg['end_date']} | Entry |Z|: {cfg['entry_z']} | Stop: {cfg['stop_z']} | Horizon: {cfg['max_horizon_days']}d")

        t0 = time.time()
        res = run_1y_walkforward_backtest(
            start_date=cfg["start_date"],
            end_date=cfg["end_date"],
            entry_z=cfg["entry_z"],
            stop_z=cfg["stop_z"],
            max_horizon_days=cfg["max_horizon_days"],
            engine=eng,
            evaluator=eval_inst,
            pairs_df=pairs_df,
            use_cache=True,
            refresh=False,
        )
        elapsed = time.time() - t0

        ov = res["overall_summary"]
        trades = res.get("trades", [])
        best_trade = sorted(trades, key=lambda t: t.get("realized_return_pct", 0), reverse=True)[0] if trades else None
        worst_trade = sorted(trades, key=lambda t: t.get("realized_return_pct", 0))[0] if trades else None

        best_str = f"{best_trade['pair_name']} (+{best_trade['realized_return_pct']}%)" if best_trade else "N/A"
        worst_str = f"{worst_trade['pair_name']} ({worst_trade['realized_return_pct']}%)" if worst_trade else "N/A"

        print(f"   [OK] Completed in {elapsed:.2f}s | Trades: {ov['total_trades']} | Win Rate: {ov['win_rate_pct']}% | PF: {ov['profit_factor']}x | Avg Ret: {ov['avg_return_pct']}% | Max DD: -{ov['max_drawdown_pct']}%")
        print(f"   [OK] Best Trade: {best_str} | Worst Trade: {worst_str}")

        results_summary.append({
            "name": cfg["name"],
            "period": f"{cfg['start_date']} to {cfg['end_date']}",
            "trades": ov["total_trades"],
            "win_rate": ov["win_rate_pct"],
            "profit_factor": ov["profit_factor"],
            "avg_return": ov["avg_return_pct"],
            "max_dd": ov["max_drawdown_pct"],
            "best_trade": best_str,
            "worst_trade": worst_str,
        })

    print("\n" + "=" * 80)
    print("ALL BENCHMARK SUITE CONFIGURATIONS PRE-COMPUTED & CACHED SUCCESSFULLY!")
    print("=" * 80)
    for r in results_summary:
        print(f"• {r['name']:<40} | Trades: {r['trades']:>4} | WR: {r['win_rate']:>5}% | PF: {r['profit_factor']:>4}x | AvgRet: {r['avg_return']:>5}% | MaxDD: -{r['max_dd']:>5}%")
    print("=" * 80)


if __name__ == "__main__":
    main()
