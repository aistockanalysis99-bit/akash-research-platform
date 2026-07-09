"""SQLite persistence for the options module — fully self-contained tables.

Deliberately does NOT touch engine/db/schema.py or any existing table, and the
paper options P&L NEVER touches the equity portfolio's cash balance.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Optional

from ...db.schema import get_connection

log = logging.getLogger(__name__)

_ensured = False


def ensure_tables() -> None:
    global _ensured
    if _ensured:
        return
    conn = get_connection()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS options_candidates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                scan_date TEXT, symbol TEXT,
                earnings_date TEXT, days_to_earnings INTEGER,
                spot REAL, strike REAL, expiry TEXT,
                straddle_cost REAL, implied_move_pct REAL,
                hist_median_move_pct REAL, hist_events INTEGER,
                cheapness REAL, atm_iv REAL,
                min_oi INTEGER, max_leg_spread_pct REAL,
                avg_theta REAL, avg_vega REAL,
                qualified INTEGER, reject_reason TEXT,
                dual_signal INTEGER DEFAULT 0,
                created_at TEXT,
                UNIQUE(scan_date, symbol)
            )""")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS options_positions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT, status TEXT DEFAULT 'open',
                contracts INTEGER, strike REAL, expiry TEXT,
                earnings_date TEXT, exit_deadline TEXT,
                entry_date TEXT, entry_spot REAL, entry_cost REAL,
                entry_iv REAL, entry_theta REAL, entry_vega REAL,
                current_value REAL, current_iv REAL, current_theta REAL,
                current_vega REAL, current_spot REAL,
                pnl_usd REAL, pnl_pct REAL,
                vega_pnl REAL, theta_pnl REAL, move_pnl REAL,
                last_marked TEXT,
                drift_alerted INTEGER DEFAULT 0,
                exit_alerted_morning INTEGER DEFAULT 0,
                exit_alerted_final INTEGER DEFAULT 0,
                exit_date TEXT, exit_value REAL, exit_reason TEXT,
                final_pnl_usd REAL, final_pnl_pct REAL,
                notes TEXT, created_at TEXT
            )""")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS options_iv_history (
                symbol TEXT, snap_date TEXT, expiry TEXT, atm_iv REAL,
                implied_move_pct REAL,
                PRIMARY KEY (symbol, snap_date)
            )""")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS options_backtests (
                symbol TEXT PRIMARY KEY,
                entry_days INTEGER,
                computed_at TEXT,
                result_json TEXT
            )""")
        conn.commit()
        _ensured = True
    finally:
        conn.close()


def save_backtest(symbol: str, entry_days: int, result: dict[str, Any]) -> None:
    ensure_tables()
    conn = get_connection()
    try:
        conn.execute(
            "INSERT OR REPLACE INTO options_backtests VALUES (?,?,?,?)",
            (symbol.upper(), entry_days, datetime.utcnow().isoformat(),
             json.dumps(result)))
        conn.commit()
    finally:
        conn.close()


def load_backtest(symbol: str) -> Optional[dict[str, Any]]:
    ensure_tables()
    conn = get_connection()
    try:
        r = conn.execute(
            "SELECT computed_at, result_json FROM options_backtests WHERE symbol=?",
            (symbol.upper(),)).fetchone()
    finally:
        conn.close()
    if not r:
        return None
    result = json.loads(r["result_json"])
    result["computed_at"] = r["computed_at"]
    return result


# ---- candidates ----------------------------------------------------------- #

def save_candidate(row: dict[str, Any]) -> None:
    ensure_tables()
    conn = get_connection()
    try:
        conn.execute("""
            INSERT INTO options_candidates
                (scan_date, symbol, earnings_date, days_to_earnings, spot,
                 strike, expiry, straddle_cost, implied_move_pct,
                 hist_median_move_pct, hist_events, cheapness, atm_iv,
                 min_oi, max_leg_spread_pct, avg_theta, avg_vega,
                 qualified, reject_reason, dual_signal, created_at)
            VALUES (:scan_date,:symbol,:earnings_date,:days_to_earnings,:spot,
                    :strike,:expiry,:straddle_cost,:implied_move_pct,
                    :hist_median_move_pct,:hist_events,:cheapness,:atm_iv,
                    :min_oi,:max_leg_spread_pct,:avg_theta,:avg_vega,
                    :qualified,:reject_reason,:dual_signal,:created_at)
            ON CONFLICT(scan_date, symbol) DO UPDATE SET
                earnings_date=excluded.earnings_date,
                days_to_earnings=excluded.days_to_earnings,
                spot=excluded.spot, strike=excluded.strike,
                expiry=excluded.expiry, straddle_cost=excluded.straddle_cost,
                implied_move_pct=excluded.implied_move_pct,
                hist_median_move_pct=excluded.hist_median_move_pct,
                hist_events=excluded.hist_events,
                cheapness=excluded.cheapness, atm_iv=excluded.atm_iv,
                min_oi=excluded.min_oi,
                max_leg_spread_pct=excluded.max_leg_spread_pct,
                avg_theta=excluded.avg_theta, avg_vega=excluded.avg_vega,
                qualified=excluded.qualified,
                reject_reason=excluded.reject_reason,
                dual_signal=excluded.dual_signal
            """, row)
        conn.commit()
    finally:
        conn.close()


def latest_candidates() -> list[dict[str, Any]]:
    ensure_tables()
    conn = get_connection()
    try:
        d = conn.execute(
            "SELECT MAX(scan_date) AS d FROM options_candidates").fetchone()
        scan_date = d["d"] if d else None
        if not scan_date:
            return []
        rows = conn.execute(
            "SELECT * FROM options_candidates WHERE scan_date=? "
            "ORDER BY qualified DESC, cheapness ASC", (scan_date,)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_candidate(candidate_id: int) -> Optional[dict[str, Any]]:
    ensure_tables()
    conn = get_connection()
    try:
        r = conn.execute("SELECT * FROM options_candidates WHERE id=?",
                         (candidate_id,)).fetchone()
        return dict(r) if r else None
    finally:
        conn.close()


def save_iv_snapshot(symbol: str, snap_date: str, expiry: str,
                     atm_iv: Optional[float], implied_move: Optional[float]) -> None:
    ensure_tables()
    conn = get_connection()
    try:
        conn.execute(
            "INSERT OR REPLACE INTO options_iv_history VALUES (?,?,?,?,?)",
            (symbol.upper(), snap_date, expiry, atm_iv, implied_move))
        conn.commit()
    finally:
        conn.close()


# ---- positions ------------------------------------------------------------ #

def insert_position(row: dict[str, Any]) -> int:
    ensure_tables()
    conn = get_connection()
    try:
        cur = conn.execute("""
            INSERT INTO options_positions
                (symbol, status, contracts, strike, expiry, earnings_date,
                 exit_deadline, entry_date, entry_spot, entry_cost, entry_iv,
                 entry_theta, entry_vega, current_value, current_spot,
                 pnl_usd, pnl_pct, notes, created_at)
            VALUES (:symbol,'open',:contracts,:strike,:expiry,:earnings_date,
                    :exit_deadline,:entry_date,:entry_spot,:entry_cost,
                    :entry_iv,:entry_theta,:entry_vega,:entry_cost,
                    :entry_spot,0,0,:notes,:created_at)
            """, row)
        conn.commit()
        return int(cur.lastrowid)
    finally:
        conn.close()


def list_positions(status: Optional[str] = None, limit: int = 200) -> list[dict[str, Any]]:
    ensure_tables()
    conn = get_connection()
    try:
        if status:
            rows = conn.execute(
                "SELECT * FROM options_positions WHERE status=? "
                "ORDER BY id DESC LIMIT ?", (status, limit)).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM options_positions ORDER BY id DESC LIMIT ?",
                (limit,)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_position(position_id: int) -> Optional[dict[str, Any]]:
    ensure_tables()
    conn = get_connection()
    try:
        r = conn.execute("SELECT * FROM options_positions WHERE id=?",
                         (position_id,)).fetchone()
        return dict(r) if r else None
    finally:
        conn.close()


def update_position(position_id: int, fields: dict[str, Any]) -> None:
    if not fields:
        return
    ensure_tables()
    conn = get_connection()
    try:
        sets = ", ".join(f"{k}=?" for k in fields)
        conn.execute(f"UPDATE options_positions SET {sets} WHERE id=?",
                     (*fields.values(), position_id))
        conn.commit()
    finally:
        conn.close()


def stats() -> dict[str, Any]:
    """Running paper record across closed positions."""
    ensure_tables()
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT final_pnl_usd, final_pnl_pct FROM options_positions "
            "WHERE status='closed'").fetchall()
    finally:
        conn.close()
    pnls = [r["final_pnl_usd"] or 0.0 for r in rows]
    pcts = [r["final_pnl_pct"] for r in rows if r["final_pnl_pct"] is not None]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]
    return {
        "trades": len(pnls),
        "win_rate_pct": round(len(wins) / len(pnls) * 100) if pnls else None,
        "total_pnl_usd": round(sum(pnls), 2),
        "avg_win_pct": round(sum(p for p in pcts if p > 0) /
                             max(1, len([p for p in pcts if p > 0])), 1) if pcts else None,
        "avg_loss_pct": round(sum(p for p in pcts if p <= 0) /
                              max(1, len([p for p in pcts if p <= 0])), 1) if pcts else None,
    }
