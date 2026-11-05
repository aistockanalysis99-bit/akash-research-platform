from datetime import datetime, timezone
from types import SimpleNamespace

from engine.db import schema
from engine.live import auto_trade_phase4 as phase4


def test_job_slot_is_claimed_once_across_connections(tmp_path, monkeypatch):
    path = tmp_path / "phase4.db"
    schema.init_db(path)
    monkeypatch.setattr(phase4, "get_connection", lambda: schema.get_connection(path))
    assert phase4.claim_job("scan", "2026-11-05")
    assert not phase4.claim_job("scan", "2026-11-05")
    phase4.finish_job("scan", "2026-11-05")
    assert not phase4.claim_job("scan", "2026-11-05")


def test_account_report_uses_broker_values_and_marks_manual_position(monkeypatch):
    monkeypatch.setattr(phase4, "list_pairs", lambda: [])
    broker = SimpleNamespace(
        get_account=lambda: SimpleNamespace(equity=100000, cash=90000, buying_power=180000),
        list_positions=lambda: SimpleNamespace(items=({
            "symbol": "AAA", "side": "long", "qty": "10", "avg_entry_price": "100",
            "current_price": "105", "market_value": "1050", "unrealized_pl": "50",
        },)),
        list_orders=lambda status: SimpleNamespace(items=()),
    )
    report = phase4.account_report(broker)
    assert "Equity: $100,000.00" in report
    assert "AAA (unmatched/manual): long 10" in report
    assert "P&L $+50.00" in report
    assert phase4.report_slot(datetime(2026, 11, 4, 19, tzinfo=timezone.utc)) == "2026-11-05"
