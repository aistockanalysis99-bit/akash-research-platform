from __future__ import annotations

import json

import pytest

from engine.config import AutoTradeConfigurationError, load_auto_trade_config


def _env(**overrides: str) -> dict[str, str]:
    env = {
        "AUTO_TRADE_ENABLED": "False",
        "AUTO_TRADE_PAPER_ONLY": "True",
        "ALPACA_API_KEY": "",
        "ALPACA_SECRET_KEY": "",
        "ALPACA_BASE_URL": "https://paper-api.alpaca.markets",
        "TELEGRAM_ENABLED": "False",
        "TELEGRAM_BOT_TOKEN": "",
        "TELEGRAM_AUTH_PASSCODE": "",
    }
    env.update(overrides)
    return env


def test_blank_credentials_are_safe_while_disarmed() -> None:
    cfg = load_auto_trade_config(_env())
    assert cfg.ready
    assert cfg.public_snapshot()["enabled"] is False


def test_armed_automation_fails_closed_without_credentials() -> None:
    cfg = load_auto_trade_config(_env(AUTO_TRADE_ENABLED="True"))
    assert not cfg.ready
    with pytest.raises(AutoTradeConfigurationError) as exc:
        cfg.require_ready()
    assert "ALPACA_API_KEY" in str(exc.value)
    assert "ALPACA_SECRET_KEY" in str(exc.value)


@pytest.mark.parametrize(
    "url",
    ["https://api.alpaca.markets", "http://paper-api.alpaca.markets", "not-a-url"],
)
def test_paper_only_rejects_non_paper_or_insecure_urls(url: str) -> None:
    cfg = load_auto_trade_config(_env(ALPACA_BASE_URL=url))
    assert not cfg.ready


def test_public_snapshot_and_repr_never_contain_secrets() -> None:
    api_key = "PK-VERY-SECRET"
    secret = "alpaca-secret-value"
    token = "123:telegram-secret"
    passcode = "987654"
    cfg = load_auto_trade_config(_env(
        ALPACA_API_KEY=api_key,
        ALPACA_SECRET_KEY=secret,
        TELEGRAM_ENABLED="True",
        TELEGRAM_BOT_TOKEN=token,
        TELEGRAM_AUTH_PASSCODE=passcode,
    ))
    rendered = repr(cfg) + json.dumps(cfg.public_snapshot())
    for value in (api_key, secret, token, passcode):
        assert value not in rendered


def test_invalid_numbers_fail_closed_without_import_crash() -> None:
    cfg = load_auto_trade_config(_env(AUTO_TRADE_MONITOR_MINUTES="abc"))
    assert not cfg.ready
    assert "AUTO_TRADE_MONITOR_MINUTES must be an integer" in cfg.validation_errors()

