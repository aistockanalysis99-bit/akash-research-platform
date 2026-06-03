"""Virtual paper-trading portfolio.

A simple, conservative position manager wired to the AI pipeline:
- PM verdict APPROVE/RESIZE → auto-create a paper position
- Position sizing: (risk_pct × equity × size_factor) / stop_distance
- Initial stop: 8% below entry (placeholder until ATR wiring)
- Trailing stop: 10% below high-water mark, ratchets up only
- Refresh: re-fetch latest close per symbol, update P&L, check stop hit
- Close: manual or auto (stop hit)

All persistence is via SQLite — see engine/db/schema.py for the table.
"""
from __future__ import annotations

import asyncio
import logging
import sqlite3
from datetime import date, datetime
from typing import Any, Optional

from ..config import (
    VIRTUAL_INITIAL_CAPITAL, VIRTUAL_MAX_GROSS_PCT, VIRTUAL_RISK_PCT,
    VIRTUAL_STOP_PCT, VIRTUAL_TRAIL_PCT,
)
from . import settings as live_settings
from ..data.fmp_client import FMPClient
from ..db.schema import get_connection
from .schemas import PMDecision

log = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Public service
# --------------------------------------------------------------------------- #


class VirtualPortfolio:
    """Service for the paper-trading position ledger."""

    def __init__(self, conn: Optional[sqlite3.Connection] = None) -> None:
        self._conn = conn
        self._owns = conn is None

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = get_connection()
        return self._conn

    def close_conn(self) -> None:
        if self._owns and self._conn is not None:
            self._conn.close()
            self._conn = None

    # ------------------------------------------------------------------ #
    # Reads
    # ------------------------------------------------------------------ #

    def list_open(self) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM virtual_positions WHERE status='open' "
            "ORDER BY entry_date DESC, id DESC"
        ).fetchall()
        return [dict(r) for r in rows]

    def list_closed(self, limit: int = 200) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM virtual_positions WHERE status='closed' "
            "ORDER BY exit_date DESC, id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]

    def list_today(self, today_iso: Optional[str] = None) -> list[dict[str, Any]]:
        today = today_iso or date.today().isoformat()
        rows = self.conn.execute(
            "SELECT * FROM virtual_positions WHERE entry_date=? "
            "ORDER BY id DESC",
            (today,),
        ).fetchall()
        return [dict(r) for r in rows]

    def get(self, position_id: int) -> Optional[dict[str, Any]]:
        row = self.conn.execute(
            "SELECT * FROM virtual_positions WHERE id=?", (position_id,)
        ).fetchone()
        return dict(row) if row else None

    def equity_snapshot(self) -> dict[str, float]:
        """Real-account model (no fixed capital ceiling, no gross cap):

            account value = cash balance + market value of holdings

        Cash is an editable balance (buys deduct, sells add; may go negative).
        Cost basis / unrealized / realized are reporting lines.
        """
        closed = self.conn.execute(
            "SELECT COALESCE(SUM(final_pnl_usd), 0.0) AS total FROM virtual_positions "
            "WHERE status='closed'"
        ).fetchone()
        open_unrealized = self.conn.execute(
            "SELECT COALESCE(SUM(current_pnl_usd), 0.0) AS total FROM virtual_positions "
            "WHERE status='open'"
        ).fetchone()
        open_market_value = self.conn.execute(
            "SELECT COALESCE(SUM(units * current_price * COALESCE(multiplier, 1)), 0.0) "
            "AS total FROM virtual_positions "
            "WHERE status='open' AND current_price IS NOT NULL"
        ).fetchone()
        open_cost = self.conn.execute(
            "SELECT COALESCE(SUM(units * entry_price * COALESCE(multiplier, 1)), 0.0) "
            "AS total FROM virtual_positions WHERE status='open'"
        ).fetchone()
        open_count = self.conn.execute(
            "SELECT COUNT(*) AS n FROM virtual_positions WHERE status='open'"
        ).fetchone()

        realized = float(closed["total"] or 0.0)
        unrealized = float(open_unrealized["total"] or 0.0)
        mv = float(open_market_value["total"] or 0.0)
        cost_basis = float(open_cost["total"] or 0.0)
        cash = live_settings.get_cash_balance()
        equity = cash + mv
        invested_pct = (mv / equity * 100.0) if equity > 0 else 0.0
        total_return_pct = (unrealized / cost_basis * 100.0) if cost_basis > 0 else 0.0

        return {
            "equity": equity,                 # account value = cash + holdings
            "cash": cash,
            "open_market_value": mv,
            "cost_basis": cost_basis,
            "unrealized_pnl": unrealized,
            "realized_pnl": realized,
            "total_return_pct": total_return_pct,
            "gross_exposure_pct": invested_pct,
            "open_positions": int(open_count["n"] or 0),
            # legacy key (some callers read it); no longer a ceiling
            "initial_capital": cost_basis,
        }

    # ------------------------------------------------------------------ #
    # Position lifecycle
    # ------------------------------------------------------------------ #

    def has_open_for_symbol(self, symbol: str) -> bool:
        row = self.conn.execute(
            "SELECT 1 FROM virtual_positions WHERE symbol=? AND status='open' LIMIT 1",
            (symbol.upper(),),
        ).fetchone()
        return bool(row)

    def create_from_pm_decision(
        self,
        symbol: str,
        decision_date: str,
        pm: PMDecision,
        current_price: float,
    ) -> Optional[int]:
        """Create a paper position from a PM verdict. Returns position ID or None."""
        symbol = symbol.upper()

        if pm.decision not in ("APPROVE", "RESIZE"):
            return None
        if pm.recommended_size_pct <= 0:
            return None
        if current_price <= 0:
            log.warning("create_from_pm_decision: bad price for %s: %s", symbol, current_price)
            return None
        if self.has_open_for_symbol(symbol):
            log.info("Skipping paper position for %s — open position already exists", symbol)
            return None

        snap = self.equity_snapshot()
        equity = snap["equity"]
        current_mv = snap["open_market_value"]
        size_factor = pm.recommended_size_pct / 100.0  # APPROVE=1.0, RESIZE=0.5
        # Live settings — each call reads fresh from DB so UI tweaks take effect.
        risk_pct = live_settings.get_risk_pct()
        stop_pct = live_settings.get_stop_pct()
        max_gross_pct = live_settings.get_max_gross_pct()
        risk_usd = equity * risk_pct * size_factor
        stop_distance_usd = current_price * stop_pct
        units = max(round(risk_usd / stop_distance_usd, 4), 0.0)
        initial_stop = current_price * (1 - stop_pct)

        # ---- Gross exposure cap (default 100% — no leverage) ----
        max_gross_usd = max_gross_pct * equity
        room_usd = max(max_gross_usd - current_mv, 0.0)
        desired_notional = units * current_price

        if room_usd <= 0 or current_price <= 0:
            log.warning(
                "%s skipped: portfolio at gross exposure cap "
                "(%.1f%% / %.0f%% allowed)",
                symbol, current_mv / equity * 100.0,
                max_gross_pct * 100.0,
            )
            return None

        if desired_notional > room_usd:
            # Scale down to fit. Refuse if the resulting position is too tiny.
            min_position_usd = equity * 0.005  # 0.5% of equity — floor
            if room_usd < min_position_usd:
                log.warning(
                    "%s skipped: only $%.0f available under gross cap, "
                    "less than the $%.0f floor",
                    symbol, room_usd, min_position_usd,
                )
                return None
            scaled_units = round(room_usd / current_price, 4)
            log.info(
                "%s scaled to fit gross cap: %.4f → %.4f units "
                "($%.0f → $%.0f notional)",
                symbol, units, scaled_units, desired_notional, room_usd,
            )
            units = scaled_units

        now_iso = datetime.utcnow().isoformat()
        cur = self.conn.execute(
            """
            INSERT INTO virtual_positions
                (symbol, entry_date, entry_price, units, initial_stop,
                 current_price, high_water_mark, trailing_stop,
                 current_pnl_pct, current_pnl_usd, last_updated,
                 status, days_held,
                 decision_symbol, decision_date, decision_verdict,
                 decision_conviction, decision_size_pct,
                 created_at, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                symbol, decision_date, current_price, units, initial_stop,
                current_price, current_price, initial_stop,
                0.0, 0.0, now_iso,
                "open", 0,
                symbol, decision_date, pm.decision,
                pm.conviction_score, pm.recommended_size_pct,
                now_iso, None,
            ),
        )
        self.conn.commit()
        pos_id = cur.lastrowid
        log.info(
            "Created paper position #%d: %s %.2f units @ $%.2f, stop $%.2f (%s, conv %d)",
            pos_id, symbol, units, current_price, initial_stop,
            pm.decision, pm.conviction_score,
        )
        return pos_id

    def has_open_option(self, symbol: str, option_type: str, strike: float, expiry: str) -> bool:
        row = self.conn.execute(
            "SELECT 1 FROM virtual_positions WHERE symbol=? AND status='open' "
            "AND instrument_type='option' AND option_type=? AND strike=? AND expiry=? LIMIT 1",
            (symbol.upper(), option_type, strike, expiry[:10]),
        ).fetchone()
        return row is not None

    def import_position(
        self,
        symbol: str,
        shares: float,
        entry_price: float,
        entry_date: Optional[str] = None,
        current_price: Optional[float] = None,
        notes: Optional[str] = None,
        instrument_type: str = "stock",
        option_type: Optional[str] = None,
        strike: Optional[float] = None,
        expiry: Optional[str] = None,
    ) -> Optional[int]:
        """Import an EXISTING holding (stock or option) with its real cost basis.

        For stocks: shares + entry_price (per share).
        For options: `shares` = contracts, `entry_price` = premium per share,
        plus option_type/strike/expiry; multiplier is 100.
        `current_price` (live quote/premium) sets the mark; else marks at entry.
        """
        symbol = symbol.upper()
        is_option = instrument_type == "option"
        if shares <= 0 or entry_price <= 0:
            return None

        if is_option:
            if not (option_type and strike and expiry):
                return None
            option_type = "call" if option_type.lower().startswith("c") else "put"
            expiry = expiry[:10]
            if self.has_open_option(symbol, option_type, strike, expiry):
                log.info("import skipped — %s %s %s %s already held",
                         symbol, strike, option_type, expiry)
                return None
            multiplier = 100.0
        else:
            if self.has_open_for_symbol(symbol):
                log.info("import skipped — %s already held", symbol)
                return None
            multiplier = 1.0

        entry_date = (entry_date or date.today().isoformat())[:10]
        mark = current_price if (current_price and current_price > 0) else entry_price
        stop_pct = live_settings.get_stop_pct()
        initial_stop = entry_price * (1 - stop_pct)
        hwm = max(entry_price, mark)
        trail = max(initial_stop, hwm * (1 - live_settings.get_trail_pct()))
        pnl_usd = (mark - entry_price) * shares * multiplier
        pnl_pct = (mark / entry_price - 1) * 100.0
        try:
            days_held = (date.today() - date.fromisoformat(entry_date)).days
        except ValueError:
            days_held = 0
        now_iso = datetime.utcnow().isoformat()

        cur = self.conn.execute(
            """
            INSERT INTO virtual_positions
                (symbol, entry_date, entry_price, units, initial_stop,
                 current_price, high_water_mark, trailing_stop,
                 current_pnl_pct, current_pnl_usd, last_updated,
                 status, days_held,
                 decision_symbol, decision_date, decision_verdict,
                 decision_conviction, decision_size_pct,
                 created_at, notes,
                 instrument_type, option_type, strike, expiry, multiplier)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                symbol, entry_date, entry_price, round(shares, 4), initial_stop,
                mark, hwm, trail,
                pnl_pct, pnl_usd, now_iso,
                "open", days_held,
                symbol, entry_date, "IMPORTED",
                None, None,
                now_iso, notes or "imported holding",
                instrument_type, option_type, strike, expiry, multiplier,
            ),
        )
        self.conn.commit()
        pos_id = cur.lastrowid
        log.info("Imported #%d: %s %s", pos_id, symbol, instrument_type)
        return pos_id

    def add_to_position(self, position_id: int, usd_amount: float, price: float) -> bool:
        """Buy more of an existing holding; blend the cost basis (weighted avg)."""
        pos = self.get(position_id)
        if pos is None or pos["status"] != "open" or price <= 0 or usd_amount <= 0:
            return False
        add_units = usd_amount / price
        old_units = float(pos["units"])
        old_entry = float(pos["entry_price"])
        new_units = old_units + add_units
        new_entry = (old_units * old_entry + add_units * price) / new_units
        pnl_usd = (price - new_entry) * new_units
        pnl_pct = (price / new_entry - 1) * 100.0
        self.conn.execute(
            """
            UPDATE virtual_positions
            SET units=?, entry_price=?, current_price=?,
                current_pnl_usd=?, current_pnl_pct=?, last_updated=?
            WHERE id=?
            """,
            (round(new_units, 4), round(new_entry, 6), price,
             pnl_usd, pnl_pct, datetime.utcnow().isoformat(), position_id),
        )
        self.conn.commit()
        live_settings.set_cash_balance(live_settings.get_cash_balance() - usd_amount)
        log.info("Added $%.0f to #%d %s: %.4f → %.4f units, avg cost $%.2f",
                 usd_amount, position_id, pos["symbol"], old_units, new_units, new_entry)
        return True

    def trim_position(self, position_id: int, fraction: float, price: float) -> bool:
        """Sell `fraction` (0-1) of a holding at `price`. Realizes P&L on the
        sold portion as a closed 'trim' row; reduces the open units. If the
        whole thing is sold, closes it fully.
        """
        pos = self.get(position_id)
        if pos is None or pos["status"] != "open" or price <= 0:
            return False
        fraction = max(0.0, min(1.0, fraction))
        if fraction <= 0:
            return False
        if fraction >= 0.999:
            return self._do_close(pos, price, "manual") or True

        units = float(pos["units"])
        entry = float(pos["entry_price"])
        sell_units = round(units * fraction, 4)
        remaining = round(units - sell_units, 4)
        realized = (price - entry) * sell_units
        realized_pct = (price / entry - 1) * 100.0
        now_iso = datetime.utcnow().isoformat()
        today = date.today().isoformat()

        # Record the sold portion as a closed 'trim' row (flows into realized P&L).
        self.conn.execute(
            """
            INSERT INTO virtual_positions
                (symbol, entry_date, entry_price, units, initial_stop,
                 current_price, high_water_mark, trailing_stop,
                 current_pnl_pct, current_pnl_usd, last_updated, status, days_held,
                 exit_date, exit_price, exit_reason, final_pnl_usd, final_pnl_pct,
                 decision_symbol, decision_date, decision_verdict,
                 decision_conviction, decision_size_pct, created_at, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'closed', ?, ?, ?, 'trim', ?, ?,
                    ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                pos["symbol"], pos["entry_date"], entry, sell_units, pos["initial_stop"],
                price, pos.get("high_water_mark"), pos.get("trailing_stop"),
                realized_pct, realized, now_iso, pos.get("days_held", 0),
                today, price, realized, realized_pct,
                pos.get("decision_symbol"), pos.get("decision_date"), pos.get("decision_verdict"),
                pos.get("decision_conviction"), pos.get("decision_size_pct"),
                now_iso, f"trim {int(fraction*100)}% of #{position_id}",
            ),
        )
        # Reduce the open position.
        rem_pnl = (price - entry) * remaining
        rem_pnl_pct = (price / entry - 1) * 100.0
        self.conn.execute(
            """
            UPDATE virtual_positions
            SET units=?, current_price=?, current_pnl_usd=?, current_pnl_pct=?, last_updated=?
            WHERE id=?
            """,
            (remaining, price, rem_pnl, rem_pnl_pct, now_iso, position_id),
        )
        self.conn.commit()
        # Partial-sale proceeds flow back to cash.
        mult = float(pos.get("multiplier") or (100 if pos.get("instrument_type") == "option" else 1))
        live_settings.set_cash_balance(
            live_settings.get_cash_balance() + price * sell_units * mult
        )
        log.info("Trimmed %d%% of #%d %s: sold %.4f units, %.4f remain (realized $%.0f)",
                 int(fraction * 100), position_id, pos["symbol"], sell_units, remaining, realized)
        return True

    def manual_close(self, position_id: int, exit_reason: str = "manual") -> bool:
        """Close a position at its current last-known price (sync, no FMP fetch)."""
        pos = self.get(position_id)
        if pos is None or pos["status"] != "open":
            return False
        exit_price = pos.get("current_price") or pos["entry_price"]
        self._do_close(pos, float(exit_price), exit_reason)
        return True

    def close_all(self, exit_reason: str = "manual_close_all") -> int:
        """Close every open position at last-known price. Returns count closed."""
        rows = self.list_open()
        n = 0
        for pos in rows:
            exit_price = pos.get("current_price") or pos["entry_price"]
            self._do_close(pos, float(exit_price), exit_reason)
            n += 1
        return n

    async def refresh_all(self, fmp: Optional[FMPClient] = None) -> dict[str, Any]:
        """Re-fetch latest price for all open positions, update P&L, check stops.

        Returns a summary dict: how many refreshed, how many stop-hit, errors.
        """
        positions = self.list_open()
        if not positions:
            return {"refreshed": 0, "closed_by_stop": 0, "errors": []}

        own_fmp = fmp is None
        if own_fmp:
            fmp = FMPClient()
        try:
            return await self._refresh_with_client(positions, fmp)
        finally:
            if own_fmp and fmp is not None:
                await fmp.aclose()

    async def _refresh_with_client(
        self, positions: list[dict], fmp: FMPClient
    ) -> dict[str, Any]:
        # Fetch prices in parallel (cap concurrency to be polite).
        sem = asyncio.Semaphore(6)

        async def fetch_one(symbol: str) -> tuple[str, tuple[Optional[float], Optional[float]]]:
            """Return (latest_close, prev_close) so we can compute day change."""
            async with sem:
                try:
                    df = await fmp.fetch_daily(symbol)
                    if df is None or df.empty:
                        return symbol, (None, None)
                    last = float(df["close"].iloc[-1])
                    prev = float(df["close"].iloc[-2]) if len(df) >= 2 else None
                    return symbol, (last, prev)
                except Exception as e:  # noqa: BLE001
                    log.warning("price fetch failed for %s: %s", symbol, e)
                    return symbol, (None, None)

        stock_positions = [p for p in positions if (p.get("instrument_type") or "stock") != "option"]
        option_positions = [p for p in positions if (p.get("instrument_type") or "stock") == "option"]

        by_sym: dict[str, tuple] = {}
        if stock_positions:
            prices = await asyncio.gather(
                *[fetch_one(p["symbol"]) for p in stock_positions]
            )
            by_sym = dict(prices)

        # Option marks via Unusual Whales (per-contract live premium).
        opt_quotes: dict[int, Optional[float]] = {}
        if option_positions:
            from .data.unusual_whales import UnusualWhalesClient, UWError
            try:
                async with UnusualWhalesClient() as uw:
                    async def opt_one(p: dict) -> tuple[int, Optional[float]]:
                        try:
                            q = await uw.fetch_option_quote(
                                p["symbol"], p.get("expiry") or "",
                                float(p.get("strike") or 0),
                                p.get("option_type") or "call",
                            )
                            return p["id"], q
                        except Exception:  # noqa: BLE001
                            return p["id"], None
                    for pid, q in await asyncio.gather(*[opt_one(p) for p in option_positions]):
                        opt_quotes[pid] = q
            except UWError as e:
                log.warning("UW unavailable for option marks: %s", e)

        refreshed = 0
        closed_by_stop = 0
        errors: list[str] = []

        for pos in positions:
            is_option = (pos.get("instrument_type") or "stock") == "option"
            mult = float(pos.get("multiplier") or (100 if is_option else 1))
            entry = float(pos["entry_price"])
            units = float(pos["units"])
            days_held = (date.today() - date.fromisoformat(pos["entry_date"][:10])).days

            if is_option:
                new_price = opt_quotes.get(pos["id"])
                if new_price is None or new_price <= 0:
                    errors.append(f"no option mark for {pos['symbol']} (kept last)")
                    continue
                pnl_usd = (new_price - entry) * units * mult
                pnl_pct = (new_price / entry - 1) * 100.0 if entry else 0.0
                # Options don't use the stock trailing-stop auto-close.
                self.conn.execute(
                    """
                    UPDATE virtual_positions
                    SET current_price=?, current_pnl_usd=?, current_pnl_pct=?,
                        last_updated=?, days_held=?
                    WHERE id=?
                    """,
                    (new_price, pnl_usd, pnl_pct,
                     datetime.utcnow().isoformat(), days_held, pos["id"]),
                )
                refreshed += 1
                continue

            # --- Stock ---
            quote = by_sym.get(pos["symbol"]) or (None, None)
            new_price, prev_close = quote
            if new_price is None or new_price <= 0:
                errors.append(f"no price for {pos['symbol']}")
                continue

            day_change_pct = None
            if prev_close and prev_close > 0:
                day_change_pct = (new_price / prev_close - 1) * 100.0

            new_hwm = max(pos.get("high_water_mark") or entry, new_price)
            new_trail = max(
                float(pos["initial_stop"]),
                new_hwm * (1 - live_settings.get_trail_pct()),
            )
            pnl_usd = (new_price - entry) * units * mult
            pnl_pct = (new_price / entry - 1) * 100.0

            if new_price <= new_trail:
                fresh = self.get(pos["id"])
                if fresh is None or fresh["status"] != "open":
                    continue
                self._do_close(fresh, float(new_price), "stop_hit")
                closed_by_stop += 1
                continue

            self.conn.execute(
                """
                UPDATE virtual_positions
                SET current_price=?, high_water_mark=?, trailing_stop=?,
                    current_pnl_usd=?, current_pnl_pct=?,
                    prev_close=?, day_change_pct=?,
                    last_updated=?, days_held=?
                WHERE id=?
                """,
                (
                    new_price, new_hwm, new_trail,
                    pnl_usd, pnl_pct,
                    prev_close, day_change_pct,
                    datetime.utcnow().isoformat(), days_held,
                    pos["id"],
                ),
            )
            refreshed += 1

        self.conn.commit()
        # Record a daily equity snapshot so the value-over-time chart has data.
        self.record_equity_snapshot()
        return {
            "refreshed": refreshed,
            "closed_by_stop": closed_by_stop,
            "errors": errors,
        }

    # ------------------------------------------------------------------ #
    # Equity history + manual entry (broker-style features)
    # ------------------------------------------------------------------ #

    def record_equity_snapshot(self, snapshot_date: Optional[str] = None) -> None:
        """Upsert today's portfolio value into portfolio_equity_history."""
        snap = self.equity_snapshot()
        d = snapshot_date or date.today().isoformat()
        self.conn.execute(
            """
            INSERT INTO portfolio_equity_history
                (snapshot_date, equity, cash, market_value,
                 realized_pnl, unrealized_pnl, open_positions, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(snapshot_date) DO UPDATE SET
                equity=excluded.equity, cash=excluded.cash,
                market_value=excluded.market_value,
                realized_pnl=excluded.realized_pnl,
                unrealized_pnl=excluded.unrealized_pnl,
                open_positions=excluded.open_positions,
                updated_at=excluded.updated_at
            """,
            (
                d, snap["equity"], snap["cash"], snap["open_market_value"],
                snap["realized_pnl"], snap["unrealized_pnl"],
                snap["open_positions"], datetime.utcnow().isoformat(),
            ),
        )
        self.conn.commit()

    def equity_history(self, limit: int = 400) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM portfolio_equity_history "
            "ORDER BY snapshot_date ASC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]

    def create_manual(
        self, symbol: str, usd_amount: float, current_price: float,
        notes: Optional[str] = None,
    ) -> Optional[int]:
        """Manually buy `usd_amount` of `symbol` at `current_price`.

        Mirrors a broker market-buy: units = amount / price, stop at the
        configured stop %. Verdict tagged MANUAL.
        """
        symbol = symbol.upper()
        if current_price <= 0 or usd_amount <= 0:
            return None
        if self.has_open_for_symbol(symbol):
            log.info("manual buy skipped — %s already held", symbol)
            return None

        stop_pct = live_settings.get_stop_pct()
        units = round(usd_amount / current_price, 4)
        initial_stop = current_price * (1 - stop_pct)
        today = date.today().isoformat()
        now_iso = datetime.utcnow().isoformat()

        cur = self.conn.execute(
            """
            INSERT INTO virtual_positions
                (symbol, entry_date, entry_price, units, initial_stop,
                 current_price, high_water_mark, trailing_stop,
                 current_pnl_pct, current_pnl_usd, last_updated,
                 status, days_held,
                 decision_symbol, decision_date, decision_verdict,
                 decision_conviction, decision_size_pct,
                 created_at, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                symbol, today, current_price, units, initial_stop,
                current_price, current_price, initial_stop,
                0.0, 0.0, now_iso,
                "open", 0,
                symbol, today, "MANUAL",
                None, None,
                now_iso, notes or "manual buy",
            ),
        )
        self.conn.commit()
        # A new purchase spends cash (may go negative — no limit enforced).
        live_settings.set_cash_balance(live_settings.get_cash_balance() - usd_amount)
        pos_id = cur.lastrowid
        log.info("Manual buy #%d: %s %.4f units @ $%.2f ($%.0f)",
                 pos_id, symbol, units, current_price, usd_amount)
        return pos_id

    # ------------------------------------------------------------------ #
    # Internal
    # ------------------------------------------------------------------ #

    def _do_close(self, pos: dict, exit_price: float, exit_reason: str) -> None:
        mult = float(pos.get("multiplier") or (100 if (pos.get("instrument_type") == "option") else 1))
        final_pnl_usd = (exit_price - pos["entry_price"]) * pos["units"] * mult
        final_pnl_pct = (exit_price / pos["entry_price"] - 1) * 100.0
        days_held = (date.today() - date.fromisoformat(pos["entry_date"][:10])).days
        self.conn.execute(
            """
            UPDATE virtual_positions
            SET status='closed', exit_date=?, exit_price=?, exit_reason=?,
                final_pnl_usd=?, final_pnl_pct=?,
                current_price=?, current_pnl_usd=?, current_pnl_pct=?,
                last_updated=?, days_held=?
            WHERE id=?
            """,
            (
                date.today().isoformat(), exit_price, exit_reason,
                final_pnl_usd, final_pnl_pct,
                exit_price, final_pnl_usd, final_pnl_pct,
                datetime.utcnow().isoformat(), days_held,
                pos["id"],
            ),
        )
        self.conn.commit()
        # Sale proceeds flow back into the cash balance (units × exit × mult).
        proceeds = exit_price * float(pos["units"]) * mult
        live_settings.set_cash_balance(live_settings.get_cash_balance() + proceeds)
        log.info(
            "Closed paper position #%d: %s exit $%.2f, P&L $%.2f (%.2f%%), reason=%s",
            pos["id"], pos["symbol"], exit_price, final_pnl_usd, final_pnl_pct, exit_reason,
        )
        # Fire-and-forget Reflector in a background thread — best-effort, must
        # not block portfolio operations even if the LLM is slow or down.
        _spawn_reflection_for_position(pos["id"])


def _spawn_reflection_for_position(position_id: int) -> None:
    """Kick off a Reflector run in a background thread."""
    import asyncio
    import threading

    def _runner() -> None:
        try:
            from .agents.reflector import reflect_on_position
            from .memory import save_lesson
            # Reload the closed position row (its post-close state)
            vp = VirtualPortfolio()
            try:
                pos = vp.get(position_id)
            finally:
                vp.close_conn()
            if pos is None or pos.get("status") != "closed":
                return
            refl = asyncio.run(reflect_on_position(pos))
            if refl is not None:
                save_lesson(refl)
                log.info("reflector: lesson saved for position #%d (%s)",
                          position_id, refl.symbol)
        except Exception as e:  # noqa: BLE001
            log.warning("reflector background task crashed: %s", e)

    threading.Thread(target=_runner, daemon=True).start()


# --------------------------------------------------------------------------- #
# Convenience: fetch latest price for one symbol (used by ai_jobs auto-create)
# --------------------------------------------------------------------------- #


async def fetch_latest_close(symbol: str) -> Optional[float]:
    """Fetch the most recent daily-bar close for one symbol via FMP."""
    async with FMPClient() as fmp:
        try:
            df = await fmp.fetch_daily(symbol)
            if df is None or df.empty:
                return None
            return float(df["close"].iloc[-1])
        except Exception as e:  # noqa: BLE001
            log.warning("fetch_latest_close failed for %s: %s", symbol, e)
            return None
