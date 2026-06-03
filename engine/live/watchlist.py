"""Watchlist — symbols the evening scheduler runs through.

Thin SQLite-backed list. No fancy ORM; the table is small (<100 rows).
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from ..db.schema import get_connection

log = logging.getLogger(__name__)


def add_symbol(symbol: str, notes: Optional[str] = None) -> bool:
    """Add a symbol to the watchlist. Returns True if newly added."""
    symbol = symbol.upper().strip()
    if not symbol:
        return False
    conn = get_connection()
    try:
        cur = conn.execute(
            "INSERT OR IGNORE INTO watchlist (symbol, added_at, notes, enabled) "
            "VALUES (?, ?, ?, 1)",
            (symbol, datetime.utcnow().isoformat(), notes),
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def remove_symbol(symbol: str) -> bool:
    """Remove a symbol. Returns True if it was present."""
    symbol = symbol.upper().strip()
    conn = get_connection()
    try:
        cur = conn.execute("DELETE FROM watchlist WHERE symbol = ?", (symbol,))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def set_enabled(symbol: str, enabled: bool) -> bool:
    symbol = symbol.upper().strip()
    conn = get_connection()
    try:
        cur = conn.execute(
            "UPDATE watchlist SET enabled = ? WHERE symbol = ?",
            (1 if enabled else 0, symbol),
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def list_all() -> list[dict]:
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT symbol, added_at, notes, enabled FROM watchlist "
            "ORDER BY symbol ASC"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def list_enabled_symbols() -> list[str]:
    """Just the enabled symbols — used by the evening scheduler."""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT symbol FROM watchlist WHERE enabled = 1 ORDER BY symbol ASC"
        ).fetchall()
        return [r["symbol"] for r in rows]
    finally:
        conn.close()
