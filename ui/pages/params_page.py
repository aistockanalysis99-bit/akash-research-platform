"""Parameter sets management."""
from __future__ import annotations

import json

from nicegui import ui

from ..api_client import api
from .layout import page_header


def render_params_page() -> None:
    page_header(active="Parameters")

    with ui.column().classes("w-full max-w-7xl mx-auto p-4 gap-4"):
        ui.label("Saved Parameter Sets").classes("text-2xl font-bold")

        sets = api.list_params()
        if not sets:
            ui.label("No parameter sets saved yet. Save one from the New Backtest page.") \
                .classes("text-gray-400")
            return

        for s in sets:
            with ui.card().classes("w-full"):
                with ui.row().classes("w-full justify-between items-center"):
                    ui.label(s["name"]).classes("text-lg font-semibold text-cyan-400")
                    with ui.row().classes("gap-2"):
                        ui.label(f"Created: {s.get('created_at', '')[:19]}") \
                            .classes("text-xs text-gray-400")
                        def make_del(name):
                            def _del():
                                api.delete_params(name)
                                ui.notify(f"Deleted '{name}'", type="positive")
                                ui.navigate.to("/params")
                            return _del
                        ui.button(icon="delete", on_click=make_del(s["name"])).props("flat color=negative")
                ui.json_editor({"content": {"json": s["params"]}, "mode": "view"}).classes("w-full")
