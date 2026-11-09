from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timezone

import pytest
import httpx
from fastapi import BackgroundTasks, HTTPException

from engine.config import load_auto_trade_config
from engine.db import schema
from engine.live.alpaca import (
    AccountSnapshot, AlpacaPaperClient, AlpacaRequestError, AssetSnapshot,
    BrokerCollection, MarketClock,
)
from engine.live.alpaca_trade_stream import decode_stream_messages
from engine.live.auto_trade_outbox import deliver_pending
from engine.live.pair_execution import (
    PairExecutionError,
    activate_kill_switch,
    client_order_id,
    get_pair,
    ingest_trade_update,
    monitor_pair,
    reconcile_pair,
    request_pair_exit,
    submit_pair_entry,
    transition_pair,
    update_control,
)


def config():
    return load_auto_trade_config({
        "AUTO_TRADE_ENABLED": "True", "AUTO_TRADE_PAPER_ONLY": "True",
        "ALPACA_API_KEY": "paper", "ALPACA_SECRET_KEY": "secret",
        "ALPACA_BASE_URL": "https://paper-api.alpaca.markets",
        "TELEGRAM_ENABLED": "False", "AUTO_TRADE_MAX_QUOTE_AGE_SECONDS": "300",
    })


class Broker:
    def __init__(self):
        self.config = config()
        self.account = AccountSnapshot("paper", "ACTIVE", "USD", 100000, 100000, 100000, 200000, False, False, False, {})
        self.assets = {symbol: AssetSnapshot(symbol, symbol, symbol, "NYSE", "active", True, True, True, True, "easy_to_borrow", {}) for symbol in ("AAA", "BBB")}
        self.quotes = {"AAA": {"bp": 99.9, "ap": 100.1, "t": "2026-11-05T10:00:00-05:00"}, "BBB": {"bp": 49.9, "ap": 50.1, "t": "2026-11-05T10:00:00-05:00"}}
        self.orders = {}
        self.submit_calls = []
        self.cancel_calls = []
        self.fail_submit_symbol = None

    def get_clock(self): return MarketClock("2026-11-05T10:00:00-05:00", True, "2026-11-06T09:30:00-05:00", "2026-11-05T16:00:00-05:00")
    def get_account(self): return self.account
    def get_asset(self, symbol): return self.assets[symbol]
    def get_latest_quote(self, symbol, **kwargs): return self.quotes[symbol]
    def list_orders(self, status="all", limit=500): return BrokerCollection(tuple())
    def list_positions(self):
        positions = []
        for symbol, side in (("AAA", 1), ("BBB", -1)):
            entry = self.orders.get(client_order_id("pair", symbol, "entry"))
            if not entry or entry["status"] != "filled":
                continue
            closed = any(
                self.orders.get(client_order_id("pair", symbol, action), {}).get("status") == "filled"
                for action in ("exit", "compensate")
            )
            if not closed:
                positions.append({
                    "symbol": symbol,
                    "qty": str(side * int(entry["filled_qty"])),
                    "market_value": str(side * int(entry["filled_qty"]) * 50),
                })
        return BrokerCollection(tuple(positions))
    def get_order_by_client_id(self, cid): return self.orders.get(cid)

    def submit_order(self, *, symbol, side, qty, client_order_id):
        order = {
            "id": f"ord-{len(self.orders)+1}", "client_order_id": client_order_id,
            "symbol": symbol, "side": side, "qty": str(qty), "filled_qty": "0",
            "filled_avg_price": None, "type": "market", "time_in_force": "day",
            "status": "new", "submitted_at": "2026-11-05T10:00:00-05:00",
            "updated_at": "2026-11-05T10:00:00-05:00",
        }
        self.orders[client_order_id] = order
        self.submit_calls.append(client_order_id)
        if symbol == self.fail_submit_symbol:
            raise TimeoutError("accepted but response lost")
        return order

    def cancel_order(self, order_id): self.cancel_calls.append(order_id)

    def fill(self, pair_id, symbol, action, price):
        cid = client_order_id(pair_id, symbol, action)
        order = self.orders[cid]
        order.update(status="filled", filled_qty=order["qty"], filled_avg_price=str(price), updated_at="2026-11-05T10:01:00-05:00")


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setattr(schema, "DB_PATH", tmp_path / "phase3.sqlite")
    schema.init_db()


