"""Centralized config loaded from environment variables."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping
from urllib.parse import urlparse

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

# Model Lab — OpenRouter gateway (one key → DeepSeek, GLM, Qwen, Claude…)
# Used by the Compare Mode harness AND as an automatic fallback when the
# primary Gemini API is overloaded (503), so analyses don't fail on a spike.
OPENROUTER_API_KEY: str = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_FALLBACK_MODEL: str = os.getenv(
    "OPENROUTER_FALLBACK_MODEL", "qwen/qwen3.7-plus")

# Options module — Polygon.io/"Massive" (chains, greeks, IV; $79 Developer tier)
POLYGON_API_KEY: str = os.getenv("POLYGON_API_KEY", "")

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
# Supports TELEGRAM_TOKEN (Render standard) and TELEGRAM_BOT_TOKEN (legacy)
TELEGRAM_TOKEN: str = os.getenv("TELEGRAM_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_BOT_TOKEN: str = TELEGRAM_TOKEN
TELEGRAM_CHAT_ID: str = os.getenv("TELEGRAM_CHAT_ID", "")
TELEGRAM_ENABLED: bool = os.getenv("TELEGRAM_ENABLED", "false").lower() in ("1", "true", "yes", "on")
TELEGRAM_AUTH_PASSCODE: str = os.getenv("TELEGRAM_AUTH_PASSCODE", "")
# Optional separate group for ALL options-related messages (same bot).
# Empty = everything goes to the main chat. Also settable live from the UI
# (settings key options_telegram_chat_id overrides this env default).
TELEGRAM_OPTIONS_CHAT_ID: str = os.getenv("TELEGRAM_OPTIONS_CHAT_ID", "")

# Set ENABLE_SCHEDULER=true in .env to auto-run morning + evening cycles.
# Default is off — manual mode for testing.
ENABLE_SCHEDULER: bool = os.getenv("ENABLE_SCHEDULER", "false").lower() in ("1", "true", "yes")
SCHEDULER_TIMEZONE: str = os.getenv("SCHEDULER_TIMEZONE", "America/New_York")
SCHEDULER_MORNING_HOUR: int = int(os.getenv("SCHEDULER_MORNING_HOUR", "8"))
SCHEDULER_MORNING_MINUTE: int = int(os.getenv("SCHEDULER_MORNING_MINUTE", "0"))
SCHEDULER_EVENING_HOUR: int = int(os.getenv("SCHEDULER_EVENING_HOUR", "16"))
SCHEDULER_EVENING_MINUTE: int = int(os.getenv("SCHEDULER_EVENING_MINUTE", "30"))
SCHEDULER_EVENING_GAP_SECS: int = int(os.getenv("SCHEDULER_EVENING_GAP_SECS", "60"))

# Strategy 4 Alpaca paper automation. Phase 1 exposes read-only broker access;
# no order-submission method exists until the later execution phase.
ALPACA_API_KEY: str = os.getenv("ALPACA_API_KEY", "")
ALPACA_SECRET_KEY: str = os.getenv("ALPACA_SECRET_KEY", "")
ALPACA_BASE_URL: str = os.getenv(
    "ALPACA_BASE_URL", "https://paper-api.alpaca.markets").rstrip("/")
ALPACA_DATA_URL: str = os.getenv(
    "ALPACA_DATA_URL", "https://data.alpaca.markets").rstrip("/")

AUTO_TRADE_ENABLED: bool = os.getenv("AUTO_TRADE_ENABLED", "false").lower() in ("1", "true", "yes", "on")
AUTO_TRADE_PAPER_ONLY: bool = os.getenv("AUTO_TRADE_PAPER_ONLY", "true").lower() in ("1", "true", "yes", "on")


def _safe_int_env(key: str, default: int) -> int:
    try:
        return int(os.getenv(key, str(default)))
    except (TypeError, ValueError):
        return default


def _safe_float_env(key: str, default: float) -> float:
    try:
        return float(os.getenv(key, str(default)))
    except (TypeError, ValueError):
        return default


# Safe import-time defaults. load_auto_trade_config() retains validation errors
# so readiness fails closed without making the whole API unimportable.
AUTO_TRADE_PREMARKET_MINUTES: int = _safe_int_env("AUTO_TRADE_PREMARKET_MINUTES", 90)
AUTO_TRADE_MONITOR_MINUTES: int = _safe_int_env("AUTO_TRADE_MONITOR_MINUTES", 10)
AUTO_TRADE_MAX_OPEN_PAIRS: int = _safe_int_env("AUTO_TRADE_MAX_OPEN_PAIRS", 3)
AUTO_TRADE_MAX_NEW_PAIRS_PER_DAY: int = _safe_int_env("AUTO_TRADE_MAX_NEW_PAIRS_PER_DAY", 2)
AUTO_TRADE_MAX_GROSS_EXPOSURE_PCT: float = _safe_float_env("AUTO_TRADE_MAX_GROSS_EXPOSURE_PCT", 0.30)
AUTO_TRADE_PAIR_CAPITAL_PCT: float = _safe_float_env("AUTO_TRADE_PAIR_CAPITAL_PCT", 0.10)
AUTO_TRADE_MIN_BUYING_POWER_RESERVE_PCT: float = _safe_float_env(
    "AUTO_TRADE_MIN_BUYING_POWER_RESERVE_PCT", 0.20)
AUTO_TRADE_MAX_QUOTE_AGE_SECONDS: int = _safe_int_env(
    "AUTO_TRADE_MAX_QUOTE_AGE_SECONDS", 300)
AUTO_TRADE_MAX_PREMARKET_GAP_PCT: float = _safe_float_env(
    "AUTO_TRADE_MAX_PREMARKET_GAP_PCT", 3.0)


class AutoTradeConfigurationError(ValueError):
    """Raised when armed automation is not safe to run."""


def _env_bool(env: Mapping[str, str], key: str, default: bool) -> bool:
    raw = env.get(key)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


@dataclass(frozen=True)
class AutoTradeConfig:
    """Validated snapshot with secrets retained only in memory."""

    enabled: bool
    paper_only: bool
    alpaca_api_key: str = field(repr=False)
    alpaca_secret_key: str = field(repr=False)
    alpaca_base_url: str
    alpaca_data_url: str
    telegram_enabled: bool
    telegram_bot_token: str = field(repr=False)
    telegram_auth_passcode: str = field(repr=False)
    premarket_minutes: int
    monitor_minutes: int
    max_open_pairs: int
    max_new_pairs_per_day: int
    max_gross_exposure_pct: float
    pair_capital_pct: float
    min_buying_power_reserve_pct: float
    max_quote_age_seconds: int
    max_premarket_gap_pct: float
    parse_errors: tuple[str, ...] = ()

    def validation_errors(self) -> list[str]:
        errors = list(self.parse_errors)
        parsed = urlparse(self.alpaca_base_url)
        if parsed.scheme != "https" or not parsed.netloc:
            errors.append("ALPACA_BASE_URL must be an absolute HTTPS URL")
        if self.paper_only and self.alpaca_base_url.rstrip("/") != "https://paper-api.alpaca.markets":
            errors.append("paper-only mode requires the Alpaca paper endpoint")
        data_url = urlparse(self.alpaca_data_url)
        if data_url.scheme != "https" or not data_url.netloc:
            errors.append("ALPACA_DATA_URL must be an absolute HTTPS URL")
        if not 1 <= self.premarket_minutes <= 360:
            errors.append("AUTO_TRADE_PREMARKET_MINUTES must be between 1 and 360")
        if not 1 <= self.monitor_minutes <= 60:
            errors.append("AUTO_TRADE_MONITOR_MINUTES must be between 1 and 60")
        if self.max_open_pairs < 1 or self.max_new_pairs_per_day < 1:
            errors.append("pair limits must be positive integers")
        if not 1 <= self.max_quote_age_seconds <= 3600:
            errors.append("AUTO_TRADE_MAX_QUOTE_AGE_SECONDS must be between 1 and 3600")
        if not 0.0 <= self.max_premarket_gap_pct <= 25.0:
            errors.append("AUTO_TRADE_MAX_PREMARKET_GAP_PCT must be between 0 and 25")
        for name, value in (
            ("AUTO_TRADE_MAX_GROSS_EXPOSURE_PCT", self.max_gross_exposure_pct),
            ("AUTO_TRADE_PAIR_CAPITAL_PCT", self.pair_capital_pct),
            ("AUTO_TRADE_MIN_BUYING_POWER_RESERVE_PCT", self.min_buying_power_reserve_pct),
        ):
            if not 0.0 <= value <= 1.0:
                errors.append(f"{name} must be between 0 and 1")
        if self.enabled and not self.alpaca_api_key:
            errors.append("armed automation requires ALPACA_API_KEY")
        if self.enabled and not self.alpaca_secret_key:
            errors.append("armed automation requires ALPACA_SECRET_KEY")
        if self.telegram_enabled and not self.telegram_bot_token:
            errors.append("enabled Telegram requires TELEGRAM_TOKEN (or TELEGRAM_BOT_TOKEN)")
        if self.telegram_enabled and not self.telegram_auth_passcode:
            errors.append("enabled Telegram requires TELEGRAM_AUTH_PASSCODE")
        return list(dict.fromkeys(errors))

    @property
    def telegram_token(self) -> str:
        """Alias for telegram_bot_token matching the TELEGRAM_TOKEN standard."""
        return self.telegram_bot_token

    @property
    def ready(self) -> bool:
        return not self.validation_errors()

    def require_ready(self) -> None:
        errors = self.validation_errors()
        if errors:
            raise AutoTradeConfigurationError("; ".join(errors))

    def public_snapshot(self) -> dict[str, object]:
        """Return readiness information with no secret values."""
        errors = self.validation_errors()
        return {
            "enabled": self.enabled,
            "paper_only": self.paper_only,
            "ready": not errors,
            "errors": errors,
            "alpaca": {
                "api_key_configured": bool(self.alpaca_api_key),
                "secret_key_configured": bool(self.alpaca_secret_key),
                "base_url": self.alpaca_base_url,
                "data_url": self.alpaca_data_url,
            },
            "telegram": {
                "enabled": self.telegram_enabled,
                "token_configured": bool(self.telegram_bot_token),
                "passcode_configured": bool(self.telegram_auth_passcode),
            },
            "limits": {
                "premarket_minutes": self.premarket_minutes,
                "monitor_minutes": self.monitor_minutes,
                "max_open_pairs": self.max_open_pairs,
                "max_new_pairs_per_day": self.max_new_pairs_per_day,
                "max_gross_exposure_pct": self.max_gross_exposure_pct,
                "pair_capital_pct": self.pair_capital_pct,
                "min_buying_power_reserve_pct": self.min_buying_power_reserve_pct,
                "max_quote_age_seconds": self.max_quote_age_seconds,
                "max_premarket_gap_pct": self.max_premarket_gap_pct,
            },
        }


def load_auto_trade_config(environ: Mapping[str, str] | None = None) -> AutoTradeConfig:
    """Load a fresh snapshot. Invalid numbers fail closed without crashing import."""
    env = os.environ if environ is None else environ
    parse_errors: list[str] = []

    def integer(key: str, default: int) -> int:
        try:
            return int(env.get(key, str(default)))
        except (TypeError, ValueError):
            parse_errors.append(f"{key} must be an integer")
            return default

    def number(key: str, default: float) -> float:
        try:
            return float(env.get(key, str(default)))
        except (TypeError, ValueError):
            parse_errors.append(f"{key} must be a number")
            return default

    return AutoTradeConfig(
        enabled=_env_bool(env, "AUTO_TRADE_ENABLED", False),
        paper_only=_env_bool(env, "AUTO_TRADE_PAPER_ONLY", True),
        alpaca_api_key=env.get("ALPACA_API_KEY", "").strip(),
        alpaca_secret_key=env.get("ALPACA_SECRET_KEY", "").strip(),
        alpaca_base_url=env.get("ALPACA_BASE_URL", "https://paper-api.alpaca.markets").strip().rstrip("/"),
        alpaca_data_url=env.get("ALPACA_DATA_URL", "https://data.alpaca.markets").strip().rstrip("/"),
        telegram_enabled=_env_bool(env, "TELEGRAM_ENABLED", False),
        telegram_bot_token=(env.get("TELEGRAM_TOKEN") or env.get("TELEGRAM_BOT_TOKEN", "")).strip(),
        telegram_auth_passcode=env.get("TELEGRAM_AUTH_PASSCODE", "").strip(),
        premarket_minutes=integer("AUTO_TRADE_PREMARKET_MINUTES", 90),
        monitor_minutes=integer("AUTO_TRADE_MONITOR_MINUTES", 10),
        max_open_pairs=integer("AUTO_TRADE_MAX_OPEN_PAIRS", 3),
        max_new_pairs_per_day=integer("AUTO_TRADE_MAX_NEW_PAIRS_PER_DAY", 2),
        max_gross_exposure_pct=number("AUTO_TRADE_MAX_GROSS_EXPOSURE_PCT", 0.30),
        pair_capital_pct=number("AUTO_TRADE_PAIR_CAPITAL_PCT", 0.10),
        min_buying_power_reserve_pct=number("AUTO_TRADE_MIN_BUYING_POWER_RESERVE_PCT", 0.20),
        max_quote_age_seconds=integer("AUTO_TRADE_MAX_QUOTE_AGE_SECONDS", 300),
        max_premarket_gap_pct=number("AUTO_TRADE_MAX_PREMARKET_GAP_PCT", 3.0),
        parse_errors=tuple(parse_errors),
    )

API_HOST: str = os.getenv("API_HOST", "127.0.0.1")
API_PORT: int = int(os.getenv("API_PORT", "8000"))
UI_HOST: str = os.getenv("UI_HOST", "127.0.0.1")
UI_PORT: int = int(os.getenv("UI_PORT", "8080"))

LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")

# Make sure directories exist
DATA_CACHE_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)
AI_RESEARCH_DIR.mkdir(parents=True, exist_ok=True)
