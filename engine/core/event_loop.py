"""Event-driven backtest engine.

Per-bar order of operations:
  1. Execute pending entry orders from previous bar at this bar's OPEN
  2. For each open position: check exits using bar's HIGH/LOW (intra-bar fill at level)
  3. For each open position: update trail_high, MAE, MFE, increment bars_in_trade
  4. Handle pyramid adds (using close)
  5. Compute new entry candidates from CLOSE-of-bar data
  6. Apply hybrid portfolio filter; queue them as pending for next bar's open
  7. Apply soft-exit decisions (decided at close, executed at next bar open)
  8. Mark equity at close

Look-ahead protection: signals at bar t use only data through close of t,
fills are at open of t+1.
"""
from __future__ import annotations

import math
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Optional

import pandas as pd

from ..core.portfolio import Portfolio
from ..core.types import (
    BacktestConfig,
    BacktestResult,
    EquityPoint,
    ExitReason,
    Position,
    RunStatus,
    StrategyParams,
    Trade,
)
from ..logging_setup import get_logger
from ..portfolio.hybrid import EntryCandidate, filter_candidates
from ..strategy.exits import (
    composite_stop_long,
    next_add_price_long,
    partial_tp_price_long,
    should_soft_exit_long,
)
from ..strategy.momentum_strategy import SymbolView, prepare_symbol_views
from ..strategy.signal import required_warmup_bars
from ..strategy.sizer import add_qty as sizer_add_qty
from ..strategy.sizer import initial_qty

log = get_logger("core.event_loop")


@dataclass
class PendingEntry:
    symbol: str
    qty: float
    initial_stop: float
    next_add_price: float
    score: float


@dataclass
class PendingSoftExit:
    symbol: str
    reason: str


ProgressCB = Optional[Callable[[int, int, datetime], None]]


def _build_timeline(views: dict[str, SymbolView]) -> list[pd.Timestamp]:
    """Sorted union of timestamps across all symbols."""
    if not views:
        return []
    all_ts = set()
    for v in views.values():
        all_ts.update(v.df["timestamp"].tolist())
    return sorted(all_ts)


def _row_at(view: SymbolView, ts: pd.Timestamp) -> Optional[pd.Series]:
    """Find the row for this exact timestamp in the symbol view. None if missing (holiday gap)."""
    df = view.df
    matches = df.index[df["timestamp"] == ts]
    if len(matches) == 0:
        return None
    return df.iloc[matches[0]]


def _build_bar_index(views: dict[str, SymbolView]) -> dict[str, dict[pd.Timestamp, int]]:
    """Pre-build a lookup: symbol -> {timestamp -> row_index} for fast access."""
    out = {}
    for sym, v in views.items():
        ts_to_idx = {ts: i for i, ts in enumerate(v.df["timestamp"].tolist())}
        out[sym] = ts_to_idx
    return out


