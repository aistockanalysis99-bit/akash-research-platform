"""Hybrid portfolio layer: per-symbol signals filtered by portfolio-level constraints.

v1 simplifications:
- Zero-correlation assumption for ex-ante portfolio vol
- When concurrent cap is hit, skip new candidates (don't evict)
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

from ..core.types import Position, StrategyParams


@dataclass
class EntryCandidate:
    symbol: str
    score: float                     # mom_score; used for ranking
    ref_price: float                 # next-bar open price (for fill)
    atr_value: float
    realized_vol: float
    initial_qty_proposed: float      # before portfolio scaling


def filter_candidates(
    candidates: list[EntryCandidate],
    open_positions: dict[str, Position],
    equity: float,
    p: StrategyParams,
) -> list[EntryCandidate]:
    """Apply portfolio-level filters and return accepted candidates with adjusted sizes.

    Order:
      1. Drop symbols already in open positions
      2. Sort remaining by score descending
      3. Take up to (max_concurrent_positions - len(open_positions))
      4. Scale sizes by min(1.0, portfolio_vol_target / current_portfolio_vol)
      5. Cap total gross to max_portfolio_gross * equity
    """
    # Step 1
    candidates = [c for c in candidates if c.symbol not in open_positions]

    # Step 2-3
    candidates.sort(key=lambda c: c.score, reverse=True)
    slots = max(0, p.max_concurrent_positions - len(open_positions))
    chosen = candidates[:slots]
    if not chosen:
        return []

    # Step 4: portfolio vol scalar
    # Estimate ex-ante portfolio vol assuming zero correlation:
    # current $vol = sum_i (qty_i * price_i * realized_vol_i)
    current_dollar_vol = 0.0
    for sym, pos in open_positions.items():
        # We don't have realized_vol per open pos here; v1 ignores existing positions for scalar
        # (they are already sized by their own vol scalar at entry).
        current_dollar_vol += pos.qty * pos.avg_price * 0.20  # rough placeholder

    cand_dollar_vol = 0.0
    for c in chosen:
        rv = c.realized_vol if not math.isnan(c.realized_vol) else 0.20
        cand_dollar_vol += c.initial_qty_proposed * c.ref_price * rv

    total_dollar_vol = current_dollar_vol + cand_dollar_vol
    target_dollar_vol = equity * p.portfolio_vol_target
    if total_dollar_vol > target_dollar_vol > 0:
        scale = max(0.0, target_dollar_vol / total_dollar_vol)
        for c in chosen:
            c.initial_qty_proposed *= scale

    # Step 5: gross cap
    current_gross = sum(pos.qty * pos.avg_price for pos in open_positions.values())
    cand_gross = sum(c.initial_qty_proposed * c.ref_price for c in chosen)
    max_gross = equity * p.max_portfolio_gross
    if current_gross + cand_gross > max_gross > 0:
        room = max(0.0, max_gross - current_gross)
        if cand_gross > 0:
            scale = room / cand_gross
            for c in chosen:
                c.initial_qty_proposed *= scale

    # Whole shares enforcement
    if not p.fractional_shares:
        for c in chosen:
            c.initial_qty_proposed = math.floor(c.initial_qty_proposed)
        chosen = [c for c in chosen if c.initial_qty_proposed >= 1]
    else:
        chosen = [c for c in chosen if c.initial_qty_proposed > 0]

    return chosen
