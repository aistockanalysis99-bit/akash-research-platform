"""Strategy 4 paper execution, reconciliation, compensation, and exits."""
from __future__ import annotations

import hashlib
import json
import math
from datetime import date, datetime, timedelta, timezone
from typing import Any, Mapping, Protocol

import pandas as pd

from ..config import AutoTradeConfig
from ..db.schema import get_connection
from ..strategy_v4_engine import StrategyV4Config
from .alpaca import AccountSnapshot, AssetSnapshot, BrokerCollection, MarketClock

PAPER_URL = "https://paper-api.alpaca.markets"
OPEN_ORDER_STATES = {"accepted", "new", "pending_new", "partially_filled", "pending_cancel", "pending_replace", "accepted_for_bidding", "stopped", "held", "suspended"}
TERMINAL_FAILURE_STATES = {"canceled", "expired", "rejected", "done_for_day", "replaced"}
PAIR_STATES = {"DRAFT", "VALIDATED", "SUBMITTING", "ORDERS_OPEN", "OPEN", "ENTRY_FAILED", "COMPENSATING", "FLAT", "EXIT_PENDING", "EXITING", "CLOSED", "ERROR_REQUIRES_ATTENTION"}
TRANSITIONS = {
    "DRAFT": {"VALIDATED", "ENTRY_FAILED"}, "VALIDATED": {"SUBMITTING", "ENTRY_FAILED"},
    "SUBMITTING": {"ORDERS_OPEN", "COMPENSATING", "ENTRY_FAILED", "ERROR_REQUIRES_ATTENTION"},
    "ORDERS_OPEN": {"OPEN", "COMPENSATING", "ENTRY_FAILED", "ERROR_REQUIRES_ATTENTION"},
    "OPEN": {"EXIT_PENDING", "ERROR_REQUIRES_ATTENTION"},
    "EXIT_PENDING": {"EXITING", "ERROR_REQUIRES_ATTENTION"},
    "EXITING": {"CLOSED", "ERROR_REQUIRES_ATTENTION"},
    "COMPENSATING": {"FLAT", "ERROR_REQUIRES_ATTENTION"},
    "ENTRY_FAILED": {"COMPENSATING"}, "FLAT": {"COMPENSATING"}, "CLOSED": set(),
    "ERROR_REQUIRES_ATTENTION": {"SUBMITTING", "COMPENSATING", "EXIT_PENDING"},
}


class PairExecutionError(RuntimeError):
    pass


class ExecutionBroker(Protocol):
    config: AutoTradeConfig
    def get_clock(self) -> MarketClock: ...
    def get_account(self) -> AccountSnapshot: ...
    def get_asset(self, symbol: str) -> AssetSnapshot: ...
    def get_latest_quote(self, symbol: str, **kwargs: Any) -> Mapping[str, Any]: ...
    def get_bars(self, symbol: str, **kwargs: Any) -> BrokerCollection: ...
    def list_orders(self, status: str = "all", limit: int = 500) -> BrokerCollection: ...
    def list_positions(self) -> BrokerCollection: ...
    def get_order_by_client_id(self, client_order_id: str) -> Mapping[str, Any] | None: ...
    def submit_order(self, *, symbol: str, side: str, qty: int, client_order_id: str) -> Mapping[str, Any]: ...
    def cancel_order(self, order_id: str) -> None: ...


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def client_order_id(pair_trade_id: str, symbol: str, action: str) -> str:
    digest = hashlib.sha256(f"{pair_trade_id}:{symbol}:{action}".encode()).hexdigest()[:32]
    return f"akash-v4-{digest}"


def normalize_order_status(value: Any) -> str:
    status = str(value or "unknown").strip().lower()
    return {"cancelled": "canceled", "partial_fill": "partially_filled", "fill": "filled"}.get(status, status)


def transition_pair(pair_trade_id: str, target: str, *, error_code: str | None = None, error_message: str | None = None) -> None:
    if target not in PAIR_STATES:
        raise PairExecutionError("unknown pair state")
    conn = get_connection()
    try:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("SELECT state FROM pair_trade_intents WHERE pair_trade_id=?", (pair_trade_id,)).fetchone()
        if row is None:
            raise PairExecutionError("pair trade not found")
        current = str(row["state"])
        if current == target:
            conn.commit()
            return
        if target not in TRANSITIONS.get(current, set()):
            raise PairExecutionError(f"invalid pair transition {current} -> {target}")
        now = _now()
        conn.execute(
            "UPDATE pair_trade_intents SET state=?, updated_at=?, error_code=?, error_message=?, "
            "closed_at=CASE WHEN ? IN ('CLOSED','FLAT') THEN ? ELSE closed_at END WHERE pair_trade_id=?",
            (target, now, error_code, (error_message or "")[:500] or None, target, now, pair_trade_id),
        )
        conn.commit()
    finally:
        conn.close()


