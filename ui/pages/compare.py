"""Compare page: side-by-side runs with overlaid equity curves."""
from __future__ import annotations

from nicegui import ui

from ..api_client import api
from ..charts import equity_overlay
from .layout import page_header


def render_compare(run_ids: list[str]) -> None:
    page_header(active="Compare")

    with ui.column().classes("w-full max-w-7xl mx-auto p-4 gap-4"):
        ui.label("Compare Runs").classes("text-2xl font-bold")

        if not run_ids or len(run_ids) < 2:
            ui.label("Select 2+ runs from Run History to compare.").classes("text-gray-400")
            return

        try:
            data = api.compare(run_ids[:5])
        except Exception as e:
            ui.label(f"Compare failed: {e}").classes("text-red-500")
            return

        runs = data.get("runs", [])
        ui.label(f"Comparing {len(runs)} runs").classes("text-sm text-gray-400")

        # Overlaid equity
        ui.plotly(equity_overlay(runs)).classes("w-full")

        # Metric comparison table
        if runs:
            metric_keys = [
                ("cagr", "CAGR %", lambda v: f"{v*100:+.2f}%"),
                ("sharpe", "Sharpe", lambda v: f"{v:.2f}"),
                ("sortino", "Sortino", lambda v: f"{v:.2f}"),
                ("max_drawdown", "Max DD %", lambda v: f"{v*100:.2f}%"),
                ("annualized_vol", "Vol %", lambda v: f"{v*100:.2f}%"),
                ("mar", "MAR", lambda v: f"{v:.2f}"),
                ("trades.total_trades", "Trades", lambda v: f"{int(v)}"),
                ("trades.win_rate", "Win %", lambda v: f"{v*100:.1f}%"),
                ("trades.profit_factor", "Profit Factor", lambda v: f"{v:.2f}"),
                ("trades.avg_trade", "Avg Trade $", lambda v: f"{v:,.2f}"),
                ("total_commission", "Commissions $", lambda v: f"{v:,.2f}"),
            ]

            cols = [{"name": "metric", "label": "Metric", "field": "metric", "align": "left"}]
            for r in runs:
                short_name = (r.get("name") or r["run_id"])[-26:]
                cols.append({"name": r["run_id"], "label": short_name, "field": r["run_id"]})
            rows = []
            for key, label, fmt in metric_keys:
                row = {"metric": label}
                for r in runs:
                    v = (r.get("metrics") or {}).get(key, 0) or 0
                    try:
                        row[r["run_id"]] = fmt(v)
                    except Exception:
                        row[r["run_id"]] = str(v)
                rows.append(row)
            ui.table(columns=cols, rows=rows, row_key="metric").classes("w-full")
