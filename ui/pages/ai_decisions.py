"""AI Decisions list page — every past analysis.

Renders rows as clickable cards (not ui.table) because the stages column
needs richer per-cell rendering — a row of small lit/unlit badges that show
which agents ran. Cards also let us color the left border by verdict.
"""
from __future__ import annotations

from nicegui import ui

from ..api_client import api
from .layout import page_header


# Compact 2-letter codes for each pipeline stage, in pipeline order.
# Each code becomes a small badge in the row's "Stages" column:
#  - lit cyan if that stage's markdown was written to disk
#  - dim grey if missing
STAGE_CODES = [
    ("signal",        "SG"),
    ("fundamental",   "FU"),
    ("news",          "NW"),
    ("technical",     "TC"),
    ("macro_context", "MC"),
    ("bull",          "BL"),
    ("bear",          "BR"),
    ("judge",         "JG"),
    ("risk_manager",  "RM"),
    ("pm",            "PM"),
    ("summary",       "SM"),
]


def render_ai_decisions() -> None:
    page_header(active="Decisions")

    with ui.column().classes("w-full max-w-7xl mx-auto p-4 gap-4"):
        ui.label("AI Decisions").classes("text-2xl font-bold")
        ui.label("Every analysis ever run. Click a row to drill into the detail page.") \
            .classes("text-sm text-gray-400")

        try:
            rows = api.ai_list_decisions()
        except Exception as e:  # noqa: BLE001
            ui.notify(f"Failed to load decisions: {e}", type="negative")
            rows = []

        if not rows:
            ui.label("No analyses yet. Run one from the AI Analysis page.") \
                .classes("text-gray-500 italic")
            return

        # ----- Status filter -----
        status_filter = {"value": "all"}
        counts = _count_by_status(rows)
        with ui.row().classes("items-center gap-2 mb-1 mt-1"):
            ui.label("Filter:").classes("text-xs text-gray-500 uppercase mr-1")
            for label, key in [
                (f"All ({counts['all']})",          "all"),
                (f"Complete ({counts['complete']})", "complete"),
                (f"Failed ({counts['failed']})",     "failed"),
            ]:
                def _click(k=key) -> None:
                    status_filter["value"] = k
                    _rebuild()
                ui.button(label, on_click=_click).props("flat dense")

        # ----- Legend -----
        with ui.row().classes("items-center gap-1 text-xs text-gray-500 mb-2"):
            ui.label("Stages:").classes("mr-1")
            for stage, code in STAGE_CODES:
                ui.badge(code, color="cyan-7").props("outline").classes("text-xs")
                ui.label(stage).classes("mr-2")

        table_container = ui.column().classes("w-full gap-1")

        def _rebuild() -> None:
            table_container.clear()
            with table_container:
                _render_table(rows, status_filter["value"])

        _rebuild()


def _count_by_status(rows: list[dict]) -> dict:
    out = {"all": len(rows), "complete": 0, "failed": 0}
    for r in rows:
        s = r.get("status", "")
        if s == "complete":
            out["complete"] += 1
        elif s.startswith("failed"):
            out["failed"] += 1
    return out


def _render_table(rows: list[dict], filter_status: str) -> None:
    if filter_status == "complete":
        rows = [r for r in rows if r.get("status") == "complete"]
    elif filter_status == "failed":
        rows = [r for r in rows if (r.get("status") or "").startswith("failed")]

    if not rows:
        ui.label("No decisions match the filter.").classes("text-gray-500 italic")
        return

    # Header row
    with ui.row().classes("w-full items-center gap-2 text-xs text-gray-500 "
                            "uppercase font-semibold px-3"):
        ui.label("Symbol").classes("w-20")
        ui.label("Date").classes("w-28")
        ui.label("Verdict").classes("w-24")
        ui.label("Conv").classes("w-14 text-center")
        ui.label("Size").classes("w-14 text-center")
        ui.label("Source").classes("w-20")
        ui.label("Stages")

    for r in rows:
        _render_decision_row(r)


def _render_decision_row(r: dict) -> None:
    status = r.get("status", "incomplete")
    is_failed = status.startswith("failed")
    decision = r.get("decision") or ("FAILED" if is_failed else "—")

    border = {
        "APPROVE":  "border-green-500",
        "RESIZE":   "border-yellow-500",
        "REJECT":   "border-red-500",
        "FAILED":   "border-red-700",
    }.get(decision, "border-gray-700")

    card = ui.card().classes(
        f"w-full cursor-pointer hover:bg-slate-800 border-l-4 {border} py-2"
    )
    with card:
        with ui.row().classes("w-full items-center gap-2 flex-wrap"):
            ui.label(r["symbol"]).classes("w-20 text-base font-bold")
            ui.label(r["date"]).classes("w-28 text-xs text-gray-400 font-mono")

            badge_color = {
                "APPROVE":  "positive",
                "RESIZE":   "warning",
                "REJECT":   "negative",
                "FAILED":   "red-10",
            }.get(decision, "grey-7")
            ui.badge(decision, color=badge_color).classes("w-24 text-center")

            conv = r.get("conviction")
            ui.label(f"{conv}/10" if conv is not None else "—") \
                .classes("w-14 text-center text-sm")
            size = r.get("size_pct")
            ui.label(f"{size}%" if size is not None else "—") \
                .classes("w-14 text-center text-sm")
            ui.label(r.get("source") or "—") \
                .classes("w-20 text-xs text-gray-400")

            # Stage chips — one per known stage
            present = set(r.get("stages_present") or [])
            with ui.row().classes("flex-1 items-center gap-1 flex-wrap"):
                for stage_key, code in STAGE_CODES:
                    if stage_key in present:
                        ui.badge(code, color="cyan-7").props("outline").classes("text-xs")
                    else:
                        ui.badge(code, color="grey-8").props("outline").classes(
                            "text-xs opacity-30"
                        )

    card.on("click", lambda r=r: ui.navigate.to(
        f"/ai/decisions/{r['symbol']}/{r['date']}"
    ))
