"""Multi-Horizon Walkforward Backtest Runner for Strategy v3 ("Asymmetric Alpha Maximizer").

Executes point-in-time simulations across 4 standard horizons:
  1. 1 Year: 2025-10-26 to 2026-10-26
  2. 2 Years: 2024-10-26 to 2026-10-26
  3. 3 Years: 2023-10-26 to 2026-10-26
  4. 5 Years: 2021-10-26 to 2026-10-26

Validates that Strategy v3 beats Strategy 1 in Net Profit % in ALL 4 horizons:
  - 1Y > +81.04%
  - 2Y > +97.97%
  - 3Y > +134.04%
  - 5Y > +113.50%

Outputs results to:
  data/backtest_v3_1y_results.json
  data/backtest_v3_2y_results.json
  data/backtest_v3_3y_results.json
  data/backtest_v3_5y_results.json
"""

from __future__ import annotations

import json
import logging
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from engine.config import DATA_CACHE_DIR, PROJECT_ROOT
from engine.logging_setup import get_logger
from engine.strategy_v3_engine import StrategyV3Config, StrategyV3Engine

logger = get_logger("run_v3_backtest")

DATA_DIR = PROJECT_ROOT / "data"

HORIZONS = {
    "1Y": {"start_date": "2025-10-26", "end_date": "2026-10-26", "min_target_profit": 81.04},
    "2Y": {"start_date": "2024-10-26", "end_date": "2026-10-26", "min_target_profit": 97.97},
    "3Y": {"start_date": "2023-10-26", "end_date": "2026-10-26", "min_target_profit": 134.04},
    "5Y": {"start_date": "2021-10-26", "end_date": "2026-10-26", "min_target_profit": 113.50},
}


def run_all_v3_horizons() -> Dict[str, Dict[str, Any]]:
    """Run all 4 horizons for Strategy v3 and save to data/."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    config = StrategyV3Config.load()
    engine = StrategyV3Engine(config)

    results: Dict[str, Dict[str, Any]] = {}

    print("======================================================================")
    print("  STRATEGY v3 ('Asymmetric Alpha Maximizer') WALKFORWARD SIMULATION   ")
    print("======================================================================")

    for period_key, h in HORIZONS.items():
        s_date = h["start_date"]
        e_date = h["end_date"]
        target_profit = h["min_target_profit"]

        print(f"\n>>> Running Strategy v3 Backtest for {period_key} ({s_date} to {e_date})...")
        t0 = time.time()
        res = engine.run_backtest(s_date, e_date)
        elapsed = time.time() - t0

        summary = res["overall_summary"]
        net_ret = summary["net_return_pct"]
        win_rate = summary["win_rate_pct"]
        pf = summary["profit_factor"]
        dd = summary["max_drawdown_pct"]
        trades_cnt = summary["total_trades"]
        floor_saved = summary.get("disaster_floor_saved_trades", 0)

        out_path = DATA_DIR / f"backtest_v3_{period_key.lower()}_results.json"
        with tempfile.NamedTemporaryFile("w", dir=str(DATA_DIR), delete=False, encoding="utf-8") as tf:
            json.dump(res, tf, indent=2)
            temp_name = tf.name
        os.replace(temp_name, out_path)

        beats_v1 = net_ret > target_profit
        status_label = "BEATS STRATEGY 1 [SUCCESS]" if beats_v1 else "BELOW TARGET [FAIL]"

        print(f"  Duration: {elapsed:.2f}s | Saved to: {out_path.name}")
        print(f"  Trades: {trades_cnt} | Win Rate: {win_rate}% | Profit Factor: {pf} | Max DD: {dd}%")
        print(f"  Disaster Floor Saved Blowouts: {floor_saved}")
        print(f"  Net Profit %: +{net_ret:.2f}% (Strategy 1 was +{target_profit:.2f}%) -> {status_label}")

        results[period_key] = res

    print("\n======================================================================")
    print("  STRATEGY v3 MULTI-HORIZON VALIDATION SUMMARY                        ")
    print("======================================================================")
    all_passed = True
    for p, h in HORIZONS.items():
        net = results[p]["overall_summary"]["net_return_pct"]
        tgt = h["min_target_profit"]
        passed = net > tgt
        if not passed:
            all_passed = False
        print(f"  {p}: Strategy 3 Net = +{net:.2f}% vs Strategy 1 = +{tgt:.2f}% (Delta = +{net - tgt:.2f}%) [{'PASS' if passed else 'FAIL'}]")

    print(f"\nALL 4 HORIZONS BEAT STRATEGY 1: {all_passed}")
    return results


if __name__ == "__main__":
    run_all_v3_horizons()
