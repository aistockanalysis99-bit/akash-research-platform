"""AI Memory browser — lessons learned from closed positions."""
from __future__ import annotations

from nicegui import ui

from ..api_client import api
from .layout import page_header


CATEGORY_COLOR = {
    "thesis_held":     "positive",
    "thesis_broke":    "negative",
    "entry_timing":    "warning",
    "exit_timing":     "warning",
    "sector_call":     "info",
    "macro_call":      "info",
    "earnings_event":  "warning",
    "valuation":       "info",
    "size_judgment":   "warning",
    "other":           "grey-7",
}


def render_memory() -> None:
    page_header(active="Memory")

    with ui.column().classes("w-full max-w-6xl mx-auto p-4 gap-4"):
        ui.label("AI Memory").classes("text-2xl font-bold")
        ui.label(
            "Lessons the Reflector has written after each closed position. "
            "The most recent are auto-injected into PM prompts so the system "
            "doesn't repeat mistakes."
        ).classes("text-sm text-gray-400")

        try:
            pending = api.memory_pending()
        except Exception as e:  # noqa: BLE001
            ui.label(f"Failed to load pending: {e}").classes("text-red-400")
            pending = []

        with ui.row().classes("items-center gap-3 mt-1"):
            ui.label(f"Closed positions awaiting reflection: {len(pending)}") \
                .classes("text-sm text-gray-300")

            async def do_reflect() -> None:
                try:
                    ui.notify("Running Reflector on pending positions…",
                              type="info")
                    r = api.memory_reflect()
                    ui.notify(
                        f"Done — saved {r['saved']}, failed {r['failed']}",
                        type="positive",
                    )
                except Exception as e:  # noqa: BLE001
                    ui.notify(f"Failed: {e}", type="negative")

            ui.button("Run Reflector now", icon="psychology",
                      on_click=do_reflect).props("color=primary")

        ui.label("Lessons").classes("text-lg font-semibold mt-3")
        try:
            lessons = api.memory_lessons(limit=200)
        except Exception as e:  # noqa: BLE001
            ui.label(f"Failed to load lessons: {e}").classes("text-red-400")
            return

        if not lessons:
            ui.label("No lessons yet. Close some positions and run the Reflector."
                     ).classes("text-gray-500 italic")
            return

        with ui.column().classes("w-full gap-2"):
            for row in lessons:
                pnl = row.get("outcome_pnl_pct")
                pnl_str = f"{pnl:+.2f}%" if pnl is not None else "?"
                pnl_color = ("text-green-400" if (pnl or 0) > 0
                              else "text-red-400" if (pnl or 0) < 0
                              else "text-gray-400")
                days = row.get("days_held") or "?"
                cat = row.get("category") or "other"
                color = CATEGORY_COLOR.get(cat, "grey-7")
                with ui.card().classes("w-full border-l-4 border-cyan-700"):
                    with ui.row().classes("items-center gap-3 flex-wrap"):
                        ui.label(row["symbol"]).classes("text-base font-bold w-20")
                        ui.label((row.get("created_at") or "")[:10]) \
                            .classes("text-xs text-gray-400 font-mono w-24")
                        ui.badge(cat.replace("_", " "), color=color) \
                            .classes("text-xs")
                        ui.label(pnl_str).classes(f"text-sm {pnl_color} w-20 text-right")
                        ui.label(f"{days}d held").classes("text-xs text-gray-400 w-20")
                        ui.label(row.get("exit_reason") or "") \
                            .classes("text-xs text-gray-400")
                    ui.label(row["lesson_text"]).classes(
                        "text-sm text-gray-200 mt-1 whitespace-pre-wrap"
                    )
