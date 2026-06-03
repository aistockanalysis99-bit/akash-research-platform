"""Virtual Portfolio page — paper-trade ledger.

Sections:
    - Snapshot strip (equity, cash, exposure, open count, realized P&L)
    - Today's Actions (positions created today)
    - Open Positions (with refresh + per-row close)
    - Closed Positions (history)
"""
from __future__ import annotations

from typing import Any, Optional

from nicegui import ui

from ..api_client import api
from .layout import page_header
from ..theme import kpi_card


def render_portfolio() -> None:
    page_header(active="Portfolio")

    with ui.column().classes("w-full max-w-7xl mx-auto p-4 gap-4"):
        ui.label("Virtual Portfolio").classes("text-2xl font-bold")
        ui.label(
            "Paper-trading ledger. APPROVE/RESIZE verdicts from the AI pipeline "
            "auto-create positions here. Click Refresh to re-fetch prices, "
            "check trailing stops, and update P&L."
        ).classes("text-sm text-gray-400")

        # =================== Snapshot strip =================== #
        snap_row = ui.row().classes("w-full gap-2 flex-wrap")

        def render_snapshot() -> None:
            snap_row.clear()
            try:
                s = api.portfolio_snapshot()
            except Exception as e:  # noqa: BLE001
                with snap_row:
                    ui.label(f"Snapshot load failed: {e}").classes("text-red-400")
                return
            with snap_row:
                kpi_card("Equity", _fmt_usd(s["equity"]), color="cyan-400",
                         help_text=f"start ${s['initial_capital']:,.0f}")
                pnl = s["realized_pnl"] + s["unrealized_pnl"]
                kpi_card("Total P&L",
                         _signed_usd(pnl),
                         color=_pnl_color(pnl))
                kpi_card("Realized", _signed_usd(s["realized_pnl"]),
                         color=_pnl_color(s["realized_pnl"]))
                kpi_card("Unrealized", _signed_usd(s["unrealized_pnl"]),
                         color=_pnl_color(s["unrealized_pnl"]))
                kpi_card("Cash", _fmt_usd(s["cash"]), color="gray-300")
                kpi_card("Gross Exposure", f"{s['gross_exposure_pct']:.1f}%",
                         color="gray-300")
                kpi_card("Open Positions", str(s["open_positions"]),
                         color="cyan-400")

        # =================== Action bar =================== #
        with ui.row().classes("w-full items-center gap-2 mt-1"):
            refresh_msg = ui.label("").classes("text-xs text-gray-500")

            def do_refresh() -> None:
                refresh_msg.text = "refreshing..."
                try:
                    result = api.portfolio_refresh()
                    msg = (f"Refreshed {result['refreshed']} • "
                           f"stop-closed {result['closed_by_stop']}")
                    if result.get("errors"):
                        msg += f" • errors: {len(result['errors'])}"
                    refresh_msg.text = msg
                    ui.notify(msg, type="positive")
                    render_snapshot()
                    render_today_panel()
                    render_open_panel()
                    render_closed_panel()
                except Exception as e:  # noqa: BLE001
                    refresh_msg.text = f"refresh failed: {e}"
                    ui.notify(f"Refresh failed: {e}", type="negative")

            ui.button("Refresh prices", icon="refresh", on_click=do_refresh) \
                .props("color=primary")

            async def do_close_all() -> None:
                from nicegui import app  # local import to avoid circular
                # Simple confirm via notify — Quasar dialog is heavy
                try:
                    r = api.portfolio_close_all()
                    n = r.get("closed_count", 0)
                    ui.notify(f"Closed {n} open position(s)", type="positive")
                    render_snapshot()
                    render_today_panel()
                    render_open_panel()
                    render_closed_panel()
                except Exception as e:  # noqa: BLE001
                    ui.notify(f"Close-all failed: {e}", type="negative")

            ui.button("Close all", icon="close", on_click=do_close_all) \
                .props("color=negative outline")

        # =================== Today's Actions =================== #
        ui.label("Today's Actions").classes("text-lg font-semibold mt-3")
        today_panel = ui.column().classes("w-full")

        def render_today_panel() -> None:
            today_panel.clear()
            try:
                rows = api.portfolio_today()
            except Exception as e:  # noqa: BLE001
                with today_panel:
                    ui.label(f"Load failed: {e}").classes("text-red-400")
                return
            with today_panel:
                if not rows:
                    ui.label("Nothing executed today. Run an analysis "
                             "with APPROVE/RESIZE to populate this.") \
                        .classes("text-gray-500 italic")
                    return
                _render_positions_table(rows, kind="open_or_closed")

        # =================== Open Positions =================== #
        ui.label("Open Positions").classes("text-lg font-semibold mt-3")
        open_panel = ui.column().classes("w-full")

        def render_open_panel() -> None:
            open_panel.clear()
            try:
                rows = api.portfolio_open()
            except Exception as e:  # noqa: BLE001
                with open_panel:
                    ui.label(f"Load failed: {e}").classes("text-red-400")
                return
            with open_panel:
                if not rows:
                    ui.label("No open positions.").classes("text-gray-500 italic")
                    return
                _render_positions_table(rows, kind="open")

        # =================== Closed Positions =================== #
        ui.label("Closed Positions").classes("text-lg font-semibold mt-3")
        closed_panel = ui.column().classes("w-full")

        def render_closed_panel() -> None:
            closed_panel.clear()
            try:
                rows = api.portfolio_closed()
            except Exception as e:  # noqa: BLE001
                with closed_panel:
                    ui.label(f"Load failed: {e}").classes("text-red-400")
                return
            with closed_panel:
                if not rows:
                    ui.label("No closed positions yet.").classes("text-gray-500 italic")
                    return
                _render_positions_table(rows, kind="closed")

        # Initial render
        render_snapshot()
        render_today_panel()
        render_open_panel()
        render_closed_panel()


