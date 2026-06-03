"""Phase 4 automation page — Settings + Scheduler + Watchlist + Telegram.

Four sections on one page (keeps top-nav uncluttered):
    1. Settings — portfolio sizing + scheduler times (live, no restart needed)
    2. Scheduler status — enabled/running, next runs, manual triggers
    3. Watchlist — symbols the evening cycle iterates over, add/remove/toggle
    4. Telegram — config status, test button, recent message log
"""
from __future__ import annotations

from typing import Any

from nicegui import ui

from ..api_client import api
from .layout import page_header


# --------------------------------------------------------------------------- #
# Settings section — portfolio sizing + scheduler times
# --------------------------------------------------------------------------- #


def _render_settings(container: ui.column) -> None:
    container.clear()
    try:
        snap = api.settings_get()
    except Exception as e:  # noqa: BLE001
        with container:
            ui.label(f"Failed to load: {e}").classes("text-red-400")
        return

    portfolio = snap.get("portfolio", {})
    scheduler = snap.get("scheduler", {})

    # Working copy of values the user can edit
    edits: dict[str, Any] = {}

    def _v(section: dict, key: str) -> Any:
        return section.get(key, {}).get("value")

    def _d(section: dict, key: str) -> Any:
        return section.get(key, {}).get("env_default")

    with container:
        with ui.card().classes("w-full"):
            ui.label("Portfolio sizing").classes("text-sm uppercase text-gray-500")
            with ui.grid(columns=3).classes("w-full gap-3 mt-1"):
                ic_in = ui.number(
                    label="Initial capital ($)",
                    value=_v(portfolio, "initial_capital"),
                    min=10_000, max=1_000_000_000, step=10_000, format="%.0f",
                ).props("dense outlined")
                ic_in.on("update:model-value",
                          lambda e: edits.update({"virtual_initial_capital": e.args}))

                rp_in = ui.number(
                    label="Risk per trade (e.g. 0.02 = 2%)",
                    value=_v(portfolio, "risk_pct"),
                    min=0.001, max=0.10, step=0.005, format="%.4f",
                ).props("dense outlined")
                rp_in.on("update:model-value",
                          lambda e: edits.update({"virtual_risk_pct": e.args}))

                sp_in = ui.number(
                    label="Initial stop (e.g. 0.08 = 8%)",
                    value=_v(portfolio, "stop_pct"),
                    min=0.02, max=0.30, step=0.005, format="%.4f",
                ).props("dense outlined")
                sp_in.on("update:model-value",
                          lambda e: edits.update({"virtual_stop_pct": e.args}))

                tp_in = ui.number(
                    label="Trailing stop (e.g. 0.10 = 10%)",
                    value=_v(portfolio, "trail_pct"),
                    min=0.02, max=0.30, step=0.005, format="%.4f",
                ).props("dense outlined")
                tp_in.on("update:model-value",
                          lambda e: edits.update({"virtual_trail_pct": e.args}))

                mg_in = ui.number(
                    label="Max gross exposure (1.0 = no leverage)",
                    value=_v(portfolio, "max_gross_pct"),
                    min=0.1, max=5.0, step=0.05, format="%.2f",
                ).props("dense outlined")
                mg_in.on("update:model-value",
                          lambda e: edits.update({"virtual_max_gross_pct": e.args}))

            ui.separator().classes("my-2")
            ui.label("Scheduler timing").classes("text-sm uppercase text-gray-500 mt-1")
            with ui.grid(columns=4).classes("w-full gap-3 mt-1"):
                tz_in = ui.input(
                    label="Timezone (IANA name)",
                    value=_v(scheduler, "timezone"),
                ).props("dense outlined")
                tz_in.on("update:model-value",
                          lambda e: edits.update({"scheduler_timezone": e.args}))

                mh_in = ui.number(
                    label="Morning hour (0-23)",
                    value=_v(scheduler, "morning_hour"),
                    min=0, max=23, step=1, format="%d",
                ).props("dense outlined")
                mh_in.on("update:model-value",
                          lambda e: edits.update({"scheduler_morning_hour": int(e.args)}))

                mm_in = ui.number(
                    label="Morning minute",
                    value=_v(scheduler, "morning_minute"),
                    min=0, max=59, step=1, format="%d",
                ).props("dense outlined")
                mm_in.on("update:model-value",
                          lambda e: edits.update({"scheduler_morning_minute": int(e.args)}))

                gap_in = ui.number(
                    label="Evening gap (secs)",
                    value=_v(scheduler, "evening_gap_secs"),
                    min=0, max=3600, step=10, format="%d",
                ).props("dense outlined")
                gap_in.on("update:model-value",
                          lambda e: edits.update({"scheduler_evening_gap_secs": int(e.args)}))

                eh_in = ui.number(
                    label="Evening hour (0-23)",
                    value=_v(scheduler, "evening_hour"),
                    min=0, max=23, step=1, format="%d",
                ).props("dense outlined")
                eh_in.on("update:model-value",
                          lambda e: edits.update({"scheduler_evening_hour": int(e.args)}))

                em_in = ui.number(
                    label="Evening minute",
                    value=_v(scheduler, "evening_minute"),
                    min=0, max=59, step=1, format="%d",
                ).props("dense outlined")
                em_in.on("update:model-value",
                          lambda e: edits.update({"scheduler_evening_minute": int(e.args)}))

            with ui.row().classes("items-center gap-2 mt-3"):
                def do_save() -> None:
                    if not edits:
                        ui.notify("Nothing changed", type="info")
                        return
                    try:
                        r = api.settings_update(edits)
                        applied = ", ".join(r.get("applied") or [])
                        ui.notify(f"Saved: {applied}", type="positive")
                        edits.clear()
                        _render_settings(container)
                    except Exception as e:  # noqa: BLE001
                        ui.notify(f"Save failed: {e}", type="negative")

                def do_reset() -> None:
                    """Revert all settings to env defaults."""
                    reset_payload = {
                        "virtual_initial_capital": _d(portfolio, "initial_capital"),
                        "virtual_risk_pct":        _d(portfolio, "risk_pct"),
                        "virtual_stop_pct":        _d(portfolio, "stop_pct"),
                        "virtual_trail_pct":       _d(portfolio, "trail_pct"),
                        "virtual_max_gross_pct":   _d(portfolio, "max_gross_pct"),
                        "scheduler_timezone":           _d(scheduler, "timezone"),
                        "scheduler_morning_hour":       _d(scheduler, "morning_hour"),
                        "scheduler_morning_minute":     _d(scheduler, "morning_minute"),
                        "scheduler_evening_hour":       _d(scheduler, "evening_hour"),
                        "scheduler_evening_minute":     _d(scheduler, "evening_minute"),
                        "scheduler_evening_gap_secs":   _d(scheduler, "evening_gap_secs"),
                    }
                    try:
                        api.settings_update(reset_payload)
                        ui.notify("Reverted to .env defaults", type="warning")
                        _render_settings(container)
                    except Exception as e:  # noqa: BLE001
                        ui.notify(f"Reset failed: {e}", type="negative")

                ui.button("Save", icon="save", on_click=do_save) \
                    .props("color=primary")
                ui.button("Reset to env defaults", icon="restart_alt",
                          on_click=do_reset).props("color=warning outline")
                ui.label(
                    "Scheduler times take effect immediately. "
                    "Portfolio sizing applies to the next position."
                ).classes("text-xs text-gray-400")


