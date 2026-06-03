"""New Backtest page: parameter form, universe, dates, run button."""
from __future__ import annotations

from datetime import datetime, timedelta

from nicegui import ui

from ..api_client import api
from .layout import page_header


def render_new_backtest() -> None:
    page_header(active="New Backtest")

    with ui.column().classes("w-full max-w-7xl mx-auto p-4 gap-4"):
        ui.label("Configure & Run Backtest").classes("text-2xl font-bold")
        ui.label("Pick parameters, then click Run. Default values match the PDF spec.") \
            .classes("text-sm text-gray-400")

        # Default state
        state = {
            "params": {
                "skip_bars": 5, "mom_short_len": 21, "mom_med_len": 63, "mom_long_len": 126,
                "w_short": 0.20, "w_med": 0.40, "w_long": 0.40,
                "vol_lookback": 20, "annualization_factor": 252,
                "entry_threshold": 0.25, "exit_threshold": 0.00,
                "fast_len": 50, "slow_len": 150, "slope_bars": 5, "breakout_len": 20,
                "atr_len": 20, "stop_atr": 2.5, "trail_atr": 3.0, "breakeven_rr": 1.0,
                "risk_pct": 0.005, "target_vol": 0.10,
                "max_lev_scalar": 1.50, "max_gross_exp": 1.50,
                "enable_scale_in": True, "max_adds": 2, "add_atr": 0.75, "add_frac": 0.50,
                "enable_partial_tp": True, "partial_pct": 50, "take_profit_rr": 2.0,
                "max_bars_in_trade": 120,
                "max_concurrent_positions": 10,
                "portfolio_vol_target": 0.10, "max_portfolio_gross": 1.0,
                "commission_bps": 2.0, "slippage_bps": 1.0,
                "fractional_shares": False,
            },
            "universe": "smoke",
            "timeframe": "1D",
            "start_date": (datetime.now() - timedelta(days=365)).date().isoformat(),
            "end_date": datetime.now().date().isoformat(),
            "initial_capital": 100_000.0,
            "run_name": "",
        }

        # Layout: 2 columns - left = params, right = universe + run
        with ui.row().classes("w-full gap-4 items-start"):
            # ----- Left: Parameters in expansions -----
            with ui.column().classes("flex-1 min-w-[420px] gap-2"):
                ui.label("Strategy Parameters").classes("text-lg font-semibold mt-1")

                # Preset loader
                with ui.row().classes("w-full items-end gap-2"):
                    presets = api.list_params()
                    preset_names = [p["name"] for p in presets]
                    preset_sel = ui.select(options=preset_names if preset_names else ["(no presets)"],
                                            label="Load Preset").classes("flex-1")
                    def load_preset() -> None:
                        nm = preset_sel.value
                        if not nm or nm == "(no presets)":
                            return
                        loaded = api.get_params(nm)
                        for k, v in loaded["params"].items():
                            if k in state["params"]:
                                state["params"][k] = v
                        ui.notify(f"Loaded preset '{nm}'. Refreshing fields...", type="positive")
                        # Refresh inputs by reloading the page
                        ui.navigate.to("/backtest")
                    ui.button("Load", on_click=load_preset).props("flat")

                # ---- Signal group ----
                with ui.expansion("Signal", icon="trending_up").classes("w-full").props('default-opened'):
                    with ui.grid(columns=2).classes("w-full gap-2"):
                        _num_input("Skip Bars", state["params"], "skip_bars", min_=0, max_=20)
                        _num_input("Short Horizon", state["params"], "mom_short_len", min_=5, max_=60)
                        _num_input("Medium Horizon", state["params"], "mom_med_len", min_=10, max_=200)
                        _num_input("Long Horizon", state["params"], "mom_long_len", min_=20, max_=500)
                        _num_input("Weight Short", state["params"], "w_short", step=0.05)
                        _num_input("Weight Medium", state["params"], "w_med", step=0.05)
                        _num_input("Weight Long", state["params"], "w_long", step=0.05)
                        _num_input("Vol Lookback", state["params"], "vol_lookback", min_=5)
                        _num_input("Annualization", state["params"], "annualization_factor", min_=1)
                        _num_input("Entry Threshold", state["params"], "entry_threshold", step=0.05)
                        _num_input("Soft-Exit Threshold", state["params"], "exit_threshold", step=0.05)

                # ---- Trend ----
                with ui.expansion("Trend Confirmation", icon="show_chart").classes("w-full"):
                    with ui.grid(columns=2).classes("w-full gap-2"):
                        _num_input("Fast EMA", state["params"], "fast_len", min_=2)
                        _num_input("Slow EMA", state["params"], "slow_len", min_=3)
                        _num_input("Slow EMA Slope Bars", state["params"], "slope_bars", min_=1)
                        _num_input("Breakout Length", state["params"], "breakout_len", min_=2)

                # ---- Risk ----
                with ui.expansion("Risk & Sizing", icon="security").classes("w-full"):
                    with ui.grid(columns=2).classes("w-full gap-2"):
                        _num_input("ATR Length", state["params"], "atr_len", min_=1)
                        _num_input("Initial Stop ATR", state["params"], "stop_atr", step=0.1)
                        _num_input("Trailing Stop ATR", state["params"], "trail_atr", step=0.1)
                        _num_input("Breakeven Trigger R", state["params"], "breakeven_rr", step=0.25)
                        _num_input("Risk % of Equity", state["params"], "risk_pct", step=0.001)
                        _num_input("Target Annualized Vol", state["params"], "target_vol", step=0.01)
                        _num_input("Max Leverage Scalar", state["params"], "max_lev_scalar", step=0.1)
                        _num_input("Max Gross Exposure x Eq", state["params"], "max_gross_exp", step=0.1)

                # ---- Scaling ----
                with ui.expansion("Scaling & Take-Profit", icon="add_chart").classes("w-full"):
                    with ui.grid(columns=2).classes("w-full gap-2"):
                        ui.checkbox("Enable Scale-In").bind_value(state["params"], "enable_scale_in")
                        _num_input("Max Add-Ons", state["params"], "max_adds", min_=0, max_=2)
                        _num_input("Scale-In Step ATR", state["params"], "add_atr", step=0.05)
                        _num_input("Add-On Size Fraction", state["params"], "add_frac", step=0.05)
                        ui.checkbox("Enable Partial TP").bind_value(state["params"], "enable_partial_tp")
                        _num_input("Partial TP Qty %", state["params"], "partial_pct", min_=1, max_=99)
                        _num_input("Partial TP R Multiple", state["params"], "take_profit_rr", step=0.25)
                        _num_input("Max Bars In Trade", state["params"], "max_bars_in_trade", min_=1)

                # ---- Portfolio (hybrid layer) ----
                with ui.expansion("Portfolio (Hybrid Layer)", icon="dashboard").classes("w-full"):
                    with ui.grid(columns=2).classes("w-full gap-2"):
                        _num_input("Max Concurrent Positions", state["params"], "max_concurrent_positions", min_=1)
                        _num_input("Portfolio Vol Target", state["params"], "portfolio_vol_target", step=0.01)
                        _num_input("Max Portfolio Gross", state["params"], "max_portfolio_gross", step=0.1)

                # ---- Costs / Execution ----
                with ui.expansion("Costs & Execution", icon="payments").classes("w-full"):
                    with ui.grid(columns=2).classes("w-full gap-2"):
                        _num_input("Commission (bps/side)", state["params"], "commission_bps", step=0.5)
                        _num_input("Slippage (bps/side)", state["params"], "slippage_bps", step=0.5)
                        ui.checkbox("Allow Fractional Shares").bind_value(state["params"], "fractional_shares")

                # Save preset
                ui.separator()
                with ui.row().classes("w-full items-end gap-2"):
                    preset_name_input = ui.input("Save current as preset").classes("flex-1")
                    def save_preset() -> None:
                        nm = (preset_name_input.value or "").strip()
                        if not nm:
                            ui.notify("Enter a preset name.", type="warning")
                            return
                        api.save_params(nm, state["params"])
                        ui.notify(f"Saved preset '{nm}'", type="positive")
                    ui.button("Save", on_click=save_preset).props("color=secondary")

            # ----- Right: Run config -----
            with ui.column().classes("min-w-[360px] max-w-[420px] gap-3"):
                ui.label("Backtest Configuration").classes("text-lg font-semibold mt-1")
                with ui.card().classes("w-full"):
                    universes = api.list_universes()
                    universe_sel = ui.select(options=universes, label="Universe", value=state["universe"]) \
                        .classes("w-full").bind_value(state, "universe")

                    universe_count_lbl = ui.label("").classes("text-xs text-gray-400")

                    def update_count() -> None:
                        try:
                            u = api.get_universe(state["universe"])
                            universe_count_lbl.text = f"{u['count']} symbols in {state['universe']}"
                        except Exception as e:
                            universe_count_lbl.text = f"error: {e}"
                    update_count()
                    universe_sel.on("update:model-value", lambda *_: update_count())

                    ui.select(options=["1D", "1W", "4h", "1h", "30m", "15m"],
                              label="Timeframe", value=state["timeframe"]) \
                        .classes("w-full").bind_value(state, "timeframe")

                    with ui.row().classes("w-full gap-2"):
                        with ui.input("Start Date").bind_value(state, "start_date").classes("flex-1") as start_input:
                            with ui.menu().props("no-parent-event") as menu:
                                with ui.date().bind_value(state, "start_date"):
                                    ui.button("Close", on_click=menu.close).props("flat")
                            with start_input.add_slot("append"):
                                ui.icon("event").on("click", menu.open).classes("cursor-pointer")
                        with ui.input("End Date").bind_value(state, "end_date").classes("flex-1") as end_input:
                            with ui.menu().props("no-parent-event") as menu2:
                                with ui.date().bind_value(state, "end_date"):
                                    ui.button("Close", on_click=menu2.close).props("flat")
                            with end_input.add_slot("append"):
                                ui.icon("event").on("click", menu2.open).classes("cursor-pointer")

                    ui.number("Initial Capital", value=state["initial_capital"], step=10_000) \
                        .classes("w-full").bind_value(state, "initial_capital")
                    ui.input("Run Name (optional)").classes("w-full").bind_value(state, "run_name")

                # Run button
                def on_run() -> None:
                    payload = {
                        "universe": state["universe"],
                        "timeframe": state["timeframe"],
                        "start_date": _iso(state["start_date"]),
                        "end_date": _iso(state["end_date"]),
                        "initial_capital": float(state["initial_capital"]),
                        "params": state["params"],
                        "run_name": state["run_name"] or None,
                    }
                    try:
                        resp = api.run_backtest(payload)
                        ui.notify(f"Started: {resp['name']}", type="positive")
                        ui.navigate.to(f"/runs/{resp['run_id']}")
                    except Exception as e:
                        ui.notify(f"Failed: {e}", type="negative")

                ui.button("Run Backtest", on_click=on_run).classes("w-full") \
                    .props('size=lg color=primary unelevated icon=play_arrow')


def _num_input(label: str, target: dict, key: str, min_=None, max_=None, step=None):
    n = ui.number(label, value=target.get(key, 0))
    if min_ is not None:
        n.props(f"min={min_}")
    if max_ is not None:
        n.props(f"max={max_}")
    if step is not None:
        n.props(f"step={step}")
    n.classes("w-full")
    n.bind_value(target, key)
    return n


def _iso(d) -> str:
    if isinstance(d, str):
        if "T" in d:
            return d
        return f"{d}T00:00:00"
    return f"{d.isoformat()}T00:00:00"
