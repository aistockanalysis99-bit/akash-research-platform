"""Agent 4 — Technical Context (Gemini Flash).

Reads 60 bars of the ticker, the matching sector ETF, and SPY → emits
volume confirmation, sector alignment, broader market context. Cheap analyst
that gives the Bull / Bear / PM agents a "real breakout vs fakeout" signal.
"""
from __future__ import annotations

import json
from typing import Any

from ..renderers.technical import render as render_md
from ..schemas import TechnicalContext
from .base import Agent


class TechnicalAgent(Agent):
    NAME = "technical"
    LLM_TIER = "flash"
    REQUIRES_DATA = ["price_history_60d", "sector_etf_history",
                     "spy_history", "profile"]
    OUTPUT_SCHEMA = TechnicalContext
    STAGE = "technical"
    PROMPT_FILE = "technical.md"

    def build_prompt(self, state) -> str:  # type: ignore[override]
        template = self.load_prompt_template()
        ctx = state.get("context", {})
        profile = ctx.get("profile") or {}

        return template.format(
            symbol=state["symbol"],
            as_of_date=state["signal_date"],
            sector=profile.get("sector") or "Unknown",
            sector_etf_symbol=ctx.get("sector_etf_symbol") or "n/a",
            symbol_history_json=_dump(ctx.get("price_history_60d") or []),
            sector_history_json=_dump(ctx.get("sector_etf_history") or []),
            spy_history_json=_dump(ctx.get("spy_history") or []),
        )

    def render(self, output: TechnicalContext) -> str:
        return render_md(output)


def _dump(obj: Any) -> str:
    return json.dumps(obj, indent=2, default=str, ensure_ascii=False)
