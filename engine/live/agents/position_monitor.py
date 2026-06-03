"""Agent 11 — Position Monitor (Gemini Pro, BATCH).

Reads ALL open paper positions in one call (key efficiency win: one LLM
invocation regardless of position count) and emits HOLD/WATCH/EXIT per
position. The PM Decision rationale + exit thesis from the original entry is
included in the bundle so the monitor can re-validate against the thesis.
"""
from __future__ import annotations

import json
from typing import Any

from ..renderers.position_monitor import render as render_md
from ..schemas import PositionMonitorReport
from .base import Agent


class PositionMonitorAgent(Agent):
    NAME = "position_review"
    LLM_TIER = "pro"
    OUTPUT_SCHEMA = PositionMonitorReport
    STAGE = "position_monitor"
    PROMPT_FILE = "position_monitor.md"

    def build_prompt(self, state: dict[str, Any]) -> str:  # type: ignore[override]
        template = self.load_prompt_template()
        positions = state.get("open_positions") or []
        regime = state.get("regime")
        snap = state.get("portfolio_snapshot") or {}

        positions_compact = [_compact_position(p) for p in positions]
        regime_snippet = regime.model_dump_json(indent=2) if regime else "null"
        snap_compact = {k: v for k, v in snap.items() if k in
                         ("equity", "realized_pnl", "unrealized_pnl",
                          "open_market_value", "gross_exposure_pct",
                          "open_positions")}

        return template.format(
            as_of_date=state["as_of_date"],
            position_count=len(positions),
            positions_json=_dump(positions_compact),
            portfolio_snapshot_json=_dump(snap_compact),
            regime_json=regime_snippet,
        )

    def render(self, output: PositionMonitorReport) -> str:
        return render_md(output)


def _dump(obj: Any) -> str:
    return json.dumps(obj, indent=2, default=str, ensure_ascii=False)


def _compact_position(p: dict[str, Any]) -> dict[str, Any]:
    """Project a virtual_positions row down to what the monitor actually needs."""
    return {
        "symbol": p.get("symbol"),
        "entry_date": p.get("entry_date"),
        "entry_price": p.get("entry_price"),
        "current_price": p.get("current_price"),
        "units": p.get("units"),
        "trailing_stop": p.get("trailing_stop"),
        "current_pnl_pct": p.get("current_pnl_pct"),
        "current_pnl_usd": p.get("current_pnl_usd"),
        "days_held": p.get("days_held", 0),
        "decision_verdict": p.get("decision_verdict"),
        "decision_conviction": p.get("decision_conviction"),
        "decision_size_pct": p.get("decision_size_pct"),
    }
