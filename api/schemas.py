"""Pydantic schemas for API I/O. Matches engine.core.types where possible."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class StrategyParamsSchema(BaseModel):
    skip_bars: int = 5
    mom_short_len: int = 21
    mom_med_len: int = 63
    mom_long_len: int = 126
    w_short: float = 0.20
    w_med: float = 0.40
    w_long: float = 0.40
    vol_lookback: int = 20
    annualization_factor: int = 252
    entry_threshold: float = 0.25
    exit_threshold: float = 0.00

    fast_len: int = 50
    slow_len: int = 150
    slope_bars: int = 5
    breakout_len: int = 20

    atr_len: int = 20
    stop_atr: float = 2.5
    trail_atr: float = 3.0
    breakeven_rr: float = 1.0
    risk_pct: float = 0.005
    target_vol: float = 0.10
    max_lev_scalar: float = 1.50
    max_gross_exp: float = 1.50

    enable_scale_in: bool = True
    max_adds: int = 2
    add_atr: float = 0.75
    add_frac: float = 0.50
    enable_partial_tp: bool = True
    partial_pct: int = 50
    take_profit_rr: float = 2.0
    max_bars_in_trade: int = 120

    max_concurrent_positions: int = 10
    portfolio_vol_target: float = 0.10
    max_portfolio_gross: float = 1.0

    commission_bps: float = 2.0
    slippage_bps: float = 1.0

    fractional_shares: bool = False


class BacktestRequest(BaseModel):
    universe: str = Field(default="smoke", description="Universe name (sp100|smoke) or 'custom'")
    custom_symbols: Optional[list[str]] = None
    timeframe: str = "1D"
    start_date: datetime
    end_date: datetime
    initial_capital: float = 100_000.0
    params: StrategyParamsSchema = Field(default_factory=StrategyParamsSchema)
    run_name: Optional[str] = None


class BacktestRunResponse(BaseModel):
    run_id: str
    name: str
    status: str
    progress: float = 0.0
    progress_msg: str = ""


class RunSummary(BaseModel):
    id: str
    name: Optional[str]
    status: str
    progress: float
    progress_msg: Optional[str]
    started_at: Optional[str]
    finished_at: Optional[str]
    timeframe: str
    universe_name: Optional[str]
    initial_capital: float
    metrics: dict[str, Any] = Field(default_factory=dict)
    error_message: Optional[str] = None


class EquityPointSchema(BaseModel):
    timestamp: str
    equity: float
    cash: float
    gross_exposure: float
    open_positions: int


class TradeSchema(BaseModel):
    id: int
    symbol: str
    entry_time: str
    exit_time: str
    entry_price: float
    exit_price: float
    qty: float
    pnl: float
    pnl_pct: float
    exit_reason: str
    bars_held: int
    mae: Optional[float]
    mfe: Optional[float]
    commission_total: Optional[float]


class PerSymbolSchema(BaseModel):
    symbol: str
    trades: int
    wins: int
    win_rate: float
    total_pnl: float
    avg_pnl: float
    best_trade: float
    worst_trade: float


class RefreshRequest(BaseModel):
    universe: Optional[str] = None
    symbols: Optional[list[str]] = None
    timeframe: str = "1D"
    years: int = 5
    full: bool = False


class ParameterSetIn(BaseModel):
    name: str
    params: StrategyParamsSchema


class ParameterSetOut(BaseModel):
    id: int
    name: str
    params: StrategyParamsSchema
    created_at: str


class CompareRequest(BaseModel):
    run_ids: list[str]
