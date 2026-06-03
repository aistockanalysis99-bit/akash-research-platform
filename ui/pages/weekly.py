"""Weekly review pages — list + detail."""
from __future__ import annotations

from nicegui import ui

from ..api_client import api
from .layout import page_header


def render_weekly() -> None:
    page_header(active="Weekly")

    with ui.column().classes("w-full max-w-5xl mx-auto p-4 gap-4"):
        ui.label("Weekly Reviews").classes("text-2xl font-bold")
        ui.label(
            "Friday post-mortems. Auto-runs at 17:00 ET Friday if the scheduler "
            "is enabled. Click 'Run now' to trigger one immediately."
        ).classes("text-sm text-gray-400")

        async def do_run() -> None:
            try:
                r = api.scheduler_run_weekly()
                if r.get("had_activity"):
                    ui.notify(f"Weekly review complete — grade {r.get('grade')}",
                              type="positive")
                else:
                    ui.notify("No activity this week — nothing to review",
                              type="info")
            except Exception as e:  # noqa: BLE001
                ui.notify(f"Failed: {e}", type="negative")

        with ui.row().classes("items-center gap-3"):
            ui.button("Run weekly review now", icon="play_arrow",
                      on_click=do_run).props("color=primary")

        ui.label("Past reviews").classes("text-lg font-semibold mt-3")
        try:
            dates = api.ai_weekly_list()
        except Exception as e:  # noqa: BLE001
            ui.label(f"Failed to load: {e}").classes("text-red-400")
            return

        if not dates:
            ui.label("No reviews yet. Click 'Run weekly review now' or wait for Friday."
                     ).classes("text-gray-500 italic")
            return

        for d in dates[:30]:
            with ui.card().classes("w-full"):
                with ui.row().classes("items-center gap-3"):
                    ui.label(d).classes("text-base font-mono w-32")
                    ui.button("Open", icon="open_in_new",
                              on_click=lambda dd=d:
                              ui.navigate.to(f"/ai/weekly/{dd}")) \
                        .props("flat color=primary")


def render_weekly_detail(date_iso: str) -> None:
    page_header(active="Weekly")

    with ui.column().classes("w-full max-w-6xl mx-auto p-4 gap-3"):
        with ui.row().classes("items-center gap-3"):
            ui.link("← All reviews", "/ai/weekly").classes(
                "text-sm text-gray-400 hover:text-cyan-400"
            ).props("no-underline")
            ui.label(f"Weekly Review — {date_iso}").classes("text-2xl font-bold")

        try:
            files = api.ai_weekly_get(date_iso)
        except Exception as e:  # noqa: BLE001
            ui.label(f"Failed to load: {e}").classes("text-red-400")
            return

        if not files:
            ui.label("No artifacts for this review.").classes("text-gray-500 italic")
            return

        # Single file expected (14_weekly_review.md); render it
        for stem, md in files.items():
            with ui.card().classes("w-full"):
                ui.markdown(md).classes("w-full")
