"""Persistence and passcode state machine for Telegram chat authorization."""
from __future__ import annotations

import hmac
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping

from ..config import AutoTradeConfig, load_auto_trade_config
from ..db.schema import get_connection

def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime | None = None) -> str:
    return (value or _now()).isoformat()


@dataclass(frozen=True)
class AuthorizedChat:
    chat_id: str
    user_id: str
    username: str | None
    first_name: str | None
    authorized_at: str


@dataclass(frozen=True)
class TelegramAuthResponse:
    code: str
    chat_id: str | None = None
    text: str | None = None


def list_authorized_chats() -> list[AuthorizedChat]:
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT chat_id, user_id, username, first_name, authorized_at "
            "FROM telegram_authorized_chats WHERE active = 1 "
            "ORDER BY authorized_at"
        ).fetchall()
        return [AuthorizedChat(**dict(row)) for row in rows]
    finally:
        conn.close()


def authorized_chat_count() -> int:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM telegram_authorized_chats WHERE active = 1"
        ).fetchone()
        return int(row["n"])
    finally:
        conn.close()


def is_authorized(chat_id: str) -> bool:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT 1 FROM telegram_authorized_chats WHERE chat_id = ? AND active = 1",
            (str(chat_id),),
        ).fetchone()
        return row is not None
    finally:
        conn.close()


def begin_authorization(chat_id: str) -> None:
    now = _iso()
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO telegram_auth_sessions "
            "(chat_id, awaiting_passcode, locked_until, updated_at) VALUES (?, 1, NULL, ?) "
            "ON CONFLICT(chat_id) DO UPDATE SET awaiting_passcode=1, updated_at=excluded.updated_at",
            (str(chat_id), now),
        )
        conn.commit()
    finally:
        conn.close()


def revoke_chat(chat_id: str) -> None:
    now = _iso()
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE telegram_authorized_chats SET active=0, revoked_at=? WHERE chat_id=?",
            (now, str(chat_id)),
        )
        conn.execute(
            "INSERT INTO telegram_auth_sessions "
            "(chat_id, awaiting_passcode, locked_until, updated_at) VALUES (?, 0, NULL, ?) "
            "ON CONFLICT(chat_id) DO UPDATE SET awaiting_passcode=0, "
            "locked_until=NULL, updated_at=excluded.updated_at",
            (str(chat_id), now),
        )
        conn.commit()
    finally:
        conn.close()


def get_last_update_id() -> int:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT last_update_id FROM telegram_bot_state WHERE singleton_id=1"
        ).fetchone()
        return int(row["last_update_id"]) if row else 0
    finally:
        conn.close()


def set_last_update_id(update_id: int) -> None:
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO telegram_bot_state (singleton_id, last_update_id, updated_at) "
            "VALUES (1, ?, ?) ON CONFLICT(singleton_id) DO UPDATE SET "
            "last_update_id=MAX(last_update_id, excluded.last_update_id), updated_at=excluded.updated_at",
            (int(update_id), _iso()),
        )
        conn.commit()
    finally:
        conn.close()