def seed_pair(state="DRAFT"):
    conn = schema.get_connection()
    try:
        conn.execute("INSERT INTO auto_trade_runs (run_id, run_type, status, started_at) VALUES ('run','dry','complete','now')")
        payload = (
            '{"hedge_ratio":1.0,"spread_mean":50.0,"spread_std":1.0,'
            '"z_score":-2.2,"proposed_legs":['
            '{"symbol":"AAA","reference_price":100.0},'
            '{"symbol":"BBB","reference_price":50.0}]}'
        )
        conn.execute("INSERT INTO strategy_v4_signal_snapshots (signal_id, run_id, session_date, ticker_a, ticker_b, decision, data_cutoff_at, config_version, config_hash, payload_json, created_at) VALUES ('sig','run','2026-11-05','AAA','BBB','QUALIFIED','2026-11-04','4','hash',?,'now')", (payload,))
        conn.execute("INSERT INTO pair_trade_intents (pair_trade_id, signal_id, session_date, ticker_a, ticker_b, state, target_z, stop_z, max_holding_date, idempotency_key, created_at, updated_at) VALUES ('pair','sig','2026-11-05','AAA','BBB',?,0.4,2.85,'2026-11-20','key','now','now')", (state,))
        conn.executemany("INSERT INTO pair_trade_legs (leg_id, pair_trade_id, symbol, side, target_qty, state, created_at, updated_at) VALUES (?, 'pair', ?, ?, ?, 'PLANNED','now','now')", [("leg-a", "AAA", "BUY", 10), ("leg-b", "BBB", "SHORT", 20)])
        conn.commit()
    finally:
        conn.close()


def arm(): update_control(armed=True, kill_switch=False, actor="test")


def open_pair(broker):
    arm(); submit_pair_entry("pair", broker)
    broker.fill("pair", "AAA", "entry", 100); broker.fill("pair", "BBB", "entry", 50)
    reconcile_pair("pair", broker)
    assert get_pair("pair")["state"] == "OPEN"


def test_state_machine_rejects_invalid_transition(db):
    seed_pair()
    with pytest.raises(PairExecutionError, match="invalid pair transition"):
        transition_pair("pair", "OPEN")


def test_entry_is_exactly_once_and_both_fills_open_pair(db):
    seed_pair(); arm(); broker = Broker()
    submit_pair_entry("pair", broker); submit_pair_entry("pair", broker)
    assert len(broker.submit_calls) == 2
    broker.fill("pair", "AAA", "entry", 100); broker.fill("pair", "BBB", "entry", 50)
    reconcile_pair("pair", broker); reconcile_pair("pair", broker)
    assert get_pair("pair")["state"] == "OPEN"
    conn = schema.get_connection()
    try:
        assert conn.execute("SELECT COUNT(*) FROM notification_outbox WHERE kind='entry_filled'").fetchone()[0] == 1
    finally: conn.close()


def test_timeout_after_acceptance_recovers_without_duplicate(db):
    seed_pair(); arm(); broker = Broker(); broker.fail_submit_symbol = "BBB"
    with pytest.raises(PairExecutionError, match="reconcile"):
        submit_pair_entry("pair", broker)
    broker.fill("pair", "AAA", "entry", 100); broker.fill("pair", "BBB", "entry", 50)
    reconcile_pair("pair", broker)
    assert get_pair("pair")["state"] == "OPEN"
    assert len(broker.submit_calls) == 2


def test_one_leg_reject_compensates_to_flat(db):
    seed_pair(); arm(); broker = Broker(); submit_pair_entry("pair", broker)
    broker.fill("pair", "AAA", "entry", 100)
    broker.orders[client_order_id("pair", "BBB", "entry")]["status"] = "rejected"
    reconcile_pair("pair", broker)
    assert get_pair("pair")["state"] == "COMPENSATING"
    broker.fill("pair", "AAA", "compensate", 99)
    reconcile_pair("pair", broker)
    assert get_pair("pair")["state"] == "FLAT"


def test_late_fill_after_cancel_is_detected_and_compensated(db):
    seed_pair(); arm(); broker = Broker(); submit_pair_entry("pair", broker)
    reconcile_pair(
        "pair", broker,
        observed_at=datetime(2026, 11, 5, 16, 0, tzinfo=timezone.utc),
        fill_timeout_minutes=5,
    )
    assert get_pair("pair")["state"] == "ENTRY_FAILED"
    broker.fill("pair", "AAA", "entry", 100)
    reconcile_pair("pair", broker)
    assert get_pair("pair")["state"] == "COMPENSATING"
    broker.fill("pair", "AAA", "compensate", 99)
    reconcile_pair("pair", broker)
    assert get_pair("pair")["state"] == "FLAT"


