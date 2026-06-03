"""CLI: refresh OHLCV cache from FMP.

Usage:
    python scripts/refresh_data.py --universe sp100 --timeframe 1D --years 5
    python scripts/refresh_data.py --universe smoke --timeframe 1D
    python scripts/refresh_data.py --symbols AAPL MSFT --timeframe 1D
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

# Path bootstrap so this script works from project root or scripts/
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engine.data.cache import refresh_universe  # noqa: E402
from engine.data.universe import get_universe  # noqa: E402
from engine.logging_setup import get_logger  # noqa: E402

log = get_logger("scripts.refresh")


def main() -> None:
    parser = argparse.ArgumentParser(description="Refresh FMP cache.")
    parser.add_argument("--universe", default=None, help="Universe name (sp100, smoke)")
    parser.add_argument("--symbols", nargs="*", default=None, help="Explicit symbols")
    parser.add_argument("--timeframe", default="1D", help="1D, 4h, 1h, 30m, 15m")
    parser.add_argument("--years", type=int, default=5, help="History depth in years")
    parser.add_argument("--full", action="store_true", help="Force full re-fetch (non-incremental)")
    args = parser.parse_args()

    if args.symbols:
        symbols = args.symbols
        label = "custom"
    elif args.universe:
        symbols = get_universe(args.universe)
        label = args.universe
    else:
        log.error("Either --symbols or --universe is required.")
        sys.exit(1)

    log.info("Refreshing %d symbols (%s) @ %s, %dy history", len(symbols), label, args.timeframe, args.years)

    def progress(done: int, total: int, sym: str) -> None:
        bar_len = 30
        pct = done / total
        filled = int(pct * bar_len)
        bar = "#" * filled + "-" * (bar_len - filled)
        sys.stdout.write(f"\r[{bar}] {done}/{total}  {sym:<10}")
        sys.stdout.flush()

    statuses = asyncio.run(
        refresh_universe(
            symbols=symbols,
            timeframe=args.timeframe,
            years_back=args.years,
            incremental=not args.full,
            progress_cb=progress,
        )
    )
    sys.stdout.write("\n")

    ok = sum(1 for s in statuses if s.bars > 0)
    log.info("Refresh complete: %d/%d symbols cached", ok, len(symbols))


if __name__ == "__main__":
    main()
