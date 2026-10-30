"""Strategy Comparison & Diagnostic Engine.

Aligns Strategy v1 (Baseline) and Strategy v2 (Confirmed Reversion & Staged Exit)
trade-for-trade across historical horizons (1Y, 2Y, 3Y, 5Y) to compute differential
delta performance metrics, classify failure causes, and categorize trades into
diagnostic cohorts.

Key Capabilities:
  1. Point-in-time Trade Matching:
     Aligns trades strictly by pair and historical timestamp windows to isolate
     the precise impact of v2's confirmation hook and staged profit exits.
  2. Four Primary Trade Diagnostic Categories:
     - Category A: "Saved Losses (The Shield)"
     - Category B: "Flipped Trades (Loss -> Win)"
     - Category C: "Preserved Winners"
     - Category D: "Missed Opportunities"
     (plus Persistent Losses and v2 New Alpha setups).
  3. Failure Cause Attribution for Strategy v1 Losses:
     - Runaway Momentum (no hook confirmation)
     - Earnings / Event Shocks (in blackout window)
     - Profit Give-Back (reached TP1 but failed to reach 0.0)
     - Stale Half-Life Decay (sluggish reversion past OU half-life)
  4. Comparative Delta Computations:
     - Δ Win Rate %, Δ Max Drawdown %, Δ Profit Factor, Capital Preserved from Saved Losses.
  5. Aligned Dual-Series Equity Curve:
     Synchronized daily equity step function for side-by-side overlay visualization.
"""

from __future__ import annotations

import json
import logging
import math
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from engine.config import PROJECT_ROOT
from engine.logging_setup import get_logger
from engine.strategy_v2_engine import EarningsCalendar

logger = get_logger("strategy_comparison_engine")


def clean_float(val: Any, default: float = 0.0) -> float:
    """Ensure a float value is RFC-8259 JSON compliant (no NaN or Inf)."""
    if val is None:
        return default
    try:
        f = float(val)
        if math.isnan(f) or math.isinf(f):
            return default
        return round(f, 4)
    except (TypeError, ValueError):
        return default


def parse_date(date_str: Optional[str]) -> Optional[datetime]:
    """Parse YYYY-MM-DD string to datetime object safely."""
    if not date_str or not isinstance(date_str, str):
        return None
    try:
        return datetime.strptime(date_str[:10], "%Y-%m-%d")
    except Exception:
        return None