@pytest.mark.parametrize(
    ("mode", "expected"),
    [
        ("target", "TARGET_Z"), ("stop", "STOP_Z"),
        ("time", "TIME_STOP"), ("vix", "VIX_PANIC"),
    ],
)
def test_strategy4_exit_triggers_both_legs(db, mode, expected):
    seed_pair(); broker = Broker(); open_pair(broker)
    if mode == "target": broker.quotes["AAA"].update(bp=99.9, ap=100.1)
    elif mode == "stop": broker.quotes["AAA"].update(bp=103.9, ap=104.1)
    else: broker.quotes["AAA"].update(bp=100.9, ap=101.1)
    result = monitor_pair(
        "pair", broker,
        on_date=date(2026, 11, 20) if mode == "time" else date(2026, 11, 6),
        market_vol_pct=30.0 if mode == "vix" else 15.0,
    )
    assert result["exit_trigger"] == expected
    assert get_pair("pair")["state"] == "EXITING"
    assert len([cid for cid in broker.orders if cid in (client_order_id("pair", "AAA", "exit"), client_order_id("pair", "BBB", "exit"))]) == 2


def test_exit_fill_closes_and_creates_one_alert(db):
    seed_pair(); broker = Broker(); open_pair(broker)
    request_pair_exit("pair", "TARGET_Z", broker)
    broker.fill("pair", "AAA", "exit", 102); broker.fill("pair", "BBB", "exit", 49)
    reconcile_pair("pair", broker); reconcile_pair("pair", broker)
    assert get_pair("pair")["state"] == "CLOSED"
    conn = schema.get_connection()
    try: assert conn.execute("SELECT COUNT(*) FROM notification_outbox WHERE kind='exit_filled'").fetchone()[0] == 1
    finally: conn.close()


def test_uncertain_exit_recovers_by_client_id(db):
    seed_pair(); broker = Broker(); open_pair(broker)
    broker.fail_submit_symbol = "BBB"
    with pytest.raises(PairExecutionError, match="reconcile"):
        request_pair_exit("pair", "TARGET_Z", broker)
    broker.fill("pair", "AAA", "exit", 102)
    broker.fill("pair", "BBB", "exit", 49)
    broker.fail_submit_symbol = None
    reconcile_pair("pair", broker)
    assert get_pair("pair")["state"] == "CLOSED"


def test_rejected_exit_leg_gets_deterministic_retry(db):
    seed_pair(); broker = Broker(); open_pair(broker)
    request_pair_exit("pair", "STOP_Z", broker)
    broker.fill("pair", "AAA", "exit", 98)
    broker.orders[client_order_id("pair", "BBB", "exit")]["status"] = "rejected"
    reconcile_pair("pair", broker)
    retry_id = client_order_id("pair", "BBB", "exit-1")
    assert retry_id in broker.orders
    broker.orders[retry_id].update(
        status="filled", filled_qty="20", filled_avg_price="52",
        updated_at="2026-11-05T10:03:00-05:00",
    )
    reconcile_pair("pair", broker)
    assert get_pair("pair")["state"] == "CLOSED"


def test_broker_position_mismatch_raises_attention_alert(db, monkeypatch):
    seed_pair(); broker = Broker(); open_pair(broker)
    monkeypatch.setattr(broker, "list_positions", lambda: BrokerCollection(tuple()))
    reconcile_pair("pair", broker)
    assert get_pair("pair")["state"] == "ERROR_REQUIRES_ATTENTION"
    assert get_pair("pair")["error_code"] == "RECONCILIATION_MISMATCH"


def test_duplicate_trade_update_is_deduped(db):
    seed_pair(); arm(); broker = Broker(); submit_pair_entry("pair", broker)
    order = dict(broker.orders[client_order_id("pair", "AAA", "entry")])
    payload = {"event": "partial_fill", "order": {**order, "filled_qty": "5"}}
    assert ingest_trade_update(payload); assert ingest_trade_update(payload)
    conn = schema.get_connection()
    try: assert conn.execute("SELECT COUNT(*) FROM broker_order_events WHERE event_type='partially_filled'").fetchone()[0] == 1
    finally: conn.close()


