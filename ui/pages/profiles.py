"""Per-stock Profiles — list page + detail/edit page."""
from __future__ import annotations

from nicegui import ui

from ..api_client import api
from .layout import page_header


PRIORITY_COLOR = {
    "tier_1": "positive",
    "tier_2": "info",
    "tier_3": "grey-7",
}


def render_profiles_list() -> None:
    page_header(active="Profiles")

    with ui.column().classes("w-full max-w-6xl mx-auto p-4 gap-4"):
        ui.label("Per-stock Profiles").classes("text-2xl font-bold")
        ui.label(
            "Research dossiers for every ticker the system has analyzed. "
            "Auto-built by Claude Opus on first analysis, hand-editable. "
            "Profiles prime every future analysis with stock-specific KPIs, "
            "bull/bear pillars, red lines, and PM notes."
        ).classes("text-sm text-gray-400")

        try:
            rows = api.profiles_list()
        except Exception as e:  # noqa: BLE001
            ui.label(f"Failed to load: {e}").classes("text-red-400")
            return

        if not rows:
            ui.label(
                "No profiles on disk yet. Run an analysis on any ticker and "
                "the system will auto-build the profile after the pipeline completes."
            ).classes("text-gray-500 italic")
            return

        # Sort: tier_1 first, then by symbol
        tier_order = {"tier_1": 0, "tier_2": 1, "tier_3": 2}
        rows.sort(key=lambda r: (tier_order.get(r.get("priority"), 9), r.get("symbol", "")))

        with ui.column().classes("w-full gap-1"):
            with ui.row().classes("w-full items-center gap-2 text-xs text-gray-500 "
                                    "uppercase font-semibold px-3"):
                ui.label("Symbol").classes("w-20")
                ui.label("Name").classes("flex-1 min-w-[200px]")
                ui.label("Sector").classes("w-44")
                ui.label("Tier").classes("w-24 text-center")
                ui.label("Intent").classes("w-20 text-center")
                ui.label("Held").classes("w-16 text-center")
                ui.label("Pillars / Red").classes("w-32 text-center")
                ui.label("Reviewed").classes("w-28")
                ui.label("").classes("w-16")

            for r in rows:
                sym = r["symbol"]
                with ui.card().classes("w-full cursor-pointer hover:bg-slate-800 py-2"):
                    with ui.row().classes("w-full items-center gap-2"):
                        ui.label(sym).classes("w-20 text-base font-bold font-mono")
                        ui.label(r.get("name") or "—") \
                            .classes("flex-1 min-w-[200px] text-sm")
                        ui.label(r.get("sector") or "—") \
                            .classes("w-44 text-xs text-gray-400")
                        tier = r.get("priority") or "?"
                        ui.badge(tier, color=PRIORITY_COLOR.get(tier, "grey-7")) \
                            .classes("w-24 text-center")
                        ui.label(r.get("position_intent") or "—") \
                            .classes("w-20 text-center text-xs")
                        ui.label("✓" if r.get("held") else "—") \
                            .classes("w-16 text-center text-xs")
                        bn = r.get("bull_pillar_count", 0)
                        rn = r.get("bear_pillar_count", 0)
                        rl = r.get("red_line_count", 0)
                        ui.label(f"🟢{bn} 🔴{rn} ⚠{rl}") \
                            .classes("w-32 text-center text-xs")
                        ui.label((r.get("last_reviewed") or "")[:10]) \
                            .classes("w-28 text-xs text-gray-400 font-mono")
                        ui.button(
                            "Open", icon="open_in_new",
                            on_click=lambda s=sym:
                            ui.navigate.to(f"/profiles/{s}"),
                        ).props("flat dense color=primary").classes("w-16")


def render_profile_detail(symbol: str) -> None:
    page_header(active="Profiles")

    with ui.column().classes("w-full max-w-6xl mx-auto p-4 gap-3"):
        with ui.row().classes("items-center gap-3"):
            ui.link("← All profiles", "/profiles").classes(
                "text-sm text-gray-400 hover:text-cyan-400"
            ).props("no-underline")
            ui.label(symbol.upper()).classes("text-3xl font-bold font-mono")

        try:
            raw = api.profile_get_raw(symbol)
        except Exception as e:  # noqa: BLE001
            ui.label(f"Failed to load: {e}").classes("text-red-400")
            return

        try:
            p = api.profile_get(symbol)
        except Exception:  # noqa: BLE001
            p = None

        # Header summary
        if p:
            with ui.card().classes("w-full"):
                with ui.row().classes("items-center gap-4 flex-wrap"):
                    ui.label(p.get("name") or symbol).classes("text-lg font-semibold")
                    ui.badge(p.get("priority") or "?",
                             color=PRIORITY_COLOR.get(p.get("priority"), "grey-7")) \
                        .classes("text-sm")
                    ui.label(p.get("sector") or "—") \
                        .classes("text-sm text-gray-400")
                    ui.label(f"intent: {p.get('position_intent') or '—'}") \
                        .classes("text-xs text-gray-500")
                    ui.label(f"held: {'yes' if p.get('held') else 'no'}") \
                        .classes("text-xs text-gray-500")
                    ui.label(f"reviewed: {(p.get('last_reviewed') or '')[:10]}") \
                        .classes("text-xs text-gray-500")
                    ui.label(f"auto-built: {'yes' if p.get('auto_built') else 'no'}") \
                        .classes("text-xs text-gray-500")

                # Quick stats row
                with ui.row().classes("w-full gap-4 mt-2"):
                    ui.label(f"📊 KPIs: {len(p.get('key_kpis') or [])}") \
                        .classes("text-xs text-gray-300")
                    ui.label(f"🟢 Bull pillars: {len(p.get('bull_thesis_pillars') or [])}") \
                        .classes("text-xs text-green-400")
                    ui.label(f"🔴 Bear pillars: {len(p.get('bear_thesis_pillars') or [])}") \
                        .classes("text-xs text-red-400")
                    ui.label(f"⚠ Red lines: {len(p.get('red_lines') or [])}") \
                        .classes("text-xs text-yellow-400")
                    ui.label(f"👥 Peers: {', '.join((p.get('preferred_peers') or [])[:6])}") \
                        .classes("text-xs text-gray-400")

        # Editable raw markdown
        ui.label("Raw file (markdown + YAML frontmatter)") \
            .classes("text-sm text-gray-500 uppercase mt-2")

        editor = ui.textarea(value=raw.get("content", "")) \
            .props("outlined autogrow") \
            .classes("w-full font-mono text-xs")

        with ui.row().classes("items-center gap-2 mt-2"):
            def do_save() -> None:
                try:
                    r = api.profile_put_raw(symbol, editor.value or "")
                    ui.notify(f"Saved {r.get('symbol')} ({r.get('name')})",
                              type="positive")
                except Exception as e:  # noqa: BLE001
                    ui.notify(f"Save failed: {e}", type="negative")

            def do_delete() -> None:
                try:
                    api.profile_delete(symbol)
                    ui.notify(f"Deleted profile for {symbol}", type="warning")
                    ui.navigate.to("/profiles")
                except Exception as e:  # noqa: BLE001
                    ui.notify(f"Delete failed: {e}", type="negative")

            ui.button("Save", icon="save", on_click=do_save).props("color=primary")
            ui.button("Delete", icon="delete", on_click=do_delete) \
                .props("color=negative outline")
            ui.label(
                "Saving validates the YAML — if it fails, the file is still "
                "saved but the profile won't load for the next analysis."
            ).classes("text-xs text-gray-500")
