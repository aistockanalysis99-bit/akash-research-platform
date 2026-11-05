"""Alpaca paper-trading adapter with bounded, explicit order operations."""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import date
from typing import Any, Mapping, Optional

import httpx

from ..config import AutoTradeConfig, load_auto_trade_config

log = logging.getLogger(__name__)


class AlpacaError(RuntimeError):
    """Base class for safe, non-secret Alpaca failures."""


class AlpacaConfigurationError(AlpacaError):
    pass


class AlpacaAuthenticationError(AlpacaError):
    pass


class AlpacaRequestError(AlpacaError):
    def __init__(self, status_code: int | None, message: str) -> None:
        self.status_code = status_code
        super().__init__(message)


class AlpacaResponseError(AlpacaError):
    pass


@dataclass(frozen=True)
class AccountSnapshot:
    account_id: str
    status: str
    currency: str
    cash: float
    portfolio_value: float
    equity: float
    buying_power: float
    pattern_day_trader: bool
    trading_blocked: bool
    account_blocked: bool
    raw: Mapping[str, Any]


@dataclass(frozen=True)
class MarketClock:
    timestamp: str
    is_open: bool
    next_open: str
    next_close: str


@dataclass(frozen=True)
class AssetSnapshot:
    asset_id: str
    symbol: str
    name: str
    exchange: str
    status: str
    tradable: bool
    marginable: bool
    shortable: bool
    easy_to_borrow: bool
    borrow_status: str
    raw: Mapping[str, Any]


@dataclass(frozen=True)
class BrokerCollection:
    items: tuple[Mapping[str, Any], ...]


def _float(payload: Mapping[str, Any], key: str) -> float:
    try:
        return float(payload.get(key, 0) or 0)
    except (TypeError, ValueError) as exc:
        raise AlpacaResponseError(f"Alpaca returned invalid {key}") from exc