def get_control() -> dict[str, Any]:
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM auto_trade_control WHERE singleton_id=1").fetchone()
        return dict(row) if row else {"armed": 0, "kill_switch": 0, "updated_at": None, "updated_by": None}
    finally:
        conn.close()


def update_control(*, armed: bool | None = None, kill_switch: bool | None = None, actor: str) -> dict[str, Any]:
    if not actor or len(actor) > 100:
        raise PairExecutionError("valid control actor required")
    current = get_control()
    next_armed = bool(current["armed"]) if armed is None else bool(armed)
    next_kill = bool(current["kill_switch"]) if kill_switch is None else bool(kill_switch)
    if next_kill:
        next_armed = False
    details = {"armed": next_armed, "kill_switch": next_kill}
    conn = get_connection()
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            "INSERT INTO auto_trade_control (singleton_id, armed, kill_switch, updated_at, updated_by) VALUES (1, ?, ?, ?, ?) "
            "ON CONFLICT(singleton_id) DO UPDATE SET armed=excluded.armed, kill_switch=excluded.kill_switch, updated_at=excluded.updated_at, updated_by=excluded.updated_by",
            (int(next_armed), int(next_kill), _now(), actor),
        )
        conn.execute(
            "INSERT INTO auto_trade_control_audit (action, actor, created_at, details_json) VALUES ('CONTROL_UPDATE', ?, ?, ?)",
            (actor, _now(), json.dumps(details, sort_keys=True)),
        )
        conn.commit()
    finally:
        conn.close()
    return get_control()


def get_pair(pair_trade_id: str) -> dict[str, Any] | None:
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM pair_trade_intents WHERE pair_trade_id=?", (pair_trade_id,)).fetchone()
        if row is None:
            return None
        pair = dict(row)
        pair["legs"] = [dict(item) for item in conn.execute("SELECT * FROM pair_trade_legs WHERE pair_trade_id=? ORDER BY symbol", (pair_trade_id,))]
        pair["orders"] = [dict(item) for item in conn.execute("SELECT * FROM broker_orders WHERE pair_trade_id=? ORDER BY submitted_at, client_order_id", (pair_trade_id,))]
        return pair
    finally:
        conn.close()


def list_pairs() -> list[dict[str, Any]]:
    conn = get_connection()
    try:
        ids = [row["pair_trade_id"] for row in conn.execute("SELECT pair_trade_id FROM pair_trade_intents ORDER BY created_at DESC LIMIT 100")]
    finally:
        conn.close()
    return [pair for pair_id in ids if (pair := get_pair(pair_id))]


def _signal_snapshot(pair_trade_id: str) -> tuple[str, dict[str, Any]]:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT s.decision, s.payload_json FROM strategy_v4_signal_snapshots s "
            "JOIN pair_trade_intents p ON p.signal_id=s.signal_id "
            "WHERE p.pair_trade_id=?",
            (pair_trade_id,),
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        raise PairExecutionError("signal snapshot missing")
    return str(row["decision"]), json.loads(row["payload_json"])


def _enqueue(kind: str, pair_id: str, text: str) -> None:
    key = f"{pair_id}:{kind}"
    notification_id = "ntf-" + hashlib.sha256(key.encode()).hexdigest()[:28]
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO notification_outbox (notification_id, idempotency_key, kind, pair_trade_id, payload_text, status, created_at) "
            "VALUES (?, ?, ?, ?, ?, 'pending', ?) ON CONFLICT(idempotency_key) DO NOTHING",
            (notification_id, key, kind, pair_id, text[:4000], _now()),
        )
        conn.commit()
    finally:
        conn.close()