class TelegramAuthService:
    MAX_FAILURES = 5
    FAILURE_WINDOW = timedelta(minutes=15)
    LOCK_DURATION = timedelta(minutes=15)

    def __init__(self, config: AutoTradeConfig | None = None) -> None:
        self.config = config or load_auto_trade_config()

    def process_update(self, update: Mapping[str, Any]) -> TelegramAuthResponse:
        update_id = update.get("update_id")
        if not isinstance(update_id, int):
            return TelegramAuthResponse("ignored_invalid_update")
        if update_id <= get_last_update_id():
            return TelegramAuthResponse("ignored_duplicate")

        message = update.get("message")
        if not isinstance(message, Mapping):
            set_last_update_id(update_id)
            return TelegramAuthResponse("ignored_non_message")
        chat = message.get("chat")
        user = message.get("from")
        text = message.get("text")
        if not isinstance(chat, Mapping) or not isinstance(user, Mapping) or not isinstance(text, str):
            set_last_update_id(update_id)
            return TelegramAuthResponse("ignored_invalid_message")

        chat_id = str(chat.get("id", ""))
        user_id = str(user.get("id", ""))
        if not chat_id or not user_id:
            set_last_update_id(update_id)
            return TelegramAuthResponse("ignored_invalid_identity")
        if chat.get("type") != "private":
            set_last_update_id(update_id)
            return TelegramAuthResponse(
                "rejected_non_private", chat_id,
                "Authorization is available only in a private chat with this bot.")

        normalized = text.strip()
        command = normalized.split(maxsplit=1)[0].split("@", 1)[0].lower()
        if command == "/start":
            if is_authorized(chat_id):
                result = "already_authorized"
                reply = "This chat is already authorized. Use /status to check bot health."
            else:
                begin_authorization(chat_id)
                result = "awaiting_passcode"
                reply = "Enter the authorization passcode to enable alerts for this private chat."
        elif command == "/stop":
            revoke_chat(chat_id)
            result = "revoked"
            reply = "Authorization removed. This chat will no longer receive alerts."
        elif command == "/status":
            if not is_authorized(chat_id):
                result = "status_unauthorized"
                reply = "This chat is not authorized. Send /start to begin."
            else:
                snapshot = self.config.public_snapshot()
                alpaca = snapshot["alpaca"]
                reply = (
                    "Authorized. Paper automation is "
                    f"{'armed' if snapshot['enabled'] else 'disarmed'}. "
                    "Alpaca credentials configured: "
                    f"{bool(alpaca['api_key_configured'] and alpaca['secret_key_configured'])}. "
                    "Strategy 4 paper execution controls are available to administrators."
                )
                result = "status_authorized"
        elif self._awaiting(chat_id):
            result, reply = self._check_passcode(
                chat_id, user_id, user, normalized)
        else:
            result = "not_awaiting"
            reply = "Send /start to authorize this private chat."

        set_last_update_id(update_id)
        return TelegramAuthResponse(result, chat_id, reply)

    def _check_passcode(
        self,
        chat_id: str,
        user_id: str,
        user: Mapping[str, Any],
        candidate: str,
    ) -> tuple[str, str]:
        locked_until = self._locked_until(chat_id)
        now = _now()
        if locked_until and locked_until > now:
            return "rate_limited", "Too many failed attempts. Try again later."

        expected = self.config.telegram_auth_passcode
        success = bool(expected) and hmac.compare_digest(
            candidate.encode("utf-8"), expected.encode("utf-8"))
        self._record_attempt(chat_id, user_id, success)
        if success:
            self._authorize(chat_id, user_id, user)
            return "authorized", "Authorization successful. This chat will now receive bot alerts."

        failures = self._recent_failures(chat_id)
        if failures >= self.MAX_FAILURES:
            self._lock(chat_id, now + self.LOCK_DURATION)
            return "rate_limited", "Too many failed attempts. Try again later."
        return "wrong_passcode", "Authorization failed. Check the passcode and try again."

    @staticmethod
    def _awaiting(chat_id: str) -> bool:
        conn = get_connection()
        try:
            row = conn.execute(
                "SELECT awaiting_passcode FROM telegram_auth_sessions WHERE chat_id=?",
                (chat_id,),
            ).fetchone()
            return bool(row and row["awaiting_passcode"])
        finally:
            conn.close()

    @staticmethod
    def _locked_until(chat_id: str) -> datetime | None:
        conn = get_connection()
        try:
            row = conn.execute(
                "SELECT locked_until FROM telegram_auth_sessions WHERE chat_id=?",
                (chat_id,),
            ).fetchone()
            if not row or not row["locked_until"]:
                return None
            return datetime.fromisoformat(row["locked_until"])
        finally:
            conn.close()

    def _recent_failures(self, chat_id: str) -> int:
        cutoff = _iso(_now() - self.FAILURE_WINDOW)
        conn = get_connection()
        try:
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM telegram_auth_attempts "
                "WHERE chat_id=? AND success=0 AND attempted_at>=?",
                (chat_id, cutoff),
            ).fetchone()
            return int(row["n"])
        finally:
            conn.close()

    @staticmethod
    def _record_attempt(chat_id: str, user_id: str, success: bool) -> None:
        conn = get_connection()
        try:
            conn.execute(
                "INSERT INTO telegram_auth_attempts "
                "(chat_id, user_id, attempted_at, success) VALUES (?, ?, ?, ?)",
                (chat_id, user_id, _iso(), 1 if success else 0),
            )
            conn.commit()
        finally:
            conn.close()

    @staticmethod
    def _authorize(chat_id: str, user_id: str, user: Mapping[str, Any]) -> None:
        now = _iso()
        conn = get_connection()
        try:
            conn.execute(
                "INSERT INTO telegram_authorized_chats "
                "(chat_id, user_id, username, first_name, authorized_at, revoked_at, active) "
                "VALUES (?, ?, ?, ?, ?, NULL, 1) "
                "ON CONFLICT(chat_id) DO UPDATE SET user_id=excluded.user_id, "
                "username=excluded.username, first_name=excluded.first_name, "
                "authorized_at=excluded.authorized_at, revoked_at=NULL, active=1",
                (chat_id, user_id, user.get("username"), user.get("first_name"), now),
            )
            conn.execute(
                "UPDATE telegram_auth_sessions SET awaiting_passcode=0, "
                "locked_until=NULL, updated_at=? WHERE chat_id=?",
                (now, chat_id),
            )
            conn.commit()
        finally:
            conn.close()

    @staticmethod
    def _lock(chat_id: str, until: datetime) -> None:
        conn = get_connection()
        try:
            conn.execute(
                "UPDATE telegram_auth_sessions SET locked_until=?, updated_at=? WHERE chat_id=?",
                (_iso(until), _iso(), chat_id),
            )
            conn.commit()
        finally:
            conn.close()