def test_kill_switch_disarms_and_cancels_pending(db):
    seed_pair(); arm(); broker = Broker(); submit_pair_entry("pair", broker)
    control = activate_kill_switch(broker, "test")
    assert not control["armed"] and control["kill_switch"]
    assert len(broker.cancel_calls) == 2


def test_outbox_claims_and_sends_once(db):
    seed_pair(); broker = Broker(); open_pair(broker)
    class Sender:
        def __init__(self): self.messages = []
        async def send_message(self, text, kind="manual", **kwargs): self.messages.append((text, kind)); return True
    sender = Sender()
    def run_immediate(coroutine):
        with pytest.raises(StopIteration) as done:
            coroutine.send(None)
        return done.value.value
    first = run_immediate(deliver_pending(sender)); second = run_immediate(deliver_pending(sender))
    assert first["sent"] == 2 and second["claimed"] == 0 and len(sender.messages) == 2


def test_disarmed_blocks_entries_but_open_pair_can_exit(db):
    seed_pair(); broker = Broker(); open_pair(broker)
    update_control(armed=False, actor="test")
    request_pair_exit("pair", "TARGET_Z", broker)
    assert get_pair("pair")["state"] == "EXITING"


def test_execution_routes_require_admin_token(db):
    import api.main as api_main
    from api.auth.security import create_access_token

    with pytest.raises(HTTPException) as missing:
        api_main.require_auto_trade_admin(None)
    assert missing.value.status_code == 401
    guest = create_access_token({"email": "guest@example.com", "role": "guest"})
    with pytest.raises(HTTPException) as forbidden:
        api_main.require_auto_trade_admin(f"Bearer {guest}")
    assert forbidden.value.status_code == 403
    admin = create_access_token({"email": "admin@example.com", "role": "admin"})
    assert api_main.require_auto_trade_admin(f"Bearer {admin}") == "admin@example.com"
    stale_admin = create_access_token({"email": "admin@akash.ai", "role": "guest"})
    assert api_main.require_auto_trade_admin(f"Bearer {stale_admin}") == "admin@akash.ai"


def test_kill_switch_requires_explicit_confirmation(db):
    import api.main as api_main
    with pytest.raises(HTTPException) as rejected:
        api_main.auto_trade_kill_switch(
            BackgroundTasks(), {"confirm": False}, "admin@example.com",
        )
    assert rejected.value.status_code == 422


def test_arming_and_entry_submission_require_explicit_confirmation(db):
    import api.main as api_main

    with pytest.raises(HTTPException) as arm_rejected:
        api_main.auto_trade_control(
            {"armed": True, "confirm": False}, "admin@example.com",
        )
    assert arm_rejected.value.status_code == 422

    with pytest.raises(HTTPException) as entry_rejected:
        api_main.auto_trade_submit_pair(
            "pair", BackgroundTasks(), {"confirm": False}, "admin@example.com",
        )
    assert entry_rejected.value.status_code == 422


def test_trade_stream_decodes_binary_updates_without_secrets():
    payload = b'{"stream":"trade_updates","data":{"event":"fill","order":{"id":"1"}}}'
    messages = decode_stream_messages(payload)
    assert messages[0]["data"]["event"] == "fill"
    assert decode_stream_messages(b"not-json") == []


def test_alpaca_order_writes_are_paper_only_and_not_retried():
    requests = []
    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.method == "POST":
            body = __import__("json").loads(request.content)
            return httpx.Response(200, json={
                "id": "order", "client_order_id": body["client_order_id"],
                "symbol": body["symbol"], "side": body["side"],
            })
        return httpx.Response(204)
    client = AlpacaPaperClient(config(), transport=httpx.MockTransport(handler))
    order = client.submit_order(symbol="AAA", side="buy", qty=1, client_order_id="safe-id")
    client.cancel_order("order")
    assert order["id"] == "order"
    assert [request.method for request in requests] == ["POST", "DELETE"]

    attempts = 0
    def timeout_handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        raise httpx.ReadTimeout("unknown outcome", request=request)
    uncertain = AlpacaPaperClient(config(), transport=httpx.MockTransport(timeout_handler))
    with pytest.raises(AlpacaRequestError, match="uncertain"):
        uncertain.submit_order(symbol="AAA", side="buy", qty=1, client_order_id="timeout-id")
    assert attempts == 1
