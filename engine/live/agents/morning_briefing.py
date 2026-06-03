"""Agent 13 — Morning Briefing Composer (Gemini Flash).

Writes the daily plain-English client briefing. ~10 lines, conversational
tone, leads with the action items.
"""
from __future__ import annotations

import json
from typing import Any

from ..renderers.morning_briefing import render as render_md
from ..schemas import MorningBriefing
from .base import Agent


class MorningBriefingAgent(Agent):
    NAME = "briefing"
    LLM_TIER = "flash"
    OUTPUT_SCHEMA = MorningBriefing
    STAGE = "morning_briefing"
    PROMPT_FILE = "morning_briefing.md"

    def build_prompt(self, state: dict[str, Any]) -> str:  # type: ignore[override]
        template = self.load_prompt_template()
        regime = state.get("regime")
        review = state.get("position_review")
        snap = state.get("portfolio_snapshot") or {}
        executed = state.get("executed_exits") or []
        confirmations = state.get("exit_confirmations") or {}

        confirmations_json = _dump(
            {sym: c.model_dump() for sym, c in confirmations.items()}
        )

        return template.format(
            as_of_date=state["as_of_date"],
            position_count=len(state.get("open_positions") or []),
            executed_exits_count=len(executed),
            executed_exits_json=_dump(executed),
            confirmations_json=confirmations_json,
            regime_json=regime.model_dump_json(indent=2) if regime else "null",
            review_json=review.model_dump_json(indent=2) if review else "null",
            portfolio_snapshot_json=_dump(snap),
        )

    def render(self, output: MorningBriefing) -> str:
        return render_md(output)


def _dump(obj: Any) -> str:
    return json.dumps(obj, indent=2, default=str, ensure_ascii=False)