def run_backtest(
    panel: dict[str, pd.DataFrame],
    config: BacktestConfig,
    progress_cb: ProgressCB = None,
    progress_every: int = 50,
) -> BacktestResult:
    """Run the backtest end-to-end. Returns a BacktestResult."""
    started_at = datetime.now(tz=timezone.utc)
    run_id = str(uuid.uuid4())
    run_name = config.run_name or _auto_run_name(config)

    p = config.params
    views = prepare_symbol_views(panel, p)
    if not views:
        return _empty_result(run_id, run_name, config, started_at, "No symbols had sufficient data.")

    timeline = _build_timeline(views)
    if not timeline:
        return _empty_result(run_id, run_name, config, started_at, "No timestamps in panel.")

    bar_idx_lookup = _build_bar_index(views)
    portfolio = Portfolio(
        initial_capital=config.initial_capital,
        commission_bps=p.commission_bps,
        slippage_bps=p.slippage_bps,
    )

    pending_entries: list[PendingEntry] = []
    pending_soft_exits: list[PendingSoftExit] = []
    warmup = required_warmup_bars(p)

    t_start = time.time()
    n_bars = len(timeline)
    last_progress_bar = -1

    for bar_i, ts in enumerate(timeline):
        # Build per-symbol bar dict
        bar_data: dict[str, pd.Series] = {}
        for sym, view in views.items():
            idx = bar_idx_lookup[sym].get(ts)
            if idx is not None:
                bar_data[sym] = view.df.iloc[idx]

        # ---------- 1. Execute pending entries at this bar's open ----------
        for pe in pending_entries:
            row = bar_data.get(pe.symbol)
            if row is None:
                continue
            ref_open = float(row["open"])
            if ref_open <= 0 or math.isnan(ref_open):
                continue
            portfolio.open_long(
                timestamp=ts.to_pydatetime() if hasattr(ts, "to_pydatetime") else ts,
                symbol=pe.symbol,
                qty=pe.qty,
                ref_price=ref_open,
                atr_value=0.0,
                initial_stop_price=pe.initial_stop,
                next_add_price=pe.next_add_price,
            )
        pending_entries = []

        # ---------- 1b. Execute pending soft exits at this bar's open ----------
        for pse in pending_soft_exits:
            row = bar_data.get(pse.symbol)
            if row is None:
                continue
            if pse.symbol not in portfolio.positions:
                continue
            ref_open = float(row["open"])
            reason_enum = ExitReason.TIME_EXIT if pse.reason == "time_exit" else ExitReason.SOFT_EXIT
            portfolio.close_full_long(
                timestamp=ts.to_pydatetime() if hasattr(ts, "to_pydatetime") else ts,
                symbol=pse.symbol,
                ref_price=ref_open,
                reason=reason_enum,
            )
        pending_soft_exits = []

        # ---------- 2. Check stops/TPs intra-bar (using high/low) ----------
        symbols_with_pos = list(portfolio.positions.keys())
        for sym in symbols_with_pos:
            pos = portfolio.positions.get(sym)
            if pos is None:
                continue
            row = bar_data.get(sym)
            if row is None:
                continue
            bar_high = float(row["high"])
            bar_low = float(row["low"])
            atr_value = float(row.get("atr", 0.0) or 0.0)

            stop_price = composite_stop_long(pos, atr_value, max(pos.trail_high, bar_high), p)

            stop_hit = bar_low <= stop_price
            tp_price = partial_tp_price_long(pos, p)
            tp_hit = (not pos.partial_taken) and p.enable_partial_tp and bar_high >= tp_price

            ts_py = ts.to_pydatetime() if hasattr(ts, "to_pydatetime") else ts

            if stop_hit and tp_hit:
                # Both hit on same bar → pessimistic: stop fills first, full close
                portfolio.close_full_long(ts_py, sym, stop_price, ExitReason.STOP)
            elif stop_hit:
                # Stop fires; full close at stop level (slippage applied inside)
                # Determine reason: trail vs initial stop
                if stop_price > pos.initial_stop:
                    reason = ExitReason.TRAIL
                else:
                    reason = ExitReason.STOP
                portfolio.close_full_long(ts_py, sym, stop_price, reason)
            elif tp_hit:
                # Partial TP at TP level
                portfolio.close_partial_long(ts_py, sym, p.partial_pct, tp_price, "partial_tp")

        # ---------- 3. Update remaining positions: trail_high, MAE/MFE, bars_in_trade ----------
        for sym, pos in list(portfolio.positions.items()):
            row = bar_data.get(sym)
            if row is None:
                continue
            close = float(row["close"])
            high = float(row["high"])
            low = float(row["low"])
            pos.trail_high = max(pos.trail_high, high)
            pos.bars_in_trade += 1
            unrealized = (close - pos.avg_price) * pos.qty
            if unrealized > pos.mfe:
                pos.mfe = unrealized
            if unrealized < pos.mae:
                pos.mae = unrealized

        # ---------- 4. Pyramid adds (at close of this bar) ----------
        if p.enable_scale_in:
            for sym, pos in list(portfolio.positions.items()):
                row = bar_data.get(sym)
                if row is None:
                    continue
                if pos.adds_done >= p.max_adds:
                    continue
                bull_state = bool(row.get("bull_state", False))
                if not bull_state:
                    continue
                close = float(row["close"])
                if close >= pos.next_add_price > 0:
                    atr_value = float(row.get("atr", 0.0) or 0.0)
                    initial_quantity_estimate = pos.qty / max(1, pos.adds_done + 1)  # rough
                    aq = sizer_add_qty(initial_quantity_estimate, p)
                    if aq <= 0:
                        continue
                    new_next = close + p.add_atr * atr_value
                    portfolio.add_long(
                        timestamp=ts.to_pydatetime() if hasattr(ts, "to_pydatetime") else ts,
                        symbol=sym,
                        add_qty=aq,
                        ref_price=close,
                        next_add_price=new_next,
                    )

        # ---------- 5. Compute entry candidates from close-of-bar ----------
        candidates: list[EntryCandidate] = []
        if bar_i >= warmup:
            for sym, row in bar_data.items():
                if sym in portfolio.positions:
                    continue
                if not bool(row.get("bull_state", False)):
                    continue
                if not bool(row.get("breakout_long", False)):
                    continue
                close = float(row["close"])
                atr_value = float(row.get("atr", 0.0) or 0.0)
                rv = float(row.get("rv", 0.0) or 0.0)
                # Use close as the reference for sizing; actual fill happens at next open
                qty = initial_qty(portfolio.current_equity, close, atr_value, rv, p)
                if qty <= 0:
                    continue
                score = float(row.get("mom_score", 0.0) or 0.0)
                candidates.append(EntryCandidate(
                    symbol=sym, score=score, ref_price=close,
                    atr_value=atr_value, realized_vol=rv,
                    initial_qty_proposed=qty,
                ))

        # ---------- 6. Filter via hybrid portfolio layer ----------
        accepted = filter_candidates(candidates, portfolio.positions, portfolio.current_equity, p)
        for c in accepted:
            row = bar_data[c.symbol]
            close = float(row["close"])
            atr_value = float(row.get("atr", 0.0) or 0.0)
            initial_stop_price = close - p.stop_atr * atr_value
            next_add = next_add_price_long(close, atr_value, p)
            pending_entries.append(PendingEntry(
                symbol=c.symbol,
                qty=c.initial_qty_proposed,
                initial_stop=initial_stop_price,
                next_add_price=next_add,
                score=c.score,
            ))

        # ---------- 7. Soft-exit decisions (executed next bar) ----------
        for sym, pos in list(portfolio.positions.items()):
            row = bar_data.get(sym)
            if row is None:
                continue
            mom = row.get("mom_score")
            mom_val = float(mom) if mom is not None and not (isinstance(mom, float) and math.isnan(mom)) else None
            ema_slow = row.get("ema_slow")
            ema_slow_val = float(ema_slow) if ema_slow is not None and not (isinstance(ema_slow, float) and math.isnan(ema_slow)) else None
            close_v = float(row["close"])
            should_exit, reason = should_soft_exit_long(pos, mom_val, ema_slow_val, close_v, p)
            if should_exit:
                pending_soft_exits.append(PendingSoftExit(symbol=sym, reason=reason))

        # ---------- 8. Mark equity ----------
        latest_close = {sym: float(bar_data[sym]["close"]) for sym in bar_data}
        portfolio.mark_equity(ts.to_pydatetime() if hasattr(ts, "to_pydatetime") else ts, latest_close)

        # Progress
        if progress_cb is not None and (bar_i - last_progress_bar) >= progress_every:
            progress_cb(bar_i + 1, n_bars, ts.to_pydatetime() if hasattr(ts, "to_pydatetime") else ts)
            last_progress_bar = bar_i

    # Close any remaining open positions at the last close
    if portfolio.positions:
        last_ts = timeline[-1]
        last_ts_py = last_ts.to_pydatetime() if hasattr(last_ts, "to_pydatetime") else last_ts
        for sym in list(portfolio.positions.keys()):
            view = views[sym]
            last_row_idx = bar_idx_lookup[sym].get(last_ts)
            if last_row_idx is None:
                # Use that symbol's last row
                last_row = view.df.iloc[-1]
            else:
                last_row = view.df.iloc[last_row_idx]
            portfolio.close_full_long(
                timestamp=last_ts_py,
                symbol=sym,
                ref_price=float(last_row["close"]),
                reason=ExitReason.END_OF_BACKTEST,
            )

    finished_at = datetime.now(tz=timezone.utc)
    elapsed = time.time() - t_start
    log.info("Backtest %s done: %d bars, %d trades, %.2fs", run_name, n_bars, len(portfolio.trades), elapsed)

    # Compute metrics (deferred import to avoid cycles)
    from ..metrics.compute import compute_all_metrics

    metrics = compute_all_metrics(portfolio.equity_curve, portfolio.trades, config)
    per_symbol_stats = _per_symbol_stats(portfolio.trades, config.universe)

    return BacktestResult(
        run_id=run_id,
        run_name=run_name,
        config=config,
        equity_curve=portfolio.equity_curve,
        trades=portfolio.trades,
        metrics=metrics,
        per_symbol_stats=per_symbol_stats,
        started_at=started_at,
        finished_at=finished_at,
        status=RunStatus.DONE,
    )


