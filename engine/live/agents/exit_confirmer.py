"""Agent 12 — Exit Confirmer (Claude Sonnet).

Second opinion before pulling the trigger on any EXIT flag from the
position monitor. Sonnet is used here (not Flash) because we want richer
reasoning before destroying P&L state.
"""
from __future__ import annotations

import json
from typing import Any

from ..renderers.exit_confirmer import render as render_md
from ..schemas import ExitConfirmation
from .base import Agent


class ExitConfirmerAgent(Agent):
    """Special agent: parameterized by the SPECIFIC position being confirmed.

    The morning pipeline instantiates one of these per position flagged EXIT,
    sets `.target_symbol` and `.review_reason`, then calls run().
    """

    NAME = "exit_confirmer"
    LLM_TIER = "sonnet"
    OUTPUT_SCHEMA = ExitConfirmation
    STAGE = "exit_confirmer"
    PROMPT_FILE = "exit_confirmer.md"

    target_symbol: str = ""
    review_reason: str = ""
    target_position: dict[str, Any] = {}  # type: ignore[assignment]

    def for_position(
        self, symbol: str, reason: str, position: dict[str, Any],
    ) -> "ExitConfirmerAgent":
        self.target_symbol = symbol
        self.review_reason = reason
        self.target_position = position
        return self

    def build_prompt(self, state: dict[str, Any]) -> str:  # type: ignore[override]
        template = self.load_prompt_template()
        regime = state.get("regime")
        regime_snippet = regime.model_dump_json(indent=2) if regime else "null"

        return template.format(
            symbol=self.target_symbol,
            as_of_date=state["as_of_date"],
            review_reason=self.review_reason,
            position_json=_dump(self.target_position),
            regime_json=regime_snippet,
        )

    def render(self, output: ExitConfirmation) -> str:
        return render_md(output)


def _dump(obj: Any) -> str:
    return json.dumps(obj, indent=2, default=str, ensure_ascii=False)
