"""Agent 7 — Debate Judge (Claude Sonnet).

Sits between the Bull/Bear debate and the PM. Reads both cases, scores them
on five dimensions, picks a winner, and outputs a conviction score the PM
uses as input. Without this agent, the PM was doing two jobs at once
(judging the debate AND making the call); this splits them cleanly.
"""
from __future__ import annotations

from ..renderers.judge import render as render_md
from ..schemas import DebateJudgment
from ..state import SignalState
from .base import Agent


class JudgeAgent(Agent):
    NAME = "judge"
    LLM_TIER = "sonnet"
    REQUIRES_AGENTS = ["bull", "bear"]
    OUTPUT_SCHEMA = DebateJudgment
    STAGE = "judge"
    PROMPT_FILE = "judge.md"

    def build_prompt(self, state: SignalState) -> str:
        template = self.load_prompt_template()
        bull = state.get("bull")
        bear = state.get("bear")
        fund = state.get("fundamental")
        news = state.get("news")
        tech = state.get("technical")

        return template.format(
            symbol=state["symbol"],
            as_of_date=state["signal_date"],
            bull_json=bull.model_dump_json(indent=2) if bull else "{}",
            bear_json=bear.model_dump_json(indent=2) if bear else "{}",
            fundamental_summary=getattr(fund, "summary", "n/a"),
            news_summary=getattr(news, "summary", "n/a"),
            technical_summary=getattr(tech, "summary", "n/a"),
        )

    def render(self, output: DebateJudgment) -> str:
        return render_md(output)
