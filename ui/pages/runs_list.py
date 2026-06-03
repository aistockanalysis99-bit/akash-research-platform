"""Runs list page: search, sort, multi-select to compare."""
from __future__ import annotations

from nicegui import ui

from ..api_client import api
from .layout import page_header


def render_runs_list() -> None:
    page_header(active="Run History")

    with ui.column().classes("w-full max-w-7xl mx-auto p-4 gap-4"):
        ui.label("Run History").classes("text-2xl font-bold")

        runs = api.list_runs(limit=500)

        if not runs:
            ui.label("No runs yet. Go to 'New Backtest' to create one.").classes("text-gray-400")
            return

        # Selection state
        selected: set[str] = set()
        selected_lbl = ui.label("0 selected").classes("text-sm text-gray-400")

        def update_sel_label() -> None:
            selected_lbl.text = f"{len(selected)} selected"

        def on_select(rid: str, val: bool) -> None:
            if val:
                selected.add(rid)
            else:
                selected.discard(rid)
            update_sel_label()

        with ui.row().classes("items-center gap-3"):
            def go_compare() -> None:
                if len(selected) < 2:
                    ui.notify("Select at least 2 runs to compare.", type="warning")
                    return
                ids = "&".join(f"r={rid}" for rid in selected)
                ui.navigate.to(f"/compare?{ids}")
            ui.button("Compare Selected", on_click=go_compare).props("icon=compare_arrows color=secondary")
            selected_lbl

        # Build rows for the table
        rows = []
        for r in runs:
            m = r.get("metrics", {}) or {}
            rows.append({
                "id": r["id"],
                "name": r.get("name") or r["id"][:8],
                "status": r.get("status", "?"),
                "started_at": r.get("started_at", "")[:19].replace("T", " "),
                "timeframe": r.get("timeframe", ""),
                "universe": r.get("universe_name", ""),
                "cagr": m.get("cagr", 0) * 100,
                "sharpe": m.get("sharpe", 0),
                "max_dd": m.get("max_drawdown", 0) * 100,
                "trades": m.get("trades.total_trades", 0),
                "win_rate": m.get("trades.win_rate", 0) * 100,
            })

        # Custom render: a table with checkboxes
        cols = [
            {"name": "select", "label": "", "field": "select"},
            {"name": "name", "label": "Name", "field": "name", "sortable": True, "align": "left"},
            {"name": "status", "label": "Status", "field": "status", "sortable": True},
            {"name": "started_at", "label": "Started", "field": "started_at", "sortable": True},
            {"name": "timeframe", "label": "TF", "field": "timeframe"},
            {"name": "universe", "label": "Universe", "field": "universe"},
            {"name": "cagr", "label": "CAGR %", "field": "cagr", "sortable": True,
             ":format": "v => Number(v).toFixed(2)"},
            {"name": "sharpe", "label": "Sharpe", "field": "sharpe", "sortable": True,
             ":format": "v => Number(v).toFixed(2)"},
            {"name": "max_dd", "label": "MaxDD %", "field": "max_dd", "sortable": True,
             ":format": "v => Number(v).toFixed(2)"},
            {"name": "trades", "label": "Trades", "field": "trades", "sortable": True},
            {"name": "win_rate", "label": "Win %", "field": "win_rate", "sortable": True,
             ":format": "v => Number(v).toFixed(1)"},
            {"name": "id", "label": "Actions", "field": "id"},
        ]
        table = ui.table(columns=cols, rows=rows, row_key="id",
                          pagination={"rowsPerPage": 50}).classes("w-full")

        # Custom slots for select-checkbox and actions
        table.add_slot("body-cell-select", """
            <q-td :props="props">
                <q-checkbox :model-value="false"
                            @update:model-value="(v) => $parent.$emit('toggleSel', {id: props.row.id, v: v})" />
            </q-td>
        """)
        table.add_slot("body-cell-id", """
            <q-td :props="props">
                <a :href="'/runs/' + props.row.id"
                   style="color:#22d3ee;text-decoration:underline;">View</a>
                &nbsp;
                <a href="#" @click.prevent="$parent.$emit('delRun', props.row.id)"
                   style="color:#ef4444;text-decoration:underline;">Delete</a>
            </q-td>
        """)

        def on_toggle_sel(e):
            on_select(e.args["id"], e.args["v"])
        table.on("toggleSel", on_toggle_sel)

        def on_del(e):
            rid = e.args
            try:
                api.delete_run(rid)
                ui.notify("Deleted. Refreshing...", type="positive")
                ui.navigate.to("/runs")
            except Exception as exc:
                ui.notify(f"Failed: {exc}", type="negative")
        table.on("delRun", on_del)
