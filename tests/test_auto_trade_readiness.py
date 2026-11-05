from __future__ import annotations

import json

from api.main import app
from engine.db import schema
from engine.live.auto_trade_readiness import readiness_snapshot


def test_redacted_readiness_and_phase3_routes(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(schema, "DB_PATH", tmp_path / "readiness.sqlite")
    schema.init_db()
    snapshot = readiness_snapshot()
    assert snapshot["phase"] == 3
    assert snapshot["trade_submission_available"] is False
    assert snapshot["database"]["ready"] is True

    serialized = json.dumps(snapshot)
    # Readiness reports presence booleans, never credential/passcode values.
    assert "TELEGRAM_AUTH_PASSCODE=1234" not in serialized
    assert "ALPACA_SECRET_KEY=" not in serialized

    paths = {route.path for route in app.routes if hasattr(route, "path")}
    assert "/auto-trade/readiness" in paths
    assert "/auto-trade/readiness/alpaca" in paths
    assert "/auto-trade/readiness/telegram" in paths
    assert "/auto-trade/pairs/{pair_trade_id}/submit" in paths
    assert "/auto-trade/kill-switch" in paths
