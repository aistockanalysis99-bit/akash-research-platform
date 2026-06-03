"""AI memory — store + inject lessons from closed positions.

Lessons live in the `lessons` SQLite table. After a position closes, the
Reflector agent (engine/live/agents/reflector.py) writes a 2-4 sentence
lesson that gets persisted here. When the PM agent builds its prompt, it
pulls the top N recent lessons via `format_lessons_for_prompt()` and the
PM gets to see what we've learned.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Optional

from ..db.schema import get_connection
from .schemas import Reflection

log = logging.getLogger(__name__)


# How many lessons to inject by default into the PM/Risk prompts.
DEFAULT_INJECTION_LIMIT = 10


def save_lesson(r: Reflection) -> int:
    conn = get_connection()
    try:
        cur = conn.execute(
            "INSERT INTO lessons "
            "(symbol, lesson_text, created_at, position_id, "
            " outcome_pnl_pct, days_held, exit_reason, category) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                r.symbol, r.lesson_text, datetime.utcnow().isoformat(),
                r.position_id, r.outcome_pnl_pct, r.days_held,
                r.exit_reason, r.category,
            ),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def list_recent(limit: int = 50) -> list[dict[str, Any]]:
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT id, symbol, lesson_text, created_at, position_id, "
            "outcome_pnl_pct, days_held, exit_reason, category "
            "FROM lessons ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def list_for_symbol(symbol: str, limit: int = 10) -> list[dict[str, Any]]:
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT id, symbol, lesson_text, created_at, position_id, "
            "outcome_pnl_pct, days_held, exit_reason, category "
            "FROM lessons WHERE symbol = ? ORDER BY created_at DESC LIMIT ?",
            (symbol.upper(), limit),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def format_lessons_for_prompt(
    symbol: Optional[str] = None,
    limit: int = DEFAULT_INJECTION_LIMIT,
) -> str:
    """Return a compact text block ready to drop into an LLM prompt.

    If `symbol` is given, prioritizes lessons about that ticker first, then
    fills the remaining slots with general recent lessons.
    """
    same_ticker: list[dict] = []
    if symbol:
        same_ticker = list_for_symbol(symbol, limit=max(1, limit // 2))

    remaining = max(0, limit - len(same_ticker))
    others: list[dict] = []
    if remaining > 0:
        recent = list_recent(limit=limit + remaining)
        seen_ids = {l["id"] for l in same_ticker}
        for row in recent:
            if row["id"] in seen_ids:
                continue
            if symbol and row["symbol"] == symbol.upper():
                # already in same_ticker bucket
                continue
            others.append(row)
            if len(others) >= remaining:
                break

    rows = same_ticker + others
    if not rows:
        return "(no historical lessons yet — this fund is in its early operating period)"

    lines = ["Prior lessons learned (most recent first):"]
    for row in rows:
        pnl = row.get("outcome_pnl_pct")
        pnl_str = f"{pnl:+.2f}%" if pnl is not None else "?"
        days = row.get("days_held") or "?"
        cat = (row.get("category") or "other").replace("_", " ")
        date = (row.get("created_at") or "")[:10]
        lines.append(
            f"- [{date} • {row['symbol']} • {pnl_str} in {days}d • {cat}] "
            f"{row['lesson_text']}"
        )
    return "\n".join(lines)


def list_pending_reflection() -> list[dict[str, Any]]:
    """Closed positions whose Reflector hasn't run yet.

    A position is "pending" if it's status=closed AND no row exists in
    `lessons` with position_id = position.id.
    """
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT p.id, p.symbol, p.entry_date, p.entry_price, p.units,
                   p.exit_date, p.exit_price, p.exit_reason,
                   p.final_pnl_usd, p.final_pnl_pct, p.days_held,
                   p.decision_verdict, p.decision_conviction,
                   p.decision_size_pct
            FROM virtual_positions p
            LEFT JOIN lessons l ON l.position_id = p.id
            WHERE p.status='closed' AND l.id IS NULL
            ORDER BY p.exit_date DESC, p.id DESC
            """
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()
