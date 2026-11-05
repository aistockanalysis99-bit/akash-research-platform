from __future__ import annotations

import pytest

from engine.config import load_auto_trade_config
from engine.db import schema
from engine.live.telegram_auth import (
    TelegramAuthService,
    authorized_chat_count,
    get_last_update_id,
    is_authorized,
    list_authorized_chats,
)
from engine.live.telegram import TelegramClient


@pytest.fixture
def auth_service(tmp_path, monkeypatch):
    db = tmp_path / "telegram.sqlite"
    monkeypatch.setattr(schema, "DB_PATH", db)
    schema.init_db()
    config = load_auto_trade_config({
        "AUTO_TRADE_ENABLED": "False",
        "AUTO_TRADE_PAPER_ONLY": "True",
        "ALPACA_BASE_URL": "https://paper-api.alpaca.markets",
        "TELEGRAM_ENABLED": "True",
        "TELEGRAM_BOT_TOKEN": "bot-token-secret",
        "TELEGRAM_AUTH_PASSCODE": "1234",
    })
    return TelegramAuthService(config)


def update(update_id: int, text: str, chat_id: int = 10, user_id: int = 20, chat_type: str = "private"):
    return {
        "update_id": update_id,
        "message": {
            "text": text,
            "chat": {"id": chat_id, "type": chat_type},
            "from": {"id": user_id, "username": "user", "first_name": "Test"},
        },
    }


def test_start_correct_passcode_status_and_stop(auth_service) -> None:
    responses = [
        auth_service.process_update(update(1, "/start")),
        auth_service.process_update(update(2, "1234")),
    ]
    assert [r.code for r in responses] == ["awaiting_passcode", "authorized"]
    assert is_authorized("10")
    assert authorized_chat_count() == 1
    status = auth_service.process_update(update(3, "/status"))
    assert status.code == "status_authorized"
    assert "Strategy 4 paper execution controls" in status.text
    stopped = auth_service.process_update(update(4, "/stop"))
    assert stopped.code == "revoked"
    assert not is_authorized("10")
    assert get_last_update_id() == 4
    assert all("1234" not in (r.text or "") for r in responses + [status, stopped])


def test_wrong_passcodes_rate_limit_without_storage(auth_service) -> None:
    auth_service.process_update(update(1, "/start"))
    for i in range(2, 6):
        assert auth_service.process_update(update(i, f"wrong-{i}")).code == "wrong_passcode"
    assert auth_service.process_update(update(6, "wrong-final")).code == "rate_limited"
    assert auth_service.process_update(update(7, "1234")).code == "rate_limited"
    assert not is_authorized("10")
    conn = schema.get_connection()
    try:
        rows = conn.execute("SELECT * FROM telegram_auth_attempts").fetchall()
        assert len(rows) == 5
        serialized = " ".join(str(dict(row)) for row in rows)
        assert "wrong" not in serialized
        assert "1234" not in serialized
    finally:
        conn.close()


def test_duplicate_update_is_not_reprocessed_and_multiple_chats_work(auth_service) -> None:
    sent = [auth_service.process_update(update(1, "/start", 10, 20))]
    assert auth_service.process_update(update(1, "/start", 10, 20)).code == "ignored_duplicate"
    sent.append(auth_service.process_update(update(2, "1234", 10, 20)))
    sent.append(auth_service.process_update(update(3, "/start", 11, 21)))
    sent.append(auth_service.process_update(update(4, "1234", 11, 21)))
    assert {row.chat_id for row in list_authorized_chats()} == {"10", "11"}
    assert len([item for item in sent if "Enter the authorization" in (item.text or "")]) == 2
    restarted = TelegramAuthService(auth_service.config)
    assert restarted.process_update(update(4, "1234", 11, 21)).code == "ignored_duplicate"
    assert is_authorized("10") and is_authorized("11")


def test_status_before_authorization_is_redacted(auth_service) -> None:
    response = auth_service.process_update(update(1, "/status"))
    assert response.code == "status_unauthorized"
    assert response.text == "This chat is not authorized. Send /start to begin."
    assert "1234" not in response.text


def test_group_chat_cannot_authorize(auth_service) -> None:
    result = auth_service.process_update(update(1, "/start", chat_type="group"))
    assert result.code == "rejected_non_private"
    assert not is_authorized("10")
    assert "private chat" in result.text


def test_broadcast_targets_are_only_authorized_chats(auth_service) -> None:
    auth_service.process_update(update(1, "/start", 10, 20))
    auth_service.process_update(update(2, "1234", 10, 20))
    auth_service.process_update(update(3, "/start", 11, 21))
    auth_service.process_update(update(4, "1234", 11, 21))
    # Even an explicitly supplied legacy chat cannot bypass passcode mode.
    targets = TelegramClient(token="token", chat_id="legacy-chat").resolve_targets(
        "options_alert")
    assert set(targets) == {"10", "11"}

