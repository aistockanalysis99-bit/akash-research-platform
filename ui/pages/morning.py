"""Morning Cycle page — daily position-management briefing.

Layout:
    [Run Morning Cycle button]
    [Active / recent jobs panel]      ← refreshed every 2s
    [Recent briefings list]            ← read from disk
"""
from __future__ import annotations

from typing import Any

from nicegui import ui

from ..api_client import api
from .layout import page_header


STAGE_DISPLAY = {
    "init":              "Initializing",
    "market_data":       "Fetching SPY + sector data",
    "regime":            "Market Regime Detector",
    "position_monitor":  "Position Monitor (batch)",
    "exit_confirmer":    "Exit Confirmer",
    "exits_executed":    "Closing positions",
    "morning_briefing":  "Daily Briefing",
    "done":              "Complete",
}


def render_morning() -> None:
    page_header(active="Morning")

    with ui.column().classes("w-full max-w-6xl mx-auto p-4 gap-4"):
        ui.label("Morning Cycle").classes("text-2xl font-bold")
        ui.label(
            "Daily position-management pass: detect market regime, review every "
            "open position, second-opinion any exits, write the client briefing. "
            "Auto-closes paper positions on confirmed EXIT."
        ).classes("text-sm text-gray-400")

        # ----------- Run button -----------
        with ui.row().classes("w-full items-center gap-3"):
            run_btn = ui.button("Run Morning Cycle", icon="wb_sunny") \
                .props("color=primary")
            status_label = ui.label("").classes("text-xs text-gray-500")

            def do_run() -> None:
                try:
                    r = api.ai_morning_run()
                    status_label.text = f"Queued (job {r['job_id'][:8]})"
                    ui.notify(f"Started morning cycle (job {r['job_id'][:8]})",
                              type="positive")
                    refresh_jobs()
                except Exception as e:  # noqa: BLE001
                    status_label.text = f"failed: {e}"
                    ui.notify(f"Failed to start: {e}", type="negative")

            run_btn.on("click", do_run)

        # ----------- Jobs panel -----------
        ui.label("Jobs").classes("text-lg font-semibold mt-3")
        jobs_panel = ui.column().classes("w-full gap-2")
        last_sig: dict[str, str] = {}

        def refresh_jobs() -> None:
            try:
                jobs = api.ai_morning_jobs()
            except Exception as e:  # noqa: BLE001
                jobs_panel.clear()
                with jobs_panel:
                    ui.label(f"Failed to load: {e}").classes("text-red-400")
                return

            current = {j.get("job_id", ""): _morning_job_sig(j) for j in jobs[:10]}
            if current == last_sig:
                return
            last_sig.clear()
            last_sig.update(current)

            jobs.sort(
                key=lambda j: (
                    0 if j.get("status") in ("running", "queued") else 1,
                    -_iso_to_int(j.get("started_at", "")),
                )
            )

            jobs_panel.clear()
            with jobs_panel:
                if not jobs:
                    ui.label("No morning cycles yet. Click Run above.") \
                        .classes("text-gray-500 italic")
                    return
                for j in jobs[:10]:
                    _render_morning_job_card(j)

        ui.timer(2.0, refresh_jobs)
        refresh_jobs()

        # ----------- Recent briefings (on disk) -----------
        ui.label("Past briefings").classes("text-lg font-semibold mt-4")
        dates_panel = ui.column().classes("w-full")

        try:
            dates = api.ai_morning_dates()
        except Exception as e:  # noqa: BLE001
            dates = []
            with dates_panel:
                ui.label(f"Failed to list: {e}").classes("text-red-400")

        if dates:
            with dates_panel:
                for d in dates[:30]:
                    with ui.card().classes("w-full"):
                        with ui.row().classes("items-center gap-3"):
                            ui.label(d).classes("text-base font-mono w-32")
                            ui.button("View", icon="open_in_new",
                                      on_click=lambda dd=d:
                                      ui.navigate.to(f"/ai/morning/{dd}")) \
                                .props("flat color=primary")
        else:
            with dates_panel:
                ui.label("No past briefings yet — run one above.") \
                    .classes("text-gray-500 italic")


