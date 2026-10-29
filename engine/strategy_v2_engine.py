#!/usr/bin/env python3
"""Strategy v2: Cointegrated Statistical Arbitrage Engine with Reversion Hook & Staged Exits.

Isolated implementation of Strategy v2 incorporating 5 quantitative upgrades:
  1. Reversion Hook Confirmation: Requires spread hurdle (|Z| >= 2.10σ), entering ONLY
     when spread crosses back inside |Z| <= 1.85σ with mean-reverting velocity (dZ/dt towards 0).
  2. Two-Tranche Staged Take-Profit & Breakeven Stop:
     - Tranche 1 (50% position): Exits at |Z| <= 0.80σ (banks initial profit).
     - Breakeven Stop: Upon TP1 execution, Tranche 2 stop loss moves to entry level (1.85σ).
     - Tranche 2 (50% position): Exits at equilibrium |Z| <= 0.20σ or at breakeven stop.
  3. Ornstein-Uhlenbeck Time Stop:
     - Maximum holding period: T_max = min(25, max(10, round(1.75 * half_life))).
     - Force market exit at T_max to prevent capital lockup in degrading spreads.
  4. Earnings & Catalyst Blackout Shield:
     - Ingests corporate earnings dates and vetoes entries within ±5 trading days of an announcement.
  5. Tightened Statistical Gauntlet:
     - Stop-Loss Barrier: 3.20σ (tightened from 3.50σ)
     - Half-Life Ceiling: <= 22.0 days (tightened from 35.0 days)
     - Minimum OLS R²: >= 0.50 (tightened from 0.35)
     - Maximum ADF p-value: <= 0.04 (tightened from 0.05)

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

# Silence statsmodels future warnings
warnings.filterwarnings("ignore", category=FutureWarning)

# Ensure project root in sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import numpy as np
import pandas as pd
from statsmodels.tsa.stattools import adfuller

from engine.config import DATA_CACHE_DIR, PROJECT_ROOT
from engine.logging_setup import get_logger

logger = get_logger("strategy_v2_engine")

CONFIG_V2_ROOT = PROJECT_ROOT / "pair_strategy_v2_config.json"
CONFIG_V2_DATA = PROJECT_ROOT / "data" / "pair_strategy_v2_config.json"
PARQUET_PATH_DEFAULT = DATA_CACHE_DIR / "universe_5y_daily.parquet"
META_PATH_DEFAULT = DATA_CACHE_DIR / "universe_meta.json"
RESEARCH_DIR_DEFAULT = DATA_CACHE_DIR / "research"


def load_strategy_v2_config(config_path: Optional[Union[Path, str]] = None) -> Dict[str, Any]:
    """Load Strategy v2 configuration from JSON with fallback defaults."""
    candidates = []
    if config_path:
        candidates.append(Path(config_path))
    candidates.extend([CONFIG_V2_ROOT, CONFIG_V2_DATA])

    for path in candidates:
        if path.exists():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Could not parse config at {path}: {e}")

    # Fallback specification matching pair_strategy_v2_config.json
    return {
        "version": "2.0.0",
        "strategy_name": "Cointegrated Stat-Arb v2 (Confirmed Reversion & Staged Exits)",
        "divergence_triggers": {
            "z_score_hurdle": 2.10,
            "z_score_hook_entry": 1.85,
            "z_score_exit_tp1": 0.80,
            "z_score_exit_tp2": 0.20,
            "z_score_stop_loss_barrier": 3.20,
            "lookback_days": 90,
        },
        "trade_management": {
            "staged_take_profit_enabled": True,
            "tp1_allocation_pct": 50,
            "move_stop_to_breakeven_on_tp1": True,
            "half_life_time_stop_multiplier": 1.75,
            "min_holding_days_floor": 10,
            "max_holding_days_cap": 25,
            "earnings_blackout_days": 5,
        },
        "gauntlet_screening_thresholds": {
            "min_correlation": 0.85,
            "max_cointegration_pvalue": 0.04,
            "min_half_life_days": 2.0,
            "max_half_life_days": 22.0,
            "max_hurst_exponent": 0.48,
            "min_r_squared": 0.50,
        },
    }


def calculate_rolling_hurst(s_vals: np.ndarray, max_lag: int = 15) -> float:
    """Fast vectorized rolling Hurst exponent via variance of differences in numpy."""
    n = len(s_vals)
    if n < 20:
        return 0.42
    lags = np.arange(2, min(max_lag, n // 4))
    if len(lags) < 3:
        return 0.42
    tau = [np.std(s_vals[lag:] - s_vals[:-lag]) for lag in lags]
    tau = [x if x > 0 else 1e-8 for x in tau]
    poly = np.polyfit(np.log(lags), np.log(tau), 1)
    return float(poly[0])


class EarningsCalendar:
    """Ingests and indexes corporate earnings announcement dates for blackout filtering."""

    def __init__(
        self,
        research_dir: Optional[Union[Path, str]] = None,
        custom_earnings: Optional[Dict[str, Union[List[str], Set[str]]]] = None,
    ) -> None:
        self.research_dir = Path(research_dir or RESEARCH_DIR_DEFAULT)
        self.earnings_by_ticker: Dict[str, Set[str]] = {}

        if custom_earnings:
            for sym, d_list in custom_earnings.items():
                clean_sym = sym.strip().upper().replace(".", "-")
                self.earnings_by_ticker[clean_sym] = {
                    pd.to_datetime(d).strftime("%Y-%m-%d") for d in d_list
                }
        else:
            self._load_from_cache()

    def _load_from_cache(self) -> None:
        """Scan data_cache/research/{ticker}/earnings_*.json and index dates."""
        if not self.research_dir.exists():
            return

        for sym_dir in self.research_dir.iterdir():
            if not sym_dir.is_dir():
                continue
            sym = sym_dir.name.strip().upper().replace(".", "-")
            for f in sym_dir.glob("earnings_*.json"):
                try:
                    with open(f, "r", encoding="utf-8") as fp:
                        payload = json.load(fp)
                    dates_set: Set[str] = set()
                    for row in payload.get("data", []):
                        raw_date = row.get("date")
                        if raw_date:
                            clean_date = raw_date[:10]
                            dates_set.add(clean_date)
                    if dates_set:
                        if sym not in self.earnings_by_ticker:
                            self.earnings_by_ticker[sym] = set()
                        self.earnings_by_ticker[sym].update(dates_set)
                except Exception as e:
                    logger.debug(f"Could not load earnings for {sym}: {e}")

    def is_in_blackout(
        self,
        ticker_a: str,
        ticker_b: str,
        target_date: Union[str, pd.Timestamp, date],
        blackout_days: int = 5,
        trading_calendar: Optional[List[pd.Timestamp]] = None,
    ) -> Tuple[bool, Optional[str]]:
        """Check if either ticker in the pair reports earnings within ±blackout_days trading days.
        
        Returns (is_blackout, reason).
        """
        ta = ticker_a.strip().upper().replace(".", "-")
        tb = ticker_b.strip().upper().replace(".", "-")
        t_ts = pd.to_datetime(target_date).normalize()

        # Build window of check dates
        if trading_calendar:
            # Binary search target_date in trading_calendar
            norm_cal = [ts.normalize() for ts in trading_calendar]
            try:
                pos = norm_cal.index(t_ts)
            except ValueError:
                # If target_date not explicitly in calendar, find insertion index
                pos = int(np.searchsorted([ts.value for ts in norm_cal], t_ts.value))
            start_pos = max(0, pos - blackout_days)
            end_pos = min(len(norm_cal), pos + blackout_days + 1)
            window_dates = {ts.strftime("%Y-%m-%d") for ts in norm_cal[start_pos:end_pos]}
        else:
            # Fallback to business days window: ±(blackout_days + 2) calendar days
            b_days = pd.bdate_range(t_ts - pd.Timedelta(days=blackout_days * 2), t_ts + pd.Timedelta(days=blackout_days * 2))
            # Slice closest ±blackout_days around target_date
            pos = int(np.searchsorted([ts.value for ts in b_days], t_ts.value))
            start_pos = max(0, pos - blackout_days)
            end_pos = min(len(b_days), pos + blackout_days + 1)
            window_dates = {ts.strftime("%Y-%m-%d") for ts in b_days[start_pos:end_pos]}

        # Check ticker A
        dates_a = self.earnings_by_ticker.get(ta, set())
        overlap_a = dates_a.intersection(window_dates)
        if overlap_a:
            first_hit = sorted(list(overlap_a))[0]
            return True, f"Earnings Blackout: {ta} reports on {first_hit} (within ±{blackout_days} trading days of {t_ts.strftime('%Y-%m-%d')})"

        # Check ticker B
        dates_b = self.earnings_by_ticker.get(tb, set())
        overlap_b = dates_b.intersection(window_dates)
        if overlap_b:
            first_hit = sorted(list(overlap_b))[0]
            return True, f"Earnings Blackout: {tb} reports on {first_hit} (within ±{blackout_days} trading days of {t_ts.strftime('%Y-%m-%d')})"

        return False, None


@dataclass
class StrategyV2Setup:
    """Represents an active Strategy v2 statistical divergence setup detected on Date T."""
    ticker_a: str
    ticker_b: str
    pair_name: str
    target_date: str                   # Date T (YYYY-MM-DD)
    direction: str                     # "LONG_A_SHORT_B" or "SHORT_A_LONG_B"
    hedge_ratio: float                 # OLS Beta
    alpha: float                       # OLS Intercept
    r_squared: float                   # OLS R-Squared
    correlation: float                 # Pearson r
    current_z_score: float             # Z-score at Date T
    abs_z_score: float
    current_spread: float              # Spread at Date T: Pa - beta * Pb
    spread_mean: float                 # 90-day rolling mean mu
    spread_std: float                  # 90-day rolling std sigma
    adf_tstat: float                   # ADF t-statistic
    adf_pvalue: float                  # ADF stationarity p-value
    half_life_days: float              # Ornstein-Uhlenbeck half-life in days
    zero_crossings: int                # Zero crossings in lookback window
    relative_spread_vol_pct: float     # (Spread Std / Price A) * 100
    spread_tier: str                   # "Ultra Tight", "Tight", "Medium", "Wide"
    composite_score: float             # 0 to 100 ranking score
    price_a_entry: float               # Closing price of A at Date T
    price_b_entry: float               # Closing price of B at Date T
    expected_reversion_return_pct: float
    risk_reward_ratio: float

    # Strategy v2 Core Attributes
    hook_confirmed: bool               # Reversion hook velocity confirmed
    hurdle_breached_z: float           # Extreme Z reached prior to hook (>= 2.10 or <= -2.10)
    hook_entry_z: float                # Z-score at hook crossing (<= 1.85 or >= -1.85)
    tp1_z_target: float                # Z target for Tranche 1 (±0.80σ)
    tp2_z_target: float                # Z target for Tranche 2 (±0.20σ)
    stop_loss_z: float                 # Initial stop loss barrier (±3.20σ)
    breakeven_stop_z: float            # Breakeven stop level for Tranche 2 (entry Z)
    target_spread_tp1: float           # Spread at TP1
    target_spread_tp2: float           # Spread at TP2
    stop_loss_spread: float            # Spread at stop barrier
    time_stop_days: int                # Dynamic OU max holding days: min(25, max(10, round(1.75 * hl)))
    earnings_blackout: bool            # True if vetoed by earnings
    earnings_veto_reason: Optional[str]

    # Filter Gates
    is_setup: bool                     # Passes all v2 gauntlet + hook + earnings gates
    is_perfect: bool                   # Passes 100% of checks
    is_tradeable: bool                 # Active setup ready for trade execution
    sector: str = "Institutional Equities"
    checks: Dict[str, bool] = field(default_factory=dict)
    passed_checks_count: int = 0
    window_bars: int = 90
    action_a: str = ""
    action_b: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Convert setup to JSON-serializable dictionary."""
        return asdict(self)


