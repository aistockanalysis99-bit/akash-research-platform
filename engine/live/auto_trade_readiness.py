"""Redacted auto-trade readiness snapshots for API/UI consumers."""
from __future__ import annotations

from typing import Any

from ..config import load_auto_trade_config
from ..db.schema import get_connection
from .alpaca import alpaca_readiness
from .telegram import TelegramClient
from .telegram_auth import authorized_chat_count
from .telegram_polling import polling_status

REQUIRED_TABLES = (
    "telegram_authorized_chats",
    "telegram_auth_attempts",
    "telegram_bot_state",
    "auto_trade_runs",
    "strategy_v4_signal_snapshots",
    "pair_trade_intents",
    "pair_trade_legs",
    "broker_orders",
    "broker_order_events",
    "notification_outbox",
    "auto_trade_control",
    "auto_trade_control_audit",
    "automation_locks",
    "automation_heartbeats",
    "alpaca_account_snapshots",
)


def database_readiness() -> dict[str, Any]:
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        present = {row["name"] for row in rows}
    finally:
        conn.close()
    missing = sorted(set(REQUIRED_TABLES) - present)
    return {"ready": not missing, "missing_tables": missing}


def readiness_snapshot() -> dict[str, Any]:
    config = load_auto_trade_config()
    from . import scheduler

    return {
        "phase": 3,
        "trade_submission_available": False,
        "configuration": config.public_snapshot(),
        "database": database_readiness(),
        "scheduler": scheduler.get_status(),
        "telegram": {
            "authorized_chat_count": authorized_chat_count(),
            **polling_status(),
        },
    }


async def telegram_readiness() -> dict[str, Any]:
    config = load_auto_trade_config()
    base = {
        "configured": bool(config.telegram_enabled and config.telegram_bot_token),
        "authorized_chat_count": authorized_chat_count(),
        **polling_status(),
    }
    if not base["configured"]:
        return {**base, "connected": False}
    try:
        identity = await TelegramClient(token=config.telegram_bot_token).get_me()
        return {
            **base,
            "connected": True,
            "bot_id": identity.get("id"),
            "username": identity.get("username"),
            "can_join_groups": bool(identity.get("can_join_groups", False)),
        }
    except Exception:  # noqa: BLE001 — readiness responses are deliberately sanitized
        return {**base, "connected": False, "error": "Telegram identity check failed"}


def broker_readiness() -> dict[str, Any]:
    return alpaca_readiness(load_auto_trade_config())
