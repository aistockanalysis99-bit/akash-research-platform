"""Persistence layer: save/load runs, trades, equity, parameter sets."""
from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict
from datetime import datetime
from typing import Any, Optional

from ..core.types import (
    BacktestConfig,
    BacktestResult,
    EquityPoint,
    RunStatus,
    StrategyParams,
    Trade,
)
from .schema import get_connection, init_db


# ----------------------- Helpers -----------------------

def _params_to_dict(p: StrategyParams) -> dict[str, Any]:
    return asdict(p)


def _dict_to_params(d: dict[str, Any]) -> StrategyParams:
    valid = {k: v for k, v in d.items() if k in StrategyParams.__dataclass_fields__}
    return StrategyParams(**valid)


def _config_to_json(cfg: BacktestConfig) -> str:
    return json.dumps({
        "universe": cfg.universe,
        "universe_name": cfg.universe_name,
        "start_date": cfg.start_date.isoformat(),
        "end_date": cfg.end_date.isoformat(),
        "timeframe": cfg.timeframe,
        "initial_capital": cfg.initial_capital,
        "params": _params_to_dict(cfg.params),
        "run_name": cfg.run_name,
    })


def _json_to_config(s: str) -> BacktestConfig:
    d = json.loads(s)
    return BacktestConfig(
        universe=d["universe"],
        start_date=datetime.fromisoformat(d["start_date"]),
        end_date=datetime.fromisoformat(d["end_date"]),
        timeframe=d["timeframe"],
        initial_capital=d.get("initial_capital", 100_000.0),
        params=_dict_to_params(d["params"]),
        run_name=d.get("run_name"),
        universe_name=d.get("universe_name", "custom"),
    )


# ----------------------- Runs -----------------------

def insert_run_pending(run_id: str, run_name: str, config: BacktestConfig) -> None:
    init_db()
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO runs (id, name, params_json, start_date, end_date, timeframe, universe,
                              universe_name, initial_capital, status, started_at, progress, progress_msg)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0.0, 'queued')
            """,
            (
                run_id,
                run_name,
                _config_to_json(config),
                config.start_date.date().isoformat(),
                config.end_date.date().isoformat(),
                config.timeframe,
                json.dumps(config.universe),
                config.universe_name,
                config.initial_capital,
                RunStatus.RUNNING.value,
                datetime.utcnow().isoformat(),
            ),
        )
        conn.commit()


def update_run_progress(run_id: str, progress: float, msg: str = "") -> None:
    with get_connection() as conn:
        conn.execute(
            "UPDATE runs SET progress = ?, progress_msg = ? WHERE id = ?",
            (progress, msg, run_id),
        )
        conn.commit()


def save_run_result(result: BacktestResult) -> None:
    init_db()
    with get_connection() as conn:
        # Update runs row
        conn.execute(
            """
            UPDATE runs SET
                status = ?, finished_at = ?, error_message = ?,
                metrics_json = ?, progress = 1.0, progress_msg = 'done'
            WHERE id = ?
            """,
            (
                result.status.value,
                result.finished_at.isoformat(),
                result.error_message,
                json.dumps(result.metrics),
                result.run_id,
            ),
        )

        # Equity curve
        conn.executemany(
            """
            INSERT OR REPLACE INTO equity_curve (run_id, timestamp, equity, cash, gross_exposure, open_positions)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                (result.run_id, ep.timestamp.isoformat(), ep.equity, ep.cash, ep.gross_exposure, ep.open_positions)
                for ep in result.equity_curve
            ],
        )

        # Trades
        conn.executemany(
            """
            INSERT INTO trades (run_id, symbol, entry_time, exit_time, entry_price, exit_price,
                                qty, pnl, pnl_pct, exit_reason, bars_held, mae, mfe, commission_total)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    result.run_id, t.symbol, t.entry_time.isoformat(), t.exit_time.isoformat(),
                    t.entry_price, t.exit_price, t.qty, t.pnl, t.pnl_pct,
                    t.exit_reason.value, t.bars_held, t.mae, t.mfe, t.commission_total,
                )
                for t in result.trades
            ],
        )

        # Per-symbol stats
        conn.executemany(
            """
            INSERT OR REPLACE INTO per_symbol_stats
                (run_id, symbol, trades, wins, win_rate, total_pnl, avg_pnl, best_trade, worst_trade)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    result.run_id, d["symbol"], d["trades"], d["wins"], d["win_rate"],
                    d["total_pnl"], d["avg_pnl"], d["best_trade"], d["worst_trade"],
                )
                for d in result.per_symbol_stats
            ],
        )
        conn.commit()


