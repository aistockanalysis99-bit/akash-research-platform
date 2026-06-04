"""Background job runner for the AI research pipeline.

Mirrors api.jobs.JobManager — runs each AI pipeline invocation inside a worker
thread via asyncio.run() and exposes progress via an in-memory dict that the
UI polls.

Pipeline runs are file-system-backed: every agent writes its markdown to
AI_RESEARCH_DIR as it completes, so even if a job is lost from memory the
work product survives on disk. The list / detail endpoints read from disk.
"""
from __future__ import annotations

import asyncio
import json
import logging
import threading
import traceback
import uuid
from datetime import date, datetime
from pathlib import Path
from typing import Any, Optional

from engine.config import AI_RESEARCH_DIR
from engine.db.schema import get_connection
from engine.live.file_store import FILE_NAMES, FileStore
from engine.live.pipeline import run_full_pipeline
from engine.live.pipeline_morning import run_morning_cycle
from engine.live.pipeline_weekly import run_weekly_cycle
from engine.live.portfolio import VirtualPortfolio, fetch_latest_close

log = logging.getLogger("api.ai_jobs")

# Order in which stages should appear in the UI progress rail.
STAGE_ORDER = ["init", "prefetch", "analysts", "debate", "pm", "summary", "done"]


class AIJobManager:
    """Tracks running AI research jobs + their stage progress.

    Job state is persisted to the `ai_jobs` SQLite table on submit + completion
    so the AI Analysis job list survives `run.py` restarts.
    """

    KIND = "analyze"

    def __init__(self) -> None:
        self._jobs: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()
        self._load_from_db()

    def _load_from_db(self) -> None:
        """Restore prior jobs (any state) on process start."""
        try:
            conn = get_connection()
            rows = conn.execute(
                "SELECT job_id, state_json FROM ai_jobs WHERE kind = ? "
                "ORDER BY started_at DESC LIMIT 200",
                (self.KIND,),
            ).fetchall()
            conn.close()
        except Exception as e:  # noqa: BLE001
            log.warning("ai_jobs: could not restore from DB: %s", e)
            return
        n = 0
        with self._lock:
            for row in rows:
                try:
                    state = json.loads(row["state_json"])
                    # Any job that was "running"/"queued" when the server died
                    # gets marked failed on reload — the worker thread is gone.
                    if state.get("status") in ("queued", "running"):
                        state["status"] = "failed"
                        state["error"] = (state.get("error") or "") + \
                            "\n[Job was in-flight when server restarted.]"
                        state["completed_at"] = datetime.utcnow().isoformat()
                        # Re-persist the failed state
                        self._persist_job(state)
                    self._jobs[row["job_id"]] = state
                    n += 1
                except Exception as e:  # noqa: BLE001
                    log.warning("ai_jobs: corrupt state for %s: %s",
                                 row["job_id"], e)
        if n:
            log.info("ai_jobs: restored %d job(s) from DB", n)

    def _persist_job(self, job: dict[str, Any]) -> None:
        """Write the current job state to ai_jobs. Idempotent on job_id."""
        try:
            conn = get_connection()
            conn.execute(
                "INSERT INTO ai_jobs (job_id, kind, symbol, status, "
                "started_at, completed_at, state_json) "
                "VALUES (?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(job_id) DO UPDATE SET "
                "status=excluded.status, completed_at=excluded.completed_at, "
                "state_json=excluded.state_json",
                (
                    job["job_id"], self.KIND, job.get("symbol"),
                    job.get("status", "queued"),
                    job.get("started_at"),
                    job.get("completed_at"),
                    json.dumps(job, default=str),
                ),
            )
            conn.commit()
            conn.close()
        except Exception as e:  # noqa: BLE001
            log.warning("ai_jobs: could not persist %s: %s",
                         job.get("job_id"), e)

    # --------------------------------------------------------------------- #
    # Public API
    # --------------------------------------------------------------------- #

    def submit(self, symbol: str, source: str, notes: Optional[str]) -> str:
        job_id = str(uuid.uuid4())
        job = {
            "job_id": job_id,
            "symbol": symbol.upper(),
            "source": source,
            "notes": notes,
            "status": "queued",
            "current_stage": None,
            "current_msg": "",
            "stages": [],
            "started_at": datetime.utcnow().isoformat(),
            "completed_at": None,
            "signal_date": None,
            "verdict": None,
            "error": None,
        }
        with self._lock:
            self._jobs[job_id] = job
        self._persist_job(job)
        threading.Thread(target=self._execute, args=(job_id,), daemon=True).start()
        return job_id

    def get(self, job_id: str) -> Optional[dict]:
        with self._lock:
            j = self._jobs.get(job_id)
            return dict(j) if j else None

    def list(self) -> list[dict]:
        with self._lock:
            return [dict(j) for j in self._jobs.values()]

    # --------------------------------------------------------------------- #
    # Worker thread
    # --------------------------------------------------------------------- #

    def _execute(self, job_id: str) -> None:
        with self._lock:
            self._jobs[job_id]["status"] = "running"

        def progress(stage: str, msg: str, **extra: Any) -> None:
            with self._lock:
                j = self._jobs.get(job_id)
                if not j:
                    return
                j["current_stage"] = stage
                j["current_msg"] = msg
                event: dict[str, Any] = {
                    "stage": stage,
                    "msg": msg,
                    "at": datetime.utcnow().isoformat(),
                }
                # Richer per-event context: agent, model, action, metrics
                event.update(extra)
                j["stages"].append(event)

        try:
            meta = self._jobs[job_id]
            symbol = meta["symbol"]
            source = meta["source"]
            notes = meta["notes"]

            state = asyncio.run(run_full_pipeline(
                symbol, source=source, notes=notes, progress=progress,
            ))

            with self._lock:
                j = self._jobs[job_id]
                j["status"] = "complete"
                j["completed_at"] = datetime.utcnow().isoformat()
                j["signal_date"] = state.get("signal_date")
                pm = state.get("pm")
                if pm is not None:
                    j["verdict"] = {
                        "decision": pm.decision,
                        "conviction": pm.conviction_score,
                        "size_pct": pm.recommended_size_pct,
                    }

            # Auto-create is intentionally disabled.
            # The AI reports the verdict via Telegram; the user decides whether
            # to add the stock to the portfolio manually (Add positions flow).

            # Persist final state
            with self._lock:
                final_state = dict(self._jobs[job_id])
            self._persist_job(final_state)
        except Exception as e:  # noqa: BLE001
            log.exception("AI job %s failed", job_id)
            with self._lock:
                j = self._jobs.get(job_id)
                if j is not None:
                    j["status"] = "failed"
                    j["error"] = f"{type(e).__name__}: {e}\n{traceback.format_exc()[-500:]}"
                    j["completed_at"] = datetime.utcnow().isoformat()
                    self._persist_job(dict(j))