def _save_order(pair_id: str, leg_id: str, order: Mapping[str, Any], cid: str) -> None:
    symbol = str(order.get("symbol", "")).upper()
    if order.get("client_order_id") != cid or not symbol or not order.get("id"):
        raise PairExecutionError("broker order does not match planned request")
    status = normalize_order_status(order.get("status"))
    raw = json.dumps(dict(order), sort_keys=True, default=str)
    event_key = hashlib.sha256(f"{order['id']}:{status}:{order.get('filled_qty')}:{order.get('updated_at')}".encode()).hexdigest()
    conn = get_connection()
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            "INSERT INTO broker_orders (broker_order_id, client_order_id, pair_trade_id, leg_id, symbol, side, order_type, time_in_force, status, qty, filled_qty, filled_avg_price, submitted_at, updated_at, raw_json) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(client_order_id) DO UPDATE SET broker_order_id=excluded.broker_order_id, status=excluded.status, filled_qty=excluded.filled_qty, filled_avg_price=excluded.filled_avg_price, updated_at=excluded.updated_at, raw_json=excluded.raw_json",
            (str(order["id"]), cid, pair_id, leg_id, symbol, str(order.get("side", "")), str(order.get("type", "market")), str(order.get("time_in_force", "day")), status, float(order.get("qty") or 0), float(order.get("filled_qty") or 0), float(order["filled_avg_price"]) if order.get("filled_avg_price") else None, order.get("submitted_at"), str(order.get("updated_at") or _now()), raw),
        )
        conn.execute(
            "INSERT INTO broker_order_events (broker_order_id, event_type, event_at, payload_json, dedupe_key) VALUES (?, ?, ?, ?, ?) ON CONFLICT(dedupe_key) DO NOTHING",
            (str(order["id"]), status, str(order.get("updated_at") or _now()), raw, event_key),
        )
        conn.commit()
    finally:
        conn.close()


def ingest_trade_update(payload: Mapping[str, Any]) -> bool:
    order = payload.get("order")
    if not isinstance(order, Mapping):
        return False
    cid = str(order.get("client_order_id", ""))
    conn = get_connection()
    try:
        local = conn.execute("SELECT pair_trade_id, leg_id FROM broker_orders WHERE client_order_id=?", (cid,)).fetchone()
    finally:
        conn.close()
    if local is None:
        return False
    merged = dict(order)
    if payload.get("event"):
        merged["status"] = payload["event"]
    _save_order(local["pair_trade_id"], local["leg_id"], merged, cid)
    return True


def _config_guard(broker: ExecutionBroker) -> None:
    broker.config.require_ready()
    control = get_control()
    if not broker.config.enabled or not control["armed"] or control["kill_switch"]:
        raise PairExecutionError("automation is disarmed or kill switch is active")
    if broker.config.alpaca_base_url.rstrip("/") != PAPER_URL:
        raise PairExecutionError("Alpaca paper endpoint required")


def _submit_once(broker: ExecutionBroker, pair_id: str, leg: Mapping[str, Any], action: str, side: str, qty: int) -> Mapping[str, Any]:
    cid = client_order_id(pair_id, str(leg["symbol"]), action)
    existing = broker.get_order_by_client_id(cid)
    order = existing or broker.submit_order(symbol=str(leg["symbol"]), side=side, qty=qty, client_order_id=cid)
    _save_order(pair_id, str(leg["leg_id"]), order, cid)
    return order


