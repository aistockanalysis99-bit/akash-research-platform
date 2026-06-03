"""AI Analysis page — start a run, see ALL active + recent jobs.

Survives navigation: every time the page renders, it asks the API for the
current job list and shows everything still running. So you can hit Run, go
to Decisions, come back, and the in-flight pipeline is still visible.
"""
from __future__ import annotations

from typing import Any

from nicegui import ui

from ..api_client import api
from .layout import page_header


# Human labels for the pipeline stages.
STAGE_DISPLAY = {
    "init":              "Initializing",
    "prefetch":          "Fetching FMP + UW + portfolio + peers",
    "analysts":          "6 analysts (Fundamental + News + Technical + "
                          "Institutional + Options + Macro)",
    "debate":            "Bull + Bear",
    "judge":             "Debate Judge",
    "risk_manager":      "Risk Manager",
    "pm":                "Portfolio Manager (Opus)",
    "summary":           "Executive summary",
    "profile_build":     "Profile build / refresh",
    "notify":            "Telegram delivery",
    "done":              "Complete",
}
STAGE_ORDER = ["init", "prefetch", "analysts", "debate", "judge",
                "risk_manager", "pm", "summary", "profile_build",
                "notify", "done"]


def render_ai_analyze() -> None:
    page_header(active="AI Analysis")

    with ui.column().classes("w-full max-w-5xl mx-auto p-4 gap-4"):
        ui.label("Analyze a Ticker").classes("text-2xl font-bold")
        ui.label(
            "Run the 9-agent pipeline on any US large-cap ticker. "
            "Runs survive page navigation — switch tabs and come back, "
            "your in-flight jobs are still here."
        ).classes("text-sm text-gray-400")

        # ----------------------------- Form ----------------------------- #
        with ui.card().classes("w-full"):
            with ui.row().classes("w-full gap-3 items-end"):
                symbol_in = ui.input(label="Symbol", placeholder="e.g. NVDA") \
                    .classes("flex-1").props("dense outlined")
                source_sel = ui.select(
                    options={"manual": "Manual", "quant": "Quant", "external": "External"},
                    label="Source", value="manual",
                ).classes("w-40").props("dense outlined")
                run_btn = ui.button("Run Analysis", icon="play_arrow") \
                    .props("color=primary")
            notes_in = ui.input(label="Notes (optional)",
                                placeholder="Why are we analyzing this today?") \
                .classes("w-full").props("dense outlined")

        # ----------------------------- Job list ----------------------------- #
        ui.label("Jobs").classes("text-lg font-semibold mt-2")
        job_panel = ui.column().classes("w-full gap-2")

        # Tracks the rendered signature per job so we only rebuild on change.
        # This is the key to keeping ui.expansion state alive across polls.
        last_signatures: dict[str, str] = {}

        def refresh_jobs() -> None:
            try:
                jobs = api.ai_list_jobs()
            except Exception as e:  # noqa: BLE001
                job_panel.clear()
                with job_panel:
                    ui.label(f"Failed to load jobs: {e}").classes("text-red-400")
                return

            # Build a signature per job — if nothing changed, don't touch DOM.
            current: dict[str, str] = {}
            for j in jobs[:15]:
                jid = j.get("job_id", "")
                current[jid] = _job_signature(j)

            if current == last_signatures:
                # Nothing visible has changed since the last poll — leave the
                # rendered cards alone so any expanded panels stay open.
                return

            last_signatures.clear()
            last_signatures.update(current)

            # Running first, then most-recent finished
            def sort_key(j: dict) -> tuple:
                running = 0 if j.get("status") in ("queued", "running") else 1
                return (running, -_iso_to_int(j.get("started_at") or ""))

            jobs.sort(key=sort_key)
            jobs = jobs[:15]

            job_panel.clear()
            with job_panel:
                if not jobs:
                    ui.label("No jobs yet — start one above.") \
                        .classes("text-gray-500 italic")
                    return
                for j in jobs:
                    _render_job_card(j)

        def start() -> None:
            sym = (symbol_in.value or "").strip().upper()
            if not sym:
                ui.notify("Enter a ticker symbol first.", type="warning")
                return
            try:
                api.ai_analyze(sym, source_sel.value or "manual",
                                notes_in.value or None)
                ui.notify(f"Started pipeline for {sym}", type="positive")
                symbol_in.set_value("")
                notes_in.set_value("")
                refresh_jobs()  # immediate visual feedback
            except Exception as e:  # noqa: BLE001
                ui.notify(f"Failed to start: {e}", type="negative")

        run_btn.on("click", start)

        # Poll the API every 2s — refreshes all visible job cards.
        ui.timer(2.0, refresh_jobs)
        refresh_jobs()


# --------------------------------------------------------------------------- #
# Job card
# --------------------------------------------------------------------------- #


