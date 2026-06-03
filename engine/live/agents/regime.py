"""Agent 10 — Market Regime Detector (Gemini Pro).

Reads SPY + VIX proxy + sector ETFs, classifies the market regime, and emits
a throttle for the day. Runs ONCE per morning; result is also injected into
new evening pipelines via the macro cache (deferred).
"""
from __future__ import annotations

import json
from typing import Any

from ..renderers.regime import render as render_md
from ..schemas import MarketRegime
from .base import Agent


class RegimeAgent(Agent):
    NAME = "regime"
    LLM_TIER = "pro"
    OUTPUT_SCHEMA = MarketRegime
    STAGE = "regime"
    PROMPT_FILE = "regime.md"

    def build_prompt(self, state: dict[str, Any]) -> str:  # type: ignore[override]
        template = self.load_prompt_template()
        md = state.get("market_data") or {}
        return template.format(
            as_of_date=state["as_of_date"],
            spy_json=_dump(md.get("spy") or {}),
            vol_json=_dump(md.get("volatility_proxy") or {}),
            sectors_ranked_json=_dump(md.get("sectors_ranked") or []),
            sectors_json=_dump(md.get("sectors") or {}),
        )

    def render(self, output: MarketRegime) -> str:
        return render_md(output)


def _dump(obj: Any) -> str:
    return json.dumps(obj, indent=2, default=str, ensure_ascii=False)
