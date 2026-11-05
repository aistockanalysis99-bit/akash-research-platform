"""Lifecycle-managed Telegram long polling for local deployments."""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

from ..config import load_auto_trade_config
from .telegram import TelegramClient
from .telegram_auth import TelegramAuthService, get_last_update_id

log = logging.getLogger(__name__)

_task: Optional[asyncio.Task[None]] = None
_stop_event: Optional[asyncio.Event] = None


async def _poll_loop() -> None:
    config = load_auto_trade_config()
    client = TelegramClient(token=config.telegram_bot_token)
    auth = TelegramAuthService(config)
    assert _stop_event is not None
    backoff = 1.0
    while not _stop_event.is_set():
        try:
            updates = await client.get_updates(
                offset=get_last_update_id() + 1,
                timeout=25,
            )
            for update in updates:
                response = auth.process_update(update)
                if response.chat_id and response.text:
                    await client.send_direct(response.chat_id, response.text)
            backoff = 1.0
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 — polling must self-heal
            log.warning("telegram polling error: %s", type(exc).__name__)
            try:
                await asyncio.wait_for(_stop_event.wait(), timeout=backoff)
            except asyncio.TimeoutError:
                pass
            backoff = min(backoff * 2, 30.0)


def start_telegram_polling() -> bool:
    """Start once when configured. Returns whether a task is active."""
    global _task, _stop_event
    config = load_auto_trade_config()
    if not (
        config.telegram_enabled
        and config.telegram_bot_token
        and config.telegram_auth_passcode
    ):
        log.info("telegram polling disabled or incomplete configuration")
        return False
    if _task is not None and not _task.done():
        return True
    _stop_event = asyncio.Event()
    _task = asyncio.create_task(_poll_loop(), name="telegram-auth-polling")
    return True


async def stop_telegram_polling() -> None:
    global _task, _stop_event
    if _task is None:
        return
    if _stop_event is not None:
        _stop_event.set()
    _task.cancel()
    try:
        await _task
    except asyncio.CancelledError:
        pass
    _task = None
    _stop_event = None


def polling_status() -> dict[str, bool]:
    return {"running": bool(_task is not None and not _task.done())}
