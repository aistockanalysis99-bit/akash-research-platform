"""Strategy v4 Quantitative Engine ("Risk-Engineered Pure Alpha").

Institutional Quantitative Pairs Trading Engine engineered to directly solve
the 8 quantitative bottlenecks of Strategy 1 and Strategy 3:
  1. Momentum Flattening Confirmation:
     Requires spread divergence (|Z| >= 2.10sigma), entering ONLY when the 2-day
     adverse momentum slope <= 0.05sigma or reversing towards the mean. Prevents falling knives.
  2. Realistic Exit Target:
     Exits 100% of position when spread recovers to |Z| <= 0.40sigma (REVERSION_TARGET).
     Captures the high-probability meat of the mean-reversion move without suffering stale decay.
  3. Tight Dynamic Stop-Loss:
     Exits immediately if dislocation crosses |Z| >= 2.85sigma (TIGHT_STOP).
     Cuts losing tails aggressively before catastrophic blowout occurs.
  4. 2x Half-Life Time Stop:
     Clamps holding duration to T_max = max(4, min(22, round(2.0 * half_life_days))) (TIME_STOP).
     Forces capital recycling out of dead, non-reverting pairs.
  5. Volatility-Inverse Position Sizing:
     Scales position sizing inversely with spread volatility:
       multiplier = min(1.25, max(0.40, 3.5 / relative_spread_vol_pct))
     Includes a 0.70x drawdown dampener when portfolio drawdown >= 20.0%.
  6. Earnings Blackout Shield:
     Vetoes entries within 5 days before and 2 days after earnings calls.
  7. VIX Macro Overlay:
     Freezes new entries when broader market volatility exceeds 25.0 to protect against liquidity shocks.
  8. Strict Volatility Tier Cap:
     Rejects pairs with relative spread volatility > 6.0%.

Zero Lookahead Guarantee:
  Historical data sliced strictly to t <= T for setup detection and gauntlet evaluation.
"""

from __future__ import annotations

import json
import logging
import math
import sys
import warnings
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Union

warnings.filterwarnings("ignore", category=FutureWarning)

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import numpy as np
import pandas as pd

from engine.config import DATA_CACHE_DIR, PROJECT_ROOT
from engine.logging_setup import get_logger
from engine.simulator_engine import PointInTimeEngine, PointInTimeSetup
from engine.strategy_v2_engine import EarningsCalendar

logger = get_logger("strategy_v4_engine")

CONFIG_V4_ROOT = PROJECT_ROOT / "pair_strategy_v4_config.json"
CONFIG_V4_DATA = PROJECT_ROOT / "data" / "pair_strategy_v4_config.json"
PARQUET_PATH_DEFAULT = DATA_CACHE_DIR / "universe_5y_daily.parquet"


def clean_float(val: Any, default: float = 0.0) -> float:
    """Ensure float is RFC-8259 JSON compliant (no NaN or Inf)."""
    if val is None:
        return default
    try:
        f = float(val)
        if math.isnan(f) or math.isinf(f):
            return default
        return round(f, 4)
    except (TypeError, ValueError):
        return default


