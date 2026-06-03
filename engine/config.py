"""Centralized config loaded from environment variables."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# Load .env from project root. override=True so .env is authoritative — fixes
# the case where the OS has stale/empty values for keys we care about.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env", override=True)

FMP_API_KEY: str = os.getenv("FMP_API_KEY", "")
# NOTE: only /stable/ endpoints work. /api/v3/ returns 403 (deprecated post-2025).
FMP_BASE_URL: str = "https://financialmodelingprep.com/stable"

# Phase 2 — AI pipeline LLM credentials
GOOGLE_API_KEY: str = os.getenv("GOOGLE_API_KEY", "")
ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")

# Phase 4 — Unusual Whales (institutional flow + dark pool + options flow)
UW_API_KEY: str = os.getenv("UW_API_KEY", "")

def _resolve_path(env_key: str, default_rel: str) -> Path:
    """Resolve a storage path from env.

    - Absolute env value (e.g. /var/data/runs.sqlite on a Render disk) is used
      as-is — critical for mounting a persistent volume in production.
    - Relative value is taken relative to PROJECT_ROOT (local dev default).
    """
    val = os.getenv(env_key, default_rel)
    p = Path(val)
    if p.is_absolute():
        return p
    return PROJECT_ROOT / val.lstrip("./")


DATA_CACHE_DIR: Path = _resolve_path("DATA_CACHE_DIR", "./data_cache")
DB_PATH: Path = _resolve_path("DB_PATH", "./runs.sqlite")
LOG_DIR: Path = _resolve_path("LOG_DIR", "./logs")

# Phase 2 — per-stock AI research artifacts (markdown + raw JSON)
AI_RESEARCH_DIR: Path = _resolve_path("AI_RESEARCH_DIR", "./ai_research")

# Phase 4 — per-stock profile dossiers (YAML frontmatter + markdown body)
WATCHLIST_PROFILE_DIR: Path = _resolve_path("WATCHLIST_PROFILE_DIR", "./watchlist")
WATCHLIST_PROFILE_DIR.mkdir(parents=True, exist_ok=True)

# Phase 3 — virtual paper-trading portfolio
VIRTUAL_INITIAL_CAPITAL: float = float(os.getenv("VIRTUAL_INITIAL_CAPITAL", "2000000"))
VIRTUAL_RISK_PCT: float = float(os.getenv("VIRTUAL_RISK_PCT", "0.02"))
VIRTUAL_STOP_PCT: float = float(os.getenv("VIRTUAL_STOP_PCT", "0.08"))
VIRTUAL_TRAIL_PCT: float = float(os.getenv("VIRTUAL_TRAIL_PCT", "0.10"))
# Max gross exposure as a fraction of equity. 1.0 = 100%, no leverage.
# Set above 1.0 only if the fund is genuinely allowed to use margin.
VIRTUAL_MAX_GROSS_PCT: float = float(os.getenv("VIRTUAL_MAX_GROSS_PCT", "1.0"))

# Phase 4 — Telegram + Scheduler
TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID: str = os.getenv("TELEGRAM_CHAT_ID", "")

# Set ENABLE_SCHEDULER=true in .env to auto-run morning + evening cycles.
# Default is off — manual mode for testing.
ENABLE_SCHEDULER: bool = os.getenv("ENABLE_SCHEDULER", "false").lower() in ("1", "true", "yes")
SCHEDULER_TIMEZONE: str = os.getenv("SCHEDULER_TIMEZONE", "America/New_York")
SCHEDULER_MORNING_HOUR: int = int(os.getenv("SCHEDULER_MORNING_HOUR", "8"))
SCHEDULER_MORNING_MINUTE: int = int(os.getenv("SCHEDULER_MORNING_MINUTE", "0"))
SCHEDULER_EVENING_HOUR: int = int(os.getenv("SCHEDULER_EVENING_HOUR", "16"))
SCHEDULER_EVENING_MINUTE: int = int(os.getenv("SCHEDULER_EVENING_MINUTE", "30"))
SCHEDULER_EVENING_GAP_SECS: int = int(os.getenv("SCHEDULER_EVENING_GAP_SECS", "60"))

API_HOST: str = os.getenv("API_HOST", "127.0.0.1")
API_PORT: int = int(os.getenv("API_PORT", "8000"))
UI_HOST: str = os.getenv("UI_HOST", "127.0.0.1")
UI_PORT: int = int(os.getenv("UI_PORT", "8080"))

LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")

# Make sure directories exist
DATA_CACHE_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)
AI_RESEARCH_DIR.mkdir(parents=True, exist_ok=True)
