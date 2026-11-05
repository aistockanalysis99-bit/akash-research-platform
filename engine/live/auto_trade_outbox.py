"""Exactly-once claimed Telegram delivery for auto-trade state transitions."""
from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from typing import Protocol

from ..db.schema import get_connection
from .telegram import TelegramClient


class NotificationSender(Protocol):
    async def send_message(self, text: str, kind: str = "manual", **kwargs) -> bool: ...


def _now() -> datetime:
    return datetime.now(timezone.utc)


def enqueue_system_alert(kind: str, text: str, dedupe_bucket: str) -> None:
    key = f"system:{kind}:{dedupe_bucket}"
    notification_id = "ntf-" + hashlib.sha256(key.encode()).hexdigest()[:28]
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO notification_outbox (notification_id, idempotency_key, kind, "
            "pair_trade_id, payload_text, status, created_at) "
            "VALUES (?, ?, ?, NULL, ?, 'pending', ?) "
            "ON CONFLICT(idempotency_key) DO NOTHING",
            (notification_id, key, kind, text[:4000], _now().isoformat()),
        )
        conn.commit()
    finally:
        conn.close()


async def deliver_pending(sender: NotificationSender | None = None, limit: int = 20) -> dict[str, int]:
    sender = sender or TelegramClient()
    conn = get_connection()
    claimed = []
    try:
        conn.execute("BEGIN IMMEDIATE")
        rows = conn.execute(
            "SELECT notification_id, kind, payload_text FROM notification_outbox "
            "WHERE (status IN ('pending','retry') AND "
            "(next_attempt_at IS NULL OR next_attempt_at<=?)) OR "
            "(status='sending' AND next_attempt_at<=?) "
            "ORDER BY created_at LIMIT ?",
            (_now().isoformat(), _now().isoformat(), max(1, min(limit, 100))),
        ).fetchall()
        for row in rows:
            conn.execute(
                "UPDATE notification_outbox SET status='sending', attempts=attempts+1, "
                "next_attempt_at=? WHERE notification_id=?",
                ((_now() + timedelta(minutes=5)).isoformat(), row["notification_id"]),
            )
            claimed.append(dict(row))
        conn.commit()
    finally:
        conn.close()

    sent = failed = 0
    for item in claimed:
        success = await sender.send_message(item["payload_text"], kind=f"auto_trade_{item['kind']}")
        conn = get_connection()
        try:
            if success:
                conn.execute(
                    "UPDATE notification_outbox SET status='sent', sent_at=?, "
                    "next_attempt_at=NULL, last_error=NULL "
                    "WHERE notification_id=?", (_now().isoformat(), item["notification_id"])
                )
                sent += 1
            else:
                conn.execute(
                    "UPDATE notification_outbox SET status='retry', next_attempt_at=?, "
                    "last_error='delivery_failed' WHERE notification_id=?",
                    ((_now() + timedelta(minutes=5)).isoformat(), item["notification_id"]),
                )
                failed += 1
            conn.commit()
        finally:
            conn.close()
    return {"claimed": len(claimed), "sent": sent, "failed": failed}
