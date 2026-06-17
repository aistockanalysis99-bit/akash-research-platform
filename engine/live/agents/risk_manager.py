"""Agent 8 — Risk Manager (Claude Sonnet + deterministic hard rules).

Runs AFTER Bull/Bear, BEFORE PM. Two layers:

1. Deterministic gates (Python, no LLM) — earnings 3-day block, sector cap,
   gross exposure cap, max position count. These are HARD; if any triggers,
   verdict is BLOCK or REDUCE_SIZE and we skip the LLM call.

2. Soft judgment (Claude Sonnet) — only if deterministic gates pass. The LLM
   weighs portfolio-level concerns (sector concentration trend, correlation
   with existing names) and may still recommend REDUCE_SIZE or CLEAR.

The PM downstream treats Risk Manager's verdict as binding for hard rules
and advisory for soft.
"""
from __future__ import annotations

import json
import logging
from datetime import date as date_cls
from typing import Any, Optional

from .. import settings as live_settings
from ..renderers.risk_manager import render as render_md
from ..schemas import RiskManagerVerdict
from .base import Agent

log = logging.getLogger(__name__)

# Hard rule thresholds — fund constitution.
MAX_SECTOR_PCT       = 30.0   # any single sector
MAX_GROSS_EXP_PCT    = 200.0  # gross exposure cap
EARNINGS_HARD_BLOCK  = 3      # days
EARNINGS_REDUCE      = 7      # days
# NOTE: the max-position cap is read live from settings (user-configurable in
# the UI), not hardcoded — see live_settings.get_max_positions().


