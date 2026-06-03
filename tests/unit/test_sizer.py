"""Tests for position sizing."""
from __future__ import annotations

import math

from engine.core.types import StrategyParams
from engine.strategy.sizer import add_qty, initial_qty, vol_scalar


def test_vol_scalar_caps_at_max_lev():
    # Very low realized vol -> big multiplier, capped
    vs = vol_scalar(realized_vol=0.01, target_vol=0.10, max_lev=1.5)
    assert vs == 1.5  # capped


def test_vol_scalar_reduces_when_vol_high():
    # High realized vol -> scalar < 1
    vs = vol_scalar(realized_vol=0.40, target_vol=0.10, max_lev=1.5)
    assert vs == 0.25


def test_vol_scalar_safe_on_zero():
    assert vol_scalar(0.0, 0.10, 1.5) == 1.0
    assert vol_scalar(float("nan"), 0.10, 1.5) == 1.0


def test_initial_qty_zero_when_atr_zero():
    p = StrategyParams()
    assert initial_qty(equity=100_000, price=100, atr_value=0.0, realized_vol_value=0.2, p=p) == 0.0


def test_initial_qty_zero_when_price_zero():
    p = StrategyParams()
    assert initial_qty(equity=100_000, price=0.0, atr_value=2.0, realized_vol_value=0.2, p=p) == 0.0


def test_initial_qty_capped_by_gross():
    """With huge ATR room and tiny stop, gross-exposure cap should bind."""
    p = StrategyParams(risk_pct=0.50, max_gross_exp=1.0)  # absurdly large risk
    qty = initial_qty(equity=100_000, price=100, atr_value=0.5, realized_vol_value=0.20, p=p)
    # Gross-cap qty: 100k * 1.0 / 100 = 1000
    assert qty <= 1000.0


def test_initial_qty_whole_shares_default():
    p = StrategyParams()  # fractional_shares=False
    qty = initial_qty(equity=100_000, price=100, atr_value=2.0, realized_vol_value=0.20, p=p)
    assert qty == math.floor(qty)


def test_initial_qty_fractional_when_enabled():
    p = StrategyParams(fractional_shares=True)
    qty = initial_qty(equity=100_000, price=100, atr_value=2.0, realized_vol_value=0.20, p=p)
    # qty is a float; just verify nonzero and not necessarily integer
    assert qty > 0


def test_add_qty_respects_fraction_and_whole_shares():
    p = StrategyParams()
    aq = add_qty(initial_quantity=10, p=p)
    assert aq == 5  # 50% of 10, floored


def test_add_qty_zero_when_fraction_zero():
    p = StrategyParams(add_frac=0.0)
    assert add_qty(100, p) == 0
