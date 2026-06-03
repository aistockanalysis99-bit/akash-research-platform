"""Data cache page: refresh data, view cache freshness."""
from __future__ import annotations

import asyncio

from nicegui import ui

from ..api_client import api
from .layout import page_header


def render_data_page() -> None:
    page_header(active="Data Cache")

    with ui.column().classes("w-full max-w-7xl mx-auto p-4 gap-4"):
        ui.label("Data Cache").classes("text-2xl font-bold")

        with ui.card().classes("w-full"):
            ui.label("Refresh OHLCV from FMP").classes("font-semibold")

            state = {"universe": "smoke", "timeframe": "1D", "years": 5, "full": False, "job_id": None}

            with ui.row().classes("w-full gap-2 items-end"):
                ui.select(options=api.list_universes(), value="smoke", label="Universe") \
                    .classes("flex-1").bind_value(state, "universe")
                ui.select(options=["1D", "4h", "1h", "30m", "15m"], value="1D", label="Timeframe") \
                    .classes("flex-1").bind_value(state, "timeframe")
                ui.number("Years", value=5, min=1, max=20).classes("w-24").bind_value(state, "years")
                ui.checkbox("Full re-fetch").bind_value(state, "full")

            progress_bar = ui.linear_progress(value=0).classes("w-full")
            progress_label = ui.label("").classes("text-xs text-gray-400")

            def kick_refresh() -> None:
                resp = api.refresh_data(
                    universe=state["universe"],
                    symbols=None,
                    timeframe=state["timeframe"],
                    years=int(state["years"]),
                    full=bool(state["full"]),
                )
                state["job_id"] = resp["job_id"]
                ui.notify(f"Refreshing {resp['symbols']} symbols...", type="positive")
                progress_label.text = "Starting..."

            ui.button("Refresh Now", on_click=kick_refresh).props("color=primary icon=refresh")

            def poll_progress():
                if not state.get("job_id"):
                    return
                try:
                    s = api.refresh_status(state["job_id"])
                except Exception as e:
                    progress_label.text = f"Error: {e}"
                    state["job_id"] = None
                    return
                done = s.get("done", 0)
                total = s.get("total", 1)
                progress_bar.value = done / max(1, total)
                progress_label.text = f"[{s.get('status','?')}] {done}/{total}  {s.get('current_symbol','')}"
                if s.get("status") in ("done", "failed"):
                    state["job_id"] = None
                    if s.get("status") == "done":
                        ui.notify("Refresh complete.", type="positive")
                    else:
                        ui.notify(f"Refresh failed: {s.get('error')}", type="negative")

            ui.timer(1.0, poll_progress)

        with ui.card().classes("w-full"):
            ui.label("Cached Files").classes("font-semibold")
            try:
                status = api.data_status()
            except Exception as e:
                ui.label(f"API error: {e}").classes("text-red-500")
                return
            if not status:
                ui.label("No cache yet.").classes("text-gray-400")
                return

            cols = [
                {"name": "symbol", "label": "Symbol", "field": "symbol", "sortable": True, "align": "left"},
                {"name": "timeframe", "label": "Timeframe", "field": "timeframe", "sortable": True},
                {"name": "bars", "label": "Bars", "field": "bars", "sortable": True},
                {"name": "first_ts", "label": "First", "field": "first_ts", "sortable": True},
                {"name": "last_ts", "label": "Last", "field": "last_ts", "sortable": True},
            ]
            for r in status:
                if r.get("first_ts"):
                    r["first_ts"] = r["first_ts"][:10]
                if r.get("last_ts"):
                    r["last_ts"] = r["last_ts"][:10]
            ui.table(columns=cols, rows=status, row_key="symbol",
                     pagination={"rowsPerPage": 25}).classes("w-full")