def _auto_run_name(config: BacktestConfig) -> str:
    """Format: YYYY-MM-DD_<sig>_<years>y_<tf>"""
    sig = config.params.signature()
    days = (config.end_date - config.start_date).days
    years = max(1, round(days / 365))
    tag = f"{years}y"
    return f"{datetime.now().strftime('%Y-%m-%d_%H%M')}_{sig}_{tag}_{config.timeframe}"


def _empty_result(
    run_id: str,
    run_name: str,
    config: BacktestConfig,
    started_at: datetime,
    msg: str,
) -> BacktestResult:
    return BacktestResult(
        run_id=run_id,
        run_name=run_name,
        config=config,
        equity_curve=[],
        trades=[],
        metrics={},
        per_symbol_stats=[],
        started_at=started_at,
        finished_at=datetime.now(tz=timezone.utc),
        status=RunStatus.FAILED,
        error_message=msg,
    )


def _per_symbol_stats(trades: list[Trade], universe: list[str]) -> list[dict]:
    by_sym: dict[str, list[Trade]] = {}
    for t in trades:
        by_sym.setdefault(t.symbol, []).append(t)
    out = []
    for sym in universe:
        ts = by_sym.get(sym, [])
        if not ts:
            continue
        wins = [t for t in ts if t.pnl > 0]
        total_pnl = sum(t.pnl for t in ts)
        out.append({
            "symbol": sym,
            "trades": len(ts),
            "wins": len(wins),
            "win_rate": (len(wins) / len(ts)) if ts else 0.0,
            "total_pnl": total_pnl,
            "avg_pnl": total_pnl / len(ts) if ts else 0.0,
            "best_trade": max((t.pnl for t in ts), default=0.0),
            "worst_trade": min((t.pnl for t in ts), default=0.0),
        })
    out.sort(key=lambda d: d["total_pnl"], reverse=True)
    return out
