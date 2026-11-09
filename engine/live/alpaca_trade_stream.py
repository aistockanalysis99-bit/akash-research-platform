"""Alpaca paper trade-update stream with REST reconciliation as fallback."""
from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from typing import Any, Mapping

from ..config import AutoTradeConfig, load_auto_trade_config
from .auto_trade_outbox import enqueue_system_alert
from .pair_execution import ingest_trade_update

log = logging.getLogger(__name__)
PAPER_STREAM_URL = "wss://paper-api.alpaca.markets/stream"


def decode_stream_messages(raw: str | bytes) -> list[Mapping[str, Any]]:
    try:
        text = raw.decode("utf-8") if isinstance(raw, bytes) else raw
        payload = json.loads(text)
    except (UnicodeDecodeError, ValueError, TypeError):
        return []
    if isinstance(payload, Mapping):
        return [payload]
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, Mapping)]
    return []


async def consume_trade_updates(
    *,
    config: AutoTradeConfig | None = None,
    stop_requested: Callable[[], bool] | None = None,
    on_disconnect: Callable[[], Awaitable[None]] | None = None,
) -> None:
    """Consume paper trade updates and reconnect with bounded backoff."""
    cfg = config or load_auto_trade_config()
    cfg.require_ready()
    if cfg.alpaca_base_url.rstrip("/") != "https://paper-api.alpaca.markets":
        raise RuntimeError("trade stream requires the Alpaca paper endpoint")
    from websockets.asyncio.client import connect

    should_stop = stop_requested or (lambda: False)
    delay = 1.0
    while not should_stop():
        try:
            async with connect(PAPER_STREAM_URL, open_timeout=15, ping_interval=20) as socket:
                await socket.send(json.dumps({
                    "action": "auth",
                    "key": cfg.alpaca_api_key,
                    "secret": cfg.alpaca_secret_key,
                }))
                await socket.send(json.dumps({
                    "action": "listen",
                    "data": {"streams": ["trade_updates"]},
                }))
                delay = 1.0
                async for raw in socket:
                    if should_stop():
                        return
                    for message in decode_stream_messages(raw):
                        if message.get("stream") == "trade_updates":
                            data = message.get("data")
                            if isinstance(data, Mapping):
                                ingest_trade_update(data)
                                event = str(data.get("event", "")).lower()
                                if event in ("fill", "partial_fill", "canceled", "rejected"):
                                    order_obj = data.get("order")
                                    if isinstance(order_obj, Mapping):
                                        cid = str(order_obj.get("client_order_id", ""))
                                        if cid:
                                            try:
                                                from ..db.schema import get_connection
                                                from .alpaca import AlpacaPaperClient
                                                from .auto_trade_outbox import deliver_pending
                                                from .pair_execution import reconcile_pair
                                                conn = get_connection()
                                                row = conn.execute(
                                                    "SELECT pair_trade_id FROM broker_orders WHERE client_order_id=?",
                                                    (cid,),
                                                ).fetchone()
                                                conn.close()
                                                if row:
                                                    pair_id = str(row["pair_trade_id"])
                                                    broker_client = AlpacaPaperClient(cfg)
                                                    await asyncio.to_thread(reconcile_pair, pair_id, broker_client)
                                                    await deliver_pending()
                                            except Exception as exc:
                                                log.warning("Stream post-event reconciliation error: %s", exc)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # credentials and payloads are never logged
            log.warning("Alpaca trade-update stream disconnected: %s", type(exc).__name__)
            if on_disconnect:
                await on_disconnect()
            else:
                enqueue_system_alert(
                    "risk_error",
                    "Alpaca trade-update stream disconnected; REST reconciliation remains active",
                    datetime.now(timezone.utc).strftime("%Y-%m-%dT%H"),
                )
            if should_stop():
                return
            await asyncio.sleep(delay)
            delay = min(delay * 2, 30.0)
