"""Runtime settings — key/value overrides on top of env defaults.

Pattern: each accessor checks the SQLite `settings` table first, falls back
to the env default from engine.config. Setters write to the table and take
effect on the next read — no restart required for the values that callers
read live (portfolio sizing, scheduler enable flag, etc).

Sensitive credentials (API keys, Telegram token) stay env-only by design.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Optional

from ..config import (
    ENABLE_SCHEDULER,
    SCHEDULER_EVENING_GAP_SECS,
    SCHEDULER_EVENING_HOUR,
    SCHEDULER_EVENING_MINUTE,
    SCHEDULER_MORNING_HOUR,
    SCHEDULER_MORNING_MINUTE,
    SCHEDULER_TIMEZONE,
    VIRTUAL_INITIAL_CAPITAL,
    VIRTUAL_MAX_GROSS_PCT,
    VIRTUAL_RISK_PCT,
    VIRTUAL_STOP_PCT,
    VIRTUAL_TRAIL_PCT,
)
from ..db.schema import get_connection

log = logging.getLogger(__name__)


# ---- Generic key/value layer --------------------------------------------- #


def _get_raw(key: str) -> Optional[str]:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT value FROM settings WHERE key = ?", (key,),
        ).fetchone()
        return row["value"] if row else None
    finally:
        conn.close()


def _set_raw(key: str, value: str) -> None:
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO settings (key, value, updated_at) VALUES (?, ?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value, "
            "updated_at=excluded.updated_at",
            (key, value, datetime.utcnow().isoformat()),
        )
        conn.commit()
    finally:
        conn.close()


def _get_float(key: str, default: float, lo: float, hi: float) -> float:
    raw = _get_raw(key)
    if raw is None:
        return default
    try:
        v = float(raw)
    except ValueError:
        return default
    return max(lo, min(hi, v))


def _get_int(key: str, default: int, lo: int, hi: int) -> int:
    raw = _get_raw(key)
    if raw is None:
        return default
    try:
        v = int(raw)
    except ValueError:
        return default
    return max(lo, min(hi, v))


def _get_bool(key: str, default: bool) -> bool:
    raw = _get_raw(key)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


# ---- Portfolio sizing accessors ------------------------------------------ #


def get_initial_capital() -> float:
    return _get_float("virtual_initial_capital",
                       VIRTUAL_INITIAL_CAPITAL, 10_000.0, 1_000_000_000.0)


def get_risk_pct() -> float:
    return _get_float("virtual_risk_pct",
                       VIRTUAL_RISK_PCT, 0.001, 0.10)


def get_stop_pct() -> float:
    return _get_float("virtual_stop_pct",
                       VIRTUAL_STOP_PCT, 0.02, 0.30)


def get_trail_pct() -> float:
    return _get_float("virtual_trail_pct",
                       VIRTUAL_TRAIL_PCT, 0.02, 0.30)


def get_max_gross_pct() -> float:
    return _get_float("virtual_max_gross_pct",
                       VIRTUAL_MAX_GROSS_PCT, 0.10, 5.0)


# ---- Scheduler accessors ------------------------------------------------- #


def get_scheduler_enabled() -> bool:
    """Effective enabled flag (UI override beats env)."""
    return _get_bool("enable_scheduler", ENABLE_SCHEDULER)


def get_scheduler_timezone() -> str:
    return _get_raw("scheduler_timezone") or SCHEDULER_TIMEZONE


def get_morning_hour() -> int:
    return _get_int("scheduler_morning_hour",
                     SCHEDULER_MORNING_HOUR, 0, 23)


def get_morning_minute() -> int:
    return _get_int("scheduler_morning_minute",
                     SCHEDULER_MORNING_MINUTE, 0, 59)


def get_evening_hour() -> int:
    return _get_int("scheduler_evening_hour",
                     SCHEDULER_EVENING_HOUR, 0, 23)


def get_evening_minute() -> int:
    return _get_int("scheduler_evening_minute",
                     SCHEDULER_EVENING_MINUTE, 0, 59)


def get_evening_gap_secs() -> int:
    return _get_int("scheduler_evening_gap_secs",
                     SCHEDULER_EVENING_GAP_SECS, 0, 3600)


# ---- Settings snapshot + bulk update ------------------------------------- #


def get_all() -> dict[str, Any]:
    """Snapshot of every effective setting + its env default for the UI."""
    return {
        "portfolio": {
            "initial_capital":   {"value": get_initial_capital(),    "env_default": VIRTUAL_INITIAL_CAPITAL},
            "risk_pct":          {"value": get_risk_pct(),           "env_default": VIRTUAL_RISK_PCT},
            "stop_pct":          {"value": get_stop_pct(),           "env_default": VIRTUAL_STOP_PCT},
            "trail_pct":         {"value": get_trail_pct(),          "env_default": VIRTUAL_TRAIL_PCT},
            "max_gross_pct":     {"value": get_max_gross_pct(),      "env_default": VIRTUAL_MAX_GROSS_PCT},
        },
        "scheduler": {
            "enabled":           {"value": get_scheduler_enabled(),  "env_default": ENABLE_SCHEDULER},
            "timezone":          {"value": get_scheduler_timezone(), "env_default": SCHEDULER_TIMEZONE},
            "morning_hour":      {"value": get_morning_hour(),       "env_default": SCHEDULER_MORNING_HOUR},
            "morning_minute":    {"value": get_morning_minute(),     "env_default": SCHEDULER_MORNING_MINUTE},
            "evening_hour":      {"value": get_evening_hour(),       "env_default": SCHEDULER_EVENING_HOUR},
            "evening_minute":    {"value": get_evening_minute(),     "env_default": SCHEDULER_EVENING_MINUTE},
            "evening_gap_secs":  {"value": get_evening_gap_secs(),   "env_default": SCHEDULER_EVENING_GAP_SECS},
        },
    }


# Whitelist of keys the API will accept for /settings POST.
SETTABLE_KEYS = {
    # portfolio
    "virtual_initial_capital",
    "virtual_risk_pct",
    "virtual_stop_pct",
    "virtual_trail_pct",
    "virtual_max_gross_pct",
    # scheduler
    "enable_scheduler",
    "scheduler_timezone",
    "scheduler_morning_hour",
    "scheduler_morning_minute",
    "scheduler_evening_hour",
    "scheduler_evening_minute",
    "scheduler_evening_gap_secs",
}


def set_many(updates: dict[str, Any]) -> dict[str, Any]:
    """Apply a batch of settings updates. Returns the new snapshot.

    Unknown keys are silently dropped (whitelist enforced).
    """
    applied: list[str] = []
    rejected: list[str] = []
    for key, value in updates.items():
        if key not in SETTABLE_KEYS:
            rejected.append(key)
            continue
        _set_raw(key, str(value))
        applied.append(key)
    return {"applied": applied, "rejected": rejected, "snapshot": get_all()}
