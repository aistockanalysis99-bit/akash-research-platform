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


def get_cash_balance() -> float:
    """Editable cash balance (un-invested funds). Default 0. Can go negative
    (margin-style) — no limit enforced."""
    return _get_float("virtual_cash_balance", 0.0,
                       -1_000_000_000.0, 1_000_000_000.0)


def set_cash_balance(value: float) -> None:
    set_many({"virtual_cash_balance": float(value)})


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


# Default cap on the number of distinct open positions in the portfolio.
DEFAULT_MAX_POSITIONS = 30


def get_max_positions() -> int:
    """Maximum number of distinct open positions allowed in the portfolio."""
    return _get_int("virtual_max_positions", DEFAULT_MAX_POSITIONS, 1, 200)


# Hard ceiling on any single stock's weight, as a fraction of the fund.
# The AI sizes each position within this cap (default 10%).
DEFAULT_MAX_SINGLE_NAME_PCT = 0.10


def get_max_single_name_pct() -> float:
    """Max weight for any one stock, as a fraction of total fund (0.10 = 10%)."""
    return _get_float("virtual_max_single_name_pct",
                       DEFAULT_MAX_SINGLE_NAME_PCT, 0.01, 1.0)


# ---- Options module (earnings-straddle scanner) accessors ------------------ #


def get_options_entry_min_days() -> int:
    return _get_int("options_entry_min_days", 3, 1, 30)


def get_options_entry_max_days() -> int:
    return _get_int("options_entry_max_days", 14, 2, 30)


def get_options_cheapness_max() -> float:
    return _get_float("options_cheapness_max", 0.80, 0.3, 2.0)


def get_options_min_oi() -> int:
    return _get_int("options_min_oi", 500, 0, 100_000)


def get_options_max_spread_pct() -> float:
    return _get_float("options_max_spread_pct", 1.5, 0.1, 20.0)


def get_options_universe() -> str:
    """Broad universe the scanner adds on top of watchlist + held stocks.
    'sp500' (default) · 'sp100' · 'none' (watchlist + holdings only)."""
    raw = (_get_raw("options_universe") or "sp500").strip().lower()
    return raw if raw in ("sp500", "sp100", "none") else "sp500"


def get_options_max_iv_percentile() -> float:
    """Optional richness gate: reject a candidate when its current ATM IV sits
    above this percentile of the stock's OWN accumulated IV history (we build
    that history daily — Polygon has no historical-IV feed). 100 = OFF (never
    rejects); the gate also stays inert until enough history exists. Buying a
    straddle when IV is already rich is the losing side, so tightening this
    (e.g. 80) refuses the most over-pumped names."""
    return _get_float("options_max_iv_percentile", 100.0, 0.0, 100.0)


def get_options_require_dual_signal() -> bool:
    """When ON, only names that are ALSO a 7+ AI-conviction pick qualify —
    focuses the strategy on stocks the platform independently likes. OFF by
    default (dual-signal stays a badge, not a filter)."""
    return _get_bool("options_require_dual_signal", False)


def get_options_profit_target_pct() -> float:
    """Send a one-time 'consider taking profit' suggestion once an open paper
    straddle is up at least this %. 0 = OFF. Notify-only — never auto-closed."""
    return _get_float("options_profit_target_pct", 50.0, 0.0, 500.0)


def get_options_stop_loss_pct() -> float:
    """Send a one-time 'consider cutting' suggestion once an open paper straddle
    is down at least this %. 0 = OFF (default — long-vol stops into earnings are
    noisy). Notify-only — never auto-closed."""
    return _get_float("options_stop_loss_pct", 0.0, 0.0, 100.0)


def get_options_max_concurrent() -> int:
    """Cap on simultaneously-open paper straddles. 0 = OFF (unlimited)."""
    return _get_int("options_max_concurrent", 0, 0, 100)


def get_options_max_sleeve_capital() -> float:
    """Cap on total capital tied up across open paper straddles (sum of entry
    cost × 100 × contracts, in $). 0 = OFF (unlimited). Keeps the options sleeve
    from quietly growing past a comfort level; fully separate from equity cash."""
    return _get_float("options_max_sleeve_capital", 0.0, 0.0, 100_000_000.0)


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
            "max_positions":     {"value": get_max_positions(),      "env_default": DEFAULT_MAX_POSITIONS},
            "max_single_name_pct": {"value": get_max_single_name_pct(), "env_default": DEFAULT_MAX_SINGLE_NAME_PCT},
        },
        "options": {
            "entry_min_days":  {"value": get_options_entry_min_days(),  "env_default": 3},
            "entry_max_days":  {"value": get_options_entry_max_days(),  "env_default": 14},
            "cheapness_max":   {"value": get_options_cheapness_max(),   "env_default": 0.80},
            "min_oi":          {"value": get_options_min_oi(),          "env_default": 500},
            "max_spread_pct":  {"value": get_options_max_spread_pct(),  "env_default": 1.5},
            "universe":        {"value": get_options_universe(),        "env_default": "sp500"},
            "max_iv_percentile":   {"value": get_options_max_iv_percentile(),   "env_default": 100.0},
            "require_dual_signal": {"value": get_options_require_dual_signal(),  "env_default": False},
            "profit_target_pct":   {"value": get_options_profit_target_pct(),    "env_default": 50.0},
            "stop_loss_pct":       {"value": get_options_stop_loss_pct(),        "env_default": 0.0},
            "max_concurrent":      {"value": get_options_max_concurrent(),       "env_default": 0},
            "max_sleeve_capital":  {"value": get_options_max_sleeve_capital(),   "env_default": 0.0},
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
    "virtual_cash_balance",
    "virtual_risk_pct",
    "virtual_stop_pct",
    "virtual_trail_pct",
    "virtual_max_gross_pct",
    "virtual_max_positions",
    "virtual_max_single_name_pct",
    # options module
    "options_entry_min_days",
    "options_entry_max_days",
    "options_cheapness_max",
    "options_min_oi",
    "options_max_spread_pct",
    "options_universe",
    "options_max_iv_percentile",
    "options_require_dual_signal",
    "options_profit_target_pct",
    "options_stop_loss_pct",
    "options_max_concurrent",
    "options_max_sleeve_capital",
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
