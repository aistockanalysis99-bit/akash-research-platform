"""Phase 5 — the Strategy Allocator.

Given a symbol and the signals around it, list every VIABLE structure and
rank them. Ranking is evidence-first: once a family has enough closed trades
(MIN_TRADES) its realized return-on-risk from the league table drives the
order; before that, a documented prior order applies. Every rank carries a
one-line WHY, and the method is always disclosed ("our results" vs "prior"),
so the recommendation is never a black box.

The allocator only ranks — it never sizes, never tracks, never trades.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

log = logging.getLogger(__name__)

MIN_TRADES = 5   # a family needs this many closed trades before its own
                 # record outranks the prior order

# Prior order (before evidence): conservative income first, event trades
# last — reflecting risk shape, not expected return.
PRIOR_ORDER = ["covered_call", "cash_secured_put", "bull_put_spread",
               "bear_call_spread", "wheel", "iron_condor", "long_straddle"]


def _league() -> dict[str, dict[str, Any]]:
    from .store import league_record
    from .structures import family_stats
    from .wheel import wheel_league_row
    league = family_stats()
    s = league_record()
    if s:
        league.setdefault("long_straddle", s)
    w = wheel_league_row()
    if w:
        league["wheel"] = w
    return league


def viable_structures(symbol: str, ctx: dict[str, Any]) -> list[dict[str, Any]]:
    """Which families COULD fire for this symbol, from the signal context:
    {holding_shares, ai: {conviction, decision, entry, target, stop},
     earnings_days, cheapness}. Pure logic — no I/O."""
    out = []
    ai = ctx.get("ai") or {}
    conviction = ai.get("conviction") or 0
    decision = (ai.get("decision") or "").upper()
    days = ctx.get("earnings_days")
    cheap = ctx.get("cheapness")

    if (ctx.get("holding_shares") or 0) >= 100:
        out.append({"key": "covered_call",
                    "why": "the fund already holds the shares — rent is the "
                           "lowest-risk income available"})
    if conviction >= 7 and ai.get("entry"):
        out.append({"key": "cash_secured_put",
                    "why": f"AI BUY {conviction}/10 — get paid to wait at its "
                           f"own entry level"})
    if conviction >= 7 and ai.get("stop") and decision not in ("AVOID", "SELL"):
        out.append({"key": "bull_put_spread",
                    "why": "defined-risk premium against the AI's stop — wins "
                           "unless its own invalidation level breaks"})
    if decision in ("AVOID", "SELL") and ai.get("stop"):
        out.append({"key": "bear_call_spread",
                    "why": "the bearish verdict finally earns — premium "
                           "against the AI's invalidation ceiling"})
    if days is not None and 1 <= days <= 10 and cheap is not None:
        if cheap <= 0.80:
            out.append({"key": "long_straddle",
                        "why": f"earnings move underpriced ({cheap}× history) "
                               f"— buy the anticipation, exit before the print"})
        elif cheap >= 1.25:
            out.append({"key": "iron_condor",
                        "why": f"earnings move overpriced ({cheap}× history) "
                               f"— sell it with wings, worst case fixed"})
    return out


def rank_structures(symbol: str, ctx: dict[str, Any],
                    league: Optional[dict[str, dict[str, Any]]] = None
                    ) -> list[dict[str, Any]]:
    """Viable structures, ranked. Injectable `league` for tests."""
    viable = viable_structures(symbol, ctx)
    if not viable:
        return []
    league = league if league is not None else _league()

    def sort_key(v: dict[str, Any]):
        rec = league.get(v["key"]) or {}
        trades = rec.get("trades") or 0
        avg = rec.get("avg_return_on_risk_pct")
        if trades >= MIN_TRADES and avg is not None:
            return (0, -avg)                    # evidence tier, best first
        return (1, PRIOR_ORDER.index(v["key"])
                if v["key"] in PRIOR_ORDER else 99)

    ranked = sorted(viable, key=sort_key)
    out = []
    for i, v in enumerate(ranked, 1):
        rec = league.get(v["key"]) or {}
        trades = rec.get("trades") or 0
        if trades >= MIN_TRADES and rec.get("avg_return_on_risk_pct") is not None:
            basis = (f"our record: {trades} closed, "
                     f"{rec.get('win_rate_pct')}% wins, "
                     f"{rec['avg_return_on_risk_pct']:+.1f}% avg on risk")
        else:
            basis = (f"prior order (only {trades} closed trade(s) — the "
                     f"record takes over at {MIN_TRADES})")
        out.append({"rank": i, "key": v["key"], "why": v["why"],
                    "basis": basis})
    return out
