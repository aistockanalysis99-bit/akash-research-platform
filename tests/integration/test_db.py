"""Integration test for SQLite persistence."""
from __future__ import annotations

import os
import tempfile
from datetime import datetime, timezone

import pandas as pd

from engine.core.event_loop import run_backtest
from engine.core.types import BacktestConfig, StrategyParams
from engine.db import repo
from engine.db.schema import init_db


def test_save_and_load_run(synthetic_uptrend_df, tmp_path, monkeypatch):
    monkeypatch.setattr(repo, "DB_PATH", tmp_path / "t.sqlite", raising=False)
    # Patch via the schema module too
    from engine.db import schema as schema_mod
    monkeypatch.setattr(schema_mod, "DB_PATH", tmp_path / "t.sqlite", raising=False)
    init_db(tmp_path / "t.sqlite")

    panel = {"UP": synthetic_uptrend_df}
    df = synthetic_uptrend_df
    config = BacktestConfig(
        universe=["UP"],
        start_date=df["timestamp"].iloc[0].to_pydatetime(),
        end_date=df["timestamp"].iloc[-1].to_pydatetime(),
        timeframe="1D",
        initial_capital=100_000,
        params=StrategyParams(),
        universe_name="test",
    )

    result = run_backtest(panel, config)

    repo.insert_run_pending(result.run_id, result.run_name, config)
    repo.save_run_result(result)

    fetched = repo.get_run(result.run_id)
    assert fetched is not None
    assert fetched["status"] == "done"
    assert fetched["metrics"].get("trades.total_trades", 0) == len(result.trades)

    eq = repo.get_equity_curve(result.run_id)
    assert len(eq) == len(result.equity_curve)

    trades = repo.get_trades(result.run_id)
    assert len(trades) == len(result.trades)


def test_parameter_set_save_load(tmp_path, monkeypatch):
    from engine.db import schema as schema_mod
    monkeypatch.setattr(schema_mod, "DB_PATH", tmp_path / "p.sqlite", raising=False)
    init_db(tmp_path / "p.sqlite")

    p = StrategyParams(stop_atr=3.5, trail_atr=4.0)
    repo.save_parameter_set("custom_test", p)
    loaded = repo.get_parameter_set("custom_test")
    assert loaded is not None
    assert loaded.stop_atr == 3.5
    assert loaded.trail_atr == 4.0
