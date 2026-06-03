"""CLI: run a backtest from cached data with default or custom params.

Usage:
    python scripts/run_backtest_cli.py --universe smoke
    python scripts/run_backtest_cli.py --universe sp100 --years 5
    python scripts/run_backtest_cli.py --universe sp100 --params my_set
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engine.core.event_loop import run_backtest  # noqa: E402
from engine.core.types import BacktestConfig, StrategyParams  # noqa: E402
from engine.data.loader import load_universe_panel  # noqa: E402
from engine.data.universe import get_universe  # noqa: E402
from engine.db import repo  # noqa: E402
from engine.logging_setup import get_logger  # noqa: E402

log = get_logger("scripts.backtest")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a backtest.")
    parser.add_argument("--universe", default="smoke")
    parser.add_argument("--timeframe", default="1D")
    parser.add_argument("--years", type=int, default=5)
    parser.add_argument("--capital", type=float, default=100_000.0)
    parser.add_argument("--params", default=None, help="Saved parameter-set name")
    parser.add_argument("--save", action="store_true", help="Persist to DB")
    args = parser.parse_args()

    if args.params:
        params = repo.get_parameter_set(args.params) or StrategyParams()
    else:
        params = StrategyParams()

    end = datetime.now(tz=timezone.utc)
    start = end - timedelta(days=365 * args.years)

    universe = get_universe(args.universe)
    log.info("Loading panel: %d symbols, %s, %dy", len(universe), args.timeframe, args.years)
    panel = load_universe_panel(universe, args.timeframe, start, end)
    if not panel:
        log.error("No cached data. Run scripts/refresh_data.py first.")
        sys.exit(1)
    log.info("Loaded %d symbols with cached bars.", len(panel))

    config = BacktestConfig(
        universe=universe,
        start_date=start,
        end_date=end,
        timeframe=args.timeframe,
        initial_capital=args.capital,
        params=params,
        universe_name=args.universe,
    )

    last_pct = [-1]

    def progress(bar_i: int, total: int, ts: datetime) -> None:
        pct = int(100 * bar_i / max(1, total))
        if pct != last_pct[0]:
            sys.stdout.write(f"\r  Backtest progress: {pct}%  ({bar_i}/{total})  {ts.date()}")
            sys.stdout.flush()
            last_pct[0] = pct

    result = run_backtest(panel, config, progress_cb=progress, progress_every=20)
    sys.stdout.write("\n")

    log.info("=== Results: %s ===", result.run_name)
    m = result.metrics
    if m:
        print(f"  Final equity:       ${m.get('final_equity', 0):,.2f}")
        print(f"  Total return:       {m.get('total_return', 0):+.2%}")
        print(f"  CAGR:               {m.get('cagr', 0):+.2%}")
        print(f"  Annualized vol:     {m.get('annualized_vol', 0):.2%}")
        print(f"  Max drawdown:       {m.get('max_drawdown', 0):.2%}")
        print(f"  Sharpe:             {m.get('sharpe', 0):.2f}")
        print(f"  Sortino:            {m.get('sortino', 0):.2f}")
        print(f"  MAR / Calmar:       {m.get('mar', 0):.2f}")
        print(f"  # Trades:           {m.get('trades.total_trades', 0)}")
        print(f"  Win rate:           {m.get('trades.win_rate', 0):.2%}")
        print(f"  Profit factor:      {m.get('trades.profit_factor', 0):.2f}")
        print(f"  Avg trade:          ${m.get('trades.avg_trade', 0):,.2f}")

    if args.save:
        repo.insert_run_pending(result.run_id, result.run_name, config)
        repo.save_run_result(result)
        print(f"\n  Saved run: {result.run_id} ({result.run_name})")


if __name__ == "__main__":
    main()
