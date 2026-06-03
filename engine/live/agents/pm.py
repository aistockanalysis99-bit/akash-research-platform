"""Portfolio Manager / CIO — Agent 9. The final voice.

Reads every prior agent's output AND the full portfolio state, then makes
the APPROVE / RESIZE / REJECT call. Also writes the plain-English
Telegram-ready message to the client.

Uses Claude Sonnet (downgraded from Opus per project decision). Sonnet handles
fiduciary-grade reasoning well at ~10x lower cost.
"""
from __future__ import annotations

import json
from typing import Any

from .. import memory as live_memory
from .. import profiles as live_profiles
from ..renderers.pm import render as render_md
from ..schemas import PMDecision
from ..state import SignalState
from .base import Agent


class PMAgent(Agent):
    NAME = "pm"
    LLM_TIER = "opus"  # M16 — upgraded from sonnet for fiduciary-grade reasoning
    REQUIRES_AGENTS = ["fundamental", "news", "institutional_flow",
                        "options_structure", "macro_regime",
                        "bull", "bear", "judge"]
    OUTPUT_SCHEMA = PMDecision
    STAGE = "pm"
    PROMPT_FILE = "pm.md"

    def build_prompt(self, state: SignalState) -> str:
        template = self.load_prompt_template()
        fund = state.get("fundamental")
        news = state.get("news")
        tech = state.get("technical")
        inst = state.get("institutional_flow")
        opts = state.get("options_structure")
        macro_reg = state.get("macro_regime")
        bull = state.get("bull")
        bear = state.get("bear")
        judge = state.get("judge")
        risk = state.get("risk")
        macro = state.get("macro")
        sig = state.get("signal_input")

        # Inject the current portfolio state — PM was previously blind to this
        # and could only read summary numbers off the Risk Manager output.
        ctx = state.get("context", {}) or {}
        snapshot = ctx.get("portfolio_snapshot") or {}
        open_positions = ctx.get("open_positions") or []
        sector_breakdown = ctx.get("sector_breakdown") or {}

        snap_compact = {
            "equity_usd":         snapshot.get("equity"),
            "cash_usd":           snapshot.get("cash"),
            "gross_exposure_pct": snapshot.get("gross_exposure_pct"),
            "open_positions":     snapshot.get("open_positions"),
            "realized_pnl_usd":   snapshot.get("realized_pnl"),
            "unrealized_pnl_usd": snapshot.get("unrealized_pnl"),
            "open_market_value":  snapshot.get("open_market_value"),
        }

        positions_compact = [_compact_position(p) for p in open_positions]

        # Memory injection — top-10 most relevant lessons from past closed trades.
        lessons_block = live_memory.format_lessons_for_prompt(
            symbol=state["symbol"], limit=10,
        )

        # Per-stock profile injection (M17) — primes PM with stock-specific
        # red lines, pm_notes, historical lessons, all the dossier knowledge.
        stock_profile = ctx.get("stock_profile")
        profile_block = live_profiles.profile_block_for_agent(stock_profile, "pm")

        # Pricing context — shared with Bull/Bear, single source of truth
        pricing = ctx.get("pricing_context") or {}

        return template.format(
            symbol=state["symbol"],
            as_of_date=state["signal_date"],
            fundamental_json=fund.model_dump_json(indent=2) if fund else "{}",
            news_json=news.model_dump_json(indent=2) if news else "{}",
            technical_json=tech.model_dump_json(indent=2) if tech else "{}",
            institutional_flow_json=inst.model_dump_json(indent=2) if inst else "{}",
            options_structure_json=opts.model_dump_json(indent=2) if opts else "{}",
            macro_regime_json=macro_reg.model_dump_json(indent=2) if macro_reg else "{}",
            earnings_dynamics_block=__import__(
                "engine.live.earnings_dynamics", fromlist=["format_for_prompt"],
            ).format_for_prompt(
                (state.get("context") or {}).get("earnings_dynamics") or {}
            ),
            bull_json=bull.model_dump_json(indent=2) if bull else "{}",
            bear_json=bear.model_dump_json(indent=2) if bear else "{}",
            judge_json=judge.model_dump_json(indent=2) if judge else "{}",
            risk_json=risk.model_dump_json(indent=2) if risk else "{}",
            macro_json=macro.model_dump_json(indent=2) if macro else "{}",
            signal_json=sig.model_dump_json(indent=2) if sig else "{}",
            portfolio_snapshot_json=_dump(snap_compact),
            open_positions_json=_dump(positions_compact),
            sector_breakdown_json=_dump(sector_breakdown),
            pricing_context_json=_dump(pricing),
            current_price=pricing.get("current_price") or "unknown",
            lessons_block=lessons_block,
            profile_block=profile_block,
        )

    def render(self, output: PMDecision) -> str:
        return render_md(output)


def _dump(obj: Any) -> str:
    return json.dumps(obj, indent=2, default=str, ensure_ascii=False)


def _compact_position(p: dict[str, Any]) -> dict[str, Any]:
    """Project a virtual_positions row to what the PM actually needs."""
    return {
        "symbol":         p.get("symbol"),
        "sector":         p.get("sector") or "?",
        "entry_date":     p.get("entry_date"),
        "entry_price":    p.get("entry_price"),
        "current_price":  p.get("current_price"),
        "units":          p.get("units"),
        "market_value":   (p.get("units") or 0) * (
            p.get("current_price") or p.get("entry_price") or 0
        ),
        "current_pnl_pct": p.get("current_pnl_pct"),
        "current_pnl_usd": p.get("current_pnl_usd"),
        "days_held":       p.get("days_held", 0),
        "trailing_stop":   p.get("trailing_stop"),
        "decision_verdict":    p.get("decision_verdict"),
        "decision_conviction": p.get("decision_conviction"),
        "decision_size_pct":   p.get("decision_size_pct"),
    }