def fail_run(run_id: str, error: str) -> None:
    with get_connection() as conn:
        conn.execute(
            "UPDATE runs SET status = ?, error_message = ?, finished_at = ?, progress_msg = 'failed' WHERE id = ?",
            (RunStatus.FAILED.value, error, datetime.utcnow().isoformat(), run_id),
        )
        conn.commit()


def get_run(run_id: str) -> Optional[dict[str, Any]]:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
        if not row:
            return None
        return _row_to_run_dict(row)


def list_runs(limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM runs ORDER BY started_at DESC LIMIT ? OFFSET ?",
            (limit, offset),
        ).fetchall()
        return [_row_to_run_dict(r) for r in rows]


def delete_run(run_id: str) -> bool:
    with get_connection() as conn:
        cur = conn.execute("DELETE FROM runs WHERE id = ?", (run_id,))
        conn.commit()
        return cur.rowcount > 0


def _row_to_run_dict(row: sqlite3.Row) -> dict[str, Any]:
    d = dict(row)
    if d.get("metrics_json"):
        try:
            d["metrics"] = json.loads(d["metrics_json"])
        except Exception:
            d["metrics"] = {}
    else:
        d["metrics"] = {}
    if d.get("universe"):
        try:
            d["universe_list"] = json.loads(d["universe"])
        except Exception:
            d["universe_list"] = []
    return d


# ----------------------- Equity / Trades / Per-symbol -----------------------

def get_equity_curve(run_id: str) -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT timestamp, equity, cash, gross_exposure, open_positions FROM equity_curve "
            "WHERE run_id = ? ORDER BY timestamp",
            (run_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def get_trades(
    run_id: str,
    symbol: Optional[str] = None,
    exit_reason: Optional[str] = None,
    limit: int = 5000,
    offset: int = 0,
) -> list[dict[str, Any]]:
    sql = "SELECT * FROM trades WHERE run_id = ?"
    args: list[Any] = [run_id]
    if symbol:
        sql += " AND symbol = ?"
        args.append(symbol)
    if exit_reason:
        sql += " AND exit_reason = ?"
        args.append(exit_reason)
    sql += " ORDER BY entry_time LIMIT ? OFFSET ?"
    args += [limit, offset]
    with get_connection() as conn:
        rows = conn.execute(sql, args).fetchall()
        return [dict(r) for r in rows]


def get_per_symbol_stats(run_id: str) -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM per_symbol_stats WHERE run_id = ? ORDER BY total_pnl DESC",
            (run_id,),
        ).fetchall()
        return [dict(r) for r in rows]


# ----------------------- Parameter Sets -----------------------

def save_parameter_set(name: str, params: StrategyParams) -> None:
    init_db()
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO parameter_sets (name, params_json, created_at)
            VALUES (?, ?, ?)
            ON CONFLICT(name) DO UPDATE SET params_json = excluded.params_json
            """,
            (name, json.dumps(_params_to_dict(params)), datetime.utcnow().isoformat()),
        )
        conn.commit()


def list_parameter_sets() -> list[dict[str, Any]]:
    init_db()
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT id, name, params_json, created_at FROM parameter_sets ORDER BY name"
        ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            try:
                d["params"] = json.loads(d["params_json"])
            except Exception:
                d["params"] = {}
            out.append(d)
        return out


def get_parameter_set(name: str) -> Optional[StrategyParams]:
    init_db()
    with get_connection() as conn:
        row = conn.execute(
            "SELECT params_json FROM parameter_sets WHERE name = ?", (name,)
        ).fetchone()
        if not row:
            return None
        return _dict_to_params(json.loads(row["params_json"]))


def delete_parameter_set(name: str) -> bool:
    with get_connection() as conn:
        cur = conn.execute("DELETE FROM parameter_sets WHERE name = ?", (name,))
        conn.commit()
        return cur.rowcount > 0