class AlpacaPaperClient:
    """Small async client restricted to GET endpoints."""

    def __init__(
        self,
        config: AutoTradeConfig | None = None,
        *,
        transport: httpx.BaseTransport | None = None,
        timeout: float = 15.0,
        max_attempts: int = 3,
    ) -> None:
        self.config = config or load_auto_trade_config()
        errors = self.config.validation_errors()
        broker_errors = [e for e in errors if "ALPACA" in e or "Alpaca" in e or "paper" in e]
        if not self.config.alpaca_api_key or not self.config.alpaca_secret_key:
            broker_errors.append("Alpaca paper credentials are not configured")
        if broker_errors:
            raise AlpacaConfigurationError("; ".join(dict.fromkeys(broker_errors)))
        self._transport = transport
        self._timeout = timeout
        self._max_attempts = max(1, max_attempts)

    @property
    def _headers(self) -> dict[str, str]:
        return {
            "APCA-API-KEY-ID": self.config.alpaca_api_key,
            "APCA-API-SECRET-KEY": self.config.alpaca_secret_key,
            "Accept": "application/json",
            "User-Agent": "akash-research-platform/auto-trade-phase1",
        }

    @staticmethod
    def _symbol(value: str) -> str:
        clean = value.strip().upper()
        if not clean or not clean.replace(".", "").replace("-", "").isalnum():
            raise ValueError("invalid asset symbol")
        return clean

    def _get(
        self,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
        data_api: bool = False,
    ) -> Any:
        base = self.config.alpaca_data_url if data_api else self.config.alpaca_base_url
        url = f"{base}{path}"
        last_error: Exception | None = None
        for attempt in range(self._max_attempts):
            try:
                response = self._get_once(url, params)
                if response.status_code in (401, 403):
                    raise AlpacaAuthenticationError("Alpaca authentication failed")
                if response.status_code == 429 or response.status_code >= 500:
                    if attempt + 1 < self._max_attempts:
                        retry_after = response.headers.get("Retry-After", "")
                        try:
                            delay = min(float(retry_after), 5.0) if retry_after else 0.25 * (2 ** attempt)
                        except ValueError:
                            delay = 0.25 * (2 ** attempt)
                        time.sleep(delay)
                        continue
                if response.status_code >= 400:
                    raise AlpacaRequestError(
                        response.status_code,
                        f"Alpaca request failed with HTTP {response.status_code}",
                    )
                try:
                    return response.json()
                except ValueError as exc:
                    raise AlpacaResponseError("Alpaca returned malformed JSON") from exc
            except AlpacaAuthenticationError:
                raise
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last_error = exc
                if attempt + 1 < self._max_attempts:
                    time.sleep(0.25 * (2 ** attempt))
                    continue
            except AlpacaError:
                raise
        log.warning("alpaca read request failed after %d attempts", self._max_attempts)
        raise AlpacaRequestError(None, "Alpaca request failed after retries") from last_error

    def _get_once(
        self, url: str, params: Mapping[str, Any] | None,
    ) -> httpx.Response:
        with httpx.Client(
            headers=self._headers,
            timeout=self._timeout,
            transport=self._transport,
        ) as client:
            return client.get(url, params=params)

    def get_account(self) -> AccountSnapshot:
        payload = self._get("/v2/account")
        if not isinstance(payload, dict) or not payload.get("id"):
            raise AlpacaResponseError("Alpaca returned an invalid account response")
        return AccountSnapshot(
            account_id=str(payload["id"]),
            status=str(payload.get("status", "")),
            currency=str(payload.get("currency", "USD")),
            cash=_float(payload, "cash"),
            portfolio_value=_float(payload, "portfolio_value"),
            equity=_float(payload, "equity"),
            buying_power=_float(payload, "buying_power"),
            pattern_day_trader=bool(payload.get("pattern_day_trader", False)),
            trading_blocked=bool(payload.get("trading_blocked", False)),
            account_blocked=bool(payload.get("account_blocked", False)),
            raw=payload,
        )

    def get_clock(self) -> MarketClock:
        payload = self._get("/v2/clock")
        required = ("timestamp", "is_open", "next_open", "next_close")
        if not isinstance(payload, dict) or any(k not in payload for k in required):
            raise AlpacaResponseError("Alpaca returned an invalid market clock")
        return MarketClock(
            timestamp=str(payload["timestamp"]),
            is_open=bool(payload["is_open"]),
            next_open=str(payload["next_open"]),
            next_close=str(payload["next_close"]),
        )

    def get_calendar(
        self, start: date | str | None = None, end: date | str | None = None,
    ) -> BrokerCollection:
        params: dict[str, str] = {}
        if start is not None:
            params["start"] = start.isoformat() if isinstance(start, date) else str(start)
        if end is not None:
            params["end"] = end.isoformat() if isinstance(end, date) else str(end)
        payload = self._get("/v2/calendar", params=params)
        return self._collection(payload, "calendar")

    def get_asset(self, symbol: str) -> AssetSnapshot:
        clean_symbol = self._symbol(symbol)
        payload = self._get(f"/v2/assets/{clean_symbol}")
        if not isinstance(payload, dict) or not payload.get("symbol"):
            raise AlpacaResponseError("Alpaca returned an invalid asset response")
        borrow_status = str(payload.get("borrow_status") or "")
        easy = bool(payload.get("easy_to_borrow", False)) or borrow_status == "easy_to_borrow"
        return AssetSnapshot(
            asset_id=str(payload.get("id", "")),
            symbol=str(payload["symbol"]),
            name=str(payload.get("name", "")),
            exchange=str(payload.get("exchange", "")),
            status=str(payload.get("status", "")),
            tradable=bool(payload.get("tradable", False)),
            marginable=bool(payload.get("marginable", False)),
            shortable=bool(payload.get("shortable", False)),
            easy_to_borrow=easy,
            borrow_status=borrow_status or ("easy_to_borrow" if easy else "unknown"),
            raw=payload,
        )

    def get_bars(
        self,
        symbol: str,
        *,
        timeframe: str = "1Day",
        start: str | None = None,
        end: str | None = None,
        limit: int = 1000,
        feed: str = "iex",
    ) -> BrokerCollection:
        params: dict[str, Any] = {
            "timeframe": timeframe,
            "limit": max(1, min(limit, 10_000)),
            "feed": feed,
            "adjustment": "all",
        }
        if start:
            params["start"] = start
        if end:
            params["end"] = end
        payload = self._get(
            f"/v2/stocks/{self._symbol(symbol)}/bars", params=params, data_api=True)
        if not isinstance(payload, dict):
            raise AlpacaResponseError("Alpaca returned an invalid bars response")
        return self._collection(payload.get("bars"), "bars")

    def get_latest_quote(self, symbol: str, *, feed: str = "iex") -> Mapping[str, Any]:
        payload = self._get(
            f"/v2/stocks/{self._symbol(symbol)}/quotes/latest",
            params={"feed": feed},
            data_api=True,
        )
        if not isinstance(payload, dict) or not isinstance(payload.get("quote"), dict):
            raise AlpacaResponseError("Alpaca returned an invalid quote response")
        return payload["quote"]

    def list_orders(self, status: str = "all", limit: int = 500) -> BrokerCollection:
        payload = self._get(
            "/v2/orders", params={"status": status, "limit": max(1, min(limit, 500)), "nested": "true"})
        return self._collection(payload, "orders")

    def get_order_by_client_id(self, client_order_id: str) -> Mapping[str, Any] | None:
        """Resolve an ambiguous submission before any retry."""
        if not client_order_id or len(client_order_id) > 48:
            raise ValueError("invalid client order ID")
        try:
            order = self._get(
                "/v2/orders:by_client_order_id",
                params={"client_order_id": client_order_id},
            )
        except AlpacaRequestError as exc:
            if exc.status_code == 404:
                return None
            raise
        if not isinstance(order, dict) or not order.get("id"):
            raise AlpacaResponseError("Alpaca returned an invalid order")
        return order

    def _order_write(self, method: str, path: str, payload: Mapping[str, Any] | None = None) -> Any:
        if self.config.alpaca_base_url.rstrip("/") != "https://paper-api.alpaca.markets":
            raise AlpacaConfigurationError("orders require the Alpaca paper endpoint")
        try:
            with httpx.Client(headers=self._headers, timeout=self._timeout, transport=self._transport) as client:
                response = client.request(method, f"{self.config.alpaca_base_url}{path}", json=payload)
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            raise AlpacaRequestError(None, "Alpaca order outcome is uncertain; reconcile by client ID") from exc
        if response.status_code in (401, 403):
            raise AlpacaAuthenticationError("Alpaca authentication failed")
        if response.status_code >= 400:
            raise AlpacaRequestError(response.status_code, f"Alpaca order request failed with HTTP {response.status_code}")
        if response.status_code == 204:
            return None
        try:
            result = response.json()
        except ValueError as exc:
            raise AlpacaResponseError("Alpaca returned malformed order JSON") from exc
        if not isinstance(result, dict) or not result.get("id"):
            raise AlpacaResponseError("Alpaca returned an invalid order")
        return result

    def submit_order(self, *, symbol: str, side: str, qty: int, client_order_id: str) -> Mapping[str, Any]:
        if side not in ("buy", "sell") or not isinstance(qty, int) or qty < 1:
            raise ValueError("invalid order side or whole-share quantity")
        if not client_order_id or len(client_order_id) > 48:
            raise ValueError("invalid client order ID")
        return self._order_write("POST", "/v2/orders", {
            "symbol": self._symbol(symbol), "side": side, "qty": str(qty),
            "type": "market", "time_in_force": "day", "client_order_id": client_order_id,
        })

    def cancel_order(self, order_id: str) -> None:
        if not order_id or not all(ch.isalnum() or ch == "-" for ch in order_id):
            raise ValueError("invalid broker order ID")
        self._order_write("DELETE", f"/v2/orders/{order_id}")

    def list_positions(self) -> BrokerCollection:
        return self._collection(self._get("/v2/positions"), "positions")

    def list_activities(
        self, activity_type: str | None = None, *, after: str | None = None,
    ) -> BrokerCollection:
        suffix = f"/{activity_type.strip().upper()}" if activity_type else ""
        params = {"after": after} if after else None
        return self._collection(
            self._get(f"/v2/account/activities{suffix}", params=params), "activities")

    def get_portfolio_history(
        self, *, period: str = "1M", timeframe: str = "1D",
    ) -> Mapping[str, Any]:
        payload = self._get(
            "/v2/account/portfolio/history",
            params={"period": period, "timeframe": timeframe, "intraday_reporting": "market_hours"},
        )
        if not isinstance(payload, dict):
            raise AlpacaResponseError("Alpaca returned an invalid portfolio history")
        return payload

    @staticmethod
    def _collection(payload: Any, label: str) -> BrokerCollection:
        if not isinstance(payload, list) or any(not isinstance(item, dict) for item in payload):
            raise AlpacaResponseError(f"Alpaca returned an invalid {label} response")
        return BrokerCollection(tuple(payload))


def alpaca_readiness(config: Optional[AutoTradeConfig] = None) -> dict[str, Any]:
    """Connectivity check with no account balances or identifiers in output."""
    cfg = config or load_auto_trade_config()
    try:
        client = AlpacaPaperClient(cfg)
        account = client.get_account()
        clock = client.get_clock()
        return {
            "configured": True,
            "connected": True,
            "paper_endpoint": cfg.alpaca_base_url == "https://paper-api.alpaca.markets",
            "account_status": account.status,
            "trading_blocked": account.trading_blocked or account.account_blocked,
            "market_clock_available": bool(clock.timestamp),
        }
    except AlpacaConfigurationError as exc:
        return {"configured": False, "connected": False, "error": str(exc)}
    except AlpacaAuthenticationError:
        return {"configured": True, "connected": False, "error": "Alpaca authentication failed"}
    except AlpacaError:
        return {"configured": True, "connected": False, "error": "Alpaca connectivity check failed"}
