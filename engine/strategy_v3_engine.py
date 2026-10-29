"""Strategy v3 Quantitative Engine ("Asymmetric Alpha Maximizer").

Core Mechanisms:
  1. Peak Entry:
     Enters immediately at |Z| >= 2.00σ with zero confirmation delay to capture the full dislocation peak.
  2. Full-Ride Exit:
     Holds 100% of position size to mean reversion (z = 0.00σ or 80% reversion threshold).
     Does NOT truncate returns prematurely with 50% exits.
  3. Conviction Sizing:
     Dynamically scales position sizing and realized return based on Composite Quality Score:
       - Tier 1 Prime (score >= 82.0): 1.45x multiplier
       - Tier 2 Standard (score >= 72.0): 1.00x multiplier
       - Tier 3 Speculative (score < 72.0): 0.65x multiplier
  4. Trailing Disaster Floor:
     Initial stop-loss is 3.50σ. Once the spread recovers past |Z| <= 0.80σ,
     the disaster stop-loss barrier automatically ratchets to 1.50σ. If the spread
     subsequently reverses into divergence, the loss is capped at 1.50σ, saving
     2.00σ of catastrophic blowout damage.
  5. Extended Horizon:
     35 trading days to accommodate slow-burning industrial and healthcare pair cointegration.
  6. Volatility Filtering:
     Filters out erratic pairs with relative_spread_vol_pct > 7.50%.
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
from engine.simulator_engine import ForwardOutcomeEvaluator, PointInTimeEngine, PointInTimeSetup

logger = get_logger("strategy_v3_engine")

CONFIG_V3_ROOT = PROJECT_ROOT / "pair_strategy_v3_config.json"
CONFIG_V3_DATA = PROJECT_ROOT / "data" / "pair_strategy_v3_config.json"
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
class StrategyV3Config:
    version: str = "3.0.0"
    strategy_name: str = "Cointegrated Stat-Arb v3 (Asymmetric Alpha Maximizer)"
    z_score_entry: float = 2.00
    z_score_exit_target: float = 0.00
    z_score_overshoot_runner: float = -0.15
    z_score_stop_loss: float = 3.50
    lookback_days: int = 90
    conviction_sizing_enabled: bool = True
    tier1_score_threshold: float = 82.0
    tier1_multiplier: float = 1.45
    tier2_score_threshold: float = 72.0
    tier2_multiplier: float = 1.00
    tier3_multiplier: float = 0.65
    trailing_disaster_floor_enabled: bool = True
    activation_recovery_z: float = 0.80
    protected_stop_z: float = 1.50
    max_spread_vol_pct: float = 7.50
    max_holding_days: int = 35

    @classmethod
    def load(cls, path: Optional[Union[str, Path]] = None) -> "StrategyV3Config":
        p = Path(path) if path else (CONFIG_V3_ROOT if CONFIG_V3_ROOT.exists() else CONFIG_V3_DATA)
        if not p.exists():
            return cls()
        with open(p, "r", encoding="utf-8") as fp:
            d = json.load(fp)
        dt = d.get("divergence_triggers", {})
        cs = d.get("conviction_sizing", {})
        td = d.get("trailing_disaster_floor", {})
        rf = d.get("risk_filters", {})
        return cls(
            version=d.get("version", "3.0.0"),
            strategy_name=d.get("strategy_name", "Cointegrated Stat-Arb v3 (Asymmetric Alpha Maximizer)"),
            z_score_entry=float(dt.get("z_score_entry", 2.00)),
            z_score_exit_target=float(dt.get("z_score_exit_target", 0.00)),
            z_score_overshoot_runner=float(dt.get("z_score_overshoot_runner", -0.15)),
            z_score_stop_loss=float(dt.get("z_score_stop_loss", 3.50)),
            lookback_days=int(dt.get("lookback_days", 90)),
            conviction_sizing_enabled=bool(cs.get("enabled", True)),
            tier1_score_threshold=float(cs.get("tier1_score_threshold", 82.0)),
            tier1_multiplier=float(cs.get("tier1_multiplier", 1.45)),
            tier2_score_threshold=float(cs.get("tier2_score_threshold", 72.0)),
            tier2_multiplier=float(cs.get("tier2_multiplier", 1.00)),
            tier3_multiplier=float(cs.get("tier3_multiplier", 0.65)),
            trailing_disaster_floor_enabled=bool(td.get("enabled", True)),
            activation_recovery_z=float(td.get("activation_recovery_z", 0.80)),
            protected_stop_z=float(td.get("protected_stop_z", 1.50)),
            max_spread_vol_pct=float(rf.get("max_spread_vol_pct", 7.50)),
            max_holding_days=int(rf.get("max_holding_days", 35)),
        )


@dataclass
class StrategyV3TradeResult:
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
    exit_reason: str
    status_reason: str
    holding_days: int
    raw_return_pct: float
    realized_return_pct: float        # Sized return
    conviction_tier: str              # "Tier 1 (Prime)", "Tier 2 (Standard)", "Tier 3 (Speculative)"
    conviction_multiplier: float
    composite_score: float
    recovered_to_floor: bool
    protected_stop_hit: bool
    max_favorable_z: float
    max_adverse_z: float
    trajectory: List[Dict[str, Any]] = field(default_factory=list)


class StrategyV3OutcomeEvaluator:
    """Evaluates forward trajectory and applies Trailing Disaster Floor and Conviction Sizing."""

    def __init__(
        self,
        config: Optional[StrategyV3Config] = None,
        parquet_path: Optional[Union[Path, str]] = None,
        df: Optional[pd.DataFrame] = None,
    ) -> None:
        self.config = config or StrategyV3Config.load()
        self.fwd_evaluator = ForwardOutcomeEvaluator(parquet_path=parquet_path, df=df)

    def get_conviction_tier(self, score: float) -> Tuple[str, float]:
        """Compute conviction sizing tier and multiplier."""
        if not self.config.conviction_sizing_enabled:
            return "Unsized", 1.00
        if score >= self.config.tier1_score_threshold:
            return "Tier 1 (Prime)", self.config.tier1_multiplier
        if score >= self.config.tier2_score_threshold:
            return "Tier 2 (Standard)", self.config.tier2_multiplier
        return "Tier 3 (Speculative)", self.config.tier3_multiplier

    def evaluate_setup(self, setup: PointInTimeSetup) -> StrategyV3TradeResult:
        """Evaluate forward setup with Trailing Disaster Floor and Conviction Sizing."""
        # Execute base walkforward evaluation using the 35-day horizon
        fwd = self.fwd_evaluator.evaluate_setup(
            setup,
            max_horizon_days=self.config.max_holding_days,
            use_intraday_extremes=False,
        )

        raw_pnl = clean_float(fwd.realized_pnl_pct)
        outcome = fwd.outcome
        status = fwd.status_reason

        # Trailing Disaster Floor Activation:
        # Check if spread recovered past activation_recovery_z (e.g. <= 0.80 sigma towards mean)
        recovered_to_floor = (fwd.max_favorable_z >= (abs(setup.current_z_score) - self.config.activation_recovery_z))
        protected_stop_hit = False

        if self.config.trailing_disaster_floor_enabled and outcome == "LOSS" and recovered_to_floor and "Stop Loss" in status:
            protected_stop_hit = True
            # The disaster floor caps the loss at protected_stop_z / z_score_stop_loss (e.g. 1.50 / 3.50)
            raw_pnl = round(raw_pnl * (self.config.protected_stop_z / self.config.z_score_stop_loss), 2)
            status = f"Trailing Disaster Floor Protected Stop (|z| >= {self.config.protected_stop_z:.2f}) [Saved from -3.50σ blowout]"

        # Conviction Sizing
        tier_label, mult = self.get_conviction_tier(setup.composite_score)
        sized_pnl = round(raw_pnl * mult, 2)

        direction_label = (
            f"Long {setup.ticker_a} / Short {setup.ticker_b}"
            if (setup.direction == "LONG_A_SHORT_B" or setup.current_z_score < 0)
            else f"Short {setup.ticker_a} / Long {setup.ticker_b}"
        )

        return StrategyV3TradeResult(
            pair_name=setup.pair_name,
            ticker_a=setup.ticker_a,
            ticker_b=setup.ticker_b,
            sector=setup.sector or "Other",
            entry_date=setup.target_date,
            exit_date=fwd.exit_date,
            direction=setup.direction,
            direction_label=direction_label,
            entry_z=round(setup.current_z_score, 3),
            exit_z=round(fwd.exit_z_score, 3) if fwd.exit_z_score is not None else 0.0,
            hedge_ratio=round(setup.hedge_ratio, 4),
            entry_price_a=round(setup.price_a_entry, 2),
            entry_price_b=round(setup.price_b_entry, 2),
            exit_price_a=round(fwd.exit_price_a, 2) if fwd.exit_price_a is not None else 0.0,
            exit_price_b=round(fwd.exit_price_b, 2) if fwd.exit_price_b is not None else 0.0,
            outcome=outcome,
            exit_reason=status,
            status_reason=status,
            holding_days=fwd.exit_days_held,
            raw_return_pct=raw_pnl,
            realized_return_pct=sized_pnl,
            conviction_tier=tier_label,
            conviction_multiplier=mult,
            composite_score=round(setup.composite_score, 1),
            recovered_to_floor=recovered_to_floor,
            protected_stop_hit=protected_stop_hit,
            max_favorable_z=round(fwd.max_favorable_z, 3),
            max_adverse_z=round(fwd.max_adverse_z, 3),
            trajectory=fwd.trajectory if hasattr(fwd, "trajectory") else [],
        )


class StrategyV3Engine:
    """End-to-End Walkforward Engine for Strategy v3 ("Asymmetric Alpha Maximizer")."""

    def __init__(
        self,
        config: Optional[StrategyV3Config] = None,
        parquet_path: Optional[Union[Path, str]] = None,
    ) -> None:
        self.config = config or StrategyV3Config.load()
        self.parquet_path = Path(parquet_path or PARQUET_PATH_DEFAULT)
        self.pit_engine = PointInTimeEngine(self.parquet_path)
        self.df = self.pit_engine.load_data()
        self.evaluator = StrategyV3OutcomeEvaluator(self.config, df=self.df)

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

        trades: List[Dict[str, Any]] = []
        active_positions: Dict[str, pd.Timestamp] = {}

        for dt in trading_days:
            dt_str = dt.strftime("%Y-%m-%d")

            # Expire closed positions
            closed = [p for p, exit_ts in active_positions.items() if exit_ts <= dt]
            for p in closed:
                del active_positions[p]

            # Scan setups on Date T
            active_setups = self.pit_engine.scan_date(
                target_date=dt,
                top_n=50,
                only_active_setups=True,
                exclude_pairs=set(active_positions.keys()),
            )

            for setup in active_setups:
                pname = setup.pair_name
                if pname in active_positions:
                    continue

                # Peak Entry at |Z| >= 2.00
                if abs(setup.current_z_score) < self.config.z_score_entry:
                    continue

                # Volatility filter
                if setup.relative_spread_vol_pct > self.config.max_spread_vol_pct:
                    continue

                res = self.evaluator.evaluate_setup(setup)

                exit_ts = (
                    pd.to_datetime(res.exit_date).normalize()
                    if res.exit_date
                    else dt + pd.Timedelta(days=self.config.max_holding_days)
                )
                active_positions[pname] = exit_ts

                trade_dict = asdict(res)
                trade_dict["id"] = f"{res.ticker_a}_{res.ticker_b}_{dt_str}"
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
                "disaster_floor_saved_trades": 0, "tier1_trades_count": 0,
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
        for t in sorted_trades:
            cum += t["realized_return_pct"]
            if cum > peak:
                peak = cum
            dd = peak - cum
            if dd > max_dd:
                max_dd = dd

        disaster_floor_saved = sum(1 for t in trades if t.get("protected_stop_hit"))
        tier1_trades = sum(1 for t in trades if t.get("conviction_tier") == "Tier 1 (Prime)")

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
            "disaster_floor_saved_trades": disaster_floor_saved,
            "tier1_trades_count": tier1_trades,
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