# --------------------------------------------------------------------------- #
# Position table — same row schema works for open, closed, and today
# --------------------------------------------------------------------------- #


def _render_positions_table(rows: list[dict[str, Any]], kind: str) -> None:
    """kind: 'open' | 'closed' | 'open_or_closed' (today's actions)."""
    # Pull equity once so we can compute portfolio-weight per row.
    try:
        snap = api.portfolio_snapshot()
        equity = float(snap.get("equity") or 0) or 1.0
    except Exception:  # noqa: BLE001
        equity = 1.0

    columns = [
        {"name": "symbol", "label": "Symbol", "field": "symbol",
         "sortable": True, "align": "left"},
        {"name": "status", "label": "Status", "field": "status",
         "sortable": True, "align": "center"},
        {"name": "weight", "label": "Weight", "field": "weight",
         "sortable": True, "align": "right"},
        {"name": "entry", "label": "Entry", "field": "entry",
         "sortable": True, "align": "right"},
        {"name": "units", "label": "Units", "field": "units",
         "sortable": True, "align": "right"},
        {"name": "current", "label": "Current", "field": "current",
         "sortable": True, "align": "right"},
        {"name": "stop", "label": "Stop", "field": "stop",
         "sortable": True, "align": "right"},
        {"name": "pnl_usd", "label": "P&L $", "field": "pnl_usd",
         "sortable": True, "align": "right"},
        {"name": "pnl_pct", "label": "P&L %", "field": "pnl_pct",
         "sortable": True, "align": "right"},
        {"name": "days", "label": "Days", "field": "days",
         "sortable": True, "align": "right"},
        {"name": "verdict", "label": "Verdict", "field": "verdict",
         "sortable": True, "align": "center"},
        {"name": "exit_reason", "label": "Exit", "field": "exit_reason",
         "sortable": False, "align": "left"},
        {"name": "action", "label": "", "field": "action",
         "sortable": False, "align": "center"},
    ]

    display_rows = []
    for r in rows:
        if r["status"] == "closed":
            pnl_usd = r.get("final_pnl_usd")
            pnl_pct = r.get("final_pnl_pct")
            current_display = r.get("exit_price")
            # For a closed position the "weight" at exit is meaningless — use 0.
            weight_pct = 0.0
        else:
            pnl_usd = r.get("current_pnl_usd")
            pnl_pct = r.get("current_pnl_pct")
            current_display = r.get("current_price")
            mv = (r.get("units") or 0) * (
                r.get("current_price") or r.get("entry_price") or 0
            )
            weight_pct = (mv / equity * 100.0) if equity > 0 else 0.0

        display_rows.append({
            "id": r["id"],
            "symbol": r["symbol"],
            "status": r["status"],
            "weight": _fmt_weight(weight_pct, r["status"]),
            "entry": _fmt_money(r["entry_price"]),
            "units": _fmt_units(r["units"]),
            "current": _fmt_money(current_display),
            "stop": _fmt_money(r.get("trailing_stop") or r.get("initial_stop")),
            "pnl_usd": _signed_usd(pnl_usd) if pnl_usd is not None else "—",
            "pnl_pct": _fmt_pct(pnl_pct),
            "days": r.get("days_held", 0),
            "verdict": f"{r.get('decision_verdict','?')} {r.get('decision_conviction','?')}/10",
            "exit_reason": r.get("exit_reason") or "",
            "action": "open" if r["status"] == "open" else "",
            "_decision_symbol": r.get("decision_symbol") or r["symbol"],
            "_decision_date": r.get("decision_date"),
            "_position_id": r["id"],
        })

    table = ui.table(
        columns=columns, rows=display_rows, row_key="id", pagination=20,
    ).classes("w-full")

    # Color P&L columns
    table.add_slot("body-cell-pnl_usd", """
        <q-td :props="props">
            <span :class="(props.value || '').startsWith('-') ? 'text-red-400'
                          : (props.value === '—' || props.value === '$0' ? 'text-gray-400' : 'text-green-400')">
                {{ props.value }}
            </span>
        </q-td>
    """)
    table.add_slot("body-cell-pnl_pct", """
        <q-td :props="props">
            <span :class="(props.value || '').startsWith('-') ? 'text-red-400'
                          : (props.value === '—' || props.value === '0.00%' ? 'text-gray-400' : 'text-green-400')">
                {{ props.value }}
            </span>
        </q-td>
    """)
    table.add_slot("body-cell-status", """
        <q-td :props="props">
            <q-badge :color="props.value === 'open' ? 'cyan' : 'grey-7'" :label="props.value"/>
        </q-td>
    """)
    table.add_slot("body-cell-action", """
        <q-td :props="props">
            <q-btn v-if="props.row.action === 'open'"
                   flat dense color="negative" icon="close"
                   @click="$parent.$emit('close-position', props.row)">Close</q-btn>
        </q-td>
    """)

    def on_close_position(e) -> None:
        row = e.args
        position_id = row.get("_position_id")
        if not position_id:
            return
        try:
            api.portfolio_close(int(position_id), reason="manual")
            ui.notify(f"Closed position #{position_id}", type="positive")
            # Trigger a soft reload
            ui.navigate.to("/portfolio")
        except Exception as ex:  # noqa: BLE001
            ui.notify(f"Close failed: {ex}", type="negative")

    table.on("close-position", on_close_position)


# --------------------------------------------------------------------------- #
# Formatters
# --------------------------------------------------------------------------- #


def _fmt_usd(v: Optional[float]) -> str:
    if v is None:
        return "—"
    return f"${v:,.0f}"


def _signed_usd(v: Optional[float]) -> str:
    if v is None:
        return "—"
    sign = "-" if v < 0 else ""
    return f"{sign}${abs(v):,.0f}"


def _fmt_money(v: Optional[float]) -> str:
    if v is None:
        return "—"
    return f"${v:,.2f}"


def _fmt_units(v: Optional[float]) -> str:
    if v is None:
        return "—"
    return f"{v:,.4f}".rstrip("0").rstrip(".")


def _fmt_pct(v: Optional[float]) -> str:
    if v is None:
        return "—"
    return f"{v:+.2f}%"


def _fmt_weight(weight_pct: float, status: str) -> str:
    """Weight column. Closed positions don't have a current weight."""
    if status == "closed":
        return "—"
    return f"{weight_pct:.2f}%"


def _pnl_color(v: float) -> str:
    if v > 0:
        return "green-400"
    if v < 0:
        return "red-400"
    return "gray-400"
