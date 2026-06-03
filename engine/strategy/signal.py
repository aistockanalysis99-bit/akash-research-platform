"""Momentum signal computation: vol-normalized weighted multi-horizon score."""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..core.types import StrategyParams
from .indicators import (
    atr,
    ema,
    realized_vol,
    rolling_highest,
    skip_adjusted_return,
)


def compute_signal_columns(df: pd.DataFrame, p: StrategyParams) -> pd.DataFrame:
    """Add all signal-related columns to a per-symbol bar DataFrame.

    Adds (in place returns a copy):
      - r_short, r_med, r_long: skip-adjusted returns
      - rv: realized vol (annualized)
      - mom_score: S_t  (NaN where insufficient history)
      - ema_fast, ema_slow, slow_rising
      - atr
      - breakout_high (prior N-bar high, exclusive of current)
      - bull_state, breakout_long
    """
    out = df.copy()
    close = out["close"]

    out["r_short"] = skip_adjusted_return(close, p.mom_short_len, p.skip_bars)
    out["r_med"] = skip_adjusted_return(close, p.mom_med_len, p.skip_bars)
    out["r_long"] = skip_adjusted_return(close, p.mom_long_len, p.skip_bars)

    weight_sum = max(p.w_short + p.w_med + p.w_long, 1e-9)
    ws, wm, wl = p.w_short / weight_sum, p.w_med / weight_sum, p.w_long / weight_sum

    out["rv"] = realized_vol(close, p.vol_lookback, p.annualization_factor)
    rv_safe = out["rv"].clip(lower=1e-6)

    raw = ws * out["r_short"] + wm * out["r_med"] + wl * out["r_long"]
    out["mom_score"] = raw / rv_safe

    out["ema_fast"] = ema(close, p.fast_len)
    out["ema_slow"] = ema(close, p.slow_len)
    out["slow_rising"] = out["ema_slow"] > out["ema_slow"].shift(p.slope_bars)

    out["atr"] = atr(out, p.atr_len)
    out["breakout_high"] = rolling_highest(out["high"], p.breakout_len)

    out["bull_state"] = (
        out["mom_score"].notna()
        & (out["mom_score"] > p.entry_threshold)
        & (out["ema_fast"] > out["ema_slow"])
        & out["slow_rising"]
    )

    # Long breakout: today's close breaks above prior N-bar high, prior close was at/below
    prior_high = out["breakout_high"]
    prev_close = out["close"].shift(1)
    out["breakout_long"] = (
        prior_high.notna()
        & (out["close"] > prior_high)
        & (prev_close <= prior_high)
    )
    return out


def required_warmup_bars(p: StrategyParams) -> int:
    """Minimum bars before any signal can fire."""
    return max(
        p.mom_long_len + p.skip_bars + 2,
        p.slow_len + p.slope_bars + 2,
        p.atr_len + 2,
        p.breakout_len + 2,
        p.vol_lookback + 2,
    )