def submit_pair_entry(pair_trade_id: str, broker: ExecutionBroker) -> dict[str, Any]:
    _config_guard(broker)
    clock = broker.get_clock()
    if not clock.is_open:
        raise PairExecutionError("regular market is closed")
    account = broker.get_account()
    if account.trading_blocked or account.account_blocked or account.equity < 2000:
        raise PairExecutionError("account is not eligible")
    pair = get_pair(pair_trade_id)
    if pair is None or pair["state"] not in ("DRAFT", "VALIDATED", "SUBMITTING", "ORDERS_OPEN"):
        raise PairExecutionError("pair is not eligible for entry")
    if pair["session_date"] != pd.Timestamp(clock.timestamp).date().isoformat():
        raise PairExecutionError("intent is stale")
    legs = pair["legs"]
    if len(legs) != 2 or {leg["side"] for leg in legs} != {"BUY", "SHORT"}:
        raise PairExecutionError("invalid two-leg intent")
    if pair["state"] == "DRAFT":
        decision, signal = _signal_snapshot(pair_trade_id)
        if decision != "QUALIFIED":
            raise PairExecutionError("signal is no longer qualified")
        positions = broker.list_positions().items
        occupied = {
            str(item.get("symbol", "")).upper()
            for item in (*positions, *broker.list_orders(status="open").items)
        }
        if any(leg["symbol"] in occupied for leg in legs):
            raise PairExecutionError("symbol already occupied")
        gross = 0.0
        references = {
            str(item.get("symbol")): float(item.get("reference_price") or 0)
            for item in signal.get("proposed_legs", [])
        }
        for leg in legs:
            asset = broker.get_asset(leg["symbol"])
            if not asset.tradable or asset.status != "active":
                raise PairExecutionError("asset is not tradable")
            if leg["side"] == "SHORT" and (not asset.shortable or not asset.easy_to_borrow):
                raise PairExecutionError("short leg is not easy to borrow")
            qty = float(leg["target_qty"])
            if qty < 1 or not qty.is_integer():
                raise PairExecutionError("whole-share quantity required")
            quote = broker.get_latest_quote(leg["symbol"], feed="iex")
            bid, ask = float(quote.get("bp", 0)), float(quote.get("ap", 0))
            stamp, observed = pd.Timestamp(quote.get("t")), pd.Timestamp(clock.timestamp)
            if bid <= 0 or ask < bid or abs((observed - stamp).total_seconds()) > broker.config.max_quote_age_seconds:
                raise PairExecutionError("invalid or stale execution quote")
            midpoint = (bid + ask) / 2
            reference = references.get(leg["symbol"], 0)
            if reference <= 0 or abs(midpoint / reference - 1) * 100 > broker.config.max_premarket_gap_pct:
                raise PairExecutionError("execution price moved beyond the configured guard")
            gross += qty * midpoint
        reserve = account.portfolio_value * broker.config.min_buying_power_reserve_pct
        if account.buying_power - gross < reserve:
            raise PairExecutionError("buying power reserve would be breached")
        current_gross = sum(abs(float(item.get("market_value") or 0)) for item in positions)
        if current_gross + gross > account.portfolio_value * broker.config.max_gross_exposure_pct:
            raise PairExecutionError("gross exposure limit would be breached")
        transition_pair(pair_trade_id, "VALIDATED")
        transition_pair(pair_trade_id, "SUBMITTING")
    try:
        for leg in legs:
            _submit_once(broker, pair_trade_id, leg, "entry", "buy" if leg["side"] == "BUY" else "sell", int(leg["target_qty"]))
        if (get_pair(pair_trade_id) or {}) .get("state") == "SUBMITTING":
            transition_pair(pair_trade_id, "ORDERS_OPEN")
            refreshed = get_pair(pair_trade_id)
            if refreshed:
                _enqueue("order_submitted", pair_trade_id, _order_submitted_message(refreshed))
    except Exception as exc:
        current = get_pair(pair_trade_id)
        if current and current["state"] == "SUBMITTING":
            transition_pair(pair_trade_id, "ERROR_REQUIRES_ATTENTION", error_code="ENTRY_OUTCOME_UNCERTAIN", error_message="Broker outcome uncertain; reconciliation required")
        _enqueue("risk_error", pair_trade_id, f"{pair_trade_id}: entry outcome uncertain; reconciliation required")
        raise PairExecutionError("entry outcome uncertain; reconcile before retry") from exc
    return get_pair(pair_trade_id) or {}


def _action_orders(pair: Mapping[str, Any], action: str) -> list[Mapping[str, Any]]:
    action_names = (action, *(f"{action}-{attempt}" for attempt in range(1, 6)))
    return [
        order for order in pair["orders"]
        if any(
            order["client_order_id"]
            == client_order_id(pair["pair_trade_id"], order["symbol"], name)
            for name in action_names
        )
    ]


def request_pair_exit(pair_trade_id: str, reason: str, broker: ExecutionBroker, *, action: str = "exit") -> dict[str, Any]:
    if action not in ("exit", "compensate"):
        raise PairExecutionError("invalid exit action")
    pair = get_pair(pair_trade_id)
    if pair is None:
        raise PairExecutionError("pair trade not found")
    if action == "exit" and pair["state"] == "OPEN":
        transition_pair(pair_trade_id, "EXIT_PENDING", error_code=reason)
        conn = get_connection()
        try:
            conn.execute(
                "UPDATE pair_trade_intents SET exit_reason=? WHERE pair_trade_id=?",
                (reason[:50], pair_trade_id),
            )
            conn.commit()
        finally:
            conn.close()
    if action == "exit" and (get_pair(pair_trade_id) or {})["state"] == "EXIT_PENDING":
        transition_pair(pair_trade_id, "EXITING", error_code=reason)
    if action == "compensate" and pair["state"] != "COMPENSATING":
        transition_pair(pair_trade_id, "COMPENSATING", error_code=reason)
    pair = get_pair(pair_trade_id) or pair
    entries = {order["symbol"]: order for order in _action_orders(pair, "entry")}
    try:
        for leg in pair["legs"]:
            entry = entries.get(leg["symbol"])
            filled = int(float(entry.get("filled_qty", 0))) if entry else 0
            existing = [
                order for order in _action_orders(pair, action)
                if order["symbol"] == leg["symbol"]
            ]
            covered = sum(
                float(order.get("qty") or 0)
                for order in existing
                if normalize_order_status(order["status"]) not in TERMINAL_FAILURE_STATES
            )
            remaining = int(max(0, filled - covered))
            if remaining:
                used = {order["client_order_id"] for order in existing}
                action_name = next(
                    name for name in (action, *(f"{action}-{attempt}" for attempt in range(1, 6)))
                    if client_order_id(pair_trade_id, leg["symbol"], name) not in used
                )
                _submit_once(
                    broker, pair_trade_id, leg, action_name,
                    "sell" if leg["side"] == "BUY" else "buy", remaining,
                )
    except Exception as exc:
        transition_pair(pair_trade_id, "ERROR_REQUIRES_ATTENTION", error_code=f"{action.upper()}_OUTCOME_UNCERTAIN", error_message="Close outcome uncertain; reconciliation required")
        _enqueue("risk_error", pair_trade_id, f"{pair_trade_id}: unbalanced exposure requires attention")
        raise PairExecutionError("close outcome uncertain; reconcile immediately") from exc
    return get_pair(pair_trade_id) or {}


