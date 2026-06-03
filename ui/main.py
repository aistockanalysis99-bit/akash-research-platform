"""NiceGUI app entry point. Routes pages to their renderers."""
from __future__ import annotations

from nicegui import app as nicegui_app
from nicegui import ui

from engine.config import UI_HOST, UI_PORT
from engine.logging_setup import get_logger

from .pages.ai_analyze import render_ai_analyze
from .pages.ai_decision_detail import render_ai_decision_detail
from .pages.ai_decisions import render_ai_decisions
from .pages.automation import render_automation
from .pages.compare import render_compare
from .pages.data_page import render_data_page
from .pages.memory import render_memory
from .pages.morning import render_morning, render_morning_detail
from .pages.profiles import render_profile_detail, render_profiles_list
from .pages.new_backtest import render_new_backtest
from .pages.params_page import render_params_page
from .pages.portfolio import render_portfolio
from .pages.run_detail import render_run_detail
from .pages.runs_list import render_runs_list
from .pages.weekly import render_weekly, render_weekly_detail
from .theme import apply_dark_theme

log = get_logger("ui.main")


@ui.page("/")
def page_home() -> None:
    # Client-facing landing = the portfolio, not the backtest form.
    apply_dark_theme()
    render_portfolio()


@ui.page("/backtest")
def page_backtest() -> None:
    # Quant/dev tool — reachable via the Admin menu, not the client nav.
    apply_dark_theme()
    render_new_backtest()


@ui.page("/runs")
def page_runs() -> None:
    apply_dark_theme()
    render_runs_list()


@ui.page("/runs/{run_id}")
def page_run_detail(run_id: str) -> None:
    apply_dark_theme()
    render_run_detail(run_id)


@ui.page("/compare")
def page_compare() -> None:
    apply_dark_theme()
    # Read repeated query params 'r=' from URL
    from nicegui import context
    request = context.client.request
    run_ids = request.query_params.getlist("r") if hasattr(request.query_params, "getlist") else []
    if not run_ids:
        # Fallback parse
        q = str(request.url.query) if request else ""
        run_ids = [v for k, v in (kv.split("=", 1) for kv in q.split("&") if "=" in kv) if k == "r"]
    render_compare(run_ids)


@ui.page("/data")
def page_data() -> None:
    apply_dark_theme()
    render_data_page()


@ui.page("/params")
def page_params() -> None:
    apply_dark_theme()
    render_params_page()


@ui.page("/ai/analyze")
def page_ai_analyze() -> None:
    apply_dark_theme()
    render_ai_analyze()


@ui.page("/ai/decisions")
def page_ai_decisions() -> None:
    apply_dark_theme()
    render_ai_decisions()


@ui.page("/ai/decisions/{symbol}/{date_iso}")
def page_ai_decision_detail(symbol: str, date_iso: str) -> None:
    apply_dark_theme()
    render_ai_decision_detail(symbol, date_iso)


@ui.page("/portfolio")
def page_portfolio() -> None:
    apply_dark_theme()
    render_portfolio()


@ui.page("/ai/morning")
def page_morning() -> None:
    apply_dark_theme()
    render_morning()


@ui.page("/ai/morning/{date_iso}")
def page_morning_detail(date_iso: str) -> None:
    apply_dark_theme()
    render_morning_detail(date_iso)


@ui.page("/automation")
def page_automation() -> None:
    apply_dark_theme()
    render_automation()


@ui.page("/ai/weekly")
def page_weekly() -> None:
    apply_dark_theme()
    render_weekly()


@ui.page("/ai/weekly/{date_iso}")
def page_weekly_detail(date_iso: str) -> None:
    apply_dark_theme()
    render_weekly_detail(date_iso)


@ui.page("/memory")
def page_memory() -> None:
    apply_dark_theme()
    render_memory()


@ui.page("/profiles")
def page_profiles() -> None:
    apply_dark_theme()
    render_profiles_list()


@ui.page("/profiles/{symbol}")
def page_profile_detail(symbol: str) -> None:
    apply_dark_theme()
    render_profile_detail(symbol)


def serve(open_browser: bool = True) -> None:
    """Run the NiceGUI app."""
    log.info("UI ready at http://%s:%d", UI_HOST, UI_PORT)
    ui.run(
        host=UI_HOST,
        port=UI_PORT,
        title="Akash Research Platform",
        dark=True,
        show=open_browser,
        reload=False,
        favicon="📈",
    )


if __name__ in {"__main__", "__mp_main__"}:
    serve()