def _render_job_card(j: dict[str, Any]) -> None:
    status = j.get("status", "unknown")
    symbol = j.get("symbol", "?")
    job_id = j.get("job_id", "?")
    short_id = job_id[:8]
    started = j.get("started_at", "")[:19].replace("T", " ")
    current_stage = j.get("current_stage") or "queued"
    current_msg = j.get("current_msg") or ""
    verdict = j.get("verdict") or {}
    signal_date = j.get("signal_date")
    stages = j.get("stages") or []
    # Find the latest stage event with model info to surface in the header
    latest_with_model = next(
        (s for s in reversed(stages) if s.get("model")), None,
    )

    # Color the left border per status
    border_color = {
        "running":  "border-cyan-500",
        "queued":   "border-gray-500",
        "complete": "border-green-500",
        "failed":   "border-red-500",
    }.get(status, "border-gray-700")

    with ui.card().classes(f"w-full border-l-4 {border_color}"):
        with ui.row().classes("w-full items-center gap-3 flex-wrap"):
            # Symbol + short id
            ui.label(symbol).classes("text-xl font-bold w-24")
            ui.label(f"#{short_id}").classes("text-xs text-gray-500 font-mono")
            ui.label(started).classes("text-xs text-gray-500")

            ui.space()

            # Status badge
            if status == "running" or status == "queued":
                ui.spinner(size="sm")
                ui.label(STAGE_DISPLAY.get(current_stage, current_stage)) \
                    .classes("text-sm text-cyan-400")
            elif status == "complete":
                decision = verdict.get("decision", "—")
                conviction = verdict.get("conviction", "—")
                size_pct = verdict.get("size_pct", "—")
                color = {
                    "APPROVE": "positive", "RESIZE": "warning",
                    "REJECT": "negative",
                }.get(decision, "info")
                ui.badge(f"{decision} {conviction}/10  •  {size_pct}%",
                         color=color).classes("text-sm")
                if signal_date:
                    ui.button("Open", icon="open_in_new",
                              on_click=lambda s=symbol, d=signal_date:
                              ui.navigate.to(f"/ai/decisions/{s}/{d}")) \
                        .props("flat dense color=primary")
            elif status == "failed":
                ui.badge("FAILED", color="negative").classes("text-sm")

        # Current line — shows msg + model if known
        if status in ("running", "queued"):
            tail = ""
            if latest_with_model and latest_with_model.get("model"):
                tail = f"  ·  using {latest_with_model['model']}"
            ui.label(f"{current_msg}{tail}").classes("text-xs text-gray-400 ml-1")

        # Stage progress dots
        _render_stage_dots(j)

        # Per-agent scorecards — visible after analysis completes
        if status == "complete" and signal_date:
            _render_agent_scorecards(symbol, signal_date)

        # Detailed stage timeline — collapsible, holds full context per event
        if stages:
            with ui.expansion("Stage timeline", icon="timeline").classes("w-full"):
                for s in stages:
                    _render_stage_event(s)

        # Error tail — full text, properly wrapped, with a hint for known issues.
        if status == "failed":
            err = (j.get("error") or "")
            hint = _error_hint(err)
            with ui.expansion("Error details", value=True).classes("w-full"):
                if hint:
                    ui.label(hint).classes("text-yellow-300 text-sm mb-1")
                # ui.code wraps long lines and is selectable, unlike fenced markdown.
                ui.code(err[:4000]).classes("w-full whitespace-pre-wrap break-all text-xs")


def _render_agent_scorecards(symbol: str, signal_date: str) -> None:
    """Grid of per-agent cards: emoji + label + score + 1-line summary.

    Reads from /ai/decisions/{symbol}/{date}/scorecards which parses
    _raw.json on disk. Shown only when an analysis has completed.
    """
    try:
        cards = api.ai_get_scorecards(symbol, signal_date)
    except Exception:  # noqa: BLE001 — never break the job-card UI
        return
    if not cards:
        return

    # Map agent names → tailwind color shades by family
    family_color = {
        "fundamental":         "bg-blue-900/40 border-blue-500",
        "news":                "bg-purple-900/40 border-purple-500",
        "technical":           "bg-cyan-900/40 border-cyan-500",
        "institutional_flow":  "bg-yellow-900/40 border-yellow-600",
        "options_structure":   "bg-orange-900/40 border-orange-500",
        "macro_regime":        "bg-pink-900/40 border-pink-500",
        "bull":                "bg-green-900/40 border-green-500",
        "bear":                "bg-red-900/40 border-red-500",
        "judge":               "bg-indigo-900/40 border-indigo-500",
        "risk":                "bg-amber-900/40 border-amber-500",
        "pm":                  "bg-emerald-900/40 border-emerald-500",
    }

    with ui.expansion("Agent scorecards", icon="dashboard", value=True) \
            .classes("w-full"):
        ui.label(f"{len(cards)} agents · click any to open the full report") \
            .classes("text-xs text-gray-500 mb-2")
        # 3 cards per row on wide screens, 2 on medium, 1 on small
        with ui.grid(columns=3).classes("w-full gap-3"):
            for c in cards:
                color = family_color.get(c["name"], "bg-slate-800 border-slate-500")
                with ui.card().classes(
                    f"border-l-4 {color} cursor-pointer hover:scale-[1.01] "
                    "transition-transform"
                ).on(
                    "click",
                    lambda s=symbol, d=signal_date:
                    ui.navigate.to(f"/ai/decisions/{s}/{d}"),
                ):
                    with ui.row().classes("items-center gap-2 w-full"):
                        ui.label(c.get("emoji") or "·").classes("text-xl")
                        ui.label(c.get("label") or c.get("name")).classes(
                            "text-sm font-semibold flex-1"
                        )
                        score_val = c.get("score_value")
                        if score_val is not None and score_val != "":
                            if isinstance(score_val, (int, float)):
                                ui.badge(f"{c.get('score_label','')}: {score_val}/10",
                                         color="primary").classes("text-xs")
                            else:
                                ui.badge(f"{c.get('score_label','')}: {score_val}",
                                         color="primary").classes("text-xs")
                    summary = c.get("summary") or ""
                    if summary:
                        ui.label(summary).classes(
                            "text-xs text-gray-300 mt-1 leading-snug"
                        )