def _refresh_known_orders(pair: Mapping[str, Any], broker: ExecutionBroker) -> None:
    for order in pair["orders"]:
        current = broker.get_order_by_client_id(order["client_order_id"])
        if current:
            _save_order(pair["pair_trade_id"], order["leg_id"], current, order["client_order_id"])


def _verify_open_positions(pair: Mapping[str, Any], broker: ExecutionBroker) -> None:
    positions = {
        str(item.get("symbol", "")).upper(): float(item.get("qty") or 0)
        for item in broker.list_positions().items
    }
    expected = {
        leg["symbol"]: (1 if leg["side"] == "BUY" else -1) * float(leg["filled_qty"])
        for leg in pair["legs"]
    }
    mismatches = {
        symbol: {"expected": qty, "broker": positions.get(symbol, 0.0)}
        for symbol, qty in expected.items()
        if not math.isclose(positions.get(symbol, 0.0), qty, abs_tol=1e-8)
    }
    if mismatches:
        transition_pair(
            pair["pair_trade_id"],
            "ERROR_REQUIRES_ATTENTION",
            error_code="RECONCILIATION_MISMATCH",
            error_message="Broker positions do not match the local pair",
        )
        _enqueue(
            "risk_error",
            pair["pair_trade_id"],
            f"{pair['pair_trade_id']}: broker/local position mismatch {json.dumps(mismatches, sort_keys=True)}",
        )


def _recover_error_state(pair_id: str) -> None:
    transition_pair(pair_id, "SUBMITTING")


def _order_submitted_message(pair: Mapping[str, Any]) -> str:
    _, signal = _signal_snapshot(str(pair["pair_trade_id"]))
    legs = pair.get("legs", [])
    entry_z = float(signal.get("z_score") or 0)
    lines = [
        f"Strategy 4 Order Placed: {pair['ticker_a']}/{pair['ticker_b']}",
        *[
            f"• {leg['side']} {leg['symbol']} x{int(float(leg.get('target_qty', 0)))}"
            for leg in legs
        ],
        f"Signal Z: {entry_z:+.3f} | Target Z: ±{float(pair['target_z']):.2f} | Stop Z: ±{float(pair['stop_z']):.2f}",
        f"Mode: Alpaca Paper Trading | Session: {pair['session_date']}",
        "Status: Orders submitted to Alpaca (ORDERS_OPEN). Awaiting fill confirmation.",
    ]
    return "\n".join(lines)


def _entry_fill_message(pair: Mapping[str, Any]) -> str:
    _, signal = _signal_snapshot(str(pair["pair_trade_id"]))
    fills = {leg["symbol"]: float(leg["avg_fill_price"]) for leg in pair["legs"]}
    beta = float(signal.get("hedge_ratio") or 0)
    mean = float(signal.get("spread_mean") or 0)
    std = float(signal.get("spread_std") or 0)
    entry_z = float(signal.get("z_score") or 0)
    fill_z = None
    target_prices = stop_prices = None
    if beta and std > 0:
        pa, pb = fills[pair["ticker_a"]], fills[pair["ticker_b"]]
        fill_z = (pa - beta * pb - mean) / std
        direction = -1.0 if entry_z < 0 else 1.0
        target_spread = mean + direction * float(pair["target_z"]) * std
        stop_spread = mean + direction * float(pair["stop_z"]) * std
        target_prices = (target_spread + beta * pb, (pa - target_spread) / beta)
        stop_prices = (stop_spread + beta * pb, (pa - stop_spread) / beta)
    capital = sum(float(leg["filled_qty"]) * float(leg["avg_fill_price"]) for leg in pair["legs"])
    lines = [
        f"Strategy 4 Order Bought / Filled: {pair['ticker_a']}/{pair['ticker_b']}",
        *[
            f"• {leg['side']} {leg['symbol']} x{int(float(leg['filled_qty']))} @ ${float(leg['avg_fill_price']):.4f}"
            for leg in pair["legs"]
        ],
        f"Signal Z: {entry_z:+.3f} | Fill Z: {fill_z:+.3f}" if fill_z is not None else f"Signal Z: {entry_z:+.3f}",
        f"Target Z: ±{float(pair['target_z']):.3f} | Stop Z: ±{float(pair['stop_z']):.3f}",
        f"Capital deployed: ${capital:.2f} | Max hold until: {pair['max_holding_date']}",
    ]
    if target_prices and stop_prices:
        lines.append(
            f"Indicative {pair['ticker_a']} target/stop {target_prices[0]:.4f}/{stop_prices[0]:.4f}; "
            f"{pair['ticker_b']} target/stop {target_prices[1]:.4f}/{stop_prices[1]:.4f}"
        )
    return "\n".join(lines)


