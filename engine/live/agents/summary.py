"""Summary Composer — writes the one-page _summary.md narrative rollup.

Cheap Gemini Flash call. Reads all prior agent outputs and produces a
human-friendly 1-page overview suitable for "executive summary" reading.
"""
from __future__ import annotations

from ..renderers.summary import render as render_md
from ..schemas import SummaryReport
from ..state import SignalState
from .base import Agent


class SummaryAgent(Agent):
    NAME = "summary"
    LLM_TIER = "flash"
    REQUIRES_AGENTS = ["fundamental", "news", "bull", "bear", "pm"]
    OUTPUT_SCHEMA = SummaryReport
    STAGE = "summary"
    PROMPT_FILE = "summary.md"

    def build_prompt(self, state: SignalState) -> str:
        template = self.load_prompt_template()
        fund = state.get("fundamental")
        news = state.get("news")
        bull = state.get("bull")
        bear = state.get("bear")
        pm = state.get("pm")

        return template.format(
            symbol=state["symbol"],
            as_of_date=state["signal_date"],
            fundamental_json=fund.model_dump_json(indent=2) if fund else "{}",
            news_json=news.model_dump_json(indent=2) if news else "{}",
            bull_json=bull.model_dump_json(indent=2) if bull else "{}",
            bear_json=bear.model_dump_json(indent=2) if bear else "{}",
            pm_json=pm.model_dump_json(indent=2) if pm else "{}",
        )

    def render(self, output: SummaryReport) -> str:
        return render_md(output)
