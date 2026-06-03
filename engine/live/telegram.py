"""Outbound Telegram client.

We don't run an interactive bot — just POST to sendMessage when the system
has something to tell the client. Token + chat_id come from .env. If either
is missing, sending becomes a no-op (returns False, logs an info line).

Every attempt is logged to the telegram_log SQLite table so the UI can show
a delivery history.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

import httpx

from ..config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
from ..db.schema import get_connection
from .schemas import MorningBriefing, PMDecision

log = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"
MAX_MESSAGE_LEN = 4000  # Telegram limit is 4096, leave headroom


class TelegramClient:
    """Async outbound-only Telegram client."""

    def __init__(
        self,
        token: Optional[str] = None,
        chat_id: Optional[str] = None,
    ) -> None:
        self.token = token if token is not None else TELEGRAM_BOT_TOKEN
        self.chat_id = chat_id if chat_id is not None else TELEGRAM_CHAT_ID

    @property
    def enabled(self) -> bool:
        return bool(self.token and self.chat_id)

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
        if not self.enabled:
            self._log(kind, symbol, truncated, success=False,
                       error="not_configured")
            log.info("telegram: skipping — token/chat_id not set")
            return False

        url = TELEGRAM_API.format(token=self.token)
        payload: dict = {"chat_id": self.chat_id, "text": truncated}
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
                    self._log(kind, symbol, truncated, success=True, error=None)
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

        self._log(kind, symbol, truncated, success=False,
                   error=last_err or "send failed after retries")
        log.warning("telegram send failed after retries: %s", last_err)
        return False

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