def render_morning_detail(date_iso: str) -> None:
    page_header(active="Morning")

    with ui.column().classes("w-full max-w-6xl mx-auto p-4 gap-3"):
        with ui.row().classes("items-center gap-3"):
            ui.link("← All briefings", "/ai/morning").classes(
                "text-sm text-gray-400 hover:text-cyan-400"
            ).props("no-underline")
            ui.label(f"Morning Cycle — {date_iso}").classes("text-2xl font-bold")

        try:
            files = api.ai_morning_files(date_iso)
        except Exception as e:  # noqa: BLE001
            ui.label(f"Failed to load: {e}").classes("text-red-400")
            return

        if not files:
            ui.label("No artifacts found for this date.").classes("text-gray-500 italic")
            return

        # Order: regime, position_monitor, briefing, then any exit_confirmer_*.
        order_keys = ["10_regime", "11_position_monitor", "13_morning_briefing"]
        ordered = []
        for k in order_keys:
            if k in files:
                ordered.append((k, files[k]))
        # Then exit confirmers
        for k in sorted(files):
            if k.startswith("12_exit_confirmer"):
                ordered.append((k, files[k]))
        # Anything else
        for k in sorted(files):
            if k not in [o[0] for o in ordered]:
                ordered.append((k, files[k]))

        # Two-column: left rail (file list), right (markdown view)
        selected = {"key": ordered[0][0] if ordered else ""}
        with ui.row().classes("w-full gap-4 items-start"):
            with ui.column().classes("w-72 gap-1"):
                ui.label("Stages").classes(
                    "text-xs text-gray-500 uppercase mt-2 mb-1"
                )
                btn_refs: dict[str, ui.button] = {}
                md_holder = {"view": None}

                def pretty(k: str) -> str:
                    return (k.replace("_", " ")
                              .replace("10 ", "1. ")
                              .replace("11 ", "2. ")
                              .replace("12 ", "3. ")
                              .replace("13 ", "4. ")
                              .title())

                def select(k: str) -> None:
                    selected["key"] = k
                    md_holder["view"].content = files.get(k, "")
                    for kk, b in btn_refs.items():
                        cls = (
                            "w-full text-left bg-slate-800 text-cyan-400 font-semibold"
                            if kk == k else
                            "w-full text-left text-gray-200 hover:text-cyan-400"
                        )
                        b.classes(replace=cls)

                for k, _md in ordered:
                    btn_refs[k] = ui.button(
                        pretty(k),
                        on_click=lambda kk=k: select(kk),
                    ).props("flat align=left").classes(
                        "w-full text-left text-gray-200 hover:text-cyan-400"
                    )

            with ui.column().classes("flex-1 min-w-0"):
                with ui.card().classes("w-full"):
                    md_holder["view"] = ui.markdown(
                        files.get(selected["key"], "")
                    ).classes("w-full")
                select(selected["key"])


# --------------------------------------------------------------------------- #
# Job card
# --------------------------------------------------------------------------- #


def _render_morning_job_card(j: dict[str, Any]) -> None:
    status = j.get("status", "unknown")
    job_id = j.get("job_id", "?")
    date_iso = j.get("as_of_date", "?")
    started = j.get("started_at", "")[:19].replace("T", " ")
    current_stage = j.get("current_stage") or "queued"
    current_msg = j.get("current_msg") or ""

    border = {
        "running":  "border-cyan-500",
        "queued":   "border-gray-500",
        "complete": "border-green-500",
        "failed":   "border-red-500",
    }.get(status, "border-gray-700")

    with ui.card().classes(f"w-full border-l-4 {border}"):
        with ui.row().classes("w-full items-center gap-3 flex-wrap"):
            ui.label(date_iso).classes("text-base font-bold w-32 font-mono")
            ui.label(f"#{job_id[:8]}").classes("text-xs text-gray-500 font-mono")
            ui.label(started).classes("text-xs text-gray-500")

            ui.space()

            if status in ("running", "queued"):
                ui.spinner(size="sm")
                ui.label(STAGE_DISPLAY.get(current_stage, current_stage)) \
                    .classes("text-sm text-cyan-400")
            elif status == "complete":
                regime = j.get("regime") or {}
                if regime:
                    regime_color = {
                        "BULL_TRENDING": "positive",
                        "BULL_CHOPPY":  "positive",
                        "NEUTRAL":      "warning",
                        "RISK_OFF":     "warning",
                        "BEAR":         "negative",
                    }.get(regime.get("regime"), "info")
                    ui.badge(f"{regime.get('regime')} {regime.get('confidence')}/10",
                             color=regime_color).classes("text-sm")
                executed = j.get("executed_exits") or []
                if executed:
                    ui.badge(f"{len(executed)} exits", color="negative") \
                        .classes("text-sm")
                ui.button("Open", icon="open_in_new",
                          on_click=lambda d=date_iso:
                          ui.navigate.to(f"/ai/morning/{d}")) \
                    .props("flat dense color=primary")
            elif status == "failed":
                ui.badge("FAILED", color="negative").classes("text-sm")

        if status in ("running", "queued") and current_msg:
            ui.label(current_msg).classes("text-xs text-gray-400 ml-1 mt-1")

        # Stage history (compact)
        stages = j.get("stages") or []
        if stages and (status not in ("running", "queued") or len(stages) > 1):
            with ui.expansion("Stage detail", icon="list").classes("w-full"):
                for s in stages:
                    extras = []
                    if s.get("model"):
                        extras.append(s["model"])
                    if s.get("metrics"):
                        m = s["metrics"]
                        extras.append(", ".join(f"{k}={v}" for k, v in m.items()))
                    extras_str = f"  [{' • '.join(extras)}]" if extras else ""
                    ui.label(f"• [{s['stage']}] {s['msg']}{extras_str}") \
                        .classes("text-xs text-gray-400 font-mono")

        if status == "failed":
            err = j.get("error") or ""
            with ui.expansion("Error details", value=True).classes("w-full"):
                ui.code(err[:4000]).classes(
                    "w-full whitespace-pre-wrap break-all text-xs"
                )


def _morning_job_sig(j: dict[str, Any]) -> str:
    regime = j.get("regime") or {}
    return "|".join([
        j.get("status", ""), j.get("current_stage", "") or "",
        (j.get("current_msg") or "")[:80],
        str(regime.get("regime", "")), str(regime.get("confidence", "")),
        str(len(j.get("executed_exits") or [])),
        str(hash(j.get("error") or ""))[:8] if j.get("error") else "",
    ])


def _iso_to_int(iso: str) -> int:
    if not iso:
        return 0
    digits = "".join(ch for ch in iso if ch.isdigit())
    return int(digits[:14]) if digits else 0
