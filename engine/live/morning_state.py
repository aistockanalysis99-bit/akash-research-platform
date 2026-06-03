"""Shared state for the morning pipeline.

Morning state is per-DAY (not per-stock). Lives in memory during one cycle;
artifacts persist to ai_research/_morning/{YYYY-MM-DD}/*.md.
"""
from __future__ import annotations

from typing import Any, Optional, TypedDict

from .schemas import (
    ExitConfirmation,
    MarketRegime,
    MorningBriefing,
    PositionMonitorReport,
)


class MorningPipelineMeta(TypedDict, total=False):
    started_at: str
    completed_at: str
    folder_path: str
    errors: list[dict[str, Any]]
    agents_run: list[str]


class MorningState(TypedDict, total=False):
    as_of_date: str            # YYYY-MM-DD

    # Snapshots taken at cycle start
    open_positions: list[dict[str, Any]]
    portfolio_snapshot: dict[str, float]

    # Raw market data bundle (for regime agent)
    market_data: dict[str, Any]

    # Agent outputs
    regime: Optional[MarketRegime]
    position_review: Optional[PositionMonitorReport]
    exit_confirmations: dict[str, ExitConfirmation]  # symbol -> confirmation
    briefing: Optional[MorningBriefing]

    # Side effects
    executed_exits: list[dict[str, Any]]   # rows we actually closed in the portfolio

    meta: MorningPipelineMeta


def new_morning_state(as_of_date: str) -> MorningState:
    return {
        "as_of_date": as_of_date,
        "open_positions": [],
        "market_data": {},
        "exit_confirmations": {},
        "executed_exits": [],
        "meta": {"errors": [], "agents_run": []},
    }
