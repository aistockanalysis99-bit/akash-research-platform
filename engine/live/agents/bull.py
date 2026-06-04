"""Bull Researcher — Agent 5.

Builds the strongest BUY case for the symbol across 4 dimensions:
business quality, momentum validity, catalyst, valuation context.

Reads the Fundamental + News reports (other agents' outputs, not raw FMP data),
plus the original signal context. Self-rates conviction 1-10.

Uses Claude Sonnet — the debate-quality reasoning is where Sonnet's gains
over Flash are most visible.
"""
from __future__ import annotations

import json
from typing import Any

from ..renderers.bull import render as render_md
from ..schemas import BullCase
from ..state import SignalState
from .base import Agent


class BullAgent(Agent):
    NAME = "bull"
    LLM_TIER = "sonnet"
    REQUIRES_AGENTS = ["fundamental", "news", "institutional_flow",
                        "options_structure", "macro_regime"]
    OUTPUT_SCHEMA = BullCase
    STAGE = "bull"
    PROMPT_FILE = "bull.md"

    def build_prompt(self, state: SignalState) -> str:
        import json as _json
        template = self.load_prompt_template()

        fund = state.get("fundamental")
        news = state.get("news")
        inst = state.get("institutional_flow")
        opts = state.get("options_structure")
        macro = state.get("macro_regime")
        sig = state.get("signal_input")
        from ..pipeline import quant_signal_block
        signal_block = quant_signal_block(state)
        ctx = state.get("context", {}) or {}
        pricing = ctx.get("pricing_context") or {}

        # M17 — per-stock dossier
        from .. import profiles as live_profiles
        stock_profile = ctx.get("stock_profile")
        profile_block = live_profiles.profile_block_for_agent(stock_profile, "bull")

        return template.format(
            symbol=state["symbol"],
            as_of_date=state["signal_date"],
            fundamental_json=fund.model_dump_json(indent=2) if fund else "{}",
            news_json=news.model_dump_json(indent=2) if news else "{}",
            institutional_flow_json=inst.model_dump_json(indent=2) if inst else "{}",
            options_structure_json=opts.model_dump_json(indent=2) if opts else "{}",
            macro_regime_json=macro.model_dump_json(indent=2) if macro else "{}",
            signal_json=sig.model_dump_json(indent=2) if sig else "{}",
            pricing_context_json=_json.dumps(pricing, indent=2, default=str),
            current_price=pricing.get("current_price") or "unknown",
            stock_profile_block=profile_block,
            quant_signal_block=signal_block,
        )

    def render(self, output: BullCase) -> str:
        return render_md(output)
