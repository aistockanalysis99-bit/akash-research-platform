"""SignalState — the single shared state object flowing through the pipeline.

Inspired by TradingAgents' AgentState pattern: a TypedDict with one slot per
agent's output, all optional, all written by exactly one agent. LangGraph reads
and writes this dict as nodes execute; each agent's slot becomes populated
exactly once, in topological order.

The data bundle (raw FMP responses) is pre-fetched into `context` BEFORE any
agent runs, so agents never make tool calls — see engine/live/data/fmp_research.
"""
from __future__ import annotations

from typing import Any, Optional, TypedDict

from .schemas import (
    BearCase,
    BullCase,
    DebateJudgment,
    FundamentalReport,
    InstitutionalFlowReport,
    MacroContextSnapshot,
    MacroRegimeReport,
    NewsReport,
    OptionsStructureReport,
    PMDecision,
    PreFilterResult,
    RiskManagerVerdict,
    SignalInput,
    SummaryReport,
    TechnicalContext,
)


class PipelineMeta(TypedDict, total=False):
    started_at: str
    completed_at: str
    folder_path: str          # Where per-stock markdown files are written
    errors: list[dict[str, Any]]
    agents_run: list[str]


class SignalState(TypedDict, total=False):
    """Shared state for one signal flowing through the AI pipeline.

    Every agent reads from this dict (the slots it needs) and writes exactly
    one slot (its own output). Nothing is mutable in-place — agents return new
    state values that LangGraph merges in.
    """

    # ---- Identity ----------------------------------------------------------
    symbol: str
    signal_date: str          # YYYY-MM-DD
    source: str               # "quant" | "manual" | "external"

    # ---- Input -------------------------------------------------------------
    signal_input: SignalInput

    # ---- Pre-fetched data bundle (raw FMP responses, before LLM) ----------
    # Keys: profile, income_q, balance_q, cashflow_q, ratios_annual,
    #       ratios_ttm, key_metrics_annual, key_metrics_ttm, earnings,
    #       analyst_estimates, news, grades, sec_filings, insider_trades,
    #       press_releases, price_history_60d, next_earnings_date
    # Values: the parsed JSON dict/list, or {"_status": "FETCH_FAILED", ...},
    # or {"_status": "UNAVAILABLE"} for premium endpoints not on plan.
    context: dict[str, Any]

    # ---- Stage outputs (each populated by exactly one agent) --------------
    pre_filter: PreFilterResult
    fundamental: Optional[FundamentalReport]
    news: Optional[NewsReport]
    technical: Optional[TechnicalContext]
    institutional_flow: Optional[InstitutionalFlowReport]
    options_structure: Optional[OptionsStructureReport]
    macro_regime: Optional[MacroRegimeReport]
    bull: Optional[BullCase]
    bear: Optional[BearCase]
    judge: Optional[DebateJudgment]
    risk: Optional[RiskManagerVerdict]
    macro: Optional[MacroContextSnapshot]
    pm: Optional[PMDecision]
    summary: Optional[SummaryReport]

    # ---- Pipeline metadata ------------------------------------------------
    meta: PipelineMeta


def new_signal_state(symbol: str, signal_date: str, source: str) -> SignalState:
    """Initialize an empty SignalState — convenience for pipeline entry points."""
    return {
        "symbol": symbol.upper(),
        "signal_date": signal_date,
        "source": source,
        "context": {},
        "meta": {
            "errors": [],
            "agents_run": [],
        },
    }
