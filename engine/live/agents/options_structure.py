"""Agent 4c — Options Structure / Dealer Positioning (Gemini Flash).

Reads three UW endpoints:
    - greek-exposure        (daily aggregate dealer gamma/delta exposure)
    - max-pain              (per-expiry max-pain strike + walls)
    - volatility/term-structure  (IV by expiry)

Produces an OptionsStructureReport — what dealer hedging will likely do to
price, where the call/put walls are, and how stressed the vol curve is.
"""
from __future__ import annotations

import json
from typing import Any

from ..renderers.options_structure import render as render_md
from ..schemas import OptionsStructureReport
from ..state import SignalState
from .base import Agent


class OptionsStructureAgent(Agent):
    NAME = "options_structure"
    LLM_TIER = "flash"
    REQUIRES_DATA = ["uw_greek_exposure", "uw_max_pain", "uw_vol_term"]
    OUTPUT_SCHEMA = OptionsStructureReport
    STAGE = "options_structure"
    PROMPT_FILE = "options_structure.md"

    def build_prompt(self, state: SignalState) -> str:
        template = self.load_prompt_template()
        ctx = state.get("context", {})
        pricing = ctx.get("pricing_context") or {}

        return template.format(
            symbol=state["symbol"],
            as_of_date=state["signal_date"],
            current_price=pricing.get("current_price") or "unknown",
            greek_exposure_json=_dump(_project_greeks(ctx.get("uw_greek_exposure") or [])),
            max_pain_json=_dump(_project_max_pain(ctx.get("uw_max_pain") or [])),
            vol_term_json=_dump(_project_vol_term(ctx.get("uw_vol_term") or [])),
        )

    def render(self, output: OptionsStructureReport) -> str:
        return render_md(output)


def _dump(obj: Any) -> str:
    return json.dumps(obj, indent=2, default=str, ensure_ascii=False)


def _project_greeks(rows: list[dict]) -> list[dict]:
    """Last 20 sessions of dealer greek exposure."""
    out = []
    for r in (rows or [])[-20:]:
        out.append({
            "date": r.get("date"),
            "call_gamma": _f(r.get("call_gamma")),
            "put_gamma": _f(r.get("put_gamma")),
            "net_gamma": (_f(r.get("call_gamma")) or 0) + (_f(r.get("put_gamma")) or 0),
            "call_delta": _f(r.get("call_delta")),
            "put_delta": _f(r.get("put_delta")),
            "call_vanna": _f(r.get("call_vanna")),
            "put_vanna": _f(r.get("put_vanna")),
        })
    return out


def _project_max_pain(rows: list[dict]) -> list[dict]:
    """All expiries with max pain levels."""
    return [
        {
            "expiry": r.get("expiry"),
            "close": _f(r.get("close")),
            "max_pain": _f(r.get("max_pain")),
            "next_upper_strike": _f(r.get("next_upper_strike")),
            "next_lower_strike": _f(r.get("next_lower_strike")),
        }
        for r in (rows or [])[:12]
    ]


def _project_vol_term(rows: list[dict]) -> list[dict]:
    return [
        {
            "expiry": r.get("expiry"),
            "iv": _f(r.get("iv") or r.get("implied_volatility")),
            "iv_low": _f(r.get("iv_low")),
            "iv_high": _f(r.get("iv_high")),
        }
        for r in (rows or [])[:10]
    ]


def _f(v) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None
