"""The Strategy Report Card — Layer 2 at portfolio scale.

Aggregates every cached per-symbol straddle backtest into one evidence
document: across N symbols and M real historical earnings events, how did
the qualifying rule actually perform? This is the number set that justifies
(or refuses) real capital.

Coverage builds incrementally: a nightly scheduler batch backtests ~20
uncached S&P 500 symbols (sequential, paced — the per-minute Polygon budget
is shared with everything else), so full-index coverage accumulates over a
few weeks without ever hammering the API. The aggregate is honest about
coverage: it always reports how much of the universe it has seen.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any, Optional

from . import store

log = logging.getLogger(__name__)

PACING_SECONDS = 2.0        # between symbol backtests in a sweep batch
STALE_DAYS = 60             # re-run a symbol's backtest after this age


def aggregate_report_card() -> dict[str, Any]:
    """Aggregate all cached straddle backtests into the Report Card."""
    rows = store.all_backtest_summaries()
    ok = [r for r in rows if not r.get("error")
          and r.get("events_priced") is not None]
    errors = [r for r in rows if r.get("error")]

    total_priced = sum(r.get("events_priced") or 0 for r in ok)
    total_qual = sum(r.get("qualifying_events") or 0 for r in ok)

    # win rate weighted by each symbol's qualifying-event count
    win_num = win_den = 0
    pnl_num = pnl_den = 0.0
    for r in ok:
        q = r.get("qualifying_events") or 0
        if q and r.get("qualifying_win_rate_pct") is not None:
            win_num += r["qualifying_win_rate_pct"] * q
            win_den += q
        if q and r.get("qualifying_avg_pnl_pct") is not None:
            pnl_num += r["qualifying_avg_pnl_pct"] * q
            pnl_den += q

    leaders = sorted(
        (r for r in ok if (r.get("qualifying_events") or 0) >= 2
         and r.get("qualifying_avg_pnl_pct") is not None),
        key=lambda r: -r["qualifying_avg_pnl_pct"])[:10]

    return {
        "symbols_covered": len(ok),
        "symbols_errored": len(errors),
        "events_priced": total_priced,
        "qualifying_events": total_qual,
        "qualifying_win_rate_pct": (round(win_num / win_den)
                                    if win_den else None),
        "qualifying_avg_pnl_pct": (round(pnl_num / pnl_den, 1)
                                   if pnl_den else None),
        "avg_implied_vs_actual": _mean(
            [r.get("avg_implied_vs_actual") for r in ok]),
        "leaders": [{"symbol": r["symbol"],
                     "qualifying_events": r.get("qualifying_events"),
                     "win_rate_pct": r.get("qualifying_win_rate_pct"),
                     "avg_pnl_pct": r.get("qualifying_avg_pnl_pct")}
                    for r in leaders],
        "generated_at": datetime.utcnow().isoformat(),
    }


def _mean(vals: list[Optional[float]]) -> Optional[float]:
    xs = [v for v in vals if v is not None]
    return round(sum(xs) / len(xs), 2) if xs else None


async def run_report_card_batch(limit: int = 20) -> dict[str, Any]:
    """Backtest up to `limit` not-yet-covered S&P 500 symbols, sequentially
    and paced. Each result lands in the same per-symbol cache the Track
    Record page uses — the sweep and the UI share one source of truth."""
    from datetime import date, timedelta
    from ...data.universe import get_universe_async
    from .backtest import backtest_symbol

    universe = [s.upper() for s in await get_universe_async("sp500")]
    have: dict[str, str] = {r["symbol"]: r.get("computed_at") or ""
                            for r in store.all_backtest_summaries()}
    stale_before = (date.today() - timedelta(days=STALE_DAYS)).isoformat()
    todo = [s for s in universe
            if s not in have or have[s][:10] < stale_before][:max(1, limit)]

    done, failed = 0, 0
    for sym in todo:
        try:
            result = await backtest_symbol(sym)
            store.save_backtest(sym, 10, result)
            done += 1
        except Exception as e:  # noqa: BLE001
            log.warning("report card sweep: %s failed: %s", sym, e)
            failed += 1
        await asyncio.sleep(PACING_SECONDS)

    covered = len(store.all_backtest_summaries())
    log.info("report card sweep: +%d done, %d failed, coverage %d/%d",
             done, failed, covered, len(universe))
    return {"batch_done": done, "batch_failed": failed,
            "coverage": covered, "universe": len(universe)}