def reconcile_pair(pair_trade_id: str, broker: ExecutionBroker, *, observed_at: datetime | None = None, fill_timeout_minutes: int = 5) -> dict[str, Any]:
    pair = get_pair(pair_trade_id)
    if pair is None:
        raise PairExecutionError("pair trade not found")
    _refresh_known_orders(pair, broker)
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE pair_trade_intents SET reconciled_at=? WHERE pair_trade_id=?",
            (_now(), pair_trade_id),
        )
        conn.commit()
    finally:
        conn.close()
    pair = get_pair(pair_trade_id) or pair
    if pair["state"] in ("ENTRY_FAILED", "FLAT"):
        entries = _action_orders(pair, "entry")
        close_action = "compensate"
        closes = _action_orders(pair, close_action)
        uncovered = any(
            float(entry.get("filled_qty") or 0)
            > sum(
                float(order.get("filled_qty") or 0)
                for order in closes
                if order["symbol"] == entry["symbol"]
                and normalize_order_status(order["status"]) == "filled"
            )
            for entry in entries
        )
        if uncovered:
            transition_pair(pair_trade_id, "COMPENSATING", error_code="LATE_ENTRY_FILL")
            request_pair_exit(pair_trade_id, "LATE_ENTRY_FILL", broker, action="compensate")
            pair = get_pair(pair_trade_id) or pair
    entry_recovery = (
        pair["state"] in ("SUBMITTING", "ORDERS_OPEN")
        or (
            pair["state"] == "ERROR_REQUIRES_ATTENTION"
            and pair.get("error_code") == "ENTRY_OUTCOME_UNCERTAIN"
        )
    )
    if entry_recovery:
        for leg in pair["legs"]:
            cid = client_order_id(pair_trade_id, leg["symbol"], "entry")
            if not any(order["client_order_id"] == cid for order in _action_orders(pair, "entry")):
                remote = broker.get_order_by_client_id(cid)
                if remote:
                    _save_order(pair_trade_id, leg["leg_id"], remote, cid)
        pair = get_pair(pair_trade_id) or pair
        entries = _action_orders(pair, "entry")
        statuses = [normalize_order_status(order["status"]) for order in entries]
        fills = [float(order.get("filled_qty") or 0) for order in entries]
        if len(entries) == 2 and all(status == "filled" for status in statuses):
            conn = get_connection()
            try:
                for order in entries:
                    conn.execute("UPDATE pair_trade_legs SET state='OPEN', filled_qty=?, avg_fill_price=?, updated_at=? WHERE leg_id=?", (order["filled_qty"], order["filled_avg_price"], _now(), order["leg_id"]))
                conn.commit()
            finally:
                conn.close()
            if pair["state"] == "ERROR_REQUIRES_ATTENTION":
                _recover_error_state(pair_trade_id)
            if (get_pair(pair_trade_id) or {})["state"] == "SUBMITTING":
                transition_pair(pair_trade_id, "ORDERS_OPEN")
            transition_pair(pair_trade_id, "OPEN")
            refreshed = get_pair(pair_trade_id) or pair
            _enqueue("entry_filled", pair_trade_id, _entry_fill_message(refreshed))
            return refreshed
        terminal = any(status in TERMINAL_FAILURE_STATES for status in statuses)
        now = observed_at or datetime.now(timezone.utc)
        timed_out = any(order.get("submitted_at") and normalize_order_status(order["status"]) in OPEN_ORDER_STATES and now - pd.Timestamp(order["submitted_at"]).to_pydatetime() >= timedelta(minutes=fill_timeout_minutes) for order in entries)
        if terminal or timed_out:
            for order in entries:
                if normalize_order_status(order["status"]) in OPEN_ORDER_STATES:
                    try:
                        broker.cancel_order(order["broker_order_id"])
                    except Exception:
                        pass
            if pair["state"] == "ERROR_REQUIRES_ATTENTION":
                _recover_error_state(pair_trade_id)
            if any(qty > 0 for qty in fills):
                transition_pair(pair_trade_id, "COMPENSATING", error_code="ENTRY_INCOMPLETE")
                request_pair_exit(pair_trade_id, "ENTRY_INCOMPLETE", broker, action="compensate")
            else:
                transition_pair(pair_trade_id, "ENTRY_FAILED", error_code="ENTRY_NOT_FILLED")
                _enqueue("entry_failed", pair_trade_id, f"{pair_trade_id}: entry failed with no exposure")
    pair = get_pair(pair_trade_id) or pair
    if pair["state"] == "ERROR_REQUIRES_ATTENTION":
        error_code = str(pair.get("error_code") or "")
        if error_code.startswith("EXIT_"):
            transition_pair(pair_trade_id, "EXIT_PENDING", error_code=pair.get("exit_reason"))
            request_pair_exit(
                pair_trade_id,
                str(pair.get("exit_reason") or "RECOVERED_EXIT"),
                broker,
                action="exit",
            )
        elif error_code.startswith("COMPENSATE_"):
            transition_pair(pair_trade_id, "COMPENSATING", error_code=error_code)
            request_pair_exit(pair_trade_id, error_code, broker, action="compensate")
        pair = get_pair(pair_trade_id) or pair
    for action, active_state, done_state in (("compensate", "COMPENSATING", "FLAT"), ("exit", "EXITING", "CLOSED")):
        if pair["state"] != active_state:
            continue
        _refresh_known_orders(pair, broker)
        pair = get_pair(pair_trade_id) or pair
        orders = _action_orders(pair, action)
        entries = {order["symbol"]: order for order in _action_orders(pair, "entry")}
        required = {
            symbol: float(order.get("filled_qty") or 0)
            for symbol, order in entries.items()
            if float(order.get("filled_qty") or 0) > 0
        }
        closed = {
            symbol: sum(
                float(order.get("filled_qty") or 0)
                for order in orders
                if order["symbol"] == symbol
                and normalize_order_status(order["status"]) == "filled"
            )
            for symbol in required
        }
        if required and all(closed.get(symbol, 0) >= qty for symbol, qty in required.items()):
            transition_pair(pair_trade_id, done_state)
            if done_state == "CLOSED":
                pnl_by_symbol = {
                    symbol: sum(
                        (1 if entries[symbol]["side"] == "buy" else -1)
                        * (float(order["filled_avg_price"]) - float(entries[symbol]["filled_avg_price"]))
                        * float(order["filled_qty"])
                        for order in orders
                        if order["symbol"] == symbol
                        and normalize_order_status(order["status"]) == "filled"
                    )
                    for symbol in required
                }
                pnl = sum(pnl_by_symbol.values())
                conn = get_connection()
                try:
                    conn.execute(
                        "UPDATE pair_trade_intents SET realized_pnl=?, unrealized_pnl=0 "
                        "WHERE pair_trade_id=?", (pnl, pair_trade_id),
                    )
                    conn.commit()
                finally:
                    conn.close()
                refreshed = get_pair(pair_trade_id) or pair
                details = ", ".join(
                    f"{symbol} {value:.2f}" for symbol, value in sorted(pnl_by_symbol.items())
                )
                _enqueue(
                    "exit_filled",
                    pair_trade_id,
                    f"Strategy 4 exit filled: {refreshed['ticker_a']}/{refreshed['ticker_b']}\n"
                    f"Reason {refreshed.get('exit_reason') or 'UNKNOWN'} | leg P&L {details} | net P&L {pnl:.2f}",
                )
            else:
                _enqueue("entry_failed", pair_trade_id, f"{pair_trade_id}: compensation filled; account flat")
        elif any(
            normalize_order_status(order["status"]) in TERMINAL_FAILURE_STATES
            for order in orders
        ):
            try:
                request_pair_exit(
                    pair_trade_id,
                    str(pair.get("exit_reason") or "CLOSE_RETRY"),
                    broker,
                    action=action,
                )
            except PairExecutionError:
                _enqueue(
                    "risk_error",
                    pair_trade_id,
                    f"{pair_trade_id}: close retry failed; exposure may be unbalanced",
                )
    result = get_pair(pair_trade_id) or {}
    if result.get("state") == "OPEN":
        _verify_open_positions(result, broker)
        result = get_pair(pair_trade_id) or result
    return result


