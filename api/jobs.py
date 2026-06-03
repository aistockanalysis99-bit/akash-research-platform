"""Background job runner for backtests.

Runs backtests in a thread pool so the API stays responsive. Streams progress
to in-memory queues; UI/WS subscribers consume from there.
"""
from __future__ import annotations

import asyncio
import threading
import traceback
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Any, Optional

from engine.core.event_loop import run_backtest
from engine.core.types import BacktestConfig
from engine.data.loader import load_universe_panel
from engine.db import repo
from engine.logging_setup import get_logger

log = get_logger("api.jobs")


class JobManager:
    """Tracks running backtest jobs + their progress queues."""

    def __init__(self, max_workers: int = 2) -> None:
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="bt")
        self._progress: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()

    def get_progress(self, run_id: str) -> dict[str, Any]:
        with self._lock:
            return dict(self._progress.get(run_id, {"progress": 0.0, "msg": "queued"}))

    def _set_progress(self, run_id: str, progress: float, msg: str) -> None:
        with self._lock:
            self._progress[run_id] = {"progress": progress, "msg": msg, "updated_at": datetime.utcnow().isoformat()}

    def submit_backtest(self, run_id: str, run_name: str, config: BacktestConfig) -> None:
        repo.insert_run_pending(run_id, run_name, config)
        self._set_progress(run_id, 0.0, "queued")
        self._executor.submit(self._execute, run_id, run_name, config)

    def _execute(self, run_id: str, run_name: str, config: BacktestConfig) -> None:
        try:
            self._set_progress(run_id, 0.0, "loading data")
            panel = load_universe_panel(config.universe, config.timeframe, config.start_date, config.end_date)
            if not panel:
                msg = "No cached data found. Run scripts/refresh_data.py first."
                repo.fail_run(run_id, msg)
                self._set_progress(run_id, 1.0, msg)
                return

            self._set_progress(run_id, 0.05, f"running on {len(panel)} symbols")

            def progress(bar_i: int, total: int, ts: datetime) -> None:
                pct = bar_i / max(1, total)
                self._set_progress(run_id, min(0.05 + 0.93 * pct, 0.98), f"bar {bar_i}/{total} @ {ts.date()}")
                repo.update_run_progress(run_id, min(0.05 + 0.93 * pct, 0.98), f"bar {bar_i}/{total}")

            config.run_name = run_name
            result = run_backtest(panel, config, progress_cb=progress, progress_every=20)
            result.run_id = run_id
            result.run_name = run_name

            self._set_progress(run_id, 0.99, "saving results")
            repo.save_run_result(result)
            self._set_progress(run_id, 1.0, "done")
            log.info("Backtest %s complete: %d trades", run_name, len(result.trades))
        except Exception as e:  # noqa: BLE001
            err = f"{type(e).__name__}: {e}\n{traceback.format_exc()[-500:]}"
            log.exception("Backtest %s failed", run_id)
            repo.fail_run(run_id, err)
            self._set_progress(run_id, 1.0, f"failed: {e}")


# Global job manager
job_manager = JobManager(max_workers=2)
