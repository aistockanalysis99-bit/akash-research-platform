"""Position sizing: risk-based with vol-target overlay."""
from __future__ import annotations

import math

from ..core.types import StrategyParams


def vol_scalar(realized_vol: float, target_vol: float, max_lev: float) -> float:
    """min(maxLev, target/realized). 1.0 if vol is zero/missing."""
    if realized_vol is None or realized_vol <= 0 or math.isnan(realized_vol):
        return 1.0
    return min(max_lev, target_vol / realized_vol)


def initial_qty(
    equity: float,
    price: float,
    atr_value: float,
    realized_vol_value: float,
    p: StrategyParams,
) -> float:
    """Compute initial trade quantity.

    Risk-based: equity * riskPct * volScalar / (stopATR * ATR)
    Capped by gross exposure: equity * maxGrossExp / price
    Whole shares unless fractional_shares is enabled.
    """
    if atr_value is None or atr_value <= 0 or math.isnan(atr_value):
        return 0.0
    if price <= 0:
        return 0.0

    vs = vol_scalar(realized_vol_value, p.target_vol, p.max_lev_scalar)
    risk_cash = equity * p.risk_pct * vs
    stop_dist = p.stop_atr * atr_value
    qty_by_risk = risk_cash / stop_dist if stop_dist > 0 else 0.0

    qty_by_gross = (equity * p.max_gross_exp) / price if price > 0 else 0.0

    qty = max(0.0, min(qty_by_risk, qty_by_gross))

    if not p.fractional_shares:
        qty = math.floor(qty)

    return float(qty)


def add_qty(initial_quantity: float, p: StrategyParams) -> float:
    """Pyramid add size."""
    qty = initial_quantity * p.add_frac
    if not p.fractional_shares:
        qty = math.floor(qty)
    return float(qty)
