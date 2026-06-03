"""Common layout: header + two-level navigation.

Three top-level sections, each revealing its own sub-pages:

    Backtesting   →  Backtest · Run History · Compare · Data Cache · Parameters
    AI Analysis   →  Analyze · Decisions · Morning · Weekly · Memory
    Portfolio     →  Portfolio · Watchlist · Automation

Pages still call `page_header(active="<legacy label>")` — the maps below
translate those legacy labels to the new structure, so we didn't have to
touch the 14 page files (only run_detail, which had no label).
"""
from __future__ import annotations

from nicegui import ui

from ..api_client import api


# section name -> list of (display label, route, {legacy active-keys})
SECTIONS: dict[str, list[tuple[str, str, set[str]]]] = {
    "Portfolio": [
        ("Portfolio",   "/",             {"Portfolio"}),
        ("Watchlist",   "/profiles",     {"Profiles"}),
        ("Automation",  "/automation",   {"Automation"}),
    ],
    "AI Analysis": [
        ("Analyze",     "/ai/analyze",   {"AI Analysis"}),
        ("Decisions",   "/ai/decisions", {"Decisions"}),
        ("Morning",     "/ai/morning",   {"Morning"}),
        ("Weekly",      "/ai/weekly",    {"Weekly"}),
        ("Memory",      "/memory",       {"Memory"}),
    ],
    "Backtesting": [
        ("Backtest",    "/backtest",     {"New Backtest"}),
        ("Run History", "/runs",         {"Run History"}),
        ("Compare",     "/compare",      {"Compare"}),
        ("Data Cache",  "/data",         {"Data Cache"}),
        ("Parameters",  "/params",       {"Parameters"}),
    ],
}

# Display order of the top-level tabs
SECTION_ORDER = ["Portfolio", "AI Analysis", "Backtesting"]

# Reverse lookup: legacy active-key -> section name
_KEY_TO_SECTION: dict[str, str] = {
    key: section
    for section, items in SECTIONS.items()
    for _, _, keys in items
    for key in keys
}


def _resolve_section(active: str) -> str:
    """Which top-level section does this legacy active-label belong to?"""
    return _KEY_TO_SECTION.get(active, "Portfolio")


def page_header(active: str = "") -> None:
    """Two-row header: section tabs on top, sub-pages of the active section below."""
    current_section = _resolve_section(active)

    with ui.header(elevated=True).classes("bg-slate-900 p-0"):
        with ui.column().classes("w-full gap-0"):

            # ---------- Row 1: brand + 3 section tabs + health ----------
            with ui.row().classes(
                "w-full items-center justify-between px-4 py-2 "
                "border-b border-slate-700"
            ):
                with ui.row().classes("items-center gap-5"):
                    ui.link("Akash", "/").classes(
                        "text-lg font-bold text-cyan-400 no-underline"
                    ).props("no-underline")

                    for section in SECTION_ORDER:
                        is_active = section == current_section
                        # Section tab navigates to its FIRST sub-page
                        first_route = SECTIONS[section][0][1]
                        tab = ui.link(section, first_route).classes(
                            "text-sm font-semibold px-1 transition-colors "
                            "hover:text-cyan-300 "
                            + ("text-cyan-400" if is_active else "text-gray-300")
                        )
                        tab.props("no-underline")

                with ui.row().classes("items-center gap-2"):
                    health = api.health()
                    color = "green" if health.get("status") == "ok" else "red"
                    ui.icon("circle", color=color, size="xs")
                    ui.label(f"API {health.get('status', '—')}").classes(
                        "text-xs text-gray-500 hidden sm:block"
                    )

            # ---------- Row 2: sub-pages of the active section ----------
            with ui.row().classes(
                "w-full items-center gap-1 px-4 py-1 bg-slate-800/60"
            ):
                for label, route, keys in SECTIONS[current_section]:
                    is_active = active in keys
                    link = ui.link(label, route).classes(
                        "text-sm px-3 py-1 rounded transition-colors "
                        + ("bg-cyan-500/20 text-cyan-300 font-semibold"
                           if is_active else "text-gray-300 hover:text-cyan-300")
                    )
                    link.props("no-underline")