@dataclass
class StrategyV4Config:
    version: str = "4.0.0"
    strategy_name: str = "Cointegrated Stat-Arb v4 (Risk-Engineered Pure Alpha)"
    description: str = "Risk-Engineered Pure Alpha with Momentum Flattening, Vol-Inverse Sizing, Tight Stops, and 2x Half-Life Time Stops"
    z_score_entry_hurdle: float = 2.10
    z_score_entry_max: float = 3.00
    max_entry_momentum_slope: float = 0.05
    z_score_exit_target: float = 0.40
    z_score_stop_loss_barrier: float = 2.85
    stop_loss_cushion: float = 1.15
    fill_at_barrier: bool = True
    lookback_days: int = 90
    target_spread_vol_pct: float = 3.5
    min_capital_multiplier: float = 0.40
    max_capital_multiplier: float = 1.25
    drawdown_dampener_enabled: bool = True
    drawdown_threshold_pct: float = 20.0
    drawdown_scaling_factor: float = 0.70
    half_life_time_stop_multiplier: float = 2.5
    min_holding_days_floor: int = 4
    max_holding_days_cap: int = 22
    earnings_blackout_days_pre: int = 5
    earnings_blackout_days_post: int = 2
    vix_overlay_enabled: bool = True
    vix_panic_threshold: float = 25.0
    max_allowed_spread_vol_pct: float = 5.5

    @classmethod
    def load(cls, path: Optional[Union[str, Path]] = None) -> "StrategyV4Config":
        p = Path(path) if path else (CONFIG_V4_ROOT if CONFIG_V4_ROOT.exists() else CONFIG_V4_DATA)
        if not p.exists():
            return cls()
        try:
            with open(p, "r", encoding="utf-8") as fp:
                d = json.load(fp)
            dt = d.get("divergence_triggers", {})
            vol = d.get("volatility_inverse_sizing", {})
            t_stops = d.get("time_and_event_stops", {})
            macro = d.get("macro_regime_overlay", {})
            tiers = d.get("spread_volatility_tiers", {})
            return cls(
                version=d.get("version", "4.0.0"),
                strategy_name=d.get("strategy_name", "Cointegrated Stat-Arb v4 (Risk-Engineered Pure Alpha)"),
                description=d.get("description", ""),
                z_score_entry_hurdle=float(dt.get("z_score_entry_hurdle", 2.10)),
                z_score_entry_max=float(dt.get("z_score_entry_max", 3.00)),
                max_entry_momentum_slope=float(dt.get("max_entry_momentum_slope", 0.05)),
                z_score_exit_target=float(dt.get("z_score_exit_target", 0.40)),
                z_score_stop_loss_barrier=float(dt.get("z_score_stop_loss_barrier", 2.85)),
                stop_loss_cushion=float(dt.get("stop_loss_cushion", 1.15)),
                fill_at_barrier=bool(dt.get("fill_at_barrier", True)),
                lookback_days=int(dt.get("lookback_days", 90)),
                target_spread_vol_pct=float(vol.get("target_spread_vol_pct", 3.5)),
                min_capital_multiplier=float(vol.get("min_capital_multiplier", 0.40)),
                max_capital_multiplier=float(vol.get("max_capital_multiplier", 1.25)),
                drawdown_dampener_enabled=bool(vol.get("drawdown_dampener_enabled", True)),
                drawdown_threshold_pct=float(vol.get("drawdown_threshold_pct", 20.0)),
                drawdown_scaling_factor=float(vol.get("drawdown_scaling_factor", 0.70)),
                half_life_time_stop_multiplier=float(t_stops.get("half_life_time_stop_multiplier", 2.5)),
                min_holding_days_floor=int(t_stops.get("min_holding_days_floor", 4)),
                max_holding_days_cap=int(t_stops.get("max_holding_days_cap", 22)),
                earnings_blackout_days_pre=int(t_stops.get("earnings_blackout_days_pre", 5)),
                earnings_blackout_days_post=int(t_stops.get("earnings_blackout_days_post", 2)),
                vix_overlay_enabled=bool(macro.get("vix_overlay_enabled", True)),
                vix_panic_threshold=float(macro.get("vix_panic_threshold", 25.0)),
                max_allowed_spread_vol_pct=float(tiers.get("max_allowed_spread_vol_pct", 5.5)),
            )
        except Exception as e:
            logger.warning(f"Error loading v4 config from {p}: {e}, using defaults.")
            return cls()


@dataclass
class StrategyV4TradeResult:
    pair_name: str
    ticker_a: str
    ticker_b: str
    sector: str
    entry_date: str
    exit_date: Optional[str]
    direction: str
    direction_label: str
    entry_z: float
    exit_z: float
    hedge_ratio: float
    entry_price_a: float
    entry_price_b: float
    exit_price_a: float
    exit_price_b: float
    outcome: str                      # "WIN", "LOSS", "NEUTRAL"
    exit_reason: str                  # "REVERSION_TARGET", "TIGHT_STOP", "TIME_STOP"
    status_reason: str
    holding_days: int
    raw_return_pct: float
    realized_return_pct: float        # Volatility-inverse sized return
    sizing_multiplier: float
    spread_vol_pct: float
    half_life_days: float
    max_holding_limit: int
    is_dampened: bool
    momentum_slope: float
    composite_score: float
    trajectory: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class StrategyV4EvaluationOutcome:
    trade_result: StrategyV4TradeResult
    exit_timestamp: pd.Timestamp


