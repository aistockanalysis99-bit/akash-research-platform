"""Quant SignalSource — live scanner that emits candidate tickers daily.

Mirrors the Phase 1 strategy logic at a single point in time:
    - Multi-horizon momentum: weighted blend of 1m / 3m / 6m / 12m returns
    - Trend filter: EMA(50) > EMA(150) AND EMA(150) slope positive
    - Breakout: latest close > highest of prior 20 closes
    - ATR(20) for stop sizing

Reads daily bars from FMP (caches via FMPClient + existing data_cache parquet
where available). Returns the top-N candidates passing all filters as
`QuantCandidate` objects ready to be fed to the evening AI pipeline.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import date
from typing import Optional

import pandas as pd

from ..data.fmp_client import FMPClient
from ..data.universe import get_universe
from .schemas import QuantCandidate

log = logging.getLogger(__name__)


# ---- Strategy parameters (mirroring the spec) ------------------------------ #

MOM_WINDOWS_DAYS = [21, 63, 126, 252]   # ~1m, 3m, 6m, 12m of trading days
MOM_WEIGHTS = [0.4, 0.3, 0.2, 0.1]
SCORE_THRESHOLD = 0.25
TREND_FAST = 50
TREND_SLOW = 150
TREND_SLOPE_BARS = 5
BREAKOUT_LOOKBACK = 20
ATR_LEN = 20


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #


async def find_candidates_today(
    universe_name: str = "SP100",
    max_candidates: int = 15,
    fmp: Optional[FMPClient] = None,
) -> list[QuantCandidate]:
    """Scan the universe and return today's quant candidates.

    Returns the list sorted by score descending, capped at `max_candidates`.
    Tickers without enough bars are skipped silently.
    """
    try:
        symbols = get_universe(universe_name)
    except Exception as e:  # noqa: BLE001
        log.warning("quant_source: unknown universe %s: %s", universe_name, e)
        return []

    own_fmp = fmp is None
    if own_fmp:
        fmp = FMPClient()
    try:
        candidates = await _scan(fmp, symbols)
    finally:
        if own_fmp and fmp is not None:
            await fmp.aclose()

    candidates.sort(key=lambda c: c.score, reverse=True)
    for i, c in enumerate(candidates[:max_candidates], start=1):
        c.rank = i
    return candidates[:max_candidates]


# --------------------------------------------------------------------------- #
# Scan + filter
# --------------------------------------------------------------------------- #


async def _scan(fmp: FMPClient, symbols: list[str]) -> list[QuantCandidate]:
    """Fetch each symbol's bars in parallel (capped) and compute the signal."""
    sem = asyncio.Semaphore(6)

    async def one(symbol: str) -> Optional[QuantCandidate]:
        async with sem:
            try:
                df = await fmp.fetch_daily(symbol)
                if df is None or df.empty or len(df) < max(MOM_WINDOWS_DAYS) + 5:
                    return None
                return _compute_signal(symbol, df)
            except Exception as e:  # noqa: BLE001
                log.warning("quant_source: %s skipped: %s", symbol, e)
                return None

    results = await asyncio.gather(*[one(s) for s in symbols])
    return [c for c in results if c is not None]


def _compute_signal(symbol: str, df: pd.DataFrame) -> Optional[QuantCandidate]:
    """Apply the strategy to one ticker's bars. Returns a candidate or None."""
    closes = df["close"].astype(float).reset_index(drop=True)
    if len(closes) < max(MOM_WINDOWS_DAYS) + 5:
        return None

    last_idx = len(closes) - 1
    last_close = float(closes.iloc[-1])

    # Momentum score — weighted blend of returns over each horizon
    score = 0.0
    for w, lookback in zip(MOM_WEIGHTS, MOM_WINDOWS_DAYS):
        if last_idx < lookback:
            return None
        past = float(closes.iloc[last_idx - lookback])
        if past <= 0:
            return None
        ret = (last_close / past) - 1.0
        score += w * ret

    # Trend filter — fast EMA above slow EMA, slow EMA rising
    ema_fast = closes.ewm(span=TREND_FAST, adjust=False).mean()
    ema_slow = closes.ewm(span=TREND_SLOW, adjust=False).mean()
    if last_idx < TREND_SLOPE_BARS:
        return None
    slope_positive = bool(ema_slow.iloc[-1] > ema_slow.iloc[-TREND_SLOPE_BARS - 1])
    trend_ok = bool(ema_fast.iloc[-1] > ema_slow.iloc[-1] and slope_positive)

    # Breakout — last close above the highest close of prior `BREAKOUT_LOOKBACK` bars
    if last_idx < BREAKOUT_LOOKBACK:
        return None
    prior_high = float(closes.iloc[-BREAKOUT_LOOKBACK - 1 : -1].max())
    breakout_ok = bool(last_close > prior_high)

    # Filter: score above threshold AND trend OK
    # Breakout is informational — we feed both states to PM for context.
    if score < SCORE_THRESHOLD or not trend_ok:
        return None

    # ATR(20) for sizing
    atr_val = _compute_atr(df, ATR_LEN)
    if atr_val is None or atr_val <= 0:
        return None

    return QuantCandidate(
        symbol=symbol.upper(),
        as_of_date=date.today().isoformat(),
        score=round(score, 4),
        trend_ok=trend_ok,
        breakout_ok=breakout_ok,
        current_price=round(last_close, 4),
        atr=round(atr_val, 4),
        rank=0,  # set by caller after sorting
    )


def _compute_atr(df: pd.DataFrame, length: int) -> Optional[float]:
    """Wilder ATR over the last `length` bars."""
    if len(df) < length + 1:
        return None
    high = df["high"].astype(float)
    low = df["low"].astype(float)
    close = df["close"].astype(float)
    prev_close = close.shift(1)
    tr = pd.concat([
        (high - low),
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1.0 / length, adjust=False).mean()
    return float(atr.iloc[-1]) if not atr.empty else None
