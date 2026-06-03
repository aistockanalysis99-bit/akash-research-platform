"""Core domain types used across the engine.

All money values are USD floats. All timestamps are timezone-aware UTC datetimes.
Quantities can be fractional if the user enables fractional shares.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional


class Direction(str, Enum):
    LONG = "long"
    SHORT = "short"


class ExitReason(str, Enum):
    STOP = "stop"
    PARTIAL_TP = "partial_tp"
    TRAIL = "trail"
    SOFT_EXIT = "soft_exit"
    TIME_EXIT = "time_exit"
    END_OF_BACKTEST = "end_of_backtest"


class RunStatus(str, Enum):
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


@dataclass(frozen=True)
class Bar:
    """One bar of OHLCV data for a single symbol."""
    timestamp: datetime
    symbol: str
    open: float
    high: float
    low: float
    close: float
    volume: float
    adj_close: float

    @property
    def is_valid(self) -> bool:
        return (
            self.high >= self.low
            and self.high >= self.open
            and self.high >= self.close
            and self.low <= self.open
            and self.low <= self.close
            and self.close > 0
        )


@dataclass
class Position:
    """An open position in a single symbol. Long-only in v1."""
    symbol: str
    qty: float                       # total shares held (sum of original + adds)
    avg_price: float                 # weighted average entry price
    entry_time: datetime
    initial_stop: float              # absolute price level for the original hard stop
    initial_risk_dist: float         # entry_price - initial_stop, positive number (R)
    trail_high: float                # highest close since entry (long)
    bars_in_trade: int = 0
    adds_done: int = 0
    next_add_price: float = 0.0      # price level that triggers the next add
    partial_taken: bool = False      # whether the 50% TP has been realized
    mae: float = 0.0                 # max adverse excursion in $
    mfe: float = 0.0                 # max favorable excursion in $
    fills: list["Fill"] = field(default_factory=list)


@dataclass
class Fill:
    """A single fill (entry add, partial exit, full exit)."""
    timestamp: datetime
    symbol: str
    qty: float                       # positive for buys, negative for sells
    price: float
    commission: float
    slippage: float
    reason: str                      # 'entry' | 'add' | 'partial_tp' | 'stop' | 'trail' | 'soft_exit' | 'time_exit'


@dataclass
class Trade:
    """A completed round-trip trade (entry to full exit)."""
    symbol: str
    entry_time: datetime
    exit_time: datetime
    entry_price: float               # avg entry
    exit_price: float                # avg exit
    qty: float                       # total shares (sum of adds)
    pnl: float                       # net of commission and slippage
    pnl_pct: float                   # pnl / (entry_price * qty)
    exit_reason: ExitReason
    bars_held: int
    mae: float
    mfe: float
    commission_total: float
    fills: list[Fill] = field(default_factory=list)


@dataclass
class EquityPoint:
    """One point on the equity curve."""
    timestamp: datetime
    equity: float
    cash: float
    gross_exposure: float
    open_positions: int


@dataclass
class StrategyParams:
    """All tunable strategy parameters. Defaults match the PDF spec."""
    # Signal
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

    # Trend
    fast_len: int = 50
    slow_len: int = 150
    slope_bars: int = 5
    breakout_len: int = 20

    # Risk
    atr_len: int = 20
    stop_atr: float = 2.5
    trail_atr: float = 3.0
    breakeven_rr: float = 1.0
    risk_pct: float = 0.005          # 0.5% of equity per initial unit
    target_vol: float = 0.10
    max_lev_scalar: float = 1.50
    max_gross_exp: float = 1.50

    # Scaling
    enable_scale_in: bool = True
    max_adds: int = 2
    add_atr: float = 0.75
    add_frac: float = 0.50
    enable_partial_tp: bool = True
    partial_pct: int = 50
    take_profit_rr: float = 2.0
    max_bars_in_trade: int = 120

    # Portfolio (hybrid layer, the v1 differentiator)
    max_concurrent_positions: int = 10
    portfolio_vol_target: float = 0.10
    max_portfolio_gross: float = 1.0

    # Costs
    commission_bps: float = 2.0
    slippage_bps: float = 1.0

    # Execution
    fractional_shares: bool = False

    def signature(self) -> str:
        """Short signature for run names (e.g. 'def' for defaults)."""
        # Hash of non-default values for naming
        from hashlib import md5
        defaults = StrategyParams()
        diffs = {
            k: getattr(self, k)
            for k in self.__dataclass_fields__
            if getattr(self, k) != getattr(defaults, k)
        }
        if not diffs:
            return "default"
        return md5(repr(sorted(diffs.items())).encode()).hexdigest()[:6]


@dataclass
class BacktestConfig:
    """Configuration for a single backtest run."""
    universe: list[str]
    start_date: datetime
    end_date: datetime
    timeframe: str                   # '1D' | '1W' | '4h' | '1h' | '30m' | '15m'
    initial_capital: float = 100_000.0
    params: StrategyParams = field(default_factory=StrategyParams)
    run_name: Optional[str] = None
    universe_name: str = "custom"


@dataclass
class BacktestResult:
    """Complete output of a backtest."""
    run_id: str
    run_name: str
    config: BacktestConfig
    equity_curve: list[EquityPoint]
    trades: list[Trade]
    metrics: dict[str, Any]
    per_symbol_stats: list[dict[str, Any]]
    started_at: datetime
    finished_at: datetime
    status: RunStatus = RunStatus.DONE
    error_message: Optional[str] = None