def render_automation() -> None:
    page_header(active="Automation")

    with ui.column().classes("w-full max-w-6xl mx-auto p-4 gap-4"):
        ui.label("Automation").classes("text-2xl font-bold")
        ui.label(
            "Scheduler, settings, watchlist, and Telegram wiring. "
            "All values below override .env defaults at runtime — no restart needed."
        ).classes("text-sm text-gray-400")

        # =================== Live Settings =================== #
        ui.label("Settings").classes("text-lg font-semibold mt-2")
        settings_panel = ui.column().classes("w-full")
        _render_settings(settings_panel)

        # =================== Scheduler =================== #
        ui.label("Scheduler").classes("text-lg font-semibold mt-3")
        scheduler_panel = ui.column().classes("w-full")
        _render_scheduler(scheduler_panel)

        # =================== Watchlist =================== #
        ui.label("Watchlist").classes("text-lg font-semibold mt-3")
        ui.label(
            "Symbols the evening cycle runs through every day. "
            "The morning cycle reviews open positions only — doesn't use this list."
        ).classes("text-xs text-gray-400")
        watchlist_panel = ui.column().classes("w-full")
        _render_watchlist(watchlist_panel)

        # =================== Telegram =================== #
        ui.label("Telegram").classes("text-lg font-semibold mt-3")
        telegram_panel = ui.column().classes("w-full")
        _render_telegram(telegram_panel)


# --------------------------------------------------------------------------- #
# Scheduler section
# --------------------------------------------------------------------------- #