# Global singleton — one job manager per process.
ai_job_manager = AIJobManager()


# --------------------------------------------------------------------------- #
# Morning Cycle Job Manager
# --------------------------------------------------------------------------- #


class MorningJobManager:
    """Runs the morning cycle in a worker thread; mirrors AIJobManager."""

    def __init__(self) -> None:
        self._jobs: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()

    def submit(self) -> str:
        job_id = str(uuid.uuid4())
        today = date.today().isoformat()
        with self._lock:
            self._jobs[job_id] = {
                "job_id": job_id,
                "as_of_date": today,
                "status": "queued",
                "current_stage": None,
                "current_msg": "",
                "stages": [],
                "started_at": datetime.utcnow().isoformat(),
                "completed_at": None,
                "regime": None,
                "executed_exits": [],
                "exit_confirmations_summary": [],
                "headline": None,
                "error": None,
            }
        threading.Thread(target=self._execute, args=(job_id,), daemon=True).start()
        return job_id

    def get(self, job_id: str) -> Optional[dict]:
        with self._lock:
            j = self._jobs.get(job_id)
            return dict(j) if j else None

    def list(self) -> list[dict]:
        with self._lock:
            return [dict(j) for j in self._jobs.values()]

    def _execute(self, job_id: str) -> None:
        with self._lock:
            self._jobs[job_id]["status"] = "running"

        def progress(stage: str, msg: str, **extra: Any) -> None:
            with self._lock:
                j = self._jobs.get(job_id)
                if not j:
                    return
                j["current_stage"] = stage
                j["current_msg"] = msg
                event: dict[str, Any] = {
                    "stage": stage, "msg": msg,
                    "at": datetime.utcnow().isoformat(),
                }
                event.update(extra)
                j["stages"].append(event)

        try:
            state = asyncio.run(run_morning_cycle(progress=progress))
            with self._lock:
                j = self._jobs[job_id]
                j["status"] = "complete"
                j["completed_at"] = datetime.utcnow().isoformat()
                regime = state.get("regime")
                if regime is not None:
                    j["regime"] = {
                        "regime": regime.regime,
                        "confidence": regime.regime_confidence,
                        "throttle": regime.new_entries_throttle,
                    }
                briefing = state.get("briefing")
                if briefing is not None:
                    j["headline"] = briefing.headline
                j["executed_exits"] = state.get("executed_exits", [])
                confirmations = state.get("exit_confirmations") or {}
                j["exit_confirmations_summary"] = [
                    {"symbol": s, "verdict": c.verdict, "urgency": c.urgency}
                    for s, c in confirmations.items()
                ]
        except Exception as e:  # noqa: BLE001
            log.exception("Morning job %s failed", job_id)
            with self._lock:
                j = self._jobs.get(job_id)
                if j:
                    j["status"] = "failed"
                    j["error"] = f"{type(e).__name__}: {e}\n{traceback.format_exc()[-500:]}"


