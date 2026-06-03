"""High-level orchestration of the momentum strategy.

Computes signal columns per symbol once at backtest start, then exposes
per-bar lookup helpers for the event loop.
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from ..core.types import StrategyParams
from .signal import compute_signal_columns, required_warmup_bars


@dataclass
class SymbolView:
    """Pre-computed signal data for one symbol, indexed by bar position."""
    symbol: str
    df: pd.DataFrame                 # full DataFrame with signal columns
    timestamps: pd.Series            # for fast position lookup


def prepare_symbol_views(
    panel: dict[str, pd.DataFrame],
    params: StrategyParams,
) -> dict[str, SymbolView]:
    """Pre-compute signal columns for every symbol in the panel."""
    out: dict[str, SymbolView] = {}
    warmup = required_warmup_bars(params)
    for sym, df in panel.items():
        if len(df) < warmup:
            continue
        df_sig = compute_signal_columns(df, params)
        out[sym] = SymbolView(symbol=sym, df=df_sig, timestamps=df_sig["timestamp"])
    return out
