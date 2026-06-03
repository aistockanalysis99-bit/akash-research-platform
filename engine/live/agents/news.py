"""News Analyst — Agent 3.

Consumes news/grades/sec_filings/insider_trades from FMP and produces a NewsReport.
Like Fundamental, this agent uses Gemini (Flash tier — news scoring is shallower
work than fundamental ratio reasoning).
"""
from __future__ import annotations

import json
from typing import Any

from ..renderers.news import render as render_md
from ..schemas import NewsReport
from ..state import SignalState
from .base import Agent


class NewsAgent(Agent):
    NAME = "news"
    LLM_TIER = "flash"
    REQUIRES_DATA = ["news", "grades", "sec_filings", "insider_trades"]
    OUTPUT_SCHEMA = NewsReport
    STAGE = "news"
    PROMPT_FILE = "news.md"

    def build_prompt(self, state: SignalState) -> str:
        template = self.load_prompt_template()
        ctx = state.get("context", {})

        # M17 — per-stock dossier block
        from .. import profiles as live_profiles
        stock_profile = ctx.get("stock_profile")
        profile_block = live_profiles.profile_block_for_agent(stock_profile, "news")

        # M19 — analyst grades with firm hit-rate scores attached
        grades_annotated = ctx.get("grades_annotated") or ctx.get("grades") or []

        return template.format(
            symbol=state["symbol"],
            as_of_date=state["signal_date"],
            news_json=_dump(_project_news(ctx.get("news") or [])),
            press_releases_json=_dump(_project_news(ctx.get("press_releases") or [])),
            grades_json=_dump(_project_grades_weighted(grades_annotated)),
            sec_filings_json=_dump(_project_filings(ctx.get("sec_filings") or [])),
            insider_trades_json=_dump(_project_insider(ctx.get("insider_trades") or [])),
            short_interest_json=_dump(ctx.get("uw_short_interest") or {}),
            stock_profile_block=profile_block,
        )

    def render(self, output: NewsReport) -> str:
        return render_md(output)


def _dump(obj: Any) -> str:
    return json.dumps(obj, indent=2, default=str, ensure_ascii=False)


def _project_news(rows: list[dict]) -> list[dict]:
    return [
        {
            "published": r.get("publishedDate"),
            "publisher": r.get("publisher") or r.get("site"),
            "title": r.get("title"),
            "url": r.get("url"),
            "snippet": (r.get("text") or "")[:600],
        }
        for r in rows[:15]
    ]


def _project_grades(rows: list[dict]) -> list[dict]:
    return [
        {
            "date": r.get("date"),
            "firm": r.get("gradingCompany"),
            "action": r.get("action"),
            "from": r.get("previousGrade"),
            "to": r.get("newGrade"),
        }
        for r in rows[:20]
    ]


def _project_grades_weighted(rows: list[dict]) -> list[dict]:
    """Grades with analyst-tracker firm_score block attached (M19).

    Each row carries `_firm_score` from analyst_tracker.annotate_grades —
    the prompt instructs the agent to weight calls by hit rate.
    """
    out = []
    for r in rows[:20]:
        fs = r.get("_firm_score") or {}
        out.append({
            "date": r.get("date"),
            "firm": r.get("gradingCompany") or r.get("firm"),
            "action": r.get("action"),
            "from": r.get("previousGrade"),
            "to": r.get("newGrade"),
            "firm_hit_rate_pct": fs.get("hit_rate_pct"),
            "firm_history": f"{fs.get('correct',0)}/{fs.get('calls',0)} "
                            f"({fs.get('label','new')}, scope={fs.get('scope','none')})",
        })
    return out


def _project_filings(rows: list[dict]) -> list[dict]:
    return [
        {
            "filed": r.get("filingDate"),
            "form": r.get("formType"),
            "link": r.get("finalLink") or r.get("link"),
        }
        for r in rows[:20]
    ]


def _project_insider(rows: list[dict]) -> list[dict]:
    return [
        {
            "transaction_date": r.get("transactionDate"),
            "filing_date": r.get("filingDate"),
            "reporter": r.get("reportingName"),
            "role": r.get("typeOfOwner"),
            "txn_type": r.get("transactionType"),
            "acq_or_disp": r.get("acquisitionOrDisposition"),
            "shares": r.get("securitiesTransacted"),
            "price": r.get("price"),
            "value_usd": r.get("_value_usd"),
        }
        for r in rows[:15]
    ]
