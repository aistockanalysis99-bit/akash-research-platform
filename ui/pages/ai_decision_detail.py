"""AI Decision Detail page — two-column layout: agent list on left, markdown on right."""
from __future__ import annotations

from nicegui import ui

from ..api_client import api
from .layout import page_header


STAGE_DISPLAY = {
    "summary":       ("Summary", "summarize"),
    "signal":        ("Signal", "input"),
    "fundamental":   ("Fundamental", "trending_up"),
    "news":          ("News", "newspaper"),
    "technical":     ("Technical", "show_chart"),
    "macro_context": ("Macro context", "public"),
    "bull":          ("Bull case", "north_east"),
    "bear":          ("Bear case", "south_east"),
    "judge":         ("Debate Judge", "balance"),
    "risk_manager":  ("Risk Manager", "shield"),
    "pm":            ("PM Verdict", "gavel"),
}
STAGE_ORDER = [
    "summary", "signal",
    "fundamental", "news", "technical",
    "macro_context",
    "bull", "bear", "judge",
    "risk_manager",
    "pm",
]


def render_ai_decision_detail(symbol: str, date_iso: str) -> None:
    page_header(active="Decisions")

    with ui.column().classes("w-full max-w-7xl mx-auto p-4 gap-3"):
        # ---- Top: symbol + date + back link ----
        with ui.row().classes("items-center gap-3 w-full"):
            ui.link("← All decisions", "/ai/decisions").classes(
                "text-sm text-gray-400 hover:text-cyan-400"
            ).props("no-underline")
            ui.label(f"{symbol.upper()}").classes("text-3xl font-bold")
            ui.label(date_iso).classes("text-sm text-gray-400")

        # ---- Fetch all stage markdowns ----
        try:
            files = api.ai_get_decision(symbol, date_iso)
        except Exception as e:  # noqa: BLE001
            ui.label(f"Failed to load: {e}").classes("text-red-400")
            return

        if not files:
            ui.label("No stage files found on disk.").classes("text-gray-500 italic")
            return

        # ---- Two-column layout (left rail + right pane) ----
        # Default selection: summary if present, else PM, else first available.
        default_stage = (
            "summary" if "summary" in files
            else "pm" if "pm" in files
            else next(iter(STAGE_ORDER if any(s in files for s in STAGE_ORDER) else files))
        )
        selected = {"stage": default_stage}

        with ui.row().classes("w-full gap-4 items-start"):
            # ===== Left rail =====
            with ui.column().classes("w-56 gap-1"):
                ui.label("Stages").classes("text-xs text-gray-500 uppercase mt-2 mb-1")

                # Build buttons up-front, save references so we can restyle on click.
                btn_refs: dict[str, ui.button] = {}
                markdown_holder = {"view": None}

                def select(stage: str) -> None:
                    selected["stage"] = stage
                    content = files.get(stage, "_(not generated)_")
                    if markdown_holder["view"] is not None:
                        markdown_holder["view"].content = content
                    # Restyle: highlight current
                    for s, b in btn_refs.items():
                        cls = (
                            "w-full text-left bg-slate-800 text-cyan-400 font-semibold"
                            if s == stage else
                            "w-full text-left text-gray-200 hover:text-cyan-400"
                        )
                        b.classes(replace=cls)

                for stage in STAGE_ORDER:
                    if stage not in files:
                        continue
                    label, icon = STAGE_DISPLAY[stage]
                    btn = ui.button(label, icon=icon,
                                     on_click=lambda s=stage: select(s)) \
                        .props("flat align=left").classes(
                            "w-full text-left text-gray-200 hover:text-cyan-400"
                        )
                    btn_refs[stage] = btn

            # ===== Right pane =====
            with ui.column().classes("flex-1 min-w-0"):
                with ui.card().classes("w-full"):
                    initial = files.get(default_stage, "")
                    markdown_holder["view"] = ui.markdown(initial).classes("w-full")

                # Apply default highlight
                select(default_stage)
