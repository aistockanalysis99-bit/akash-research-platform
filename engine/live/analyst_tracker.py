"""Analyst track-record weighting — accumulates `/grades` calls into a
small SQLite-backed history and computes a hit-rate per (firm, analyst).

The system records every analyst call it sees. After ~6 months of data,
we can tell whether "Wedbush raised PT to $400" is signal or noise by
checking if Wedbush has been right >50% of the time on this name and on
the sector overall.

For Day 1 (no history): every analyst gets a neutral 50% prior. Score
will diverge as data accumulates.
"""
from __future__ import annotations

import logging
import sqlite3
from datetime import date, datetime
from pathlib import Path
from typing import Any, Optional

from ..db.schema import get_connection

log = logging.getLogger(__name__)


SCHEMA = """
CREATE TABLE IF NOT EXISTS analyst_calls (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    firm TEXT NOT NULL,
    analyst TEXT,
    call_date TEXT NOT NULL,
    action TEXT,                 -- upgrade / downgrade / initiate / maintain / target_change
    previous_grade TEXT,
    new_grade TEXT,
    previous_target REAL,
    new_target REAL,
    price_at_call REAL,
    -- For scoring: filled in later when we look back
    price_30d_after REAL,
    price_90d_after REAL,
    correct BOOLEAN,             -- 1 if upgrade & price rose / downgrade & price fell
    UNIQUE(symbol, firm, call_date, action)
);
CREATE INDEX IF NOT EXISTS idx_analyst_calls_firm ON analyst_calls(firm);
CREATE INDEX IF NOT EXISTS idx_analyst_calls_symbol ON analyst_calls(symbol);
"""


def ensure_schema() -> None:
    conn = get_connection()
    try:
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()


def record_calls(symbol: str, grades_rows: list[dict], current_price: Optional[float]) -> int:
    """Insert any new analyst calls into the local table. Idempotent.

    Returns the number of new rows inserted.
    """
    if not grades_rows:
        return 0
    ensure_schema()
    conn = get_connection()
    inserted = 0
    try:
        for r in grades_rows:
            try:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO analyst_calls
                    (symbol, firm, analyst, call_date, action,
                     previous_grade, new_grade,
                     previous_target, new_target, price_at_call)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        symbol.upper(),
                        r.get("gradingCompany") or r.get("firm") or "Unknown",
                        r.get("analyst") or None,
                        (r.get("date") or "")[:10],
                        r.get("action") or None,
                        r.get("previousGrade") or None,
                        r.get("newGrade") or None,
                        _f(r.get("previousPriceTarget")),
                        _f(r.get("newPriceTarget")),
                        current_price,
                    ),
                )
                if conn.total_changes > 0:
                    inserted += 1
            except sqlite3.Error as e:
                log.warning("analyst_tracker: insert failed: %s", e)
        conn.commit()
    finally:
        conn.close()
    return inserted


def firm_score(firm: str, symbol: Optional[str] = None) -> dict[str, Any]:
    """Get hit-rate score for a firm. Symbol-specific if available, else overall.

    Returns:
        {
          "firm": "Wedbush",
          "calls": 24,
          "correct": 14,
          "hit_rate_pct": 58.3,
          "label": "above_average" | "average" | "below_average" | "new",
          "scope": "symbol" | "overall" | "none"
        }
    """
    ensure_schema()
    conn = get_connection()
    try:
        # Try symbol-specific first
        if symbol:
            rows = conn.execute(
                "SELECT correct FROM analyst_calls "
                "WHERE firm = ? AND symbol = ? AND correct IS NOT NULL",
                (firm, symbol.upper()),
            ).fetchall()
            if len(rows) >= 5:
                return _summarize(firm, rows, "symbol")
        # Fall back to overall
        rows = conn.execute(
            "SELECT correct FROM analyst_calls "
            "WHERE firm = ? AND correct IS NOT NULL",
            (firm,),
        ).fetchall()
        if rows:
            return _summarize(firm, rows, "overall")
        return {
            "firm": firm,
            "calls": 0,
            "correct": 0,
            "hit_rate_pct": None,
            "label": "new",
            "scope": "none",
        }
    finally:
        conn.close()


def _summarize(firm: str, rows: list, scope: str) -> dict[str, Any]:
    n = len(rows)
    correct = sum(1 for r in rows if r[0])
    hit_rate = (correct / n) * 100
    if hit_rate >= 60:
        label = "above_average"
    elif hit_rate >= 45:
        label = "average"
    else:
        label = "below_average"
    return {
        "firm": firm,
        "calls": n,
        "correct": correct,
        "hit_rate_pct": round(hit_rate, 1),
        "label": label,
        "scope": scope,
    }


def update_call_outcomes(symbol: str, current_price: float) -> int:
    """Look back at analyst calls 30+ days old for this symbol and grade
    them. Returns count of updates.

    A call is "correct" if:
      - upgrade / PT raise → price moved up vs price_at_call
      - downgrade / PT cut → price moved down vs price_at_call
      - else → neutral (correct = NULL stays)
    """
    if current_price is None or current_price <= 0:
        return 0
    ensure_schema()
    conn = get_connection()
    updated = 0
    try:
        cutoff = (date.today().toordinal() - 30)
        cutoff_iso = date.fromordinal(cutoff).isoformat()
        # Find calls older than 30 days with no outcome yet
        rows = conn.execute(
            """
            SELECT id, action, previous_target, new_target, price_at_call
            FROM analyst_calls
            WHERE symbol = ? AND correct IS NULL
              AND call_date <= ? AND price_at_call IS NOT NULL
            """,
            (symbol.upper(), cutoff_iso),
        ).fetchall()

        for row in rows:
            pid, action, prev_pt, new_pt, price0 = row
            if price0 is None or price0 <= 0:
                continue
            ret_pct = ((current_price - price0) / price0) * 100
            bullish = False
            if action and ("upgrad" in action.lower() or "raise" in action.lower()):
                bullish = True
            elif new_pt is not None and prev_pt is not None and new_pt > prev_pt:
                bullish = True
            elif action and ("downgrad" in action.lower() or "cut" in action.lower()):
                bullish = False
            elif new_pt is not None and prev_pt is not None and new_pt < prev_pt:
                bullish = False
            else:
                continue  # neutral call — skip grading

            correct = (ret_pct > 2 and bullish) or (ret_pct < -2 and not bullish)
            conn.execute(
                """
                UPDATE analyst_calls
                SET price_30d_after = ?, correct = ?
                WHERE id = ?
                """,
                (current_price, 1 if correct else 0, pid),
            )
            updated += 1
        conn.commit()
    finally:
        conn.close()
    return updated


def annotate_grades(symbol: str, grades_rows: list[dict]) -> list[dict]:
    """Attach a `firm_score` block to each grades row for prompt injection."""
    out = []
    for r in grades_rows:
        firm = r.get("gradingCompany") or r.get("firm") or "Unknown"
        out.append({**r, "_firm_score": firm_score(firm, symbol)})
    return out


def _f(v) -> Optional[float]:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None
