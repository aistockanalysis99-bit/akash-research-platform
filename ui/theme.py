"""Theming + small style helpers."""
from __future__ import annotations

from nicegui import ui


def apply_dark_theme() -> None:
    ui.dark_mode().enable()


def kpi_card(label: str, value: str, color: str = "primary", help_text: str = "") -> None:
    """A small KPI card for the summary grid."""
    with ui.card().classes("min-w-[160px] flex-1"):
        with ui.column().classes("gap-1"):
            ui.label(label).classes("text-xs text-gray-500 uppercase")
            ui.label(value).classes(f"text-2xl font-bold text-{color}")
            if help_text:
                ui.label(help_text).classes("text-xs text-gray-400")


def section_header(text: str, icon: str = "") -> None:
    with ui.row().classes("items-center gap-2 mt-2"):
        if icon:
            ui.icon(icon).classes("text-xl")
        ui.label(text).classes("text-lg font-semibold")