def _render_scheduler(container: ui.column) -> None:
    container.clear()
    try:
        status = api.scheduler_status()
    except Exception as e:  # noqa: BLE001
        with container:
            ui.label(f"Failed to load: {e}").classes("text-red-400")
        return

    with container:
        with ui.card().classes("w-full"):
            with ui.row().classes("items-center gap-3 flex-wrap"):
                running = status.get("running", False)
                enabled_cfg = status.get("enabled_in_config", False)
                color = ("positive" if running else
                         "warning" if enabled_cfg else "grey-7")
                label = ("RUNNING" if running else
                          "ENABLED, NOT RUNNING" if enabled_cfg else "DISABLED")
                ui.badge(label, color=color).classes("text-sm")

                # ----- Start/Stop buttons -----
                def do_start() -> None:
                    try:
                        api.scheduler_start()
                        ui.notify("Scheduler started", type="positive")
                        _render_scheduler(container)
                    except Exception as e:  # noqa: BLE001
                        ui.notify(f"Start failed: {e}", type="negative")

                def do_stop() -> None:
                    try:
                        api.scheduler_stop()
                        ui.notify("Scheduler stopped", type="warning")
                        _render_scheduler(container)
                    except Exception as e:  # noqa: BLE001
                        ui.notify(f"Stop failed: {e}", type="negative")

                if running:
                    ui.button("Stop scheduler", icon="stop",
                              on_click=do_stop).props("color=negative outline dense")
                else:
                    ui.button("Start scheduler", icon="play_arrow",
                              on_click=do_start).props("color=primary dense")

                ui.label(f"TZ: {status.get('timezone')}") \
                    .classes("text-xs text-gray-400")
                ui.label(f"Morning: {status.get('morning_cron')}") \
                    .classes("text-xs text-gray-400")
                ui.label(f"Evening: {status.get('evening_cron')}") \
                    .classes("text-xs text-gray-400")

            jobs = status.get("jobs", []) or []
            if jobs:
                ui.label("Next runs").classes("text-xs uppercase text-gray-500 mt-2")
                for j in jobs:
                    nxt = (j.get("next_run") or "—")[:19].replace("T", " ")
                    with ui.row().classes("items-center gap-3"):
                        ui.label(j["name"]).classes("w-56 text-sm")
                        ui.label(f"next: {nxt}").classes("text-sm font-mono text-gray-300")
            else:
                ui.label(
                    "No jobs scheduled. Set ENABLE_SCHEDULER=true in .env, then "
                    "restart the server."
                ).classes("text-xs text-gray-500 mt-2 italic")

            # Manual triggers — always available regardless of scheduler state.
            with ui.row().classes("items-center gap-2 mt-3"):
                async def run_morning() -> None:
                    try:
                        r = api.scheduler_run_morning()
                        ui.notify(f"Morning cycle queued (job {r['job_id'][:8]})",
                                  type="positive")
                        ui.navigate.to("/ai/morning")
                    except Exception as e:  # noqa: BLE001
                        ui.notify(f"Failed: {e}", type="negative")

                async def run_evening() -> None:
                    try:
                        r = api.scheduler_run_evening()
                        n = len(r.get("symbols_submitted") or [])
                        ui.notify(f"Evening cycle submitted {n} symbol(s)",
                                  type="positive")
                        ui.navigate.to("/ai/analyze")
                    except Exception as e:  # noqa: BLE001
                        ui.notify(f"Failed: {e}", type="negative")

                ui.button("Run morning now", icon="wb_sunny",
                          on_click=run_morning).props("color=primary")
                ui.button("Run evening now (watchlist)", icon="nights_stay",
                          on_click=run_evening).props("color=primary outline")

            last = status.get("last_runs") or {}
            if last:
                ui.label("Last runs").classes("text-xs uppercase text-gray-500 mt-2")
                for key, info in last.items():
                    when = (info.get("at") or "")[:19].replace("T", " ")
                    extra = ""
                    if info.get("job_id"):
                        extra = f"  job={info['job_id'][:8]}"
                    elif info.get("symbols_submitted"):
                        extra = f"  symbols={','.join(info['symbols_submitted'][:8])}"
                    suffix = "  (manual)" if info.get("manual") else ""
                    ui.label(f"  {key}: {when}{extra}{suffix}") \
                        .classes("text-xs text-gray-400 font-mono")


# --------------------------------------------------------------------------- #
# Watchlist section
# --------------------------------------------------------------------------- #