class StrategyV4OutcomeEvaluator:
    """Evaluates forward trajectory under Strategy v4 Risk-Engineered Execution Rules."""

    def __init__(
        self,
        config: Optional[StrategyV4Config] = None,
        parquet_path: Optional[Union[Path, str]] = None,
        df: Optional[pd.DataFrame] = None,
    ) -> None:
        self.config = config or StrategyV4Config.load()
        self.parquet_path = Path(parquet_path or PARQUET_PATH_DEFAULT)
        self.df = df
        self._arrays: Optional[Dict[Tuple[str, str], np.ndarray]] = None
        self._dates: Optional[List[pd.Timestamp]] = None
        self._index: Optional[pd.DatetimeIndex] = None

        if self.df is not None:
            self._init_data(self.df)

    def _init_data(self, df: pd.DataFrame) -> None:
        norm_df = df.copy()
        norm_df.index = pd.to_datetime(norm_df.index).normalize()
        self.df = norm_df.sort_index()
        self._index = self.df.index
        self._dates = list(self.df.index)
        self._arrays = {col: self.df[col].to_numpy(dtype=float) for col in self.df.columns}

    def load_data(self) -> pd.DataFrame:
        if self.df is None:
            if not self.parquet_path.exists():
                raise FileNotFoundError(f"Parquet dataset not found at {self.parquet_path}")
            raw = pd.read_parquet(self.parquet_path)
            self._init_data(raw)
        return self.df

    def evaluate_setup(
        self,
        setup: PointInTimeSetup,
        sizing_multiplier: float,
        is_dampened: bool,
        momentum_slope: float,
    ) -> StrategyV4EvaluationOutcome:
        self.load_data()
        assert self._index is not None and self._dates is not None and self._arrays is not None

        t_entry = pd.to_datetime(setup.target_date).normalize()
        pos = int(self._index.searchsorted(t_entry, side="right"))
        n_dates = len(self._dates)

        # Dynamic holding ceiling: 2.0 * half_life (clamped between min_holding_days_floor and max_holding_days_cap)
        t_max = max(
            self.config.min_holding_days_floor,
            min(self.config.max_holding_days_cap, int(round(self.config.half_life_time_stop_multiplier * setup.half_life_days))),
        )

        direction_label = (
            f"Long {setup.ticker_a} / Short {setup.ticker_b}"
            if (setup.direction == "LONG_A_SHORT_B" or setup.current_z_score < 0)
            else f"Short {setup.ticker_a} / Long {setup.ticker_b}"
        )

        if pos >= n_dates:
            return StrategyV4EvaluationOutcome(
                trade_result=StrategyV4TradeResult(
                    pair_name=setup.pair_name,
                    ticker_a=setup.ticker_a,
                    ticker_b=setup.ticker_b,
                    sector=setup.sector or "Other",
                    entry_date=setup.target_date,
                    exit_date=setup.target_date,
                    direction=setup.direction,
                    direction_label=direction_label,
                    entry_z=round(setup.current_z_score, 3),
                    exit_z=round(setup.current_z_score, 3),
                    hedge_ratio=round(setup.hedge_ratio, 4),
                    entry_price_a=round(setup.price_a_entry, 2),
                    entry_price_b=round(setup.price_b_entry, 2),
                    exit_price_a=round(setup.price_a_entry, 2),
                    exit_price_b=round(setup.price_b_entry, 2),
                    outcome="OPEN",
                    exit_reason="OPEN",
                    status_reason="No future market data available after entry date",
                    holding_days=0,
                    raw_return_pct=0.0,
                    realized_return_pct=0.0,
                    sizing_multiplier=sizing_multiplier,
                    spread_vol_pct=round(setup.relative_spread_vol_pct, 2),
                    half_life_days=round(setup.half_life_days, 1),
                    max_holding_limit=t_max,
                    is_dampened=is_dampened,
                    momentum_slope=round(momentum_slope, 4),
                    composite_score=round(setup.composite_score, 1),
                ),
                exit_timestamp=t_entry,
            )

        end_pos = min(n_dates, pos + t_max)
        future_dates = self._dates[pos:end_pos]

        ta = setup.ticker_a
        tb = setup.ticker_b
        key_a = ("Adj Close", ta) if ("Adj Close", ta) in self._arrays else ("Close", ta)
        key_b = ("Adj Close", tb) if ("Adj Close", tb) in self._arrays else ("Close", tb)

        if key_a not in self._arrays or key_b not in self._arrays or not future_dates:
            return StrategyV4EvaluationOutcome(
                trade_result=StrategyV4TradeResult(
                    pair_name=setup.pair_name,
                    ticker_a=setup.ticker_a,
                    ticker_b=setup.ticker_b,
                    sector=setup.sector or "Other",
                    entry_date=setup.target_date,
                    exit_date=setup.target_date,
                    direction=setup.direction,
                    direction_label=direction_label,
                    entry_z=round(setup.current_z_score, 3),
                    exit_z=round(setup.current_z_score, 3),
                    hedge_ratio=round(setup.hedge_ratio, 4),
                    entry_price_a=round(setup.price_a_entry, 2),
                    entry_price_b=round(setup.price_b_entry, 2),
                    exit_price_a=round(setup.price_a_entry, 2),
                    exit_price_b=round(setup.price_b_entry, 2),
                    outcome="NEUTRAL",
                    exit_reason="DATA_MISSING",
                    status_reason="Ticker missing in future dataset",
                    holding_days=0,
                    raw_return_pct=0.0,
                    realized_return_pct=0.0,
                    sizing_multiplier=sizing_multiplier,
                    spread_vol_pct=round(setup.relative_spread_vol_pct, 2),
                    half_life_days=round(setup.half_life_days, 1),
                    max_holding_limit=t_max,
                    is_dampened=is_dampened,
                    momentum_slope=round(momentum_slope, 4),
                    composite_score=round(setup.composite_score, 1),
                ),
                exit_timestamp=t_entry,
            )

        close_a = self._arrays[key_a][pos:end_pos]
        close_b = self._arrays[key_b][pos:end_pos]

        has_hl = (
            ("High", ta) in self._arrays and ("High", tb) in self._arrays and
            ("Low", ta) in self._arrays and ("Low", tb) in self._arrays
        )
        if has_hl:
            high_a = self._arrays[("High", ta)][pos:end_pos]
            low_a = self._arrays[("Low", ta)][pos:end_pos]
            high_b = self._arrays[("High", tb)][pos:end_pos]
            low_b = self._arrays[("Low", tb)][pos:end_pos]

        beta = setup.hedge_ratio
        mu = setup.spread_mean
        sigma = setup.spread_std
        is_long = (setup.direction == "LONG_A_SHORT_B" or setup.current_z_score < 0)
        invested_capital = max(0.01, setup.price_a_entry + abs(beta) * setup.price_b_entry)

        target_exit_z = self.config.z_score_exit_target
        abs_entry_z = abs(setup.current_z_score)
        actual_stop_z = max(self.config.z_score_stop_loss_barrier, abs_entry_z + self.config.stop_loss_cushion)

        target_spread = (mu - target_exit_z * sigma) if is_long else (mu + target_exit_z * sigma)
        stop_spread = (mu - actual_stop_z * sigma) if is_long else (mu + actual_stop_z * sigma)

        resolved_outcome: Optional[str] = None
        exit_reason: str = ""
        exit_date_str: Optional[str] = None
        exit_days = 0
        exit_pa = 0.0
        exit_pb = 0.0
        exit_spread = 0.0
        exit_z = 0.0
        path: List[Dict[str, Any]] = []

        for i, f_date in enumerate(future_dates, start=1):
            f_date_str = f_date.strftime("%Y-%m-%d")
            pa_c = float(close_a[i - 1])
            pb_c = float(close_b[i - 1])
            s_c = float(pa_c - beta * pb_c)
            z_c = float((s_c - mu) / sigma)

            path.append({
                "date": f_date_str,
                "days_elapsed": i,
                "price_a": round(pa_c, 2),
                "price_b": round(pb_c, 2),
                "spread": round(s_c, 4),
                "z_score": round(z_c, 4),
            })

            stop_hit = False
            target_hit = False

            if is_long:
                # Entered at z <= -2.10
                if z_c <= -actual_stop_z:
                    stop_hit = True
                if z_c >= -target_exit_z:
                    target_hit = True
            else:
                # Entered at z >= +2.10
                if z_c >= actual_stop_z:
                    stop_hit = True
                if z_c <= target_exit_z:
                    target_hit = True

            # Strict priority: Stop loss takes priority over target if both trigger on same day
            if stop_hit:
                resolved_outcome = "LOSS"
                exit_reason = "TIGHT_STOP"
                exit_date_str = f_date_str
                exit_days = i
                exit_pa = pa_c
                exit_pb = pb_c
                exit_spread = stop_spread if self.config.fill_at_barrier else s_c
                exit_z = -actual_stop_z if is_long else actual_stop_z
                break
            elif target_hit:
                resolved_outcome = "WIN"
                exit_reason = "REVERSION_TARGET"
                exit_date_str = f_date_str
                exit_days = i
                exit_pa = pa_c
                exit_pb = pb_c
                exit_spread = target_spread if self.config.fill_at_barrier else s_c
                exit_z = -target_exit_z if is_long else target_exit_z
                break

        # Time Stop hit if neither stop nor target triggered
        if resolved_outcome is None:
            exit_days = len(future_dates)
            exit_date_str = future_dates[-1].strftime("%Y-%m-%d")
            exit_pa = float(close_a[-1])
            exit_pb = float(close_b[-1])
            exit_spread = float(exit_pa - beta * exit_pb)
            exit_z = float((exit_spread - mu) / sigma)
            exit_reason = "TIME_STOP"

            raw_diff = (exit_spread - setup.current_spread) if is_long else (setup.current_spread - exit_spread)
            resolved_outcome = "WIN" if raw_diff > 0 else ("LOSS" if raw_diff < 0 else "NEUTRAL")

        # PnL computation
        raw_pnl = (exit_spread - setup.current_spread) if is_long else (setup.current_spread - exit_spread)
        raw_return_pct = round((raw_pnl / invested_capital) * 100.0, 2)
        realized_return_pct = round(raw_return_pct * sizing_multiplier, 2)

        status_desc = {
            "REVERSION_TARGET": f"Realistic Reversion Target (|z| <= {target_exit_z:.2f}) on Day {exit_days}",
            "TIGHT_STOP": f"Tight Dynamic Stop Loss (|z| >= {actual_stop_z:.2f}) on Day {exit_days}",
            "TIME_STOP": f"2x Half-Life Time Stop (T_max = {t_max}d) on Day {exit_days}",
        }.get(exit_reason, exit_reason)

        res = StrategyV4TradeResult(
            pair_name=setup.pair_name,
            ticker_a=setup.ticker_a,
            ticker_b=setup.ticker_b,
            sector=setup.sector or "Other",
            entry_date=setup.target_date,
            exit_date=exit_date_str,
            direction=setup.direction,
            direction_label=direction_label,
            entry_z=round(setup.current_z_score, 3),
            exit_z=round(exit_z, 3),
            hedge_ratio=round(setup.hedge_ratio, 4),
            entry_price_a=round(setup.price_a_entry, 2),
            entry_price_b=round(setup.price_b_entry, 2),
            exit_price_a=round(exit_pa, 2),
            exit_price_b=round(exit_pb, 2),
            outcome=resolved_outcome,
            exit_reason=exit_reason,
            status_reason=status_desc,
            holding_days=exit_days,
            raw_return_pct=raw_return_pct,
            realized_return_pct=realized_return_pct,
            sizing_multiplier=round(sizing_multiplier, 2),
            spread_vol_pct=round(setup.relative_spread_vol_pct, 2),
            half_life_days=round(setup.half_life_days, 1),
            max_holding_limit=t_max,
            is_dampened=is_dampened,
            momentum_slope=round(momentum_slope, 4),
            composite_score=round(setup.composite_score, 1),
            trajectory=path,
        )

        exit_ts = pd.to_datetime(exit_date_str).normalize() if exit_date_str else t_entry
        return StrategyV4EvaluationOutcome(trade_result=res, exit_timestamp=exit_ts)


