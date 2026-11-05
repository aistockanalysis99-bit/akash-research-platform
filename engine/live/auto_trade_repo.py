"""Persistence helpers for deterministic Strategy 4 dry scans."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Mapping

from ..db.schema import get_connection


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def claim_run(
    run_id: str,
    *,
    session_date: str,
    config_hash: str,
) -> tuple[bool, str]:
    """Atomically claim a deterministic run ID."""
    conn = get_connection()
    try:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT status FROM auto_trade_runs WHERE run_id=?", (run_id,)
        ).fetchone()
        if row:
            conn.commit()
            return False, str(row["status"])
        conn.execute(
            "INSERT INTO auto_trade_runs "
            "(run_id, run_type, session_date, status, started_at, config_hash) "
            "VALUES (?, 'strategy_v4_dry_scan', ?, 'running', ?, ?)",
            (run_id, session_date, utc_now_iso(), config_hash),
        )
        conn.commit()
        return True, "running"
    finally:
        conn.close()


def complete_run(run_id: str, summary: Mapping[str, Any]) -> None:
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE auto_trade_runs SET status='complete', finished_at=?, "
            "summary_json=?, error_code=NULL, error_message=NULL WHERE run_id=?",
            (utc_now_iso(), json.dumps(summary, sort_keys=True), run_id),
        )
        conn.commit()
    finally:
        conn.close()


def fail_run(run_id: str, code: str, message: str) -> None:
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE auto_trade_runs SET status='failed', finished_at=?, "
            "error_code=?, error_message=? WHERE run_id=?",
            (utc_now_iso(), code, message[:500], run_id),
        )
        conn.commit()
    finally:
        conn.close()


def save_signal(signal: Mapping[str, Any]) -> None:
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO strategy_v4_signal_snapshots "
            "(signal_id, run_id, session_date, ticker_a, ticker_b, decision, "
            "rejection_reason, data_cutoff_at, config_version, config_hash, "
            "payload_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(signal_id) DO UPDATE SET decision=excluded.decision, "
            "rejection_reason=excluded.rejection_reason, payload_json=excluded.payload_json",
            (
                signal["signal_id"], signal["run_id"], signal["session_date"],
                signal["ticker_a"], signal["ticker_b"], signal["decision"],
                signal.get("rejection_reason"), signal["data_cutoff_at"],
                signal["config_version"], signal["config_hash"],
                json.dumps(signal["payload"], sort_keys=True), utc_now_iso(),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def save_intent(intent: Mapping[str, Any]) -> None:
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO pair_trade_intents "
            "(pair_trade_id, signal_id, session_date, ticker_a, ticker_b, state, "
            "target_z, stop_z, max_holding_date, idempotency_key, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, 'DRAFT', ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(idempotency_key) DO NOTHING",
            (
                intent["pair_trade_id"], intent["signal_id"], intent["session_date"],
                intent["ticker_a"], intent["ticker_b"], intent["target_z"],
                intent["stop_z"], intent["max_holding_date"],
                intent["idempotency_key"], utc_now_iso(), utc_now_iso(),
            ),
        )
        for leg in intent["legs"]:
            conn.execute(
                "INSERT INTO pair_trade_legs "
                "(leg_id, pair_trade_id, symbol, side, target_qty, state, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, 'PLANNED', ?, ?) "
                "ON CONFLICT(leg_id) DO NOTHING",
                (
                    leg["leg_id"], intent["pair_trade_id"], leg["symbol"],
                    leg["side"], leg["qty"], utc_now_iso(), utc_now_iso(),
                ),
            )
        conn.commit()
    finally:
        conn.close()


def get_run_bundle(run_id: str) -> dict[str, Any] | None:
    conn = get_connection()
    try:
        run = conn.execute(
            "SELECT * FROM auto_trade_runs WHERE run_id=?", (run_id,)
        ).fetchone()
        if not run:
            return None
        signals = conn.execute(
            "SELECT * FROM strategy_v4_signal_snapshots WHERE run_id=? "
            "ORDER BY CASE decision WHEN 'QUALIFIED' THEN 0 ELSE 1 END, "
            "ticker_a, ticker_b",
            (run_id,),
        ).fetchall()
        parsed_signals = []
        for row in signals:
            item = dict(row)
            item["payload"] = json.loads(item.pop("payload_json"))
            parsed_signals.append(item)
        result = dict(run)
        result["summary"] = json.loads(result.pop("summary_json")) if result.get("summary_json") else None
        result.pop("summary_json", None)
        result["signals"] = parsed_signals
        return result
    finally:
        conn.close()


def latest_run_bundle() -> dict[str, Any] | None:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT run_id FROM auto_trade_runs "
            "WHERE run_type='strategy_v4_dry_scan' ORDER BY started_at DESC LIMIT 1"
        ).fetchone()
    finally:
        conn.close()
    return get_run_bundle(str(row["run_id"])) if row else None


def open_pair_count() -> int:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM pair_trade_intents "
            "WHERE state IN ('SUBMITTING','ORDERS_OPEN','OPEN','EXIT_PENDING','EXITING')"
        ).fetchone()
        return int(row["n"])
    finally:
        conn.close()


def session_intent_count(session_date: str) -> int:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM pair_trade_intents WHERE session_date=?",
            (session_date,),
        ).fetchone()
        return int(row["n"])
    finally:
        conn.close()
