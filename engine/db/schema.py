"""SQLite schema and migration. Single-call init creates everything."""
from __future__ import annotations

import sqlite3
from pathlib import Path

from ..config import DB_PATH

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS parameter_sets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    params_json TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY,
    name TEXT,
    params_json TEXT NOT NULL,
    start_date TEXT NOT NULL,
    end_date TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    universe TEXT NOT NULL,
    universe_name TEXT,
    initial_capital REAL NOT NULL,
    status TEXT NOT NULL,
    started_at TIMESTAMP NOT NULL,
    finished_at TIMESTAMP,
    error_message TEXT,
    metrics_json TEXT,
    progress REAL DEFAULT 0.0,
    progress_msg TEXT
);

CREATE TABLE IF NOT EXISTS equity_curve (
    run_id TEXT NOT NULL,
    timestamp TIMESTAMP NOT NULL,
    equity REAL NOT NULL,
    cash REAL NOT NULL,
    gross_exposure REAL NOT NULL,
    open_positions INTEGER NOT NULL,
    PRIMARY KEY (run_id, timestamp),
    FOREIGN KEY (run_id) REFERENCES runs(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    entry_time TIMESTAMP NOT NULL,
    exit_time TIMESTAMP NOT NULL,
    entry_price REAL NOT NULL,
    exit_price REAL NOT NULL,
    qty REAL NOT NULL,
    pnl REAL NOT NULL,
    pnl_pct REAL NOT NULL,
    exit_reason TEXT NOT NULL,
    bars_held INTEGER NOT NULL,
    mae REAL,
    mfe REAL,
    commission_total REAL,
    FOREIGN KEY (run_id) REFERENCES runs(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS per_symbol_stats (
    run_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    trades INTEGER NOT NULL,
    wins INTEGER NOT NULL,
    win_rate REAL NOT NULL,
    total_pnl REAL NOT NULL,
    avg_pnl REAL NOT NULL,
    best_trade REAL NOT NULL,
    worst_trade REAL NOT NULL,
    PRIMARY KEY (run_id, symbol),
    FOREIGN KEY (run_id) REFERENCES runs(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_trades_run ON trades(run_id);
CREATE INDEX IF NOT EXISTS idx_trades_run_symbol ON trades(run_id, symbol);
CREATE INDEX IF NOT EXISTS idx_equity_run ON equity_curve(run_id);
CREATE INDEX IF NOT EXISTS idx_runs_started ON runs(started_at DESC);

-- ===== Phase 3: Virtual Portfolio =====

CREATE TABLE IF NOT EXISTS virtual_positions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    -- entry
    entry_date TEXT NOT NULL,
    entry_price REAL NOT NULL,
    units REAL NOT NULL,
    initial_stop REAL NOT NULL,
    -- current state
    current_price REAL,
    high_water_mark REAL,
    trailing_stop REAL,
    current_pnl_pct REAL,
    current_pnl_usd REAL,
    last_updated TEXT,
    -- lifecycle
    status TEXT NOT NULL DEFAULT 'open',  -- 'open' | 'closed'
    days_held INTEGER NOT NULL DEFAULT 0,
    -- exit (null while open)
    exit_date TEXT,
    exit_price REAL,
    exit_reason TEXT,
    final_pnl_usd REAL,
    final_pnl_pct REAL,
    -- link back to the AI decision that created this paper trade
    decision_symbol TEXT,
    decision_date TEXT,
    decision_verdict TEXT,
    decision_conviction INTEGER,
    decision_size_pct INTEGER,
    -- audit
    created_at TEXT NOT NULL,
    notes TEXT
);

CREATE INDEX IF NOT EXISTS idx_vp_symbol      ON virtual_positions(symbol);
CREATE INDEX IF NOT EXISTS idx_vp_status      ON virtual_positions(status);
CREATE INDEX IF NOT EXISTS idx_vp_entry_date  ON virtual_positions(entry_date);
CREATE INDEX IF NOT EXISTS idx_vp_decision    ON virtual_positions(decision_symbol, decision_date);

-- ===== Phase 4: Watchlist (symbols the evening scheduler runs through) =====

CREATE TABLE IF NOT EXISTS watchlist (
    symbol TEXT PRIMARY KEY,
    added_at TEXT NOT NULL,
    notes TEXT,
    enabled INTEGER NOT NULL DEFAULT 1
);

-- ===== Phase 4: Telegram outbound log =====

CREATE TABLE IF NOT EXISTS telegram_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sent_at TEXT NOT NULL,
    kind TEXT NOT NULL,           -- 'pm_verdict' | 'morning_briefing' | 'manual' | 'error'
    symbol TEXT,                  -- nullable for non-symbol messages
    text TEXT NOT NULL,
    success INTEGER NOT NULL,
    error TEXT
);

CREATE INDEX IF NOT EXISTS idx_telegram_sent ON telegram_log(sent_at DESC);

-- ===== Phase 4: Runtime settings (overrides for env defaults) =====

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- ===== Phase 4: AI memory — lessons from closed positions =====

CREATE TABLE IF NOT EXISTS lessons (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    lesson_text TEXT NOT NULL,
    created_at TEXT NOT NULL,
    position_id INTEGER,
    outcome_pnl_pct REAL,
    days_held INTEGER,
    exit_reason TEXT,
    -- A short category the Reflector picks, used for filtering injected lessons
    category TEXT
);

CREATE INDEX IF NOT EXISTS idx_lessons_symbol  ON lessons(symbol);
CREATE INDEX IF NOT EXISTS idx_lessons_created ON lessons(created_at DESC);

-- ===== Phase 4: Job persistence — AI Analysis + Morning jobs survive restart =====

CREATE TABLE IF NOT EXISTS ai_jobs (
    job_id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,           -- 'analyze' | 'morning' | 'weekly'
    symbol TEXT,                  -- analyze only; null for morning/weekly
    status TEXT NOT NULL,         -- 'queued' | 'running' | 'complete' | 'failed'
    started_at TEXT NOT NULL,
    completed_at TEXT,
    state_json TEXT NOT NULL      -- full job dict serialized
);

CREATE INDEX IF NOT EXISTS idx_ai_jobs_started ON ai_jobs(started_at DESC);
CREATE INDEX IF NOT EXISTS idx_ai_jobs_kind    ON ai_jobs(kind, started_at DESC);

-- Daily snapshot of the paper portfolio's value — powers the value-over-time
-- chart. One row per calendar date (latest snapshot of the day wins).
CREATE TABLE IF NOT EXISTS portfolio_equity_history (
    snapshot_date  TEXT PRIMARY KEY,   -- YYYY-MM-DD
    equity         REAL NOT NULL,
    cash           REAL NOT NULL,
    market_value   REAL NOT NULL,
    realized_pnl   REAL NOT NULL,
    unrealized_pnl REAL NOT NULL,
    open_positions INTEGER NOT NULL,
    updated_at     TEXT NOT NULL
);

-- ===== Strategy 4 Alpaca auto-trade foundation (Phase 1) =====

CREATE TABLE IF NOT EXISTS telegram_authorized_chats (
    chat_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    username TEXT,
    first_name TEXT,
    authorized_at TEXT NOT NULL,
    revoked_at TEXT,
    active INTEGER NOT NULL DEFAULT 1
);

CREATE INDEX IF NOT EXISTS idx_tg_authorized_active
    ON telegram_authorized_chats(active, authorized_at);

CREATE TABLE IF NOT EXISTS telegram_auth_sessions (
    chat_id TEXT PRIMARY KEY,
    awaiting_passcode INTEGER NOT NULL DEFAULT 0,
    locked_until TEXT,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS telegram_auth_attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id TEXT NOT NULL,
    user_id TEXT,
    attempted_at TEXT NOT NULL,
    success INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_tg_auth_attempts_chat_time
    ON telegram_auth_attempts(chat_id, attempted_at DESC);

CREATE TABLE IF NOT EXISTS telegram_bot_state (
    singleton_id INTEGER PRIMARY KEY CHECK (singleton_id = 1),
    last_update_id INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS auto_trade_runs (
    run_id TEXT PRIMARY KEY,
    run_type TEXT NOT NULL,
    session_date TEXT,
    status TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    config_hash TEXT,
    summary_json TEXT,
    error_code TEXT,
    error_message TEXT
);

CREATE INDEX IF NOT EXISTS idx_auto_trade_runs_started
    ON auto_trade_runs(started_at DESC);

CREATE TABLE IF NOT EXISTS strategy_v4_signal_snapshots (
    signal_id TEXT PRIMARY KEY,
    run_id TEXT,
    session_date TEXT NOT NULL,
    ticker_a TEXT NOT NULL,
    ticker_b TEXT NOT NULL,
    decision TEXT NOT NULL,
    rejection_reason TEXT,
    data_cutoff_at TEXT NOT NULL,
    config_version TEXT NOT NULL,
    config_hash TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (run_id) REFERENCES auto_trade_runs(run_id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_v4_signals_session
    ON strategy_v4_signal_snapshots(session_date, decision);

CREATE TABLE IF NOT EXISTS pair_trade_intents (
    pair_trade_id TEXT PRIMARY KEY,
    signal_id TEXT,
    session_date TEXT NOT NULL,
    ticker_a TEXT NOT NULL,
    ticker_b TEXT NOT NULL,
    state TEXT NOT NULL,
    target_z REAL,
    stop_z REAL,
    max_holding_date TEXT,
    idempotency_key TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    closed_at TEXT,
    error_code TEXT,
    error_message TEXT,
    exit_reason TEXT,
    current_z REAL,
    unrealized_pnl REAL,
    realized_pnl REAL,
    reconciled_at TEXT,
    FOREIGN KEY (signal_id) REFERENCES strategy_v4_signal_snapshots(signal_id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_pair_trade_state
    ON pair_trade_intents(state, session_date);

CREATE TABLE IF NOT EXISTS pair_trade_legs (
    leg_id TEXT PRIMARY KEY,
    pair_trade_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL,
    target_qty REAL NOT NULL,
    filled_qty REAL NOT NULL DEFAULT 0,
    avg_fill_price REAL,
    state TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(pair_trade_id, symbol),
    FOREIGN KEY (pair_trade_id) REFERENCES pair_trade_intents(pair_trade_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS broker_orders (
    broker_order_id TEXT PRIMARY KEY,
    client_order_id TEXT NOT NULL UNIQUE,
    pair_trade_id TEXT,
    leg_id TEXT,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL,
    order_type TEXT NOT NULL,
    time_in_force TEXT NOT NULL,
    status TEXT NOT NULL,
    qty REAL,
    filled_qty REAL,
    filled_avg_price REAL,
    submitted_at TEXT,
    updated_at TEXT NOT NULL,
    raw_json TEXT NOT NULL,
    FOREIGN KEY (pair_trade_id) REFERENCES pair_trade_intents(pair_trade_id) ON DELETE SET NULL,
    FOREIGN KEY (leg_id) REFERENCES pair_trade_legs(leg_id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_broker_orders_pair
    ON broker_orders(pair_trade_id, status);

CREATE TABLE IF NOT EXISTS broker_order_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    broker_order_id TEXT,
    event_type TEXT NOT NULL,
    event_at TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    dedupe_key TEXT NOT NULL UNIQUE,
    FOREIGN KEY (broker_order_id) REFERENCES broker_orders(broker_order_id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS notification_outbox (
    notification_id TEXT PRIMARY KEY,
    idempotency_key TEXT NOT NULL UNIQUE,
    kind TEXT NOT NULL,
    pair_trade_id TEXT,
    payload_text TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    attempts INTEGER NOT NULL DEFAULT 0,
    next_attempt_at TEXT,
    created_at TEXT NOT NULL,
    sent_at TEXT,
    last_error TEXT,
    FOREIGN KEY (pair_trade_id) REFERENCES pair_trade_intents(pair_trade_id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_notification_outbox_status
    ON notification_outbox(status, next_attempt_at);

CREATE TABLE IF NOT EXISTS auto_trade_control (
    singleton_id INTEGER PRIMARY KEY CHECK (singleton_id = 1),
    armed INTEGER NOT NULL DEFAULT 0,
    kill_switch INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL,
    updated_by TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS auto_trade_control_audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    action TEXT NOT NULL,
    actor TEXT NOT NULL,
    created_at TEXT NOT NULL,
    details_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS auto_trade_job_runs (
    name TEXT NOT NULL,
    slot TEXT NOT NULL,
    status TEXT NOT NULL,
    started_at TEXT NOT NULL,
    lease_until TEXT NOT NULL,
    finished_at TEXT,
    error_type TEXT,
    PRIMARY KEY(name, slot)
);

CREATE INDEX IF NOT EXISTS idx_auto_trade_job_runs_started
    ON auto_trade_job_runs(started_at DESC);

CREATE TABLE IF NOT EXISTS automation_locks (
    lock_name TEXT PRIMARY KEY,
    owner_id TEXT NOT NULL,
    acquired_at TEXT NOT NULL,
    expires_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS automation_heartbeats (
    component TEXT PRIMARY KEY,
    instance_id TEXT NOT NULL,
    status TEXT NOT NULL,
    heartbeat_at TEXT NOT NULL,
    details_json TEXT
);

CREATE TABLE IF NOT EXISTS alpaca_account_snapshots (
    snapshot_id TEXT PRIMARY KEY,
    captured_at TEXT NOT NULL,
    equity REAL NOT NULL,
    cash REAL NOT NULL,
    buying_power REAL NOT NULL,
    portfolio_value REAL NOT NULL,
    long_market_value REAL,
    short_market_value REAL,
    payload_json TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_alpaca_snapshots_captured
    ON alpaca_account_snapshots(captured_at DESC);
"""

# Idempotent column migrations for tables that predate a feature.
_MIGRATIONS = [
    ("pair_trade_intents", "exit_reason", "TEXT"),
    ("pair_trade_intents", "current_z", "REAL"),
    ("pair_trade_intents", "unrealized_pnl", "REAL"),
    ("pair_trade_intents", "realized_pnl", "REAL"),
    ("pair_trade_intents", "reconciled_at", "TEXT"),
    ("virtual_positions", "prev_close", "REAL"),
    ("virtual_positions", "day_change_pct", "REAL"),
    # Options support: instrument_type 'stock'|'option'; option-specific fields.
    # For stocks multiplier=1; for options multiplier=100 and units=contracts,
    # entry_price/current_price = premium per share.
    ("virtual_positions", "instrument_type", "TEXT DEFAULT 'stock'"),
    ("virtual_positions", "option_type", "TEXT"),          # 'call' | 'put'
    ("virtual_positions", "strike", "REAL"),
    ("virtual_positions", "expiry", "TEXT"),               # YYYY-MM-DD
    ("virtual_positions", "multiplier", "REAL DEFAULT 1"),
    # Stop-alert de-dupe: the date we last notified that this position breached
    # its trailing stop. The system NEVER auto-closes — it only notifies.
    ("virtual_positions", "stop_alerted_on", "TEXT"),
    # AI-managed risk: the per-stock stop the AI set (overrides the flat
    # trailing stop for breach alerts), refreshed by the daily lifecycle review.
    ("virtual_positions", "ai_stop_price", "REAL"),
    ("virtual_positions", "ai_stop_rationale", "TEXT"),
]


def get_connection(db_path: Path | str | None = None) -> sqlite3.Connection:
    """Open a connection to the SQLite DB. Foreign keys enabled."""
    path = Path(db_path) if db_path else DB_PATH
    # detect_types is intentionally OFF: we store ISO-8601 strings and parse on read.
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def init_db(db_path: Path | str | None = None) -> None:
    """Create tables if missing, then apply idempotent column migrations."""
    conn = get_connection(db_path)
    try:
        conn.executescript(SCHEMA_SQL)
        conn.commit()
        # Add any missing columns (safe to run repeatedly).
        for table, col, coltype in _MIGRATIONS:
            existing = {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
            if col not in existing:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {coltype}")
        conn.commit()
    finally:
        conn.close()
