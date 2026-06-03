"""Run detail page: live progress while running, full results when done."""
from __future__ import annotations

from nicegui import ui

from ..api_client import api
from ..charts import (
    bars_held_histogram,
    equity_with_drawdown,
    exit_reason_pie,
    mae_mfe_scatter,
    monthly_heatmap,
    per_symbol_bar,
    rolling_12m_chart,
)
from ..theme import kpi_card, section_header
from .layout import page_header


def render_run_detail(run_id: str) -> None:
    page_header(active="Run History")

    container = ui.column().classes("w-full max-w-7xl mx-auto p-4 gap-4")

    with container:
        ui.label(f"Run: {run_id[:8]}…").classes("text-2xl font-bold")
        progress_label = ui.label("Loading...").classes("text-sm text-gray-400")
        progress_bar = ui.linear_progress(value=0.0, show_value=True).classes("w-full")

        results_container = ui.column().classes("w-full gap-4")

        state = {"polling": True, "rendered": False}

        def refresh():  # called periodically
            try:
                data = api.get_run(run_id)
            except Exception as e:
                progress_label.text = f"Error fetching run: {e}"
                return
            status = data.get("status", "")
            progress = float(data.get("progress", 0.0) or 0.0)
            msg = data.get("progress_msg") or ""
            progress_bar.value = progress
            progress_label.text = f"[{status}] {msg}  ({int(progress * 100)}%)"

            if status in ("done", "failed") and not state["rendered"]:
                state["polling"] = False
                state["rendered"] = True
                results_container.clear()
                if status == "failed":
                    with results_container:
                        ui.label("Backtest failed").classes("text-2xl text-red-500 font-bold")
                        ui.label(data.get("error_message", "")).classes("text-sm text-gray-400")
                    return
                _render_results(results_container, run_id, data)

        ui.timer(0.5, refresh)
        # Fire immediately so the page renders without a 1s wait
        refresh()