class RiskManagerAgent(Agent):
    """Special agent — has its own run() because the deterministic gates may
    short-circuit before any LLM call.
    """

    NAME = "risk"
    LLM_TIER = "sonnet"
    REQUIRES_AGENTS = ["fundamental", "bull", "bear"]
    OUTPUT_SCHEMA = RiskManagerVerdict
    STAGE = "risk_manager"
    PROMPT_FILE = "risk_manager.md"

    async def run(self, state):  # type: ignore[override]
        symbol = state["symbol"]
        as_of = state["signal_date"]
        ctx = state.get("context", {}) or {}
        portfolio_snapshot = ctx.get("portfolio_snapshot") or {}
        sector_breakdown = ctx.get("sector_breakdown") or {}

        fundamental = state.get("fundamental")
        profile = ctx.get("profile") or {}
        sector = profile.get("sector") or "Unknown"

        earnings_days = getattr(fundamental, "earnings_risk_days", None)
        n_positions = int(portfolio_snapshot.get("open_positions") or 0)
        max_positions = live_settings.get_max_positions()
        gross_exp = float(portfolio_snapshot.get("gross_exposure_pct") or 0.0)
        sector_now_pct = float(sector_breakdown.get(sector) or 0.0)

        rules_triggered: list[str] = []
        det_block: Optional[str] = None
        det_size: Optional[int] = None

        # ---- Hard rule 1: Earnings 3-day block ----
        if isinstance(earnings_days, int) and 0 <= earnings_days <= EARNINGS_HARD_BLOCK:
            rules_triggered.append(f"earnings_in_{earnings_days}_days")
            det_block = f"Earnings in {earnings_days} days — within 3-day hard block."
            det_size = 0

        # ---- Hard rule 2: Earnings 4-7 day reduce ----
        elif isinstance(earnings_days, int) and EARNINGS_HARD_BLOCK < earnings_days <= EARNINGS_REDUCE:
            rules_triggered.append(f"earnings_in_{earnings_days}_days_reduce")
            det_size = min(det_size if det_size is not None else 100, 50)

        # ---- Hard rule 3: Max positions (user-configurable) ----
        if n_positions >= max_positions:
            rules_triggered.append("max_positions_reached")
            if det_block is None:
                det_block = f"Already holding {n_positions}/{max_positions} positions."
                det_size = 0

        # ---- Hard rule 4: Gross exposure cap ----
        if gross_exp >= MAX_GROSS_EXP_PCT:
            rules_triggered.append("gross_exposure_at_cap")
            if det_block is None:
                det_block = f"Gross exposure at {gross_exp:.1f}% (cap {MAX_GROSS_EXP_PCT}%)."
                det_size = 0

        # ---- Hard rule 5: Sector cap (approximation — adding ~5% notional) ----
        sector_after_pct = sector_now_pct + 5.0  # rough estimate per position
        if sector_now_pct >= MAX_SECTOR_PCT:
            rules_triggered.append("sector_cap_breached")
            if det_block is None:
                det_block = f"{sector} sector at {sector_now_pct:.1f}% — cap is {MAX_SECTOR_PCT}%."
                det_size = 0
        elif sector_after_pct > MAX_SECTOR_PCT:
            rules_triggered.append("sector_cap_near")
            det_size = min(det_size if det_size is not None else 100, 50)

        # ---- Hard rule 6: Already holding this symbol ----
        existing_symbols = {p["symbol"] for p in (ctx.get("open_positions") or [])}
        if symbol.upper() in existing_symbols:
            rules_triggered.append("already_holding")
            if det_block is None:
                det_block = f"Already holding {symbol} — no pyramiding in Phase 2."
                det_size = 0

        # ---- Decision path: deterministic block ----
        if det_block is not None:
            verdict = RiskManagerVerdict(
                symbol=symbol, as_of_date=as_of,
                verdict="BLOCK", recommended_size_pct=0,
                rules_triggered=rules_triggered,
                deterministic_block_reason=det_block,
                sector=sector,
                sector_concentration_now_pct=sector_now_pct,
                sector_concentration_after_pct=sector_now_pct,
                gross_exposure_now_pct=gross_exp,
                open_position_count=n_positions,
                earnings_risk_days=earnings_days,
                reasoning=(
                    f"Hard rule triggered: {det_block} "
                    "No LLM call — deterministic block."
                ),
            )
            return self._finalize(state, verdict)

        # ---- Decision path: deterministic reduce — still call LLM for nuance ----
        # ---- Otherwise: LLM call for soft judgment ----
        from ..llm.structured import invoke_structured_or_freetext
        prompt = self._build_prompt(state, sector, sector_now_pct, sector_after_pct,
                                      gross_exp, n_positions, earnings_days,
                                      rules_triggered, det_size)
        result = await invoke_structured_or_freetext(
            self.llm, prompt, self.OUTPUT_SCHEMA,
        )
        verdict = result.instance

        # Code overrides the LLM if soft judgment violates a hard rule.
        if det_size is not None and verdict.recommended_size_pct > det_size:
            log.info("risk: code capping LLM size %d → %d", verdict.recommended_size_pct, det_size)
            new_verdict = verdict.model_copy(update={
                "recommended_size_pct": det_size,
                "verdict": "REDUCE_SIZE" if det_size > 0 else "BLOCK",
                "rules_triggered": list(set(verdict.rules_triggered + rules_triggered)),
            })
            verdict = new_verdict

        return self._finalize(state, verdict)

    def _finalize(self, state, verdict: RiskManagerVerdict):
        markdown = self.render(verdict)
        self.fs.write_markdown(
            state["symbol"], state["signal_date"], self.STAGE, markdown,
        )
        new_state = dict(state)
        new_state[self.NAME] = verdict
        meta = dict(new_state.get("meta", {}))
        meta.setdefault("agents_run", []).append(self.NAME)
        new_state["meta"] = meta
        return new_state

    def _build_prompt(self, state, sector, sector_now, sector_after,
                       gross_exp, n_pos, earnings_days, rules, det_size) -> str:
        template = self.load_prompt_template()
        ctx = state.get("context", {}) or {}
        snap = ctx.get("portfolio_snapshot") or {}
        open_positions = ctx.get("open_positions") or []
        sector_breakdown = ctx.get("sector_breakdown") or {}

        # Compact: just per-position {sym, sector, market_value}
        compact_positions = [
            {"symbol": p["symbol"], "sector": p.get("sector") or "?",
             "market_value": (p.get("units") or 0) * (p.get("current_price") or p.get("entry_price") or 0),
             "pnl_pct": p.get("current_pnl_pct")}
            for p in open_positions
        ]

        fundamental = state.get("fundamental")
        bull = state.get("bull")
        bear = state.get("bear")

        return template.format(
            symbol=state["symbol"],
            as_of_date=state["signal_date"],
            sector=sector,
            sector_now_pct=f"{sector_now:.2f}",
            sector_after_pct=f"{sector_after:.2f}",
            gross_exposure_pct=f"{gross_exp:.2f}",
            open_positions_count=n_pos,
            earnings_risk_days=earnings_days if earnings_days is not None else "unknown",
            equity_usd=f"{snap.get('equity', 0):,.0f}",
            cash_usd=f"{snap.get('cash', 0):,.0f}",
            rules_already_triggered=rules,
            mandatory_size_cap=det_size if det_size is not None else 100,
            open_positions_json=json.dumps(compact_positions, indent=2, default=str),
            sector_breakdown_json=json.dumps(sector_breakdown, indent=2),
            fundamental_summary=getattr(fundamental, "summary", "n/a"),
            bull_conviction=getattr(bull, "conviction_self_rated", "?"),
            bear_conviction=getattr(bear, "conviction_self_rated", "?"),
        )

    def build_prompt(self, state) -> str:  # type: ignore[override]
        # Required by Agent base; unused — _build_prompt has the real impl
        # because we need parameters from the deterministic-gate calculation.
        return self._build_prompt(state, "", 0.0, 0.0, 0.0, 0, None, [], None)

    def render(self, output: RiskManagerVerdict) -> str:
        return render_md(output)