morning_job_manager = MorningJobManager()


# --------------------------------------------------------------------------- #
# Morning artifact disk readers
# --------------------------------------------------------------------------- #


def list_morning_dates() -> list[str]:
    return FileStore().list_morning_dates()


def read_morning_files(date_iso: str) -> dict[str, str]:
    return FileStore().read_morning_files(date_iso)


# ------------------------------------------------------------------------- #
# Disk readers (used by list + detail endpoints)
# ------------------------------------------------------------------------- #


def list_decisions_on_disk() -> list[dict[str, Any]]:
    """Scan AI_RESEARCH_DIR and return one row per (symbol, date) folder.

    Skips the `_morning` folder — those are morning-cycle artifacts, not
    per-stock decisions; they're served separately by the /ai/morning routes.
    """
    out: list[dict[str, Any]] = []
    if not AI_RESEARCH_DIR.exists():
        return out

    for sym_dir in sorted(AI_RESEARCH_DIR.iterdir(), reverse=True):
        if not sym_dir.is_dir():
            continue
        if sym_dir.name.startswith("_"):
            continue   # skip _morning and any other reserved meta-folders
        for date_dir in sorted(sym_dir.iterdir(), reverse=True):
            if not date_dir.is_dir():
                continue
            out.append(_summarize_folder(sym_dir.name, date_dir.name, date_dir))
    return out


def _summarize_folder(symbol: str, date_iso: str, folder: Path) -> dict[str, Any]:
    """Pull a one-row summary from a per-stock folder."""
    info: dict[str, Any] = {
        "symbol": symbol,
        "date": date_iso,
        "decision": None,
        "conviction": None,
        "size_pct": None,
        "source": None,
        "stages_present": [],
        "has_summary": False,
        "status": "incomplete",   # 'complete' | 'incomplete' (no PM verdict on disk)
    }
    for stage, filename in FILE_NAMES.items():
        if (folder / filename).exists():
            info["stages_present"].append(stage)
    info["has_summary"] = "summary" in info["stages_present"]

    raw_path = folder / FILE_NAMES["raw"]
    if raw_path.exists():
        try:
            raw = json.loads(raw_path.read_text(encoding="utf-8"))
            pm = raw.get("pm") or {}
            if pm:
                info["decision"] = pm.get("decision")
                info["conviction"] = pm.get("conviction_score")
                info["size_pct"] = pm.get("recommended_size_pct")
                info["status"] = "complete"
            info["source"] = raw.get("source")
        except (json.JSONDecodeError, KeyError):
            pass

    # If the folder has stages but no PM verdict, mark it as failed (the run
    # crashed somewhere mid-pipeline).
    if info["decision"] is None and info["stages_present"]:
        # A signal-only folder is a run that died before any analyst — distinct
        # from runs that partially completed (failed_partial vs failed_early).
        if len(info["stages_present"]) <= 1:
            info["status"] = "failed_early"
        else:
            info["status"] = "failed_partial"

    return info


def read_decision_files(symbol: str, date_iso: str) -> dict[str, str]:
    """Return every stage's markdown for one (symbol, date)."""
    folder = AI_RESEARCH_DIR / symbol.upper() / date_iso
    if not folder.exists():
        raise FileNotFoundError(f"No analysis for {symbol} on {date_iso}")

    out: dict[str, str] = {}
    for stage, filename in FILE_NAMES.items():
        path = folder / filename
        if not path.exists():
            continue
        if stage == "raw":
            continue  # served separately if needed
        out[stage] = path.read_text(encoding="utf-8")
    return out
