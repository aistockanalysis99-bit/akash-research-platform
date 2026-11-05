from __future__ import annotations

import sqlite3

from engine.db.schema import init_db
from engine.live.auto_trade_readiness import REQUIRED_TABLES


def test_phase1_schema_is_idempotent_and_round_trips(tmp_path) -> None:
    db = tmp_path / "phase1.sqlite"
    init_db(db)
    init_db(db)
    conn = sqlite3.connect(db)
    try:
        tables = {row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        assert set(REQUIRED_TABLES) <= tables
        conn.execute(
            "INSERT INTO auto_trade_runs "
            "(run_id, run_type, status, started_at) VALUES ('r1', 'readiness', 'complete', 'now')"
        )
        conn.execute(
            "INSERT INTO automation_heartbeats "
            "(component, instance_id, status, heartbeat_at) VALUES ('api', 'i1', 'ok', 'now')"
        )
        conn.commit()
        assert conn.execute("SELECT COUNT(*) FROM auto_trade_runs").fetchone()[0] == 1
        assert conn.execute("SELECT status FROM automation_heartbeats").fetchone()[0] == "ok"
    finally:
        conn.close()