def _market_volatility_from_broker(broker: ExecutionBroker) -> float | None:
    try:
        rows = broker.get_bars("SPY", timeframe="1Day", limit=30, feed="iex").items
        closes = pd.Series([float(row.get("c")) for row in rows if row.get("c")])
        value = closes.pct_change().tail(20).std() * (252 ** 0.5) * 100
        return float(value) if pd.notna(value) else None
    except Exception:
        return None


def monitor_pair(
    pair_trade_id: str,
    broker: ExecutionBroker,
    *,
    on_date: date | None = None,
    market_vol_pct: float | None = None,
) -> dict[str, Any]:
    pair = get_pair(pair_trade_id)
    if pair is None or pair["state"] != "OPEN":
        return pair or {}
    conn = get_connection()
    try:
        row = conn.execute("SELECT s.payload_json FROM strategy_v4_signal_snapshots s JOIN pair_trade_intents p ON p.signal_id=s.signal_id WHERE p.pair_trade_id=?", (pair_trade_id,)).fetchone()
    finally:
        conn.close()
    if row is None:
        raise PairExecutionError("signal snapshot missing")
    signal = json.loads(row["payload_json"])
    quotes = {}
    clock = broker.get_clock()
    observed = pd.Timestamp(clock.timestamp)
    for leg in pair["legs"]:
        quote = broker.get_latest_quote(leg["symbol"], feed="iex")
        bid, ask = float(quote.get("bp", 0)), float(quote.get("ap", 0))
        stamp = pd.Timestamp(quote.get("t"))
        if (
            bid <= 0 or ask < bid
            or abs((observed - stamp).total_seconds()) > broker.config.max_quote_age_seconds
        ):
            _enqueue("risk_error", pair_trade_id, f"{pair_trade_id}: monitoring quote is invalid or stale")
            raise PairExecutionError("invalid or stale monitoring quote")
        quotes[leg["symbol"]] = (bid + ask) / 2
    spread_std = float(signal.get("spread_std") or 0)
    if spread_std <= 0:
        raise PairExecutionError("invalid signal spread standard deviation")
    z_score = (quotes[pair["ticker_a"]] - float(signal["hedge_ratio"]) * quotes[pair["ticker_b"]] - float(signal["spread_mean"])) / spread_std
    unrealized = sum(
        (1 if leg["side"] == "BUY" else -1)
        * (quotes[leg["symbol"]] - float(leg["avg_fill_price"] or 0))
        * float(leg["filled_qty"])
        for leg in pair["legs"]
    )
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE pair_trade_intents SET current_z=?, unrealized_pnl=? WHERE pair_trade_id=?",
            (z_score, unrealized, pair_trade_id),
        )
        conn.commit()
    finally:
        conn.close()
    reason = None
    if abs(z_score) <= float(pair["target_z"]): reason = "TARGET_Z"
    elif abs(z_score) >= float(pair["stop_z"]): reason = "STOP_Z"
    elif (on_date or date.today()) >= date.fromisoformat(pair["max_holding_date"]): reason = "TIME_STOP"
    current_market_vol = (
        market_vol_pct
        if market_vol_pct is not None
        else _market_volatility_from_broker(broker)
    )
    strategy_config = StrategyV4Config.load()
    if (
        strategy_config.vix_overlay_enabled
        and current_market_vol is not None
        and current_market_vol > strategy_config.vix_panic_threshold
    ):
        reason = "VIX_PANIC"
    account = broker.get_account()
    if account.trading_blocked or account.account_blocked: reason = "BROKER_RISK"
    if reason:
        request_pair_exit(pair_trade_id, reason, broker)
    result = get_pair(pair_trade_id) or pair
    result["live_z_score"] = round(z_score, 6)
    result["market_vol_pct"] = current_market_vol
    result["exit_trigger"] = reason
    return result


def reconcile_all(broker: ExecutionBroker) -> list[dict[str, Any]]:
    active = {"SUBMITTING", "ORDERS_OPEN", "OPEN", "EXIT_PENDING", "EXITING", "COMPENSATING", "ERROR_REQUIRES_ATTENTION"}
    return [reconcile_pair(pair["pair_trade_id"], broker) for pair in list_pairs() if pair["state"] in active]


def activate_kill_switch(broker: ExecutionBroker | None, actor: str) -> dict[str, Any]:
    control = update_control(kill_switch=True, actor=actor)
    if broker is None:
        return control
    for pair in list_pairs():
        if pair["state"] not in {"SUBMITTING", "ORDERS_OPEN"}:
            continue
        for order in _action_orders(pair, "entry"):
            if normalize_order_status(order["status"]) in OPEN_ORDER_STATES:
                try:
                    broker.cancel_order(order["broker_order_id"])
                except Exception:
                    _enqueue("risk_error", pair["pair_trade_id"], f"{pair['pair_trade_id']}: kill-switch cancellation requires reconciliation")
    return control
