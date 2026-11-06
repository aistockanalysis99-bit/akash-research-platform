"""Telegram transport for outbound alerts and inbound authorization replies.

General outbound alerts are broadcast only to chats authorized by the passcode
flow. The legacy TELEGRAM_CHAT_ID is used only when passcode onboarding is not
configured, preserving older deployments without bypassing the new allow-list.

Every attempt is logged to the telegram_log SQLite table so the UI can show
a delivery history.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

import httpx

from ..config import (
    TELEGRAM_AUTH_PASSCODE,
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_CHAT_ID,
    TELEGRAM_ENABLED,
    TELEGRAM_TOKEN,
)
from ..db.schema import get_connection
from .schemas import MorningBriefing, PMDecision

log = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"
TELEGRAM_METHOD_API = "https://api.telegram.org/bot{token}/{method}"
MAX_MESSAGE_LEN = 4000  # Telegram limit is 4096, leave headroom

# Message kinds that belong to the OPTIONS side of the platform. When a
# separate options group is configured (settings key options_telegram_chat_id
# or env TELEGRAM_OPTIONS_CHAT_ID), these — and only these — route there.
# Everything else (stock verdicts, morning briefings, errors) stays in the
# main chat. Same bot either way.
OPTIONS_KINDS_PREFIX = "options"          # options_digest/_alert/_exit/_weekly
OPTIONS_KINDS_EXACT = {"strategy_board"}  # the evening board digest


def _is_options_kind(kind: str) -> bool:
    return kind.startswith(OPTIONS_KINDS_PREFIX) or kind in OPTIONS_KINDS_EXACT


class TelegramClient:
    """Async outbound-only Telegram client."""

    def __init__(
        self,
        token: Optional[str] = None,
        chat_id: Optional[str] = None,
    ) -> None:
        self.token = token if token is not None else (TELEGRAM_TOKEN or TELEGRAM_BOT_TOKEN)
        self._explicit_chat = chat_id is not None
        self.chat_id = chat_id if chat_id is not None else TELEGRAM_CHAT_ID

    @property
    def enabled(self) -> bool:
        return bool(TELEGRAM_ENABLED and self.token)

    async def send_message(
        self,
        text: str,
        kind: str = "manual",
        symbol: Optional[str] = None,
        parse_mode: Optional[str] = None,  # None = plain text, no escaping needed
    ) -> bool:
        """Send `text` to the configured chat. Returns True on success.

        On failure, logs to console + telegram_log. Never raises — calling
        code should not be coupled to delivery reliability.
        """
        truncated = text[:MAX_MESSAGE_LEN]
        targets = self.resolve_targets(kind)

        if not (self.enabled and targets):
            self._log(kind, symbol, truncated, success=False,
                       error="not_configured")
            log.info("telegram: skipping — disabled, token missing, or no authorized chat")
            return False

        results = [
            await self._send_one(target, truncated, parse_mode=parse_mode)
            for target in dict.fromkeys(targets)
        ]
        success = any(results)
        self._log(
            kind,
            symbol,
            truncated,
            success=success,
            error=None if success else "send failed for all authorized chats",
        )
        return success

    def resolve_targets(self, kind: str = "manual") -> list[str]:
        """Resolve recipients without exposing credentials or bypassing auth.

        Once passcode onboarding is configured, every normal broadcast uses the
        authorization table. Legacy fixed chat IDs remain a fallback only for
        older deployments that have no onboarding passcode.
        """
        if TELEGRAM_AUTH_PASSCODE:
            try:
                from .telegram_auth import list_authorized_chats
                return list(dict.fromkeys(row.chat_id for row in list_authorized_chats()))
            except Exception as e:  # noqa: BLE001
                log.warning("telegram: authorized-chat lookup failed: %s", e)
                return []

        if self._explicit_chat and self.chat_id:
            return [self.chat_id]
        if _is_options_kind(kind):
            try:
                from . import settings as live_settings
                options_chat = live_settings.get_options_telegram_chat_id()
                if options_chat:
                    return [options_chat]
            except Exception as e:  # noqa: BLE001
                log.warning("telegram: options-chat lookup failed: %s", e)
        return [TELEGRAM_CHAT_ID] if TELEGRAM_CHAT_ID else []

    async def send_direct(
        self, chat_id: str, text: str, parse_mode: Optional[str] = None,
    ) -> bool:
        """Reply to a specific chat during authorization; never broadcasts."""
        if not (self.enabled and chat_id):
            return False
        return await self._send_one(str(chat_id), text[:MAX_MESSAGE_LEN], parse_mode)

    async def _send_one(
        self, target_chat: str, text: str, parse_mode: Optional[str] = None,
    ) -> bool:
        """Low-level send with bounded retry. Does not write message content logs."""

        url = TELEGRAM_API.format(token=self.token)
        payload: dict = {"chat_id": target_chat, "text": text}
        if parse_mode:
            payload["parse_mode"] = parse_mode

        # Retry on transient failures (network blips, timeouts, 429/5xx).
        # A single dropped message used to mean the whole verdict half went
        # missing — now we try up to 3 times with backoff.
        import asyncio
        last_err: Optional[str] = None
        for attempt in range(3):
            try:
                async with httpx.AsyncClient(timeout=20.0) as client:
                    r = await client.post(url, json=payload)
                if r.status_code == 200 and r.json().get("ok") is True:
                    return True
                # Non-OK response — capture body, decide whether to retry
                last_err = f"HTTP {r.status_code}: {r.text[:200]}"
                # 429 = rate limited; respect Telegram's retry_after if given
                retry_after = 1.0
                if r.status_code == 429:
                    try:
                        retry_after = float(
                            r.json().get("parameters", {}).get("retry_after", 1)
                        )
                    except Exception:  # noqa: BLE001
                        retry_after = 2.0
                elif r.status_code < 500 and r.status_code != 429:
                    # 4xx other than 429 (e.g. bad request) won't fix on retry
                    break
                await asyncio.sleep(retry_after + attempt)
            except Exception as e:  # noqa: BLE001 — transient network error
                last_err = f"{type(e).__name__}: {e}"[:200] or "unknown_error"
                await asyncio.sleep(0.5 + attempt)

        log.warning("telegram send failed after retries: %s", last_err)
        return False

    async def get_me(self) -> dict:
        """Return Telegram bot identity. Token is never included."""
        if not self.enabled:
            raise RuntimeError("Telegram is not configured")
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(
                TELEGRAM_METHOD_API.format(token=self.token, method="getMe"))
        data = response.json()
        if response.status_code != 200 or not data.get("ok"):
            raise RuntimeError("Telegram bot identity check failed")
        result = data.get("result")
        if not isinstance(result, dict):
            raise RuntimeError("Telegram returned an invalid bot identity")
        return result

    async def get_updates(
        self, *, offset: int, timeout: int = 25,
    ) -> list[dict]:
        """Long-poll Telegram updates; caller persists the processed offset."""
        if not self.enabled:
            return []
        async with httpx.AsyncClient(timeout=timeout + 10.0) as client:
            response = await client.get(
                TELEGRAM_METHOD_API.format(token=self.token, method="getUpdates"),
                params={
                    "offset": offset,
                    "timeout": timeout,
                    "allowed_updates": '["message"]',
                },
            )
        data = response.json()
        if response.status_code != 200 or not data.get("ok"):
            raise RuntimeError("Telegram update polling failed")
        result = data.get("result", [])
        return result if isinstance(result, list) else []

    # ------------------------------------------------------------------ #
    # Convenience builders
    # ------------------------------------------------------------------ #

    async def send_pm_verdict(self, symbol: str, pm: PMDecision) -> bool:
        """Send TWO messages for every PM verdict — stock view, then portfolio fit.

        The stock view is the research thesis (buy/size/exit) regardless of
        whether we execute today. The portfolio-fit view (sent ~1 sec after)
        explains the execution decision — including why a high-conviction
        BUY may still be REJECTed when the book has no room.

        Returns True if at least the stock message was sent.
        """
        # 1️⃣ Stock-focused message
        stock_text = (pm.telegram_message or "").strip()
        if not stock_text:
            stock_text = (
                f"{pm.decision} {symbol} — conviction {pm.conviction_score}/10, "
                f"size {pm.recommended_size_pct}%"
            )
        # Prefix so the client knows what kind of message this is
        stock_payload = f"📈 STOCK VIEW · {symbol} · {pm.decision}\n\n{stock_text}"
        ok_stock = await self.send_message(
            stock_payload, kind="pm_verdict_stock", symbol=symbol,
        )

        # 2️⃣ Portfolio-fit message (if PM wrote one)
        portfolio_text = (pm.telegram_portfolio_message or "").strip()
        if portfolio_text:
            portfolio_payload = (
                f"💼 PORTFOLIO FIT · {symbol}\n\n{portfolio_text}"
            )
            # Send right after — small spacing for chat readability
            import asyncio
            await asyncio.sleep(0.8)
            await self.send_message(
                portfolio_payload, kind="pm_verdict_portfolio", symbol=symbol,
            )

        return ok_stock

    async def send_morning_briefing(self, briefing: MorningBriefing) -> bool:
        text = briefing.telegram_message.strip() or briefing.headline
        return await self.send_message(text, kind="morning_briefing")

    async def send_error_notification(
        self, source: str, error: str, symbol: Optional[str] = None,
    ) -> bool:
        prefix = f"⚠ {source}"
        if symbol:
            prefix += f" ({symbol})"
        return await self.send_message(
            f"{prefix}\n\n{error[:1000]}", kind="error", symbol=symbol,
        )

    # ------------------------------------------------------------------ #
    # Persistence
    # ------------------------------------------------------------------ #

    def _log(
        self, kind: str, symbol: Optional[str], text: str,
        success: bool, error: Optional[str],
    ) -> None:
        try:
            conn = get_connection()
            try:
                conn.execute(
                    "INSERT INTO telegram_log "
                    "(sent_at, kind, symbol, text, success, error) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (datetime.utcnow().isoformat(), kind, symbol, text,
                     1 if success else 0, error),
                )
                conn.commit()
            finally:
                conn.close()
        except Exception as e:  # noqa: BLE001
            log.warning("telegram: failed to persist log row: %s", e)


# Module-level convenience singleton — cheap to construct so this is fine.
def telegram() -> TelegramClient:
    return TelegramClient()


def recent_log(limit: int = 50) -> list[dict]:
    """Read the most recent telegram_log entries."""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT id, sent_at, kind, symbol, text, success, error "
            "FROM telegram_log ORDER BY sent_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()
