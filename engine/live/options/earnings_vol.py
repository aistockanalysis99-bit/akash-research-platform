"""Earnings volatility math — realized past-earnings moves + cheapness ratio.

The strategy's edge is selection: only buy straddles when the CURRENT implied
earnings move is cheap vs what the stock ACTUALLY moved on its past 8-12
earnings. This module computes the realized side from FMP daily bars +
historical earnings dates (both already available in the platform).
"""
from __future__ import annotations

import logging
import statistics
from datetime import date
from typing import Optional

log = logging.getLogger(__name__)


def realized_earnings_moves(bars_df, earnings_dates: list[date],
                            max_events: int = 12) -> list[dict]:
    """Per past earnings date, the absolute % gap the stock made around it.

    FMP doesn't flag BMO vs AMC, so we take the LARGER of the two candidate
    gaps (close[d-1]→close[d] for BMO, close[d]→close[d+1] for AMC) — the
    earnings reaction dominates both windows, so max() lands on the right one.
    """
    if bars_df is None or bars_df.empty:
        return []
    closes = bars_df["close"].astype(float).tolist()
    dates = [str(ts)[:10] for ts in bars_df["timestamp"]]
    idx_by_date = {d: i for i, d in enumerate(dates)}
    today = date.today()

    out: list[dict] = []
    for ed in sorted([d for d in earnings_dates if d < today], reverse=True)[:max_events]:
        ed_iso = ed.isoformat()
        # trading day on/after the earnings date
        i = idx_by_date.get(ed_iso)
        if i is None:
            later = [j for j, d in enumerate(dates) if d > ed_iso]
            if not later:
                continue
            i = later[0]
        if i < 1 or i >= len(closes):
            continue
        gaps = []
        if closes[i - 1]:
            gaps.append(abs(closes[i] / closes[i - 1] - 1) * 100)
        if i + 1 < len(closes) and closes[i]:
            gaps.append(abs(closes[i + 1] / closes[i] - 1) * 100)
        if gaps:
            out.append({"earnings_date": ed_iso, "move_pct": round(max(gaps), 2)})
    return out


def median_move(moves: list[dict]) -> Optional[float]:
    vals = [m["move_pct"] for m in moves if m.get("move_pct") is not None]
    return round(statistics.median(vals), 2) if len(vals) >= 4 else None


def implied_move_pct(straddle_cost: float, spot: float) -> Optional[float]:
    """Market-implied move by expiry ≈ ATM straddle cost / spot (the same
    definition oquants and the client's tool use for 'expected move')."""
    if not straddle_cost or not spot or spot <= 0:
        return None
    return round(straddle_cost / spot * 100, 2)


def cheapness_ratio(implied_pct: Optional[float],
                    hist_median_pct: Optional[float]) -> Optional[float]:
    """implied ÷ realized-history. ≤0.80 = underpriced event (buy-vol zone)."""
    if not implied_pct or not hist_median_pct or hist_median_pct <= 0:
        return None
    return round(implied_pct / hist_median_pct, 2)