class StrategyComparisonEngine:
    """Institutional analytics engine comparing Strategy v1 and Strategy v2."""

    def __init__(self, project_root: Optional[Path] = None):
        self.project_root = project_root or PROJECT_ROOT
        self.data_dir = self.project_root / "data"
        self.cache_dir = self.data_dir / "backtest_runs_cache"
        self.earnings_cal = EarningsCalendar(self.project_root / "data_cache" / "research")

        # Mapping for v1 baseline files across horizons
        self.v1_files: Dict[str, Path] = {
            "1Y": self.data_dir / "backtest_1y_results.json",
            "2Y": self.cache_dir / "2024-10-26_2026-10-26_ez2.0_sz3.5_h30.json",
            "3Y": self.cache_dir / "2023-10-26_2026-10-26_ez2.0_sz3.5_h30.json",
            "5Y": self.cache_dir / "2021-10-27_2026-10-26_ez2.0_sz3.5_h30.json",
        }

        # Mapping for v2 precomputed results across horizons
        self.v2_files: Dict[str, Path] = {
            "1Y": self.data_dir / "backtest_v2_1y_results.json",
            "2Y": self.data_dir / "backtest_v2_2y_results.json",
            "3Y": self.data_dir / "backtest_v2_3y_results.json",
            "5Y": self.data_dir / "backtest_v2_5y_results.json",
        }

        # Mapping for v3 precomputed results across horizons
        self.v3_files: Dict[str, Path] = {
            "1Y": self.data_dir / "backtest_v3_1y_results.json",
            "2Y": self.data_dir / "backtest_v3_2y_results.json",
            "3Y": self.data_dir / "backtest_v3_3y_results.json",
            "5Y": self.data_dir / "backtest_v3_5y_results.json",
        }

        # Mapping for v4 precomputed results across horizons
        self.v4_files: Dict[str, Path] = {
            "1Y": self.data_dir / "backtest_v4_1y_results.json",
            "2Y": self.data_dir / "backtest_v4_2y_results.json",
            "3Y": self.data_dir / "backtest_v4_3y_results.json",
            "5Y": self.data_dir / "backtest_v4_5y_results.json",
        }

    def load_v1_results(self, period: str = "1Y") -> Dict[str, Any]:
        """Load Strategy v1 results for the specified horizon."""
        clean_period = period.strip().upper()
        f_path = self.v1_files.get(clean_period)
        if not f_path or not f_path.exists():
            # Fallback to 1Y file if specific cache does not exist
            f_path = self.data_dir / "backtest_1y_results.json"

        if not f_path.exists():
            raise FileNotFoundError(f"Strategy v1 baseline file not found: {f_path}")

        with open(f_path, "r", encoding="utf-8") as fp:
            return json.load(fp)

    def load_v2_results(self, period: str = "1Y") -> Dict[str, Any]:
        """Load Strategy v2 results for the specified horizon."""
        clean_period = period.strip().upper()
        f_path = self.v2_files.get(clean_period)
        if not f_path or not f_path.exists():
            f_path = self.data_dir / f"backtest_v2_{clean_period.lower()}_results.json"

        if not f_path.exists():
            raise FileNotFoundError(f"Strategy v2 result file not found: {f_path}")

        with open(f_path, "r", encoding="utf-8") as fp:
            return json.load(fp)

    def load_v3_results(self, period: str = "1Y") -> Dict[str, Any]:
        """Load Strategy v3 results for the specified horizon."""
        clean_period = period.strip().upper()
        f_path = self.v3_files.get(clean_period)
        if not f_path or not f_path.exists():
            f_path = self.data_dir / f"backtest_v3_{clean_period.lower()}_results.json"

        if not f_path.exists():
            return {}

        with open(f_path, "r", encoding="utf-8") as fp:
            return json.load(fp)

    def load_v4_results(self, period: str = "1Y") -> Dict[str, Any]:
        """Load Strategy v4 results for the specified horizon."""
        clean_period = period.strip().upper()
        f_path = self.v4_files.get(clean_period)
        if not f_path or not f_path.exists():
            f_path = self.data_dir / f"backtest_v4_{clean_period.lower()}_results.json"

        if not f_path.exists():
            return {}

        with open(f_path, "r", encoding="utf-8") as fp:
            return json.load(fp)

    def classify_failure_cause(self, trade: Dict[str, Any]) -> str:
        """Classify why a Strategy v1 trade failed into one of 4 root causes."""
        ticker_a = trade.get("ticker_a", "")
        ticker_b = trade.get("ticker_b", "")
        entry_d = trade.get("entry_date", "")
        reason = trade.get("status_reason", "")
        max_fav = abs(clean_float(trade.get("max_favorable_z", 0.0)))
        max_adv = abs(clean_float(trade.get("max_adverse_z", 0.0)))
        holding = clean_float(trade.get("holding_days", 0.0))
        hl = clean_float(trade.get("half_life_days", 20.0), default=20.0)

        # 1. Earnings / Binary Event Shock
        is_blackout, _ = self.earnings_cal.is_in_blackout(ticker_a, ticker_b, entry_d, blackout_days=5)
        if is_blackout or (holding <= 2 and max_adv >= 1.5):
            return "EARNINGS_SHOCK"

        # 2. Profit Give-Back (reached >= 0.80 sigma favorable but did not reach 0.0 before stop)
        if max_fav >= 0.80:
            return "PROFIT_GIVEBACK"

        # 3. Stale Half-Life Decay (lingered longer than half-life or expired)
        if "expired" in reason.lower() or holding >= hl or holding >= 12:
            return "STALE_DECAY"

        # 4. Runaway Momentum (blew out immediately without confirmation hook)
        return "RUNAWAY_MOMENTUM"

    def match_trades(
        self,
        v1_trades: List[Dict[str, Any]],
        v2_trades: List[Dict[str, Any]],
        max_entry_diff_days: int = 10,
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """Align trades strictly by pair and historical timestamp window.

        Returns:
            (trade_deltas, category_metrics)
        """
        matched_v1_to_v2: Dict[int, int] = {}
        used_v2_indices: Set[int] = set()

        # Step 1: Greedy nearest-entry matching for same pair with overlapping intervals
        for i, t1 in enumerate(v1_trades):
            p1 = t1.get("pair_name")
            d1_entry = parse_date(t1.get("entry_date"))
            d1_exit = parse_date(t1.get("exit_date")) or d1_entry

            if not d1_entry or not d1_exit:
                continue

            best_match: Optional[int] = None
            min_diff: float = 999.0

            for j, t2 in enumerate(v2_trades):
                if j in used_v2_indices:
                    continue
                if t2.get("pair_name") != p1:
                    continue

                d2_entry = parse_date(t2.get("entry_date"))
                d2_exit = parse_date(t2.get("exit_date")) or d2_entry
                if not d2_entry or not d2_exit:
                    continue

                entry_diff = abs((d2_entry - d1_entry).days)
                # Overlap test: max(entry1, entry2) <= min(exit1, exit2)
                overlaps = max(d1_entry, d2_entry) <= min(d1_exit, d2_exit)

                if (entry_diff <= max_entry_diff_days or overlaps) and entry_diff < min_diff:
                    min_diff = entry_diff
                    best_match = j

            if best_match is not None:
                matched_v1_to_v2[i] = best_match
                used_v2_indices.add(best_match)

        # Step 2: Build categorized trade deltas
        trade_deltas: List[Dict[str, Any]] = []

        saved_losses_count = 0
        flipped_trades_count = 0
        preserved_winners_count = 0
        missed_opportunities_count = 0
        persistent_losses_count = 0
        degraded_wins_count = 0
        capital_preserved_loss_pct = 0.0

        for i, t1 in enumerate(v1_trades):
            v1_out = t1.get("outcome", "NEUTRAL")
            v1_ret = clean_float(t1.get("realized_return_pct", 0.0))
            j = matched_v1_to_v2.get(i)

            if j is not None:
                t2 = v2_trades[j]
                v2_out = t2.get("outcome", "NEUTRAL")
                v2_ret = clean_float(t2.get("realized_return_pct", 0.0))
                ret_delta = round(v2_ret - v1_ret, 2)

                if v1_out == "LOSS" and v2_out == "WIN":
                    category = "FLIPPED_TRADE"
                    category_label = "Flipped Trade (Loss -> Win)"
                    flipped_trades_count += 1
                    explanation = (
                        f"In v1, trade hit stop-loss ({v1_ret:+.2f}%) waiting for full reversion to 0.0σ. "
                        f"In v2, Staged TP1 banked profits at 0.80σ and moved stop to breakeven, closing at {v2_ret:+.2f}%."
                    )
                elif v1_out == "WIN" and v2_out == "WIN":
                    category = "PRESERVED_WINNER"
                    category_label = "Preserved Winner"
                    preserved_winners_count += 1
                    explanation = (
                        f"High-conviction mean-reverting setup captured by both engines. "
                        f"v1 realized {v1_ret:+.2f}%, v2 realized {v2_ret:+.2f}% with risk-managed staging."
                    )
                elif v1_out == "LOSS" and v2_out == "LOSS":
                    category = "PERSISTENT_LOSS"
                    category_label = "Persistent Loss"
                    persistent_losses_count += 1
                    explanation = (
                        f"Structural breakdown stopped out in both strategies. v2 tightened stop barrier to 3.20σ "
                        f"(v1: {v1_ret:+.2f}% vs v2: {v2_ret:+.2f}%)."
                    )
                elif v1_out == "WIN" and v2_out == "LOSS":
                    category = "DEGRADED_WIN"
                    category_label = "Degraded Win"
                    degraded_wins_count += 1
                    explanation = (
                        f"v1 closed in slight profit ({v1_ret:+.2f}%) while v2 exited via tight stop/time stop ({v2_ret:+.2f}%)."
                    )
                else:
                    category = "NEUTRAL_COHORT"
                    category_label = "Neutral Alignment"
                    explanation = f"v1 outcome was {v1_out}; v2 outcome was {v2_out}."

                trade_deltas.append({
                    "id": f"DELTA_{t1.get('id', i)}_{t2.get('id', j)}",
                    "pair_name": t1.get("pair_name"),
                    "sector": t1.get("sector") or t2.get("sector", "Other"),
                    "direction": t1.get("direction_label") or t2.get("direction_label"),
                    "category": category,
                    "category_label": category_label,
                    "v1_entry_date": t1.get("entry_date"),
                    "v1_exit_date": t1.get("exit_date"),
                    "v1_outcome": v1_out,
                    "v1_return_pct": v1_ret,
                    "v1_exit_reason": t1.get("status_reason"),
                    "v2_entry_date": t2.get("entry_date"),
                    "v2_exit_date": t2.get("exit_date"),
                    "v2_outcome": v2_out,
                    "v2_return_pct": v2_ret,
                    "v2_exit_reason": t2.get("exit_reason"),
                    "return_delta_pct": ret_delta,
                    "failure_cause": self.classify_failure_cause(t1) if v1_out == "LOSS" else None,
                    "explanation": explanation,
                })
            else:
                # Unmatched v1 trade (avoided or filtered in v2)
                failure_cause = self.classify_failure_cause(t1) if v1_out == "LOSS" else None

                if v1_out == "LOSS":
                    category = "SAVED_LOSS"
                    category_label = "Saved Loss (The Shield)"
                    saved_losses_count += 1
                    if v1_ret < 0:
                        capital_preserved_loss_pct += abs(v1_ret)
                    explanation = (
                        f"v1 lost {v1_ret:+.2f}% due to {failure_cause.replace('_', ' ').title()}. "
                        f"Strategy v2 completely vetoed entry via confirmation hook / earnings blackout, preserving 100% of capital."
                    )
                elif v1_out == "WIN":
                    category = "MISSED_OPPORTUNITY"
                    category_label = "Missed Opportunity"
                    missed_opportunities_count += 1
                    explanation = (
                        f"v1 captured +{v1_ret:.2f}%, but setup was screened out in v2 by the stricter statistical gauntlet "
                        f"(R² >= 0.50, HL <= 22d, ADF p <= 0.04)."
                    )
                else:
                    category = "UNMATCHED_NEUTRAL"
                    category_label = "Unmatched Neutral"
                    explanation = "Neutral or open trade filtered out in Strategy v2."

                trade_deltas.append({
                    "id": f"DELTA_{t1.get('id', i)}_V1ONLY",
                    "pair_name": t1.get("pair_name"),
                    "sector": t1.get("sector", "Other"),
                    "direction": t1.get("direction_label"),
                    "category": category,
                    "category_label": category_label,
                    "v1_entry_date": t1.get("entry_date"),
                    "v1_exit_date": t1.get("exit_date"),
                    "v1_outcome": v1_out,
                    "v1_return_pct": v1_ret,
                    "v1_exit_reason": t1.get("status_reason"),
                    "v2_entry_date": None,
                    "v2_exit_date": None,
                    "v2_outcome": "VETOED",
                    "v2_return_pct": 0.0,
                    "v2_exit_reason": "VETOED_BY_V2_GAUNTLET",
                    "return_delta_pct": round(0.0 - v1_ret, 2),
                    "failure_cause": failure_cause,
                    "explanation": explanation,
                })

        # Step 3: Add v2 New Alpha setups (trades taken in v2 with no v1 match)
        v2_new_alpha_count = 0
        for j, t2 in enumerate(v2_trades):
            if j not in used_v2_indices:
                v2_new_alpha_count += 1
                v2_ret = clean_float(t2.get("realized_return_pct", 0.0))
                v2_out = t2.get("outcome", "NEUTRAL")
                trade_deltas.append({
                    "id": f"DELTA_V2ONLY_{t2.get('id', j)}",
                    "pair_name": t2.get("pair_name"),
                    "sector": t2.get("sector", "Other"),
                    "direction": t2.get("direction_label"),
                    "category": "V2_NEW_ALPHA",
                    "category_label": "v2 New Alpha Setup",
                    "v1_entry_date": None,
                    "v1_exit_date": None,
                    "v1_outcome": "UNTRIGGERED",
                    "v1_return_pct": 0.0,
                    "v1_exit_reason": None,
                    "v2_entry_date": t2.get("entry_date"),
                    "v2_exit_date": t2.get("exit_date"),
                    "v2_outcome": v2_out,
                    "v2_return_pct": v2_ret,
                    "v2_exit_reason": t2.get("exit_reason"),
                    "return_delta_pct": round(v2_ret - 0.0, 2),
                    "failure_cause": None,
                    "explanation": (
                        f"Independent high-conviction trade identified by v2 hook confirmation. Realized {v2_ret:+.2f}% ({v2_out})."
                    ),
                })

        category_metrics = {
            "saved_losses_count": saved_losses_count,
            "flipped_trades_count": flipped_trades_count,
            "preserved_winners_count": preserved_winners_count,
            "missed_opportunities_count": missed_opportunities_count,
            "persistent_losses_count": persistent_losses_count,
            "degraded_wins_count": degraded_wins_count,
            "v2_new_alpha_count": v2_new_alpha_count,
            "total_matched_pairs": len(matched_v1_to_v2),
            "capital_preserved_loss_pct": round(capital_preserved_loss_pct, 2),
        }

        return trade_deltas, category_metrics

    def classify_v1_failures(self, v1_trades: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Aggregate failure attribution breakdown for all Strategy v1 losses."""
        losses = [t for t in v1_trades if t.get("outcome") == "LOSS"]
        total_losses = len(losses)

        counts = {
            "RUNAWAY_MOMENTUM": 0,
            "EARNINGS_SHOCK": 0,
            "PROFIT_GIVEBACK": 0,
            "STALE_DECAY": 0,
        }

        for t in losses:
            cause = self.classify_failure_cause(t)
            counts[cause] = counts.get(cause, 0) + 1

        pcts = {}
        for k, v in counts.items():
            pcts[k] = round((v / total_losses * 100) if total_losses > 0 else 0.0, 1)

        return {
            "total_losses": total_losses,
            "counts": counts,
            "percentages": pcts,
            "descriptions": {
                "RUNAWAY_MOMENTUM": "Continuous divergence through 3.5σ barrier without mean-reversion hook.",
                "EARNINGS_SHOCK": "Binary earnings announcements within ±5 days causing overnight gap divergence.",
                "PROFIT_GIVEBACK": "Spread reached favorable TP1 territory (<= 0.80σ) but reversed into a stop before hitting 0.0.",
                "STALE_DECAY": "Lingered beyond OU half-life duration without decisive reversion.",
            },
        }

    def build_aligned_equity(
        self,
        v1_trades: List[Dict[str, Any]],
        v2_equity_curve: List[Dict[str, Any]],
        v3_equity_curve: Optional[List[Dict[str, Any]]] = None,
        v4_equity_curve: Optional[List[Dict[str, Any]]] = None,
    ) -> List[Dict[str, Any]]:
        """Construct a synchronized multi-series daily equity step function for Strategy 1, 2, 3, and 4."""
        # 1. Map v1 realized returns by date
        v1_sorted = sorted(
            v1_trades,
            key=lambda x: parse_date(x.get("exit_date") or x.get("entry_date")) or datetime(1970, 1, 1),
        )

        v1_daily: Dict[str, float] = {}
        cum_v1 = 0.0
        for t in v1_sorted:
            d_str = t.get("exit_date") or t.get("entry_date")
            if d_str:
                cum_v1 += clean_float(t.get("realized_return_pct", 0.0))
                v1_daily[d_str] = round(cum_v1, 2)

        # 2. Map v2 realized returns by date
        v2_daily: Dict[str, float] = {}
        for pt in v2_equity_curve:
            d_str = pt.get("date")
            if d_str:
                v2_daily[d_str] = clean_float(pt.get("cumulative_equity_pct", 0.0))

        # 3. Map v3 realized returns by date
        v3_daily: Dict[str, float] = {}
        if v3_equity_curve:
            for pt in v3_equity_curve:
                d_str = pt.get("date")
                if d_str:
                    v3_daily[d_str] = clean_float(pt.get("cumulative_equity_pct", 0.0))

        # 4. Map v4 realized returns by date
        v4_daily: Dict[str, float] = {}
        if v4_equity_curve:
            for pt in v4_equity_curve:
                d_str = pt.get("date")
                if d_str:
                    v4_daily[d_str] = clean_float(pt.get("cumulative_equity_pct", 0.0))

        # 5. Combine and sort all unique dates
        all_dates = sorted(
            list(
                set(v1_daily.keys())
                .union(set(v2_daily.keys()))
                .union(set(v3_daily.keys()))
                .union(set(v4_daily.keys()))
            )
        )

        aligned: List[Dict[str, Any]] = []
        curr_v1 = 0.0
        curr_v2 = 0.0
        curr_v3 = 0.0
        curr_v4 = 0.0

        for d in all_dates:
            if d in v1_daily:
                curr_v1 = v1_daily[d]
            if d in v2_daily:
                curr_v2 = v2_daily[d]
            if d in v3_daily:
                curr_v3 = v3_daily[d]
            if d in v4_daily:
                curr_v4 = v4_daily[d]

            alpha_spread = round(curr_v2 - curr_v1, 2)
            v3_alpha_spread = round(curr_v3 - curr_v1, 2)
            v4_alpha_spread = round(curr_v4 - curr_v1, 2)
            aligned.append({
                "date": d,
                "v1_equity": round(curr_v1, 2),
                "v2_equity": round(curr_v2, 2),
                "v3_equity": round(curr_v3, 2),
                "v4_equity": round(curr_v4, 2),
                "spread_alpha": alpha_spread,
                "v3_spread_alpha": v3_alpha_spread,
                "v4_spread_alpha": v4_alpha_spread,
            })

        return aligned

    def compare(self, period: str = "1Y") -> Dict[str, Any]:
        """Execute full comparative analysis across Strategy 1, 2, 3, and 4 for a given horizon."""
        clean_period = period.strip().upper()
        if clean_period not in ("1Y", "2Y", "3Y", "5Y"):
            clean_period = "1Y"

        v1_data = self.load_v1_results(clean_period)
        v2_data = self.load_v2_results(clean_period)
        v3_data = self.load_v3_results(clean_period)
        v4_data = self.load_v4_results(clean_period)

        v1_trades = v1_data.get("trades", [])
        v2_trades = v2_data.get("trades", [])
        v3_trades = v3_data.get("trades", [])
        v4_trades = v4_data.get("trades", [])

        v1_summary = v1_data.get("overall_summary", {})
        v2_summary = v2_data.get("overall_summary", {})
        v3_summary = v3_data.get("overall_summary", {})
        v4_summary = v4_data.get("overall_summary", {})

        # Trade matching and cohort categorization
        trade_deltas, category_metrics = self.match_trades(v1_trades, v2_trades)

        # Failure cause attribution for v1 losses
        failure_attribution = self.classify_v1_failures(v1_trades)

        # Aligned equity curves
        v2_equity_curve = v2_data.get("equity_curve", [])
        v3_equity_curve = v3_data.get("equity_curve", [])
        v4_equity_curve = v4_data.get("equity_curve", [])
        aligned_equity = self.build_aligned_equity(v1_trades, v2_equity_curve, v3_equity_curve, v4_equity_curve)

        # Differential Delta Metrics
        v1_wr = clean_float(v1_summary.get("win_rate_pct", 0.0))
        v2_wr = clean_float(v2_summary.get("win_rate_pct", 0.0))
        delta_wr = round(v2_wr - v1_wr, 1)

        v1_pf = clean_float(v1_summary.get("profit_factor", 0.0))
        v2_pf = clean_float(v2_summary.get("profit_factor", 0.0))
        delta_pf = round(v2_pf - v1_pf, 2)

        v1_dd = clean_float(v1_summary.get("max_drawdown_pct", 0.0))
        v2_dd = clean_float(v2_summary.get("max_drawdown_pct", 0.0))
        delta_dd_saved = round(v1_dd - v2_dd, 1)  # Positive means drawdown reduction / risk saved

        v1_avg_ret = clean_float(v1_summary.get("avg_return_pct", 0.0))
        v2_avg_ret = clean_float(v2_summary.get("avg_return_pct", 0.0))
        delta_avg_ret = round(v2_avg_ret - v1_avg_ret, 2)

        v1_avg_hold = clean_float(v1_summary.get("avg_holding_days", 0.0))
        v2_avg_hold = clean_float(v2_summary.get("avg_holding_days", 0.0))
        delta_avg_hold = round(v2_avg_hold - v1_avg_hold, 1)

        # v3 Key Metrics
        v3_wr = clean_float(v3_summary.get("win_rate_pct", 0.0))
        v3_pf = clean_float(v3_summary.get("profit_factor", 0.0))
        v3_dd = clean_float(v3_summary.get("max_drawdown_pct", 0.0))
        v3_avg_ret = clean_float(v3_summary.get("avg_return_pct", 0.0))

        # v4 Key Metrics
        v4_wr = clean_float(v4_summary.get("win_rate_pct", 0.0))
        v4_pf = clean_float(v4_summary.get("profit_factor", 0.0))
        v4_dd = clean_float(v4_summary.get("max_drawdown_pct", 0.0))
        v4_avg_ret = clean_float(v4_summary.get("avg_return_pct", 0.0))
        v4_avg_hold = clean_float(v4_summary.get("avg_holding_days", 0.0))

        v1_net_ret = clean_float(v1_summary.get("gross_profit_pct", 0.0) - v1_summary.get("gross_loss_pct", 0.0))
        v2_net_ret = clean_float(v2_summary.get("gross_profit_pct", 0.0) - v2_summary.get("gross_loss_pct", 0.0))
        v3_net_ret = clean_float(v3_summary.get("net_return_pct", 0.0)) or clean_float(v3_summary.get("gross_profit_pct", 0.0) - v3_summary.get("gross_loss_pct", 0.0))
        v4_net_ret = clean_float(v4_summary.get("net_return_pct", 0.0)) or clean_float(v4_summary.get("gross_profit_pct", 0.0) - v4_summary.get("gross_loss_pct", 0.0))

        summary_delta = {
            "period": clean_period,
            "win_rate_v1": v1_wr,
            "win_rate_v2": v2_wr,
            "win_rate_v3": v3_wr,
            "win_rate_v4": v4_wr,
            "delta_win_rate_pct": delta_wr,
            "profit_factor_v1": v1_pf,
            "profit_factor_v2": v2_pf,
            "profit_factor_v3": v3_pf,
            "profit_factor_v4": v4_pf,
            "delta_profit_factor": delta_pf,
            "max_drawdown_v1": v1_dd,
            "max_drawdown_v2": v2_dd,
            "max_drawdown_v3": v3_dd,
            "max_drawdown_v4": v4_dd,
            "delta_max_drawdown_saved_pct": delta_dd_saved,
            "avg_return_v1": v1_avg_ret,
            "avg_return_v2": v2_avg_ret,
            "avg_return_v3": v3_avg_ret,
            "avg_return_v4": v4_avg_ret,
            "delta_avg_return_pct": delta_avg_ret,
            "avg_holding_days_v1": v1_avg_hold,
            "avg_holding_days_v2": v2_avg_hold,
            "avg_holding_days_v4": v4_avg_hold,
            "delta_avg_holding_days": delta_avg_hold,
            "total_net_return_v1": v1_net_ret,
            "total_net_return_v2": v2_net_ret,
            "total_net_return_v3": v3_net_ret,
            "total_net_return_v4": v4_net_ret,
            "total_trades_v1": len(v1_trades),
            "total_trades_v2": len(v2_trades),
            "total_trades_v3": len(v3_trades),
            "total_trades_v4": len(v4_trades),
            "capital_preserved_loss_pct": category_metrics["capital_preserved_loss_pct"],
        }

        return {
            "period": clean_period,
            "summary_delta": summary_delta,
            "category_metrics": category_metrics,
            "failure_attribution": failure_attribution,
            "v1_summary": v1_summary,
            "v2_summary": v2_summary,
            "v3_summary": v3_summary,
            "v4_summary": v4_summary,
            "trade_deltas": trade_deltas,
            "aligned_equity": aligned_equity,
        }