def _render_results(container, run_id: str, run: dict) -> None:
    metrics = run.get("metrics", {}) or {}
    eq = api.get_equity(run_id)
    trades = api.get_trades(run_id, limit=20000)
    per_sym = api.get_per_symbol(run_id)

    with container:
        # ---- KPI cards ----
        with ui.row().classes("w-full gap-2 flex-wrap"):
            kpi_card("Final Equity", f"${metrics.get('final_equity', 0):,.0f}", "primary")
            kpi_card("Total Return", f"{metrics.get('total_return', 0)*100:+.2f}%",
                     "positive" if metrics.get("total_return", 0) >= 0 else "negative")
            kpi_card("CAGR", f"{metrics.get('cagr', 0)*100:+.2f}%",
                     "positive" if metrics.get("cagr", 0) >= 0 else "negative")
            kpi_card("Sharpe", f"{metrics.get('sharpe', 0):.2f}", "primary")
            kpi_card("Sortino", f"{metrics.get('sortino', 0):.2f}", "primary")
            kpi_card("Max DD", f"{metrics.get('max_drawdown', 0)*100:.2f}%", "negative")
            kpi_card("MAR / Calmar", f"{metrics.get('mar', 0):.2f}", "primary")
            kpi_card("Annual Vol", f"{metrics.get('annualized_vol', 0)*100:.2f}%", "primary")
            kpi_card("# Trades", f"{metrics.get('trades.total_trades', 0)}", "primary")
            kpi_card("Win Rate", f"{metrics.get('trades.win_rate', 0)*100:.1f}%", "primary")
            kpi_card("Profit Factor", f"{metrics.get('trades.profit_factor', 0):.2f}", "primary")
            kpi_card("Avg Trade", f"${metrics.get('trades.avg_trade', 0):,.2f}", "primary")

        # ---- Tabs ----
        with ui.tabs().classes("w-full") as tabs:
            tab_summary = ui.tab("Summary")
            tab_equity = ui.tab("Equity & Drawdown")
            tab_returns = ui.tab("Returns")
            tab_trades = ui.tab("Trades")
            tab_per_sym = ui.tab("Per-Symbol")
            tab_diag = ui.tab("Diagnostics")
            tab_params = ui.tab("Parameters")

        with ui.tab_panels(tabs, value=tab_summary).classes("w-full"):

            # ---- Summary ----
            with ui.tab_panel(tab_summary):
                with ui.row().classes("w-full gap-3 flex-wrap"):
                    with ui.card().classes("flex-1 min-w-[280px]"):
                        section_header("Trade Stats")
                        ui.label(f"Winners: {metrics.get('trades.winners', 0)}")
                        ui.label(f"Losers: {metrics.get('trades.losers', 0)}")
                        ui.label(f"Avg Win: ${metrics.get('trades.avg_win', 0):,.2f}")
                        ui.label(f"Avg Loss: ${metrics.get('trades.avg_loss', 0):,.2f}")
                        ui.label(f"Largest Win: ${metrics.get('trades.largest_win', 0):,.2f}")
                        ui.label(f"Largest Loss: ${metrics.get('trades.largest_loss', 0):,.2f}")
                        ui.label(f"Avg Bars Held: {metrics.get('trades.avg_bars_held', 0):.1f}")
                        ui.label(f"Max Consec Wins: {metrics.get('trades.max_consec_winners', 0)}")
                        ui.label(f"Max Consec Losses: {metrics.get('trades.max_consec_losers', 0)}")
                        ui.label(f"Expectancy/trade: ${metrics.get('trades.expectancy', 0):,.2f}")
                    with ui.card().classes("flex-1 min-w-[280px]"):
                        section_header("Risk")
                        ui.label(f"Max Drawdown: {metrics.get('max_drawdown', 0)*100:.2f}%")
                        ui.label(f"DD Duration (days): {metrics.get('max_drawdown_duration_days', 0)}")
                        ui.label(f"Annualized Vol: {metrics.get('annualized_vol', 0)*100:.2f}%")
                        ui.label(f"Top-5 Trade Share: {metrics.get('concentration.top5_share', 0)*100:.1f}%")
                        ui.label(f"Top Symbol Share: {metrics.get('concentration.top1_symbol_share', 0)*100:.1f}%")
                    with ui.card().classes("flex-1 min-w-[280px]"):
                        section_header("Costs")
                        ui.label(f"Total Commission: ${metrics.get('total_commission', 0):,.2f}")
                        ui.label(f"Cost % of P&L: {metrics.get('cost_pct_of_pnl', 0)*100:.2f}%")

            # ---- Equity & Drawdown ----
            with ui.tab_panel(tab_equity):
                log_toggle = ui.switch("Log scale").classes("mb-2")
                fig = equity_with_drawdown(eq)
                plot = ui.plotly(fig).classes("w-full")
                def on_toggle():
                    plot.update_figure(equity_with_drawdown(eq, log_scale=log_toggle.value))
                log_toggle.on("update:model-value", lambda *_: on_toggle())

            # ---- Returns ----
            with ui.tab_panel(tab_returns):
                ui.plotly(monthly_heatmap(metrics.get("monthly_returns") or {})).classes("w-full")
                ui.plotly(rolling_12m_chart(metrics.get("rolling_12m_returns") or {})).classes("w-full")

            # ---- Trades ----
            with ui.tab_panel(tab_trades):
                ui.label(f"Showing {len(trades)} trades").classes("text-sm text-gray-400")
                ui.button("Download CSV",
                          on_click=lambda: ui.download(api.trades_csv_url(run_id))) \
                    .props("icon=download")
                if trades:
                    cols = [
                        {"name": "symbol", "label": "Symbol", "field": "symbol", "sortable": True, "align": "left"},
                        {"name": "entry_time", "label": "Entry", "field": "entry_time", "sortable": True},
                        {"name": "exit_time", "label": "Exit", "field": "exit_time", "sortable": True},
                        {"name": "entry_price", "label": "Entry $", "field": "entry_price", "sortable": True,
                         ":format": "v => Number(v).toFixed(2)"},
                        {"name": "exit_price", "label": "Exit $", "field": "exit_price", "sortable": True,
                         ":format": "v => Number(v).toFixed(2)"},
                        {"name": "qty", "label": "Qty", "field": "qty", "sortable": True},
                        {"name": "pnl", "label": "P&L $", "field": "pnl", "sortable": True,
                         ":format": "v => Number(v).toFixed(2)"},
                        {"name": "pnl_pct", "label": "P&L %", "field": "pnl_pct", "sortable": True,
                         ":format": "v => (Number(v)*100).toFixed(2) + '%'"},
                        {"name": "exit_reason", "label": "Reason", "field": "exit_reason", "sortable": True},
                        {"name": "bars_held", "label": "Bars", "field": "bars_held", "sortable": True},
                    ]
                    ui.table(columns=cols, rows=trades, row_key="id",
                             pagination={"rowsPerPage": 25}).classes("w-full")

            # ---- Per-Symbol ----
            with ui.tab_panel(tab_per_sym):
                ui.plotly(per_symbol_bar(per_sym)).classes("w-full")
                if per_sym:
                    cols = [
                        {"name": "symbol", "label": "Symbol", "field": "symbol", "sortable": True},
                        {"name": "trades", "label": "# Trades", "field": "trades", "sortable": True},
                        {"name": "wins", "label": "Wins", "field": "wins", "sortable": True},
                        {"name": "win_rate", "label": "Win %", "field": "win_rate", "sortable": True,
                         ":format": "v => (Number(v)*100).toFixed(1) + '%'"},
                        {"name": "total_pnl", "label": "Total P&L", "field": "total_pnl", "sortable": True,
                         ":format": "v => Number(v).toFixed(2)"},
                        {"name": "avg_pnl", "label": "Avg P&L", "field": "avg_pnl", "sortable": True,
                         ":format": "v => Number(v).toFixed(2)"},
                    ]
                    ui.table(columns=cols, rows=per_sym, row_key="symbol",
                             pagination={"rowsPerPage": 50}).classes("w-full")

            # ---- Diagnostics ----
            with ui.tab_panel(tab_diag):
                with ui.row().classes("w-full gap-2"):
                    ui.plotly(exit_reason_pie(metrics.get("exit_reasons") or {})).classes("flex-1")
                    ui.plotly(bars_held_histogram(trades)).classes("flex-1")
                ui.plotly(mae_mfe_scatter(trades)).classes("w-full")

            # ---- Parameters ----
            with ui.tab_panel(tab_params):
                # Pull from run row
                from engine.db import repo
                row = repo.get_run(run_id)
                if row:
                    import json
                    try:
                        cfg = json.loads(row.get("params_json", "{}"))
                        ui.label("Configuration").classes("text-lg font-semibold")
                        ui.json_editor({"content": {"json": cfg}}).classes("w-full")
                    except Exception:
                        ui.label("Could not parse parameters")
