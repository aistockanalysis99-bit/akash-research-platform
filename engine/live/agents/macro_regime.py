"""Agent 4d — Macro Regime per Ticker (Gemini Flash).

Reads broad market context from Unusual Whales market endpoints:
    - market-tide          (net call/put premium across all options)
    - sector-etfs          (sector ETF performance + flow)
    - economic-calendar    (upcoming FOMC, CPI, NFP)
Plus the symbol's own sector and price action.

Tells the PM: is the current regime risk-on or risk-off, where is the
rotation pointing, is this ticker aligned with the regime, and what's the
nearest high-impact macro event that could shake it.
"""
from __future__ import annotations

import json
from typing import Any

from ..renderers.macro_regime import render as render_md
from ..schemas import MacroRegimeReport
from ..state import SignalState
from .base import Agent


class MacroRegimeAgent(Agent):
    NAME = "macro_regime"
    LLM_TIER = "flash"
    REQUIRES_DATA = ["uw_market_tide", "uw_sector_etfs", "uw_econ_calendar",
                     "profile"]
    OUTPUT_SCHEMA = MacroRegimeReport
    STAGE = "macro_regime"
    PROMPT_FILE = "macro_regime.md"

    def build_prompt(self, state: SignalState) -> str:
        template = self.load_prompt_template()
        ctx = state.get("context", {})
        profile = ctx.get("profile") or {}

        return template.format(
            symbol=state["symbol"],
            as_of_date=state["signal_date"],
            ticker_sector=profile.get("sector") or "Unknown",
            market_tide_json=_dump(_project_tide(ctx.get("uw_market_tide") or [])),
            sector_etfs_json=_dump(_project_sectors(ctx.get("uw_sector_etfs") or [])),
            econ_calendar_json=_dump(_project_calendar(ctx.get("uw_econ_calendar") or [])),
        )

    def render(self, output: MacroRegimeReport) -> str:
        return render_md(output)


def _dump(obj: Any) -> str:
    return json.dumps(obj, indent=2, default=str, ensure_ascii=False)


def _project_tide(rows: list[dict]) -> list[dict]:
    """Last 10 minutes/hours of market tide."""
    return [
        {
            "time": r.get("time") or r.get("date"),
            "net_call_premium": _f(r.get("net_call_premium")),
            "net_put_premium": _f(r.get("net_put_premium")),
            "net_volume": _f(r.get("net_volume")),
        }
        for r in (rows or [])[-30:]
    ]


def _project_sectors(rows: list[dict]) -> list[dict]:
    return [
        {
            "etf": r.get("ticker") or r.get("etf"),
            "sector": r.get("sector"),
            "perf_today_pct": _f(r.get("perf_change_today") or r.get("pct_change_today")),
            "perf_week_pct": _f(r.get("perf_change_week") or r.get("pct_change_week")),
            "call_premium": _f(r.get("call_premium")),
            "put_premium": _f(r.get("put_premium")),
        }
        for r in (rows or [])[:15]
    ]


def _project_calendar(rows: list[dict]) -> list[dict]:
    """Next 14 days of high-impact macro events."""
    out = []
    for r in (rows or [])[:30]:
        impact = (r.get("impact") or "").lower()
        if impact not in ("high", "medium", ""):
            continue
        out.append({
            "date": r.get("date") or r.get("event_date"),
            "event": r.get("event") or r.get("name"),
            "impact": impact,
            "country": r.get("country"),
            "forecast": r.get("forecast"),
            "previous": r.get("previous"),
        })
    return out[:15]


def _f(v) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None
