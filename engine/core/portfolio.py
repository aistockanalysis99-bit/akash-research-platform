"""Portfolio book-keeping during a backtest: cash, positions, equity."""
from __future__ import annotations

import math
from datetime import datetime
from typing import Optional

from ..logging_setup import get_logger
from .types import (
    EquityPoint,
    ExitReason,
    Fill,
    Position,
    Trade,
)

log = get_logger("core.portfolio")


class Portfolio:
    """Tracks cash, open positions, fills, and produces equity curve & trades."""

    def __init__(self, initial_capital: float, commission_bps: float, slippage_bps: float):
        self.initial_capital = initial_capital
        self.cash = initial_capital
        self.commission_rate = commission_bps / 10_000.0
        self.slippage_rate = slippage_bps / 10_000.0
        self.positions: dict[str, Position] = {}
        self.trades: list[Trade] = []
        self.equity_curve: list[EquityPoint] = []
        self._open_fills: dict[str, list[Fill]] = {}  # by symbol, current open trade fills

    # ---------- Cost helpers ----------
    def _apply_buy_slippage(self, price: float) -> float:
        return price * (1.0 + self.slippage_rate)

    def _apply_sell_slippage(self, price: float) -> float:
        return price * (1.0 - self.slippage_rate)

    def _commission(self, qty: float, price: float) -> float:
        return abs(qty) * price * self.commission_rate

    # ---------- Entry / Add ----------
    def open_long(
        self,
        timestamp: datetime,
        symbol: str,
        qty: float,
        ref_price: float,        # bar's open price for fill
        atr_value: float,
        initial_stop_price: float,
        next_add_price: float,
    ) -> Optional[Position]:
        if qty <= 0 or ref_price <= 0:
            return None
        fill_price = self._apply_buy_slippage(ref_price)
        notional = qty * fill_price
        commission = self._commission(qty, fill_price)
        cost = notional + commission
        if cost > self.cash:
            # Reduce qty to fit available cash (round down)
            max_qty = max(0.0, (self.cash - commission) / fill_price)
            if max_qty < 1.0:
                return None
            qty = math.floor(max_qty)
            if qty <= 0:
                return None
            notional = qty * fill_price
            commission = self._commission(qty, fill_price)
            cost = notional + commission

        self.cash -= cost
        risk_dist = max(fill_price - initial_stop_price, 1e-9)
        pos = Position(
            symbol=symbol,
            qty=qty,
            avg_price=fill_price,
            entry_time=timestamp,
            initial_stop=initial_stop_price,
            initial_risk_dist=risk_dist,
            trail_high=fill_price,
            bars_in_trade=0,
            adds_done=0,
            next_add_price=next_add_price,
            partial_taken=False,
            mae=0.0,
            mfe=0.0,
        )
        slip = (fill_price - ref_price) * qty
        fill = Fill(
            timestamp=timestamp,
            symbol=symbol,
            qty=qty,
            price=fill_price,
            commission=commission,
            slippage=slip,
            reason="entry",
        )
        pos.fills.append(fill)
        self.positions[symbol] = pos
        self._open_fills[symbol] = [fill]
        log.debug("OPEN LONG %s qty=%.4f @ %.4f stop=%.4f", symbol, qty, fill_price, initial_stop_price)
        return pos

    def add_long(
        self,
        timestamp: datetime,
        symbol: str,
        add_qty: float,
        ref_price: float,
        next_add_price: float,
    ) -> bool:
        pos = self.positions.get(symbol)
        if pos is None or add_qty <= 0:
            return False
        fill_price = self._apply_buy_slippage(ref_price)
        commission = self._commission(add_qty, fill_price)
        cost = add_qty * fill_price + commission
        if cost > self.cash:
            return False
        self.cash -= cost
        # Recompute weighted average price; risk_dist stays based on initial stop relative to original entry
        new_qty = pos.qty + add_qty
        pos.avg_price = (pos.avg_price * pos.qty + fill_price * add_qty) / new_qty
        pos.qty = new_qty
        pos.adds_done += 1
        pos.next_add_price = next_add_price
        slip = (fill_price - ref_price) * add_qty
        fill = Fill(
            timestamp=timestamp, symbol=symbol, qty=add_qty,
            price=fill_price, commission=commission, slippage=slip, reason="add",
        )
        pos.fills.append(fill)
        self._open_fills[symbol].append(fill)
        return True

    # ---------- Exit ----------
    def close_partial_long(
        self,
        timestamp: datetime,
        symbol: str,
        qty_pct: int,
        ref_price: float,
        reason: str,
    ) -> Optional[Fill]:
        pos = self.positions.get(symbol)
        if pos is None or pos.partial_taken:
            return None
        sell_qty = pos.qty * (qty_pct / 100.0)
        if not _is_fractional_ok(sell_qty):
            sell_qty = math.floor(sell_qty)
        if sell_qty <= 0:
            return None
        fill_price = self._apply_sell_slippage(ref_price)
        commission = self._commission(sell_qty, fill_price)
        proceeds = sell_qty * fill_price - commission
        self.cash += proceeds
        pos.qty -= sell_qty
        pos.partial_taken = True
        slip = (ref_price - fill_price) * sell_qty
        fill = Fill(
            timestamp=timestamp, symbol=symbol, qty=-sell_qty,
            price=fill_price, commission=commission, slippage=slip, reason=reason,
        )
        pos.fills.append(fill)
        self._open_fills[symbol].append(fill)
        return fill

    def close_full_long(
        self,
        timestamp: datetime,
        symbol: str,
        ref_price: float,
        reason: ExitReason,
    ) -> Optional[Trade]:
        pos = self.positions.get(symbol)
        if pos is None:
            return None
        if pos.qty <= 0:
            self._cleanup_position(symbol)
            return None
        fill_price = self._apply_sell_slippage(ref_price)
        commission = self._commission(pos.qty, fill_price)
        proceeds = pos.qty * fill_price - commission
        self.cash += proceeds
        slip = (ref_price - fill_price) * pos.qty
        fill = Fill(
            timestamp=timestamp, symbol=symbol, qty=-pos.qty,
            price=fill_price, commission=commission, slippage=slip, reason=reason.value,
        )
        pos.fills.append(fill)
        self._open_fills[symbol].append(fill)

        # Construct Trade from all fills
        trade = self._make_trade(symbol, pos, fill, reason)
        self.trades.append(trade)
        self._cleanup_position(symbol)
        return trade

    def _make_trade(
        self,
        symbol: str,
        pos: Position,
        final_fill: Fill,
        reason: ExitReason,
    ) -> Trade:
        fills = self._open_fills.get(symbol, list(pos.fills))
        # Total bought
        bought_qty = sum(f.qty for f in fills if f.qty > 0)
        sold_qty = -sum(f.qty for f in fills if f.qty < 0)
        # Weighted avg entry/exit
        avg_entry = sum(f.qty * f.price for f in fills if f.qty > 0) / bought_qty if bought_qty > 0 else 0.0
        avg_exit = sum(-f.qty * f.price for f in fills if f.qty < 0) / sold_qty if sold_qty > 0 else 0.0
        gross = sum(-f.qty * f.price for f in fills)  # -qty*price: buys negative, sells positive
        commission = sum(f.commission for f in fills)
        pnl = gross - commission
        notional = avg_entry * bought_qty if bought_qty > 0 else 1.0
        pnl_pct = pnl / notional if notional > 0 else 0.0
        return Trade(
            symbol=symbol,
            entry_time=pos.entry_time,
            exit_time=final_fill.timestamp,
            entry_price=avg_entry,
            exit_price=avg_exit,
            qty=bought_qty,
            pnl=pnl,
            pnl_pct=pnl_pct,
            exit_reason=reason,
            bars_held=pos.bars_in_trade,
            mae=pos.mae,
            mfe=pos.mfe,
            commission_total=commission,
            fills=list(fills),
        )

    def _cleanup_position(self, symbol: str) -> None:
        self.positions.pop(symbol, None)
        self._open_fills.pop(symbol, None)

    # ---------- Mark-to-market ----------
    def mark_equity(self, timestamp: datetime, latest_close: dict[str, float]) -> EquityPoint:
        gross = 0.0
        for sym, pos in self.positions.items():
            px = latest_close.get(sym, pos.avg_price)
            gross += pos.qty * px
        equity = self.cash + gross
        ep = EquityPoint(
            timestamp=timestamp,
            equity=equity,
            cash=self.cash,
            gross_exposure=gross,
            open_positions=len(self.positions),
        )
        self.equity_curve.append(ep)
        return ep

    @property
    def current_equity(self) -> float:
        if self.equity_curve:
            return self.equity_curve[-1].equity
        return self.cash


def _is_fractional_ok(qty: float) -> bool:
    return qty == math.floor(qty)