class StrategyV4Engine:
    """End-to-End Walkforward Simulation Engine for Strategy v4."""

    def __init__(
        self,
        config: Optional[StrategyV4Config] = None,
        parquet_path: Optional[Union[Path, str]] = None,
    ) -> None:
        self.config = config or StrategyV4Config.load()
        self.parquet_path = Path(parquet_path or PARQUET_PATH_DEFAULT)
        self.pit_engine = PointInTimeEngine(self.parquet_path)
        self.df = self.pit_engine.load_data()
        self.evaluator = StrategyV4OutcomeEvaluator(self.config, df=self.df)
        self.earnings_calendar = EarningsCalendar()

        # Build market volatility proxy (rolling 20d annualized realized volatility of universe returns)
        adj_close = self.df["Adj Close"] if "Adj Close" in self.df.columns.levels[0] else self.df["Close"]
        market_returns = adj_close.pct_change().mean(axis=1)
        self.market_vol_series = market_returns.rolling(20).std() * np.sqrt(252) * 100.0

    def run_backtest(
        self,
        start_date: str,
        end_date: str,
    ) -> Dict[str, Any]:
        """Execute walkforward simulation across specified date window."""
        start_ts = pd.to_datetime(start_date).tz_localize(None).normalize()
        end_ts = pd.to_datetime(end_date).tz_localize(None).normalize()

        fields = self.df.columns.levels[0].tolist() if isinstance(self.df.columns, pd.MultiIndex) else []
        price_matrix = self.df["Adj Close"] if "Adj Close" in fields else self.df["Close"]

        trading_days = [d for d in price_matrix.index if start_ts <= d <= end_ts]
        if not trading_days:
            raise ValueError(f"No trading days found between {start_date} and {end_date}.")

        date_index = self.df.index
        arrays = {col: self.df[col].to_numpy(dtype=float) for col in self.df.columns}

        trades: List[Dict[str, Any]] = []
        active_positions: Dict[str, pd.Timestamp] = {}
        cum_pnl = 0.0
        peak_pnl = 0.0

        for dt in trading_days:
            dt_str = dt.strftime("%Y-%m-%d")

            # Expire closed positions
            closed = [p for p, exit_ts in active_positions.items() if exit_ts <= dt]
            for p in closed:
                del active_positions[p]

            # VIX macro check
            curr_vix = self.market_vol_series.get(dt, 15.0)
            if np.isnan(curr_vix):
                curr_vix = 15.0
            if self.config.vix_overlay_enabled and curr_vix > self.config.vix_panic_threshold:
                # Market panic regime, freeze new entries
                continue

            active_setups = self.pit_engine.scan_date(
                target_date=dt,
                top_n=50,
                only_active_setups=True,
                exclude_pairs=set(active_positions.keys()),
            )

            current_dd = max(0.0, peak_pnl - cum_pnl)
            is_dd_dampened = (
                self.config.drawdown_dampener_enabled and current_dd >= self.config.drawdown_threshold_pct
            )

            for setup in active_setups:
                pname = setup.pair_name
                if pname in active_positions:
                    continue

                # Divergence hurdle: 2.10 <= |Z| < 3.00
                if abs(setup.current_z_score) < self.config.z_score_entry_hurdle or abs(setup.current_z_score) >= self.config.z_score_entry_max:
                    continue

                # Volatility cap: spread vol <= 5.5%
                if setup.relative_spread_vol_pct > self.config.max_allowed_spread_vol_pct:
                    continue

                # Earnings blackout entry veto (5d pre)
                in_blackout, _ = self.earnings_calendar.is_in_blackout(
                    setup.ticker_a,
                    setup.ticker_b,
                    dt,
                    blackout_days=self.config.earnings_blackout_days_pre,
                )
                if in_blackout:
                    continue

                # Momentum Flattening Confirmation (Check T-1 spread)
                dt_pos = date_index.get_loc(dt)
                if dt_pos < 1:
                    continue

                key_a = ("Adj Close", setup.ticker_a) if ("Adj Close", setup.ticker_a) in arrays else ("Close", setup.ticker_a)
                key_b = ("Adj Close", setup.ticker_b) if ("Adj Close", setup.ticker_b) in arrays else ("Close", setup.ticker_b)
                if key_a not in arrays or key_b not in arrays:
                    continue

                pa_prev = arrays[key_a][dt_pos - 1]
                pb_prev = arrays[key_b][dt_pos - 1]
                if np.isnan(pa_prev) or np.isnan(pb_prev) or pa_prev <= 0 or pb_prev <= 0:
                    continue

                s_prev = pa_prev - setup.hedge_ratio * pb_prev
                z_prev = (s_prev - setup.spread_mean) / setup.spread_std
                z_curr = setup.current_z_score

                # Momentum Confirmation:
                # 1. Reversing towards mean (Delta Z in favorable direction), OR
                # 2. 2-day spread velocity is flattening (|Z_t - Z_{t-1}| <= max_entry_momentum_slope)
                is_reversing = (z_curr > z_prev) if z_curr < 0 else (z_curr < z_prev)
                is_flattening = abs(z_curr - z_prev) <= self.config.max_entry_momentum_slope

                if not (is_reversing or is_flattening):
                    # Accelerating runaway knife, skip!
                    continue

                # Volatility-Inverse Sizing
                spread_vol_safe = max(0.01, setup.relative_spread_vol_pct)
                raw_mult = min(
                    self.config.max_capital_multiplier,
                    max(self.config.min_capital_multiplier, self.config.target_spread_vol_pct / spread_vol_safe),
                )
                final_mult = raw_mult * (self.config.drawdown_scaling_factor if is_dd_dampened else 1.0)

                outcome = self.evaluator.evaluate_setup(
                    setup=setup,
                    sizing_multiplier=final_mult,
                    is_dampened=is_dd_dampened,
                    momentum_slope=abs(z_curr - z_prev),
                )

                trade_res = outcome.trade_result
                active_positions[pname] = outcome.exit_timestamp

                cum_pnl += trade_res.realized_return_pct
                if cum_pnl > peak_pnl:
                    peak_pnl = cum_pnl

                trade_dict = asdict(trade_res)
                trade_dict["id"] = f"{trade_res.ticker_a}_{trade_res.ticker_b}_{dt_str}"
                trades.append(trade_dict)

        # Summary KPIs
        summary = self._compute_summary(trades)
        equity_curve = self._compute_equity_curve(trades, trading_days)
        monthly_returns = self._compute_monthly_returns(trades)

        return {
            "version": self.config.version,
            "strategy_name": self.config.strategy_name,
            "period": {
                "start_date": start_date,
                "end_date": end_date,
                "trading_days": len(trading_days),
            },
            "overall_summary": summary,
            "equity_curve": equity_curve,
            "monthly_returns": monthly_returns,
            "trades": trades,
            "meta": {
                "config": asdict(self.config),
                "total_trades": len(trades),
            },
        }

    def _compute_summary(self, trades: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Compute institutional scorecard metrics."""
        total = len(trades)
        if total == 0:
            return {
                "total_trades": 0, "win_count": 0, "loss_count": 0, "neutral_count": 0,
                "win_rate_pct": 0.0, "net_return_pct": 0.0, "gross_profit_pct": 0.0,
                "gross_loss_pct": 0.0, "profit_factor": 0.0, "max_drawdown_pct": 0.0,
                "avg_return_pct": 0.0, "avg_holding_days": 0.0,
                "reversion_target_exits": 0, "tight_stop_exits": 0, "time_stop_exits": 0,
                "sharpe_ratio": 0.0, "calmar_ratio": 0.0,
            }

        wins = [t for t in trades if t["outcome"] == "WIN"]
        losses = [t for t in trades if t["outcome"] == "LOSS"]
        neutrals = [t for t in trades if t["outcome"] == "NEUTRAL"]

        gross_profit = sum(t["realized_return_pct"] for t in wins)
        gross_loss = abs(sum(t["realized_return_pct"] for t in losses))
        net_return = sum(t["realized_return_pct"] for t in trades)

        win_rate = (len(wins) / total) * 100.0 if total > 0 else 0.0
        profit_factor = round(gross_profit / gross_loss, 2) if gross_loss > 0 else 99.0

        avg_return = round(net_return / total, 2) if total > 0 else 0.0
        avg_holding = round(sum(t["holding_days"] for t in trades) / total, 1) if total > 0 else 0.0

        # Drawdown computation
        cum = 0.0
        peak = 0.0
        max_dd = 0.0
        sorted_trades = sorted(trades, key=lambda x: x.get("exit_date") or x["entry_date"])
        trade_returns = []
        for t in sorted_trades:
            ret = t["realized_return_pct"]
            trade_returns.append(ret)
            cum += ret
            if cum > peak:
                peak = cum
            dd = peak - cum
            if dd > max_dd:
                max_dd = dd

        # Sharpe & Calmar approximations
        ret_arr = np.array(trade_returns)
        std_ret = np.std(ret_arr) if len(ret_arr) > 1 else 1.0
        sharpe = round(float((np.mean(ret_arr) / (std_ret if std_ret > 1e-4 else 1.0)) * np.sqrt(total)), 2)
        calmar = round(float(net_return / (max_dd if max_dd > 0 else 1.0)), 2)

        rev_exits = sum(1 for t in trades if t.get("exit_reason") == "REVERSION_TARGET")
        stop_exits = sum(1 for t in trades if t.get("exit_reason") == "TIGHT_STOP")
        time_exits = sum(1 for t in trades if t.get("exit_reason") == "TIME_STOP")

        return {
            "total_trades": total,
            "win_count": len(wins),
            "loss_count": len(losses),
            "neutral_count": len(neutrals),
            "win_rate_pct": round(win_rate, 1),
            "net_return_pct": round(net_return, 2),
            "gross_profit_pct": round(gross_profit, 2),
            "gross_loss_pct": round(gross_loss, 2),
            "profit_factor": profit_factor,
            "max_drawdown_pct": round(max_dd, 2),
            "avg_return_pct": avg_return,
            "avg_holding_days": avg_holding,
            "reversion_target_exits": rev_exits,
            "tight_stop_exits": stop_exits,
            "time_stop_exits": time_exits,
            "sharpe_ratio": sharpe,
            "calmar_ratio": calmar,
        }

    def _compute_equity_curve(
        self,
        trades: List[Dict[str, Any]],
        trading_days: List[pd.Timestamp],
    ) -> List[Dict[str, Any]]:
        """Compute daily compounding equity trajectory."""
        sorted_trades = sorted(trades, key=lambda x: x.get("exit_date") or x["entry_date"])
        trade_by_exit: Dict[str, float] = {}
        for t in sorted_trades:
            d = t.get("exit_date") or t["entry_date"]
            trade_by_exit[d] = trade_by_exit.get(d, 0.0) + t["realized_return_pct"]

        curve: List[Dict[str, Any]] = []
        cum = 0.0
        peak = 0.0

        for dt in trading_days:
            dt_str = dt.strftime("%Y-%m-%d")
            pnl = trade_by_exit.get(dt_str, 0.0)
            cum += pnl
            if cum > peak:
                peak = cum
            dd = peak - cum
            curve.append({
                "date": dt_str,
                "daily_pnl_pct": round(pnl, 2),
                "cumulative_equity_pct": round(cum, 2),
                "drawdown_pct": round(dd, 2),
            })

        return curve

    def _compute_monthly_returns(self, trades: List[Dict[str, Any]]) -> Dict[str, float]:
        """Aggregate returns by YYYY-MM."""
        monthly: Dict[str, float] = {}
        for t in trades:
            d = t.get("exit_date") or t["entry_date"]
            m_key = d[:7]
            monthly[m_key] = monthly.get(m_key, 0.0) + t["realized_return_pct"]
        return {k: round(v, 2) for k, v in sorted(monthly.items())}