def _render_stage_event(s: dict[str, Any]) -> None:
    """One line in the expanded stage timeline — richer than the dot rail."""
    bits: list[str] = [f"[{s.get('stage', '?')}]"]
    if s.get("agent"):
        bits.append(f"@{s['agent']}")
    bits.append(s.get("msg") or "")
    tail_pieces: list[str] = []
    if s.get("model"):
        tail_pieces.append(s["model"])
    if s.get("action"):
        tail_pieces.append(s["action"])
    metrics = s.get("metrics") or {}
    if metrics:
        m_str = ", ".join(f"{k}={v}" for k, v in metrics.items() if v is not None)
        if m_str:
            tail_pieces.append(m_str)
    tail = f"   · {' • '.join(tail_pieces)}" if tail_pieces else ""
    ui.label(" ".join(bits) + tail).classes(
        "text-xs text-gray-400 font-mono whitespace-pre-wrap"
    )


def _render_stage_dots(j: dict[str, Any]) -> None:
    """Six little dots — green for completed stages, blue spinner for current."""
    seen_stages = {s["stage"] for s in (j.get("stages") or [])}
    current = j.get("current_stage")
    status = j.get("status")

    with ui.row().classes("gap-1 mt-1 items-center"):
        for stage in STAGE_ORDER:
            if stage not in (set(STAGE_DISPLAY.keys())):
                continue
            if status == "complete" or stage in seen_stages:
                # Either already passed through or finished entirely
                done = (stage in seen_stages) or status == "complete"
                if stage == current and status not in ("complete",):
                    color = "cyan"
                else:
                    color = "green" if done else "grey-7"
            else:
                color = "grey-7"
            ui.icon("circle", color=color, size="xs")
            ui.label(STAGE_DISPLAY.get(stage, stage)).classes("text-xs text-gray-400 mr-2")


def _iso_to_int(iso: str) -> int:
    """Sortable int from an ISO timestamp string. Empty/bad strings sort last."""
    if not iso:
        return 0
    digits = "".join(ch for ch in iso if ch.isdigit())
    return int(digits[:14]) if digits else 0


def _job_signature(j: dict[str, Any]) -> str:
    """A stable string that changes ONLY when something visible about the job changed.

    Used to gate panel re-renders so expanded sections (error details, etc.)
    don't get torn down on every poll.
    """
    verdict = j.get("verdict") or {}
    error_hash = str(hash(j.get("error") or ""))[:8] if j.get("error") else ""
    return "|".join([
        j.get("status", ""),
        j.get("current_stage", "") or "",
        (j.get("current_msg") or "")[:80],
        str(verdict.get("decision", "")),
        str(verdict.get("conviction", "")),
        str(verdict.get("size_pct", "")),
        error_hash,
    ])


def _error_hint(err: str) -> str:
    """Translate common error patterns into one-line plain-English hints."""
    if not err:
        return ""
    low = err.lower()
    if "resource_exhausted" in low or "429" in low or "quota" in low:
        return (
            "Hint: Gemini free-tier quota exhausted. Either wait (the per-minute "
            "limit resets in ~60s; the daily limit at UTC midnight) or enable "
            "billing on the Google AI project to lift the cap."
        )
    if "anthropic" in low and ("rate" in low or "429" in low):
        return "Hint: Anthropic rate-limited. Wait 30-60s and retry."
    if "fmp" in low and ("429" in low or "rate" in low):
        return "Hint: FMP rate-limited. Wait a minute, the throttle will recover."
    if "402" in low or "premium" in low:
        return "Hint: an endpoint requires a higher FMP/LLM plan tier."
    if "different loop" in low or "attached to a different" in low:
        return "Hint: event loop bug — please report; we thought this was fixed."
    return ""