def _render_watchlist(container: ui.column) -> None:
    container.clear()

    new_sym = {"value": ""}
    new_notes = {"value": ""}

    with container:
        # Add form
        with ui.row().classes("items-end gap-2 w-full"):
            sym_in = ui.input(label="Symbol", placeholder="e.g. NVDA") \
                .classes("w-40").props("dense outlined")
            notes_in = ui.input(label="Notes (optional)",
                                placeholder="why we're watching this") \
                .classes("flex-1").props("dense outlined")

            def add() -> None:
                sym = (sym_in.value or "").strip().upper()
                if not sym:
                    ui.notify("Type a symbol first", type="warning")
                    return
                try:
                    r = api.watchlist_add(sym, notes_in.value or None)
                    if r.get("added"):
                        ui.notify(f"Added {sym} to watchlist", type="positive")
                    else:
                        ui.notify(f"{sym} already in watchlist", type="warning")
                    sym_in.set_value("")
                    notes_in.set_value("")
                    _render_watchlist(container)
                except Exception as e:  # noqa: BLE001
                    ui.notify(f"Add failed: {e}", type="negative")

            ui.button("Add", icon="add", on_click=add).props("color=primary")

        # Current list
        try:
            rows = api.watchlist_list()
        except Exception as e:  # noqa: BLE001
            ui.label(f"Failed to load: {e}").classes("text-red-400")
            return

        if not rows:
            ui.label("Watchlist is empty. Add symbols above.") \
                .classes("text-gray-500 italic mt-2")
            return

        with ui.column().classes("w-full gap-1 mt-2"):
            with ui.row().classes("w-full text-xs text-gray-500 uppercase px-3"):
                ui.label("Symbol").classes("w-20")
                ui.label("Enabled").classes("w-20 text-center")
                ui.label("Added").classes("w-44 font-mono")
                ui.label("Notes").classes("flex-1")
                ui.label("").classes("w-20")  # remove button col

            for r in rows:
                with ui.card().classes("w-full py-2"):
                    with ui.row().classes("w-full items-center gap-2"):
                        ui.label(r["symbol"]).classes("w-20 font-bold")

                        enabled_val = bool(r.get("enabled", 1))
                        sw = ui.switch(value=enabled_val) \
                            .classes("w-20").props("dense")
                        def _toggle(s=r["symbol"], switch=sw) -> None:
                            try:
                                api.watchlist_toggle(s, bool(switch.value))
                            except Exception as e:  # noqa: BLE001
                                ui.notify(f"Toggle failed: {e}", type="negative")
                        sw.on("update:model-value", _toggle)

                        ui.label((r.get("added_at") or "")[:19].replace("T", " ")) \
                            .classes("w-44 text-xs text-gray-400 font-mono")
                        ui.label(r.get("notes") or "—") \
                            .classes("flex-1 text-xs text-gray-300")

                        def _remove(s=r["symbol"]) -> None:
                            try:
                                api.watchlist_remove(s)
                                ui.notify(f"Removed {s}", type="positive")
                                _render_watchlist(container)
                            except Exception as e:  # noqa: BLE001
                                ui.notify(f"Remove failed: {e}", type="negative")
                        ui.button("Remove", icon="close", on_click=_remove) \
                            .props("flat dense color=negative").classes("w-20")


# --------------------------------------------------------------------------- #
# Telegram section
# --------------------------------------------------------------------------- #


def _render_telegram(container: ui.column) -> None:
    container.clear()
    with container:
        with ui.card().classes("w-full"):
            ui.label(
                "Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in .env. "
                "PM verdicts (APPROVE/RESIZE) and morning briefings auto-send."
            ).classes("text-xs text-gray-400")

            async def do_test() -> None:
                try:
                    r = api.telegram_test()
                    if r.get("sent"):
                        ui.notify("Test message sent — check Telegram",
                                  type="positive")
                    elif not r.get("configured"):
                        ui.notify("Telegram is not configured. Add token + chat_id to .env.",
                                  type="warning")
                    else:
                        ui.notify("Send failed — see /telegram/log for details",
                                  type="negative")
                    _render_telegram(container)  # refresh the log
                except Exception as e:  # noqa: BLE001
                    ui.notify(f"Test failed: {e}", type="negative")

            ui.button("Send test message", icon="send", on_click=do_test) \
                .props("color=primary outline")

        # Recent log
        try:
            log = api.telegram_log(limit=20)
        except Exception as e:  # noqa: BLE001
            ui.label(f"Failed to load log: {e}").classes("text-red-400")
            return

        if not log:
            ui.label("No messages sent yet.") \
                .classes("text-gray-500 italic mt-2")
            return

        ui.label("Recent messages").classes("text-xs uppercase text-gray-500 mt-2")
        for row in log:
            color = "border-green-500" if row.get("success") else "border-red-500"
            with ui.card().classes(f"w-full border-l-4 {color} py-1"):
                with ui.row().classes("w-full items-center gap-3"):
                    ui.label((row.get("sent_at") or "")[:19].replace("T", " ")) \
                        .classes("w-44 text-xs text-gray-400 font-mono")
                    ui.label(row.get("kind") or "—").classes("w-32 text-xs")
                    ui.label(row.get("symbol") or "").classes("w-16 text-xs")
                    ok_text = "sent" if row.get("success") else f"FAIL: {(row.get('error') or '')[:60]}"
                    ui.label(ok_text).classes(
                        "text-xs " + ("text-green-400" if row.get("success")
                                       else "text-red-400")
                    )
                ui.label((row.get("text") or "")[:300]) \
                    .classes("text-xs text-gray-300 whitespace-pre-wrap break-all")
