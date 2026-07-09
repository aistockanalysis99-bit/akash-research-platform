"""APScheduler wrapper — drives the daily morning + evening cycles.

Lifecycle:
    - api/main.py starts the scheduler on FastAPI startup if ENABLE_SCHEDULER=true
    - The scheduler triggers:
        * Morning cycle daily at SCHEDULER_MORNING_HOUR:SCHEDULER_MORNING_MINUTE ET
        * Evening cycle (over the watchlist) daily at SCHEDULER_EVENING_*
    - Weekly review (Friday) is wired but defaults to a no-op until Agent 14 lands

All jobs are submitted via the existing in-process job managers — same code
path the UI uses for manual triggers. So scheduled runs behave identically.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any, Optional
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from . import settings as live_settings
from .quant_source import find_candidates_today
from .watchlist import list_enabled_symbols

log = logging.getLogger(__name__)

# Module-level singleton — built lazily on first start_scheduler() call.
_scheduler: Optional[AsyncIOScheduler] = None
_last_runs: dict[str, dict[str, Any]] = {}


# --------------------------------------------------------------------------- #
# Job functions
# --------------------------------------------------------------------------- #


async def _job_morning_cycle() -> None:
    """Kick off the 4-agent morning cycle via the job manager."""
    # Import lazily — these modules import scheduler indirectly, avoid cycles.
    from api.ai_jobs import morning_job_manager

    log.info("scheduler: kicking off morning cycle")
    job_id = morning_job_manager.submit()
    _last_runs["morning_cycle"] = {
        "at": datetime.utcnow().isoformat(),
        "job_id": job_id,
    }


async def _job_evening_watchlist() -> None:
    """Loop through enabled watchlist symbols + quant candidates.

    We don't await each one to completion — the AIJobManager runs them in
    worker threads. We just submit with a small delay between to space out
    LLM API load.
    """
    from api.ai_jobs import ai_job_manager

    # Watchlist symbols + quant candidates, deduped (watchlist first)
    watchlist = [s.upper() for s in list_enabled_symbols()]
    quant_candidates = await _quant_candidates_or_empty()
    quant_symbols = [c.symbol for c in quant_candidates]

    seen: set[str] = set()
    combined: list[tuple[str, str, str]] = []   # (symbol, source, notes)
    for s in watchlist:
        if s not in seen:
            combined.append((s, "scheduled", "Evening watchlist"))
            seen.add(s)
    for c in quant_candidates:
        if c.symbol not in seen:
            note = f"Quant: score {c.score:.3f}, rank {c.rank}, " \
                    f"breakout={'Y' if c.breakout_ok else 'N'}"
            combined.append((c.symbol, "quant", note))
            seen.add(c.symbol)

    log.info(
        "scheduler: evening cycle — %d watchlist + %d quant = %d unique",
        len(watchlist), len(quant_symbols), len(combined),
    )
    submitted: list[dict[str, str]] = []
    gap = live_settings.get_evening_gap_secs()
    for sym, source, notes in combined:
        try:
            ai_job_manager.submit(sym, source, notes)
            submitted.append({"symbol": sym, "source": source})
        except Exception as e:  # noqa: BLE001
            log.warning("scheduler: failed to submit %s: %s", sym, e)
        await asyncio.sleep(gap)

    _last_runs["evening_cycle"] = {
        "at": datetime.utcnow().isoformat(),
        "symbols_submitted": submitted,
        "watchlist_count": len(watchlist),
        "quant_count": len(quant_symbols),
    }


async def _quant_candidates_or_empty() -> list:
    """Run the quant scanner. Never raise — if it fails, return []."""
    try:
        candidates = await find_candidates_today(
            universe_name="SP100", max_candidates=15,
        )
        return candidates
    except Exception as e:  # noqa: BLE001
        log.warning("scheduler: quant scan failed: %s", e)
        return []


async def _job_weekly_review() -> None:
    """Friday weekly review. Pushes to Telegram automatically inside the cycle."""
    from .pipeline_weekly import run_weekly_cycle
    log.info("scheduler: kicking off weekly review")
    try:
        await run_weekly_cycle()
        _last_runs["weekly_review"] = {"at": datetime.utcnow().isoformat()}
    except Exception as e:  # noqa: BLE001
        log.exception("scheduler: weekly review failed: %s", e)


# ---- Options module jobs (fully additive — failures never touch the rest) -- #


async def _job_options_scan() -> None:
    """Evening earnings-straddle scan (16:45 ET, on fresh EOD chains)."""
    try:
        from .options.scanner import run_scan
        res = await run_scan(notify=True)
        _last_runs["options_scan"] = {
            "at": datetime.utcnow().isoformat(),
            "scanned": res.get("scanned"), "qualified": res.get("qualified")}
    except Exception as e:  # noqa: BLE001
        log.exception("scheduler: options scan failed: %s", e)


async def _job_options_morning() -> None:
    """Morning mark: refresh open straddles + drift / date-revision / exit-day alerts."""
    try:
        from .options.positions import check_exit_alerts, mark_open_positions
        res = await mark_open_positions(notify=True)
        n = await check_exit_alerts(notify=True)
        _last_runs["options_morning"] = {
            "at": datetime.utcnow().isoformat(),
            "marked": res.get("marked"), "exit_alerts": n}
    except Exception as e:  # noqa: BLE001
        log.exception("scheduler: options morning failed: %s", e)


async def _job_options_final_alert() -> None:
    """Final pre-deadline exit warning (14:45 ET, fresh values, no digest)."""
    try:
        from .options.positions import check_exit_alerts, mark_open_positions
        await mark_open_positions(notify=False)
        n = await check_exit_alerts(notify=True)
        _last_runs["options_final_alert"] = {
            "at": datetime.utcnow().isoformat(), "exit_alerts": n}
    except Exception as e:  # noqa: BLE001
        log.exception("scheduler: options final alert failed: %s", e)


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #


def is_running() -> bool:
    return _scheduler is not None and _scheduler.running


def start_scheduler(force: bool = False) -> None:
    """Start the scheduler. Idempotent. Reads schedule from live settings.

    If `force` is True, ignores the enable flag — used by the UI "start" button.
    Otherwise honors live_settings.get_scheduler_enabled() (env default override).
    """
    global _scheduler
    if _scheduler is not None and _scheduler.running:
        return
    if not force and not live_settings.get_scheduler_enabled():
        log.info("scheduler: enable_scheduler=false — staying disabled")
        return

    tz_name = live_settings.get_scheduler_timezone()
    morn_h = live_settings.get_morning_hour()
    morn_m = live_settings.get_morning_minute()
    eve_h = live_settings.get_evening_hour()
    eve_m = live_settings.get_evening_minute()

    tz = ZoneInfo(tz_name)
    sched = AsyncIOScheduler(timezone=tz)
    sched.add_job(
        _job_morning_cycle,
        CronTrigger(hour=morn_h, minute=morn_m,
                    day_of_week="mon-fri", timezone=tz),
        id="morning_cycle",
        name="Morning cycle",
        replace_existing=True,
    )
    sched.add_job(
        _job_evening_watchlist,
        CronTrigger(hour=eve_h, minute=eve_m,
                    day_of_week="mon-fri", timezone=tz),
        id="evening_cycle",
        name="Evening cycle (watchlist + quant)",
        replace_existing=True,
    )
    # Weekly Performance Review — Friday after the evening cycle
    sched.add_job(
        _job_weekly_review,
        CronTrigger(hour=17, minute=0,
                    day_of_week="fri", timezone=tz),
        id="weekly_review",
        name="Weekly performance review (Friday)",
        replace_existing=True,
    )
    # ---- Options module (earnings straddles) — additive jobs ----
    sched.add_job(
        _job_options_scan,
        CronTrigger(hour=16, minute=45, day_of_week="mon-fri", timezone=tz),
        id="options_scan",
        name="Options: earnings-straddle scan",
        replace_existing=True,
    )
    sched.add_job(
        _job_options_morning,
        CronTrigger(hour=9, minute=15, day_of_week="mon-fri", timezone=tz),
        id="options_morning",
        name="Options: mark positions + exit-day alerts",
        replace_existing=True,
    )
    sched.add_job(
        _job_options_final_alert,
        CronTrigger(hour=14, minute=45, day_of_week="mon-fri", timezone=tz),
        id="options_final_alert",
        name="Options: final exit warning",
        replace_existing=True,
    )
    sched.start()
    _scheduler = sched
    log.info(
        "scheduler: started (tz=%s, morning %02d:%02d, evening %02d:%02d)",
        tz_name, morn_h, morn_m, eve_h, eve_m,
    )


def restart_scheduler() -> None:
    """Rebuild the scheduler from current settings. Used after edits."""
    stop_scheduler()
    start_scheduler(force=True)


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None and _scheduler.running:
        _scheduler.shutdown(wait=False)
    _scheduler = None
    log.info("scheduler: stopped")


def get_status() -> dict[str, Any]:
    """Snapshot for the UI — reads live settings."""
    info: dict[str, Any] = {
        "enabled_in_config": live_settings.get_scheduler_enabled(),
        "running": is_running(),
        "timezone": live_settings.get_scheduler_timezone(),
        "morning_cron": f"{live_settings.get_morning_hour():02d}:{live_settings.get_morning_minute():02d} mon-fri",
        "evening_cron": f"{live_settings.get_evening_hour():02d}:{live_settings.get_evening_minute():02d} mon-fri",
        "evening_gap_secs": live_settings.get_evening_gap_secs(),
        "last_runs": dict(_last_runs),
        "jobs": [],
    }
    if _scheduler is not None and _scheduler.running:
        for job in _scheduler.get_jobs():
            info["jobs"].append({
                "id": job.id,
                "name": job.name,
                "next_run": job.next_run_time.isoformat() if job.next_run_time else None,
                "trigger": str(job.trigger),
            })
    return info


async def trigger_morning_now() -> str:
    """Manually fire the morning cycle (returns the job_id)."""
    from api.ai_jobs import morning_job_manager
    job_id = morning_job_manager.submit()
    _last_runs["morning_cycle"] = {
        "at": datetime.utcnow().isoformat(),
        "job_id": job_id,
        "manual": True,
    }
    return job_id


async def trigger_evening_now() -> dict[str, Any]:
    """Manually fire the evening cycle (watchlist + quant). Returns summary."""
    # Re-use the same code path the scheduler uses
    await _job_evening_watchlist()
    summary = dict(_last_runs.get("evening_cycle") or {})
    summary["manual"] = True
    return summary


async def trigger_weekly_now() -> dict[str, Any]:
    """Manually fire the Friday weekly review."""
    from .pipeline_weekly import run_weekly_cycle
    report = await run_weekly_cycle()
    summary = {
        "at": datetime.utcnow().isoformat(),
        "manual": True,
        "grade": report.weekly_grade if report else None,
        "had_activity": report is not None,
    }
    _last_runs["weekly_review"] = summary
    return summary


async def trigger_quant_scan_now() -> list[dict[str, Any]]:
    """Run the quant scanner and return today's candidates (don't submit)."""
    candidates = await _quant_candidates_or_empty()
    return [c.model_dump() for c in candidates]
