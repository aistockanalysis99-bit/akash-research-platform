from __future__ import annotations

import json

import httpx
import pytest

from engine.config import load_auto_trade_config
from engine.live.alpaca import (
    AlpacaAuthenticationError,
    AlpacaPaperClient,
    AlpacaRequestError,
    AlpacaResponseError,
)


def _config():
    return load_auto_trade_config({
        "AUTO_TRADE_ENABLED": "False",
        "AUTO_TRADE_PAPER_ONLY": "True",
        "ALPACA_API_KEY": "paper-key",
        "ALPACA_SECRET_KEY": "paper-secret",
        "ALPACA_BASE_URL": "https://paper-api.alpaca.markets",
        "ALPACA_DATA_URL": "https://data.alpaca.markets",
        "TELEGRAM_ENABLED": "False",
    })


def _json(status: int, payload) -> httpx.Response:
    return httpx.Response(
        status,
        content=json.dumps(payload).encode(),
        headers={"content-type": "application/json"},
    )


def test_read_only_account_clock_asset_and_collections() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["APCA-API-KEY-ID"] == "paper-key"
        if request.url.path == "/v2/account":
            return _json(200, {
                "id": "acct", "status": "ACTIVE", "cash": "90000",
                "portfolio_value": "100000", "equity": "100000",
                "buying_power": "200000", "currency": "USD",
            })
        if request.url.path == "/v2/clock":
            return _json(200, {
                "timestamp": "2026-11-05T09:00:00-05:00", "is_open": False,
                "next_open": "2026-11-05T09:30:00-05:00",
                "next_close": "2026-11-05T16:00:00-05:00",
            })
        if request.url.path == "/v2/assets/AAPL":
            return _json(200, {
                "id": "asset", "symbol": "AAPL", "name": "Apple",
                "exchange": "NASDAQ", "status": "active", "tradable": True,
                "marginable": True, "shortable": True,
                "borrow_status": "easy_to_borrow",
            })
        if request.url.path == "/v2/orders":
            return _json(200, [{"id": "o1"}])
        if request.url.path == "/v2/positions":
            return _json(200, [{"symbol": "AAPL"}])
        if request.url.path == "/v2/calendar":
            return _json(200, [{"date": "2026-11-05", "open": "09:30", "close": "16:00"}])
        if request.url.path == "/v2/stocks/AAPL/bars":
            return _json(200, {"bars": [{"t": "2026-11-04T21:00:00Z", "c": 100.0}]})
        if request.url.path == "/v2/stocks/AAPL/quotes/latest":
            return _json(200, {"quote": {"bp": 99.9, "ap": 100.1}})
        if request.url.path == "/v2/account/activities":
            return _json(200, [{"id": "activity-1"}])
        if request.url.path == "/v2/account/portfolio/history":
            return _json(200, {"equity": [100000.0], "timestamp": [1]})
        raise AssertionError(request.url)

    client = AlpacaPaperClient(_config(), transport=httpx.MockTransport(handler))
    account = client.get_account()
    clock = client.get_clock()
    asset = client.get_asset("aapl")
    orders = client.list_orders()
    positions = client.list_positions()
    calendar = client.get_calendar("2026-11-05", "2026-11-05")
    bars = client.get_bars("AAPL")
    quote = client.get_latest_quote("AAPL")
    activities = client.list_activities()
    history = client.get_portfolio_history()
    assert account.equity == 100000
    assert not clock.is_open
    assert asset.shortable and asset.easy_to_borrow
    assert orders.items[0]["id"] == "o1"
    assert positions.items[0]["symbol"] == "AAPL"
    assert calendar.items[0]["date"] == "2026-11-05"
    assert bars.items[0]["c"] == 100.0
    assert quote["ap"] == 100.1
    assert activities.items[0]["id"] == "activity-1"
    assert history["equity"] == [100000.0]
    assert callable(client.submit_order)
    assert callable(client.cancel_order)


def test_authentication_failure_is_sanitized() -> None:
    client = AlpacaPaperClient(
        _config(), transport=httpx.MockTransport(lambda _: _json(401, {"message": "bad secret"})))
    with pytest.raises(AlpacaAuthenticationError) as exc:
        client.get_account()
    assert "paper-secret" not in str(exc.value)


def test_429_and_5xx_retry_then_succeed() -> None:
    calls = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return _json(429, {"message": "slow"})
        if calls == 2:
            return _json(503, {"message": "busy"})
        return _json(200, {
            "id": "acct", "status": "ACTIVE", "cash": "1",
            "portfolio_value": "1", "equity": "1", "buying_power": "1",
        })

    client = AlpacaPaperClient(
        _config(), transport=httpx.MockTransport(handler), max_attempts=3)
    assert client.get_account().account_id == "acct"
    assert calls == 3


def test_timeout_retries_are_bounded() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise httpx.ReadTimeout("timeout", request=request)

    client = AlpacaPaperClient(
        _config(), transport=httpx.MockTransport(handler), max_attempts=2)
    with pytest.raises(AlpacaRequestError):
        client.get_clock()
    assert calls == 2


def test_malformed_response_is_rejected() -> None:
    client = AlpacaPaperClient(
        _config(), transport=httpx.MockTransport(lambda _: httpx.Response(200, content=b"not-json")))
    with pytest.raises(AlpacaResponseError):
        client.get_account()


def test_invalid_symbols_are_rejected_before_http() -> None:
    client = AlpacaPaperClient(
        _config(),
        transport=httpx.MockTransport(
            lambda _: (_ for _ in ()).throw(AssertionError("HTTP must not run"))),
    )
    with pytest.raises(ValueError):
        client.get_asset("../orders")
    with pytest.raises(ValueError):
        client.get_bars("AAPL?feed=sip")