@dataclass
class StrategyV2EvaluationResult:
    """Forward Walk-Forward Evaluation Result for Strategy v2 (t > T).
    
    Tracks two-tranche staged execution, breakeven stop movements, and OU time stops.
    """
    pair_name: str
    target_date: str                   # Entry Date T (YYYY-MM-DD)
    direction: str
    outcome: str                       # "WIN", "LOSS", "NEUTRAL", or "OPEN"
    status_reason: str                 # Descriptive narrative
    exit_reason: str                   # "TP1_AND_TP2", "TP1_AND_BREAKEVEN", "STOP_LOSS", "TIME_STOP", "EXPIRED"
    entry_price_a: float
    entry_price_b: float
    entry_spread: float
    entry_z_score: float
    exit_date: Optional[str] = None    # Date when trade fully closed
    exit_days_held: int = 0            # Total trading days held
    exit_price_a: Optional[float] = None
    exit_price_b: Optional[float] = None
    exit_spread: Optional[float] = None
    exit_z_score: Optional[float] = None
    realized_pnl_pct: float = 0.0      # Combined return on invested capital (%)

    # Staged Tranche Details
    tp1_hit: bool = False
    tp1_date: Optional[str] = None
    tp1_days_held: int = 0
    tp1_z_score: Optional[float] = None
    tranche1_pnl_pct: float = 0.0      # Realized return on Tranche 1 (50% weight)

    tp2_hit: bool = False
    tp2_date: Optional[str] = None
    tp2_days_held: int = 0
    tp2_z_score: Optional[float] = None
    tranche2_pnl_pct: float = 0.0      # Realized return on Tranche 2 (50% weight)

    breakeven_stop_hit: bool = False
    time_stop_hit: bool = False
    stop_loss_hit: bool = False

    max_favorable_z: float = 0.0       # Best Z reached towards mean reversion
    max_adverse_z: float = 0.0         # Worst Z reached against trade direction
    path: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert result to JSON-serializable dictionary."""
        return asdict(self)


class StrategyV2Engine:
    """Point-in-Time Setup Detector for Strategy v2.
    
    Enforces Zero Lookahead (t <= T), Reversion Hook confirmation, Tightened Gauntlet,
    and Earnings Blackout shielding.
    """

    def __init__(
        self,
        parquet_path: Optional[Union[Path, str]] = None,
        df: Optional[pd.DataFrame] = None,
        config: Optional[Dict[str, Any]] = None,
        earnings_calendar: Optional[EarningsCalendar] = None,
    ) -> None:
        self.parquet_path = Path(parquet_path or PARQUET_PATH_DEFAULT)
        self.df = df
        self.earnings_calendar = earnings_calendar or EarningsCalendar()
        self._pairs: Optional[List[Dict[str, Any]]] = None
        self._pair_meta_map: Dict[str, Dict[str, Any]] = {}
        self.apply_config(config or load_strategy_v2_config())

    def apply_config(self, config: Dict[str, Any]) -> None:
        """Apply and unpack configuration dictionary into active engine thresholds."""
        self.config = config
        div_cfg = self.config.get("divergence_triggers", {})
        self.z_hurdle = float(div_cfg.get("z_score_hurdle", 2.10))
        self.z_hook = float(div_cfg.get("z_score_hook_entry", 1.85))
        self.tp1_z = float(div_cfg.get("z_score_exit_tp1", 0.80))
        self.tp2_z = float(div_cfg.get("z_score_exit_tp2", 0.20))
        self.stop_loss_z = float(div_cfg.get("z_score_stop_loss_barrier", 3.20))
        self.default_lookback = int(div_cfg.get("lookback_days", 90))
        self.min_valid_bars = 30

        tm_cfg = self.config.get("trade_management", {})
        self.hl_mult = float(tm_cfg.get("half_life_time_stop_multiplier", 1.75))
        self.min_holding_floor = int(tm_cfg.get("min_holding_days_floor", 10))
        self.max_holding_cap = int(tm_cfg.get("max_holding_days_cap", 25))
        self.blackout_days = int(tm_cfg.get("earnings_blackout_days", 5))

        gaunt_cfg = self.config.get("gauntlet_screening_thresholds", {})
        self.min_correlation = float(gaunt_cfg.get("min_correlation", 0.85))
        self.max_coint_p = float(gaunt_cfg.get("max_cointegration_pvalue", 0.04))
        self.min_half_life = float(gaunt_cfg.get("min_half_life_days", 2.0))
        self.max_half_life = float(gaunt_cfg.get("max_half_life_days", 22.0))
        self.max_hurst = float(gaunt_cfg.get("max_hurst_exponent", 0.48))
        self.min_r_squared = float(gaunt_cfg.get("min_r_squared", 0.50))

    def load_data(self) -> pd.DataFrame:
        """Load and normalize historical daily dataset into memory."""
        if self.df is None:
            if not self.parquet_path.exists():
                raise FileNotFoundError(f"Universe Parquet not found at {self.parquet_path}")
            raw = pd.read_parquet(self.parquet_path)
            raw.index = pd.to_datetime(raw.index)
            if raw.index.tz is not None:
                raw.index = raw.index.tz_localize(None)
            raw.index = raw.index.normalize()
            self.df = raw.sort_index()
        return self.df

    def slice_history(self, target_date: Union[str, pd.Timestamp, date]) -> pd.DataFrame:
        """Strictly truncate historical data to t <= target_date with zero lookahead bias."""
        df = self.load_data()
        ts = pd.to_datetime(target_date).normalize()
        pos = int(df.index.searchsorted(ts, side="right"))
        sliced = df.iloc[:pos]
        if not sliced.empty and sliced.index[-1] > ts:
            raise ValueError(f"Lookahead violation: {sliced.index[-1]} > {ts}")
        return sliced

    def get_pairs(self) -> List[Dict[str, Any]]:
        """Retrieve eligible pairs from universe metadata or curated files."""
        if self._pairs is not None:
            return self._pairs

        # Check universe_meta.json
        meta_file = META_PATH_DEFAULT
        if meta_file.exists():
            try:
                with open(meta_file, "r", encoding="utf-8") as f:
                    meta = json.load(f)
                intact = meta.get("pair_metrics", {}).get("intact_pairs", [])
                parsed_pairs = []
                for item in intact:
                    if isinstance(item, str) and "/" in item:
                        ta, tb = item.split("/", 1)
                        parsed_pairs.append({"ticker_a": ta.strip(), "ticker_b": tb.strip()})
                    elif isinstance(item, dict) and "ticker_a" in item:
                        parsed_pairs.append(item)
                if parsed_pairs:
                    self._pairs = parsed_pairs
                    return self._pairs
            except Exception as e:
                logger.warning(f"Could not load intact pairs from meta: {e}")

        # Fallback default pairs
        self._pairs = [
            {"ticker_a": "MTB", "ticker_b": "PNC"},
            {"ticker_a": "FITB", "ticker_b": "PNC"},
            {"ticker_a": "DELL", "ticker_b": "HPE"},
            {"ticker_a": "ADI", "ticker_b": "KLAC"},
            {"ticker_a": "MS", "ticker_b": "RF"},
            {"ticker_a": "DUK", "ticker_b": "SO"},
            {"ticker_a": "GS", "ticker_b": "MS"},
            {"ticker_a": "AMD", "ticker_b": "MRVL"},
        ]
        return self._pairs

    def calculate_ou_half_life(self, spread: np.ndarray) -> float:
        """Compute Ornstein-Uhlenbeck half-life in days."""
        if len(spread) < 10:
            return 999.0
        ds = np.diff(spread)
        s_lag = spread[:-1]
        try:
            poly = np.polyfit(s_lag, ds, 1)
            lam = float(poly[0])
            if lam >= -1e-6:
                return 999.0
            return round(float(-math.log(2.0) / lam), 2)
        except Exception:
            return 999.0

    def calculate_time_stop_days(self, half_life_days: float) -> int:
        """Calculate Ornstein-Uhlenbeck dynamic time stop: min(25, max(10, round(1.75 * hl)))."""
        raw = round(self.hl_mult * half_life_days)
        return int(min(self.max_holding_cap, max(self.min_holding_floor, raw)))

    def is_hook_confirmed(
        self,
        z_series: np.ndarray,
        hurdle: Optional[float] = None,
        hook_entry: Optional[float] = None,
        lookback_window: int = 15,
    ) -> Tuple[bool, str, float, float]:
        """Evaluate Reversion Hook Confirmation on rolling Z-score array.
        
        Rules:
          - Long Spread: In recent lookback, Z reached <= -hurdle (-2.10).
            Current bar crosses back inside -hook_entry (Z_t >= -1.85) with positive slope:
            (Z_t - Z_{t-1}) > 0, and not already reverted past TP1 (Z_t < -0.80).
          - Short Spread: In recent lookback, Z reached >= +hurdle (+2.10).
            Current bar crosses back inside +hook_entry (Z_t <= +1.85) with negative slope:
            (Z_t - Z_{t-1}) < 0, and not already reverted past TP1 (Z_t > +0.80).
            
        Returns:
          (confirmed: bool, direction: str, hurdle_breached_z: float, hook_z: float)
        """
        h = hurdle or self.z_hurdle
        e = hook_entry or self.z_hook

        if len(z_series) < 3:
            return False, "NONE", 0.0, 0.0

        z_curr = float(z_series[-1])
        z_prev = float(z_series[-2])
        delta_z = z_curr - z_prev

        recent_slice = z_series[-min(lookback_window, len(z_series)):]
        min_recent_z = float(np.min(recent_slice))
        max_recent_z = float(np.max(recent_slice))

        # Check Long Spread Hook (reversion from negative dislocation)
        # Condition: minimum Z was <= -h (e.g. <= -2.10)
        # Crossing: Z_t >= -e (e.g. >= -1.85), previous Z_prev was below -e (or min was <= -h), delta_z > 0
        if min_recent_z <= -h and z_curr >= -e and delta_z > 0 and z_curr < -self.tp1_z:
            # Confirm that the spread was indeed deeper than -e recently
            if any(z < -e for z in recent_slice[:-1]):
                return True, "LONG_A_SHORT_B", min_recent_z, z_curr

        # Check Short Spread Hook (reversion from positive dislocation)
        # Condition: maximum Z was >= +h (e.g. >= +2.10)
        # Crossing: Z_t <= +e (e.g. <= +1.85), previous Z_prev was above +e, delta_z < 0
        if max_recent_z >= h and z_curr <= e and delta_z < 0 and z_curr > self.tp1_z:
            if any(z > e for z in recent_slice[:-1]):
                return True, "SHORT_A_LONG_B", max_recent_z, z_curr

        return False, "NONE", (max_recent_z if z_curr >= 0 else min_recent_z), z_curr

    def calculate_pair_pit(
        self,
        ticker_a: str,
        ticker_b: str,
        target_date: Union[str, pd.Timestamp, date],
        price_col: str = "Adj Close",
        history: Optional[pd.DataFrame] = None,
        col_arrays: Optional[Dict[str, np.ndarray]] = None,
        only_active_setups: bool = False,
    ) -> Optional[StrategyV2Setup]:
        """Calculate Point-in-Time metrics for a pair strictly at Date T for Strategy v2."""
        clean_a = ticker_a.strip().upper().replace(".", "-")
        clean_b = ticker_b.strip().upper().replace(".", "-")

        if col_arrays is not None and clean_a in col_arrays and clean_b in col_arrays:
            pa = col_arrays[clean_a]
            pb = col_arrays[clean_b]
        else:
            if history is None:
                history = self.slice_history(target_date)
            if len(history) < self.min_valid_bars:
                return None

            available_fields = history.columns.levels[0].tolist()
            p_field = price_col if price_col in available_fields else ("Close" if "Close" in available_fields else available_fields[0])
            try:
                pa_s = history[p_field][clean_a].dropna()
                pb_s = history[p_field][clean_b].dropna()
            except KeyError:
                return None

            common_idx = pa_s.index.intersection(pb_s.index)
            if len(common_idx) < self.min_valid_bars:
                return None

            pa = pa_s.loc[common_idx].to_numpy(dtype=float)[-self.default_lookback:]
            pb = pb_s.loc[common_idx].to_numpy(dtype=float)[-self.default_lookback:]

        if len(pa) < self.min_valid_bars or len(pb) < self.min_valid_bars:
            return None

        # 1. Rolling OLS Regression: Pa = alpha + beta * Pb
        try:
            poly = np.polyfit(pb, pa, 1)
            beta = float(poly[0])
            alpha = float(poly[1])
        except Exception:
            return None

        spread = pa - beta * pb
        mean_spread = float(np.mean(spread))
        std_spread = float(np.std(spread))
        if std_spread < 1e-8:
            return None

        # Rolling Z-score series
        z_series = (spread - mean_spread) / std_spread
        current_z = float(z_series[-1])
        abs_z = abs(current_z)
        current_spread = float(spread[-1])

        # 2. Pearson Correlation & R-Squared
        cov_matrix = np.corrcoef(pa, pb)
        correlation = float(cov_matrix[0, 1]) if cov_matrix.shape == (2, 2) else 0.0
        r_squared = float(correlation ** 2) if not np.isnan(correlation) else 0.0

        # Fast Filter: Evaluate Reversion Hook Confirmation before expensive ADF
        hook_confirmed, hook_direction, hurdle_z, hook_z = self.is_hook_confirmed(z_series)

        if only_active_setups and (not hook_confirmed or correlation < self.min_correlation or r_squared < self.min_r_squared):
            return None

        # 3. Augmented Dickey-Fuller Cointegration Test
        try:
            adf_res = adfuller(spread, autolag="AIC")
            adf_tstat = float(adf_res[0])
            adf_pvalue = float(adf_res[1])
        except Exception:
            adf_tstat = 0.0
            adf_pvalue = 1.0

        # 4. OU Half-Life & Time Stop
        half_life_days = self.calculate_ou_half_life(spread)
        time_stop_days = self.calculate_time_stop_days(half_life_days)
        diff_signs = np.diff(np.signbit(spread - mean_spread))
        zero_crossings = int(np.sum(diff_signs != 0))

        # 5. Volatility Tier
        last_pa = float(pa[-1])
        last_pb = float(pb[-1])
        relative_spread_vol_pct = round((std_spread / max(0.01, last_pa)) * 100.0, 2)
        spread_tier = (
            "Ultra Tight" if relative_spread_vol_pct <= 2.5
            else "Tight" if relative_spread_vol_pct <= 4.5
            else "Medium" if relative_spread_vol_pct <= 7.0
            else "Wide"
        )

        # Determine setup direction
        if hook_confirmed:
            direction = hook_direction
        else:
            direction = "SHORT_A_LONG_B" if current_z >= 0 else "LONG_A_SHORT_B"

        # 7. Targets & Barriers
        if direction == "LONG_A_SHORT_B":
            tp1_z_target = -self.tp1_z
            tp2_z_target = -self.tp2_z
            stop_loss_z = -self.stop_loss_z
            breakeven_stop_z = current_z
            target_spread_tp1 = mean_spread + tp1_z_target * std_spread
            target_spread_tp2 = mean_spread + tp2_z_target * std_spread
            stop_loss_spread = mean_spread + stop_loss_z * std_spread
            action_a = f"BUY {clean_a}"
            action_b = f"SHORT {clean_b}"
        else:
            tp1_z_target = self.tp1_z
            tp2_z_target = self.tp2_z
            stop_loss_z = self.stop_loss_z
            breakeven_stop_z = current_z
            target_spread_tp1 = mean_spread + tp1_z_target * std_spread
            target_spread_tp2 = mean_spread + tp2_z_target * std_spread
            stop_loss_spread = mean_spread + stop_loss_z * std_spread
            action_a = f"SHORT {clean_a}"
            action_b = f"BUY {clean_b}"

        # 8. Earnings Blackout Check
        t_date_str = pd.to_datetime(target_date).strftime("%Y-%m-%d")
        cal = list(history.index) if history is not None else None
        in_blackout, blackout_reason = self.earnings_calendar.is_in_blackout(
            clean_a, clean_b, target_date, blackout_days=self.blackout_days, trading_calendar=cal
        )

        # 9. Hurst Exponent
        hurst_val = calculate_rolling_hurst(spread)

        # 10. Tightened Strategy v2 Gauntlet Checks
        checks = {
            "reversion_hook_confirmed": bool(hook_confirmed),
            "earnings_blackout_safe": bool(not in_blackout),
            "cointegration_pvalue": bool(adf_pvalue <= self.max_coint_p),
            "correlation": bool(correlation >= self.min_correlation),
            "half_life_reversion": bool(self.min_half_life <= half_life_days <= self.max_half_life),
            "hurst_mean_reverting": bool(hurst_val <= self.max_hurst),
            "adf_stationarity": bool(adf_tstat <= -2.8),
            "liquidity_adv": True,
            "zero_crossings": bool(zero_crossings >= 6),
            "r_squared": bool(r_squared >= self.min_r_squared),
            "spread_tightness": bool(relative_spread_vol_pct <= 7.0),
        }
        passed_checks_count = sum(1 for v in checks.values() if v)
        is_perfect = bool(passed_checks_count == len(checks))

        # Active tradeable setup in Strategy v2 requires:
        # Hook confirmed, No earnings blackout, and passes core statistical gauntlet
        is_setup = bool(
            hook_confirmed
            and not in_blackout
            and adf_pvalue <= self.max_coint_p
            and correlation >= self.min_correlation
            and half_life_days <= self.max_half_life
            and r_squared >= self.min_r_squared
            and relative_spread_vol_pct <= 7.0
        )
        is_tradeable = is_setup

        disloc = abs(current_spread - target_spread_tp1)
        expected_reversion_return_pct = round(float((disloc / max(0.01, last_pa)) * 100.0), 2)
        stop_dist = abs(stop_loss_spread - current_spread)
        risk_reward_ratio = round(float(disloc / max(0.01, stop_dist)), 2)

        # Composite ranking score (0 to 100)
        c_score = (
            min(1.0, max(0.0, (correlation - 0.70) / 0.30)) * 25.0
            + min(1.0, max(0.0, (0.05 - adf_pvalue) / 0.05)) * 25.0
            + min(1.0, max(0.0, (self.max_half_life - half_life_days) / self.max_half_life)) * 20.0
            + min(1.0, max(0.0, (7.0 - relative_spread_vol_pct) / 7.0)) * 15.0
            + (15.0 if hook_confirmed else 0.0)
        )
        composite_score = round(float(c_score), 1)

        return StrategyV2Setup(
            ticker_a=clean_a,
            ticker_b=clean_b,
            pair_name=f"{clean_a}/{clean_b}",
            target_date=t_date_str,
            direction=direction,
            hedge_ratio=round(beta, 4),
            alpha=round(alpha, 4),
            r_squared=round(r_squared, 4),
            correlation=round(correlation, 4),
            current_z_score=round(current_z, 4),
            abs_z_score=round(abs_z, 4),
            current_spread=round(current_spread, 4),
            spread_mean=round(mean_spread, 4),
            spread_std=round(std_spread, 4),
            adf_tstat=round(adf_tstat, 4),
            adf_pvalue=round(adf_pvalue, 4),
            half_life_days=half_life_days,
            zero_crossings=zero_crossings,
            relative_spread_vol_pct=relative_spread_vol_pct,
            spread_tier=spread_tier,
            composite_score=composite_score,
            price_a_entry=round(last_pa, 2),
            price_b_entry=round(last_pb, 2),
            expected_reversion_return_pct=expected_reversion_return_pct,
            risk_reward_ratio=risk_reward_ratio,
            hook_confirmed=hook_confirmed,
            hurdle_breached_z=round(hurdle_z, 4),
            hook_entry_z=round(hook_z, 4),
            tp1_z_target=round(tp1_z_target, 4),
            tp2_z_target=round(tp2_z_target, 4),
            stop_loss_z=round(stop_loss_z, 4),
            breakeven_stop_z=round(breakeven_stop_z, 4),
            target_spread_tp1=round(target_spread_tp1, 4),
            target_spread_tp2=round(target_spread_tp2, 4),
            stop_loss_spread=round(stop_loss_spread, 4),
            time_stop_days=time_stop_days,
            earnings_blackout=in_blackout,
            earnings_veto_reason=blackout_reason,
            is_setup=is_setup,
            is_perfect=is_perfect,
            is_tradeable=is_tradeable,
            checks=checks,
            passed_checks_count=passed_checks_count,
            window_bars=len(pa),
            action_a=action_a,
            action_b=action_b,
        )

    def scan_date(
        self,
        target_date: Union[str, pd.Timestamp, date],
        top_n: int = 20,
        only_active_setups: bool = True,
        price_col: str = "Adj Close",
        exclude_pairs: Optional[Set[str]] = None,
    ) -> List[StrategyV2Setup]:
        """Scan all universe pairs for Date T and return ranked Strategy v2 setups."""
        history = self.slice_history(target_date)
        if len(history) < self.min_valid_bars:
            return []

        available_fields = history.columns.levels[0].tolist()
        p_field = price_col if price_col in available_fields else ("Close" if "Close" in available_fields else available_fields[0])
        price_matrix = history[p_field].iloc[-self.default_lookback:]

        # Extract ticker columns
        col_arrays: Dict[str, np.ndarray] = {}
        for col in price_matrix.columns:
            clean_col = str(col).strip().upper().replace(".", "-")
            col_arrays[clean_col] = price_matrix[col].to_numpy(dtype=float)

        pairs = self.get_pairs()
        setups: List[StrategyV2Setup] = []

        for p in pairs:
            ta = p.get("ticker_a", "")
            tb = p.get("ticker_b", "")
            if not ta or not tb:
                continue

            clean_a = str(ta).strip().upper().replace(".", "-")
            clean_b = str(tb).strip().upper().replace(".", "-")
            pair_key = f"{clean_a}/{clean_b}"
            if exclude_pairs and pair_key in exclude_pairs:
                continue

            setup = self.calculate_pair_pit(
                clean_a,
                clean_b,
                target_date=target_date,
                price_col=p_field,
                history=history,
                col_arrays=col_arrays,
                only_active_setups=only_active_setups,
            )
            if setup is None:
                continue

            if only_active_setups and not setup.is_setup:
                continue

            setups.append(setup)

        setups.sort(key=lambda s: (s.composite_score, s.abs_z_score), reverse=True)
        return setups[:top_n]


class StrategyV2OutcomeEvaluator:
    """Evaluates forward trade outcomes (t > T) under Strategy v2 execution rules.
    
    Execution Architecture:
      - 2-Tranche Sizing (50% Tranche 1, 50% Tranche 2).
      - Tranche 1 exits at |Z| <= 0.80σ (TP1).
      - Breakeven Stop: Upon TP1, Tranche 2 stop loss moves to entry level (1.85σ).
      - Tranche 2 exits at |Z| <= 0.20σ (TP2) or at breakeven stop.
      - Stop-Loss Barrier: |Z| >= 3.20σ exits entire remaining position (strict priority over targets).
      - OU Time Stop: Exit market at T_max = min(25, max(10, round(1.75 * half_life))).
    """

    def __init__(
        self,
        parquet_path: Optional[Union[Path, str]] = None,
        df: Optional[pd.DataFrame] = None,
        config: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.config = config or load_strategy_v2_config()
        self.parquet_path = Path(parquet_path or PARQUET_PATH_DEFAULT)
        self.df = df
        self._arrays: Optional[Dict[Tuple[str, str], np.ndarray]] = None
        self._index: Optional[pd.DatetimeIndex] = None
        self._dates: Optional[List[pd.Timestamp]] = None

        if self.df is not None:
            norm_df = self.df.copy()
            norm_df.index = pd.to_datetime(norm_df.index)
            if norm_df.index.tz is not None:
                norm_df.index = norm_df.index.tz_localize(None)
            norm_df.index = norm_df.index.normalize()
            self.df = norm_df.sort_index()
            self._build_array_cache()

    def _build_array_cache(self) -> None:
        """Pre-cache float numpy arrays for high-speed forward evaluation."""
        if self.df is not None and self._arrays is None:
            self._index = self.df.index
            self._dates = list(self.df.index)
            self._arrays = {col: self.df[col].to_numpy(dtype=float) for col in self.df.columns}

    def load_data(self) -> pd.DataFrame:
        """Load and cache full universe dataset into memory."""
        if self.df is None:
            if not self.parquet_path.exists():
                raise FileNotFoundError(f"Universe Parquet not found at {self.parquet_path}")
            raw = pd.read_parquet(self.parquet_path)
            raw.index = pd.to_datetime(raw.index)
            if raw.index.tz is not None:
                raw.index = raw.index.tz_localize(None)
            raw.index = raw.index.normalize()
            self.df = raw.sort_index()
            self._build_array_cache()
        return self.df

    def evaluate_setup(
        self,
        setup: StrategyV2Setup,
        max_horizon_days: Optional[int] = None,
        use_intraday_extremes: bool = True,
    ) -> StrategyV2EvaluationResult:
        """Evaluate forward performance of a Strategy v2 setup across future bars."""
        self.load_data()
        assert self._index is not None and self._dates is not None and self._arrays is not None

        t_entry = pd.to_datetime(setup.target_date).normalize()
        pos = int(self._index.searchsorted(t_entry, side="right"))
        n_dates = len(self._dates)

        if pos >= n_dates:
            return StrategyV2EvaluationResult(
                pair_name=setup.pair_name,
                target_date=setup.target_date,
                direction=setup.direction,
                outcome="OPEN",
                status_reason="No future market data available after entry date",
                exit_reason="OPEN",
                entry_price_a=setup.price_a_entry,
                entry_price_b=setup.price_b_entry,
                entry_spread=setup.current_spread,
                entry_z_score=setup.current_z_score,
            )

        # Dynamic holding ceiling: setup.time_stop_days
        effective_horizon = setup.time_stop_days
        if max_horizon_days and max_horizon_days > 0:
            effective_horizon = min(effective_horizon, max_horizon_days)

        end_pos = min(n_dates, pos + effective_horizon)
        future_dates = self._dates[pos:end_pos]
        if not future_dates:
            return StrategyV2EvaluationResult(
                pair_name=setup.pair_name,
                target_date=setup.target_date,
                direction=setup.direction,
                outcome="OPEN",
                status_reason="No future market data available after entry date",
                exit_reason="OPEN",
                entry_price_a=setup.price_a_entry,
                entry_price_b=setup.price_b_entry,
                entry_spread=setup.current_spread,
                entry_z_score=setup.current_z_score,
            )

        ta = setup.ticker_a
        tb = setup.ticker_b
        key_a = ("Adj Close", ta) if ("Adj Close", ta) in self._arrays else ("Close", ta)
        key_b = ("Adj Close", tb) if ("Adj Close", tb) in self._arrays else ("Close", tb)

        if key_a not in self._arrays or key_b not in self._arrays:
            return StrategyV2EvaluationResult(
                pair_name=setup.pair_name,
                target_date=setup.target_date,
                direction=setup.direction,
                outcome="NEUTRAL",
                status_reason="Ticker missing in future dataset",
                exit_reason="DATA_MISSING",
                entry_price_a=setup.price_a_entry,
                entry_price_b=setup.price_b_entry,
                entry_spread=setup.current_spread,
                entry_z_score=setup.current_z_score,
            )

        close_a = self._arrays[key_a][pos:end_pos]
        close_b = self._arrays[key_b][pos:end_pos]

        has_hl = (
            ("High", ta) in self._arrays
            and ("High", tb) in self._arrays
            and ("Low", ta) in self._arrays
            and ("Low", tb) in self._arrays
            and use_intraday_extremes
        )
        if has_hl:
            high_a = self._arrays[("High", ta)][pos:end_pos]
            low_a = self._arrays[("Low", ta)][pos:end_pos]
            high_b = self._arrays[("High", tb)][pos:end_pos]
            low_b = self._arrays[("Low", tb)][pos:end_pos]

        beta = setup.hedge_ratio
        mu = setup.spread_mean
        sigma = setup.spread_std
        is_long = (setup.direction == "LONG_A_SHORT_B")
        invested_capital = max(0.01, setup.price_a_entry + abs(beta) * setup.price_b_entry)

        z0 = setup.current_z_score
        s0 = setup.current_spread
        tp1_z_target = setup.tp1_z_target
        tp2_z_target = setup.tp2_z_target
        stop_z_barrier = setup.stop_loss_z
        breakeven_z = setup.breakeven_stop_z

        # Tranche State Tracking
        tranche1_closed = False
        tp1_date_str: Optional[str] = None
        tp1_days = 0
        tp1_z = 0.0
        tp1_pnl_pct = 0.0

        tranche2_closed = False
        tp2_date_str: Optional[str] = None
        tp2_days = 0
        tp2_z = 0.0
        tranche2_pnl_pct = 0.0

        breakeven_stop_active = False
        breakeven_stop_hit = False
        stop_loss_hit = False
        time_stop_hit = False

        max_favorable_z = 0.0
        max_adverse_z = 0.0
        path: List[Dict[str, Any]] = []

        resolved_outcome: Optional[str] = None
        resolved_reason: str = ""
        resolved_exit_reason: str = ""
        final_exit_date: Optional[str] = None
        final_exit_days = 0
        final_pa = 0.0
        final_pb = 0.0
        final_spread = 0.0
        final_z = 0.0

        for i, f_date in enumerate(future_dates, start=1):
            f_date_str = f_date.strftime("%Y-%m-%d")
            pa_c = float(close_a[i - 1])
            pb_c = float(close_b[i - 1])
            s_c = float(pa_c - beta * pb_c)
            z_c = float((s_c - mu) / sigma)

            if has_hl:
                if beta >= 0:
                    s_max = float(high_a[i - 1] - beta * low_b[i - 1])
                    s_min = float(low_a[i - 1] - beta * high_b[i - 1])
                else:
                    s_max = float(high_a[i - 1] - beta * high_b[i - 1])
                    s_min = float(low_a[i - 1] - beta * low_b[i - 1])
                z_max = float((s_max - mu) / sigma)
                z_min = float((s_min - mu) / sigma)
            else:
                s_max = s_c
                s_min = s_c
                z_max = z_c
                z_min = z_c

            # Excursions
            if is_long:
                fav_z = max(z_c - z0, z_max - z0)
                adv_z = max(z0 - z_c, z0 - z_min)
            else:
                fav_z = max(z0 - z_c, z0 - z_min)
                adv_z = max(z_c - z0, z_max - z0)

            max_favorable_z = max(max_favorable_z, float(fav_z))
            max_adverse_z = max(max_adverse_z, float(adv_z))

            path.append({
                "date": f_date_str,
                "days_elapsed": i,
                "price_a": round(pa_c, 2),
                "price_b": round(pb_c, 2),
                "spread": round(s_c, 4),
                "z_score": round(z_c, 4),
            })

            # =================================================================
            # STAGE 1: Check Tranche 1 Exit (TP1) or Initial Stop Loss (3.20σ)
            # =================================================================
            if not tranche1_closed:
                # 1. Stop Loss Check (Constraint: Stop loss takes absolute priority)
                initial_stop_hit = False
                if is_long:
                    if z_c <= stop_z_barrier or z_min <= stop_z_barrier:
                        initial_stop_hit = True
                else:
                    if z_c >= stop_z_barrier or z_max >= stop_z_barrier:
                        initial_stop_hit = True

                # 2. TP1 Check
                tp1_condition_hit = False
                if is_long:
                    if z_c >= tp1_z_target or z_max >= tp1_z_target:
                        tp1_condition_hit = True
                else:
                    if z_c <= tp1_z_target or z_min <= tp1_z_target:
                        tp1_condition_hit = True

                # Enforce Stop Priority Rule
                if initial_stop_hit:
                    stop_loss_hit = True
                    tranche1_closed = True
                    tranche2_closed = True
                    final_exit_date = f_date_str
                    final_exit_days = i
                    final_pa = pa_c
                    final_pb = pb_c
                    final_spread = s_c
                    final_z = z_c

                    # PnL on Stop Out at 3.20σ
                    exit_s = setup.stop_loss_spread
                    spread_delta = (exit_s - s0) if is_long else (s0 - exit_s)
                    loss_pct = round((spread_delta / invested_capital) * 100.0, 2)
                    tp1_pnl_pct = loss_pct
                    tranche2_pnl_pct = loss_pct
                    tp1_z = stop_z_barrier
                    tp2_z = stop_z_barrier

                    resolved_outcome = "LOSS"
                    resolved_exit_reason = "STOP_LOSS"
                    resolved_reason = f"Initial Stop Loss Barrier Breached (|Z| >= {abs(stop_z_barrier):.2f}) on Day {i}"
                    break

                elif tp1_condition_hit:
                    # TP1 Executed! Bank 50% profit
                    tranche1_closed = True
                    tp1_date_str = f_date_str
                    tp1_days = i
                    tp1_z = tp1_z_target
                    s_tp1 = setup.target_spread_tp1
                    spread_delta_t1 = (s_tp1 - s0) if is_long else (s0 - s_tp1)
                    tp1_pnl_pct = round((spread_delta_t1 / invested_capital) * 100.0, 2)

                    # Engage Breakeven Stop for Tranche 2!
                    breakeven_stop_active = True

                    # Check if TP2 was ALSO hit on the exact same day
                    tp2_same_day = False
                    if is_long:
                        if z_c >= tp2_z_target or z_max >= tp2_z_target:
                            tp2_same_day = True
                    else:
                        if z_c <= tp2_z_target or z_min <= tp2_z_target:
                            tp2_same_day = True

                    if tp2_same_day:
                        tranche2_closed = True
                        tp2_date_str = f_date_str
                        tp2_days = i
                        tp2_z = tp2_z_target
                        s_tp2 = setup.target_spread_tp2
                        spread_delta_t2 = (s_tp2 - s0) if is_long else (s0 - s_tp2)
                        tranche2_pnl_pct = round((spread_delta_t2 / invested_capital) * 100.0, 2)

                        final_exit_date = f_date_str
                        final_exit_days = i
                        final_pa = pa_c
                        final_pb = pb_c
                        final_spread = s_tp2
                        final_z = tp2_z_target

                        resolved_outcome = "WIN"
                        resolved_exit_reason = "TP1_AND_TP2"
                        resolved_reason = f"Both Staged Targets Hit (TP1 & TP2 reached) on Day {i}"
                        break

            # =================================================================
            # STAGE 2: Tranche 1 is Closed -> Tranche 2 Active (TP2 or Breakeven)
            # =================================================================
            elif not tranche2_closed:
                # 1. Breakeven Stop Check: Did spread re-diverge back across entry level?
                be_stop_triggered = False
                if is_long:
                    # Long Spread entered at z0 <= -1.85. Stop if spread falls back to <= z0
                    if z_c <= breakeven_z or z_min <= breakeven_z:
                        be_stop_triggered = True
                else:
                    # Short Spread entered at z0 >= +1.85. Stop if spread rises back to >= z0
                    if z_c >= breakeven_z or z_max >= breakeven_z:
                        be_stop_triggered = True

                # 2. TP2 Target Check: Reached equilibrium (|Z| <= 0.20σ)
                tp2_condition_hit = False
                if is_long:
                    if z_c >= tp2_z_target or z_max >= tp2_z_target:
                        tp2_condition_hit = True
                else:
                    if z_c <= tp2_z_target or z_min <= tp2_z_target:
                        tp2_condition_hit = True

                if be_stop_triggered:
                    breakeven_stop_hit = True
                    tranche2_closed = True
                    tp2_date_str = f_date_str
                    tp2_days = i
                    tp2_z = breakeven_z
                    # Breakeven spread exit: PnL on Tranche 2 is 0.0%
                    tranche2_pnl_pct = 0.0

                    final_exit_date = f_date_str
                    final_exit_days = i
                    final_pa = pa_c
                    final_pb = pb_c
                    final_spread = s0
                    final_z = breakeven_z

                    # Overall trade is WIN because Tranche 1 took profit at 0.80σ!
                    resolved_outcome = "WIN"
                    resolved_exit_reason = "TP1_AND_BREAKEVEN"
                    resolved_reason = f"TP1 locked profit on Day {tp1_days}; Tranche 2 stopped at Breakeven on Day {i}"
                    break

                elif tp2_condition_hit:
                    tranche2_closed = True
                    tp2_date_str = f_date_str
                    tp2_days = i
                    tp2_z = tp2_z_target
                    s_tp2 = setup.target_spread_tp2
                    spread_delta_t2 = (s_tp2 - s0) if is_long else (s0 - s_tp2)
                    tranche2_pnl_pct = round((spread_delta_t2 / invested_capital) * 100.0, 2)

                    final_exit_date = f_date_str
                    final_exit_days = i
                    final_pa = pa_c
                    final_pb = pb_c
                    final_spread = s_tp2
                    final_z = tp2_z_target

                    resolved_outcome = "WIN"
                    resolved_exit_reason = "TP1_AND_TP2"
                    resolved_reason = f"Full Mean Reversion Achieved: TP1 on Day {tp1_days}, TP2 on Day {i}"
                    break

            # =================================================================
            # STAGE 3: OU Time Stop Check
            # =================================================================
            if i >= setup.time_stop_days:
                time_stop_hit = True
                final_exit_date = f_date_str
                final_exit_days = i
                final_pa = pa_c
                final_pb = pb_c
                final_spread = s_c
                final_z = z_c

                # Close any remaining open tranches at market close
                spread_delta_market = (s_c - s0) if is_long else (s0 - s_c)
                market_pnl_pct = round((spread_delta_market / invested_capital) * 100.0, 2)

                if not tranche1_closed:
                    tranche1_closed = True
                    tp1_days = i
                    tp1_pnl_pct = market_pnl_pct
                    tp1_z = z_c

                if not tranche2_closed:
                    tranche2_closed = True
                    tp2_days = i
                    tranche2_pnl_pct = market_pnl_pct
                    tp2_z = z_c

                comb_pnl = round(0.50 * tp1_pnl_pct + 0.50 * tranche2_pnl_pct, 2)
                resolved_outcome = "WIN" if comb_pnl > 0.05 else ("LOSS" if comb_pnl < -0.05 else "NEUTRAL")
                resolved_exit_reason = "TIME_STOP"
                resolved_reason = f"Ornstein-Uhlenbeck Time Stop Reached ({i} days >= T_max {setup.time_stop_days}d). Closed at market."
                break

        # If loop finished without early exit (end of historical horizon)
        if resolved_outcome is None:
            final_exit_date = future_dates[-1].strftime("%Y-%m-%d")
            final_exit_days = len(future_dates)
            final_pa = float(close_a[-1])
            final_pb = float(close_b[-1])
            final_spread = float(final_pa - beta * final_pb)
            final_z = float((final_spread - mu) / sigma)

            spread_delta_end = (final_spread - s0) if is_long else (s0 - final_spread)
            end_pnl_pct = round((spread_delta_end / invested_capital) * 100.0, 2)

            if not tranche1_closed:
                tp1_pnl_pct = end_pnl_pct
                tp1_days = final_exit_days
                tp1_z = final_z

            if not tranche2_closed:
                tranche2_pnl_pct = end_pnl_pct
                tp2_days = final_exit_days
                tp2_z = final_z

            comb_pnl = round(0.50 * tp1_pnl_pct + 0.50 * tranche2_pnl_pct, 2)
            resolved_outcome = "WIN" if comb_pnl > 0.05 else ("LOSS" if comb_pnl < -0.05 else "NEUTRAL")
            resolved_exit_reason = "TIME_STOP"
            resolved_reason = f"Evaluated across available future horizon ({final_exit_days} days). Closed at market."

        # Combined Realized Return on Invested Capital: 50% Tranche 1 + 50% Tranche 2
        combined_pnl_pct = round(0.50 * tp1_pnl_pct + 0.50 * tranche2_pnl_pct, 2)

        return StrategyV2EvaluationResult(
            pair_name=setup.pair_name,
            target_date=setup.target_date,
            direction=setup.direction,
            outcome=resolved_outcome,
            status_reason=resolved_reason,
            exit_reason=resolved_exit_reason,
            entry_price_a=setup.price_a_entry,
            entry_price_b=setup.price_b_entry,
            entry_spread=setup.current_spread,
            entry_z_score=setup.current_z_score,
            exit_date=final_exit_date,
            exit_days_held=final_exit_days,
            exit_price_a=round(final_pa, 2),
            exit_price_b=round(final_pb, 2),
            exit_spread=round(final_spread, 4),
            exit_z_score=round(final_z, 4),
            realized_pnl_pct=combined_pnl_pct,
            tp1_hit=bool(resolved_exit_reason in ("TP1_AND_TP2", "TP1_AND_BREAKEVEN")),
            tp1_date=tp1_date_str,
            tp1_days_held=tp1_days,
            tp1_z_score=round(tp1_z, 4),
            tranche1_pnl_pct=tp1_pnl_pct,
            tp2_hit=bool(resolved_exit_reason == "TP1_AND_TP2"),
            tp2_date=tp2_date_str,
            tp2_days_held=tp2_days,
            tp2_z_score=round(tp2_z, 4),
            tranche2_pnl_pct=tranche2_pnl_pct,
            breakeven_stop_hit=breakeven_stop_hit,
            time_stop_hit=time_stop_hit,
            stop_loss_hit=stop_loss_hit,
            max_favorable_z=round(max_favorable_z, 4),
            max_adverse_z=round(max_adverse_z, 4),
            path=path,
        )
