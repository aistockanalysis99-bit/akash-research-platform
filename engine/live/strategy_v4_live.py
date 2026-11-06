"""Deterministic Strategy 4 pre-market dry scanner.

Phase 2 creates auditable DRAFT intents only. It never submits broker orders.
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Protocol, Sequence

import numpy as np
import pandas as pd

from ..config import AutoTradeConfig, PROJECT_ROOT, load_auto_trade_config
from ..simulator_engine import PointInTimeEngine, PointInTimeSetup
from ..earnings_calendar import EarningsCalendar
from ..db.schema import init_db
from ..strategy_v4_engine import (
    StrategyV4Config,
    evaluate_strategy_v4_entry,
)
from . import auto_trade_repo as repo
from .alpaca import (
    AccountSnapshot,
    AlpacaPaperClient,
    AssetSnapshot,
    BrokerCollection,
    MarketClock,
)


class ReadOnlyBroker(Protocol):
    def get_account(self) -> AccountSnapshot: ...
    def get_clock(self) -> MarketClock: ...
    def get_calendar(self, start: date | str | None = None, end: date | str | None = None) -> BrokerCollection: ...
    def get_asset(self, symbol: str) -> AssetSnapshot: ...
    def get_bars(self, symbol: str, **kwargs: Any) -> BrokerCollection: ...
    def get_latest_quote(self, symbol: str, **kwargs: Any) -> Mapping[str, Any]: ...
    def list_orders(self, status: str = "all", limit: int = 500) -> BrokerCollection: ...
    def list_positions(self) -> BrokerCollection: ...
    def get_portfolio_history(
        self, *, period: str = "1M", timeframe: str = "1D",
    ) -> Mapping[str, Any]: ...


class DryScanError(RuntimeError):
    pass


@dataclass(frozen=True)
class MarketSessionContext:
    observed_at: datetime
    session_date: date
    data_cutoff_date: date
    next_open: datetime
    next_close: datetime
    early_close: bool
    trading_dates: tuple[date, ...] = ()
    market_is_open: bool = False


def canonical_hash(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(encoded).hexdigest()


def strategy_config_hash(config: StrategyV4Config) -> str:
    return canonical_hash(asdict(config))


def _chart_snapshot(
    frame: pd.DataFrame,
    setup: PointInTimeSetup,
    cutoff: date,
    lookback_days: int,
) -> dict[str, Any]:
    """Persist the exact bars and spread model used for the scan decision."""
    prices = frame["Adj Close"][[setup.ticker_a, setup.ticker_b]].dropna().tail(lookback_days)
    bars: list[dict[str, Any]] = []
    for stamp, row in prices.iterrows():
        price_a = float(row[setup.ticker_a])
        price_b = float(row[setup.ticker_b])
        spread = price_a - setup.hedge_ratio * price_b
        z_score = (
            (spread - setup.spread_mean) / setup.spread_std
            if setup.spread_std > 1e-12 else 0.0
        )
        bars.append({
            "date": pd.Timestamp(stamp).date().isoformat(),
            "price_a": round(price_a, 4),
            "price_b": round(price_b, 4),
            "spread": round(spread, 6),
            "z_score": round(float(z_score), 6),
        })
    return {
        "ticker_a": setup.ticker_a,
        "ticker_b": setup.ticker_b,
        "current_date": cutoff.isoformat(),
        "reveal": False,
        "setup": setup.to_dict(),
        "historical_bars": bars,
        "forward_bars": None,
        "forward_outcome": None,
        "source": "strategy_v4_scan_snapshot",
    }


def _rejection_details(
    reason: str,
    payload: Mapping[str, Any],
    config: StrategyV4Config,
) -> list[dict[str, str]]:
    """Explain every rejection with measured and required values."""
    actuals: dict[str, tuple[str, str, str]] = {
        "adf_stationarity": (
            f"{float(payload.get('adf_tstat', 0)):.3f}", "≤ -2.800",
            "The spread did not demonstrate strong enough mean-reverting stationarity.",
        ),
        "cointegration_pvalue": (
            f"{float(payload.get('adf_pvalue', 1)):.4f}", "≤ 0.0500",
            "The probability of a non-stationary relationship is above the allowed level.",
        ),
        "correlation": (
            f"{float(payload.get('correlation', 0)):.3f}", "≥ 0.850",
            "The two stocks are not moving together closely enough for this pair model.",
        ),
        "r_squared": (
            f"{float(payload.get('r_squared', 0)):.3f}", "≥ 0.350",
            "The hedge regression explains too little of the relationship between the stocks.",
        ),
        "half_life_reversion": (
            f"{float(payload.get('half_life_days', 0)):.1f} days", "2.0–35.0 days",
            "The estimated reversion speed is outside the strategy's usable holding range.",
        ),
        "zero_crossings": (
            str(int(payload.get('zero_crossings', 0))), "≥ 6",
            "The spread has not crossed its mean often enough to prove repeatable reversion.",
        ),
        "spread_tightness": (
            f"{float(payload.get('spread_vol_pct', 0)):.2f}%", "≤ 7.00%",
            "The spread is too volatile for a stable paired position.",
        ),
    }
    details: list[dict[str, str]] = []
    if reason == "GAUNTLET_FAILED":
        for check in payload.get("failed_checks", []):
            actual, required, explanation = actuals.get(
                str(check), ("Failed", "Must pass", "This econometric requirement was not met."))
            details.append({"rule": str(check), "actual": actual,
                            "required": required, "explanation": explanation})
        return details

    z_abs = abs(float(payload.get("z_score", 0)))
    rules: dict[str, tuple[str, str, str]] = {
        "ENTRY_Z_BELOW_HURDLE": (
            f"|Z| = {z_abs:.2f}σ", f"≥ {config.z_score_entry_hurdle:.2f}σ",
            "The price spread has not diverged far enough to create a Strategy 4 entry.",
        ),
        "ENTRY_Z_ABOVE_MAX": (
            f"|Z| = {z_abs:.2f}σ", f"< {config.z_score_entry_max:.2f}σ",
            "The divergence is beyond the safe entry cap and may indicate a structural break.",
        ),
        "MOMENTUM_NOT_FLATTENING": (
            f"ΔZ = {float(payload.get('momentum_slope', 0)):.3f}σ",
            f"≤ {config.max_entry_momentum_slope:.3f}σ or reversing",
            "The spread is still moving away from its mean, so the falling-knife guard blocked entry.",
        ),
        "SPREAD_VOLATILITY_CAP": (
            f"{float(payload.get('spread_vol_pct', 0)):.2f}%",
            f"≤ {config.max_allowed_spread_vol_pct:.2f}%",
            "Spread volatility is above the Strategy 4 safety cap.",
        ),
        "VIX_PANIC_FREEZE": (
            f"{float(payload.get('market_vol_pct', 0)):.2f}",
            f"≤ {config.vix_panic_threshold:.2f}",
            "The macro-volatility overlay freezes new entries in a panic regime.",
        ),
        "EARNINGS_BLACKOUT": (
            str(payload.get("earnings_blackout_reason") or "Earnings window"),
            "Outside the configured earnings blackout",
            "Company earnings can break the historical pair relationship, so entry is blocked.",
        ),
        "PREVIOUS_Z_UNAVAILABLE": (
            "Previous Z unavailable", "Two consecutive valid Z observations",
            "Strategy 4 could not confirm that divergence momentum is flattening or reversing.",
        ),
        "PAIR_DATA_UNAVAILABLE": (
            "Insufficient aligned bars", f"≥ {config.lookback_days} valid daily bars",
            "The pair cannot be evaluated reliably without a complete aligned price history.",
        ),
        "BROKER_MARKET_DATA_UNAVAILABLE": (
            "Broker data request failed", "Fresh Alpaca asset and quote data",
            "Execution eligibility could not be verified, so the trade failed closed.",
        ),
    }
    actual, required, explanation = rules.get(
        reason,
        (reason.replace("_", " ").title(), "All execution and risk checks must pass",
         "A Strategy 4 execution or portfolio safety rule prevented this trade."),
    )
    return [{"rule": reason, "actual": actual, "required": required,
             "explanation": explanation}]


def load_elite_pairs(path: Path | None = None) -> list[dict[str, Any]]:
    source = path or PROJECT_ROOT / "elite_curated_pairs.json"
    payload = json.loads(source.read_text(encoding="utf-8"))
    pairs = payload.get("pairs", payload) if isinstance(payload, dict) else payload
    if not isinstance(pairs, list):
        raise DryScanError("elite pair universe is invalid")
    return [p for p in pairs if isinstance(p, dict) and p.get("ticker_a") and p.get("ticker_b")]


def resolve_market_session(clock: MarketClock, calendar: Sequence[Mapping[str, Any]]) -> MarketSessionContext:
    observed = pd.Timestamp(clock.timestamp).to_pydatetime()
    next_open = pd.Timestamp(clock.next_open).to_pydatetime()
    next_close = pd.Timestamp(clock.next_close).to_pydatetime()
    session_date = observed.date() if clock.is_open else next_open.date()
    rows = sorted(calendar, key=lambda row: str(row.get("date", "")))
    dates = [pd.Timestamp(str(row["date"])).date() for row in rows if row.get("date")]
    previous = [d for d in dates if d < session_date]
    if not previous:
        raise DryScanError("market calendar does not contain a completed prior session")
    target_row = next((row for row in rows if str(row.get("date"))[:10] == session_date.isoformat()), {})
    close_text = str(target_row.get("close", "16:00"))
    early_close = close_text not in ("16:00", "1600")
    return MarketSessionContext(
        observed_at=observed,
        session_date=session_date,
        data_cutoff_date=max(previous),
        next_open=next_open,
        next_close=next_close,
        early_close=early_close,
        trading_dates=tuple(dates),
        market_is_open=clock.is_open,
    )


def _normalize_bar_frame(frame: pd.DataFrame, cutoff: date, min_bars: int) -> pd.DataFrame:
    if frame.empty:
        raise DryScanError("EMPTY_BARS")
    result = frame.copy()
    result.index = pd.to_datetime(result.index, utc=True).tz_convert(None).normalize()
    if result.index.has_duplicates:
        raise DryScanError("DUPLICATE_BARS")
    if not result.index.is_monotonic_increasing:
        raise DryScanError("NON_MONOTONIC_BARS")
    result = result.sort_index()
    result = result[result.index <= pd.Timestamp(cutoff)]
    if len(result) < min_bars:
        raise DryScanError("INSUFFICIENT_BARS")
    if result.index[-1].date() != cutoff:
        raise DryScanError("STALE_DAILY_BARS")
    required = ("Open", "High", "Low", "Close", "Adj Close")
    if any(col not in result for col in required):
        raise DryScanError("MISSING_OHLC_FIELDS")
    values = result[list(required)].to_numpy(dtype=float)
    if not np.isfinite(values).all() or (values <= 0).any():
        raise DryScanError("INVALID_OHLC_VALUES")
    if (result["Adj Close"].pct_change().abs() > 0.45).any():
        raise DryScanError("SPLIT_LIKE_DISCONTINUITY")
    return result


def validate_market_frame(
    frame: pd.DataFrame,
    symbols: Iterable[str],
    cutoff: date,
    min_bars: int,
) -> pd.DataFrame:
    if not isinstance(frame.columns, pd.MultiIndex):
        raise DryScanError("MARKET_FRAME_REQUIRES_MULTIINDEX_COLUMNS")
    clean: dict[tuple[str, str], pd.Series] = {}
    errors: list[str] = []
    for symbol in sorted(set(symbols)):
        cols: dict[str, pd.Series] = {}
        for field in ("Open", "High", "Low", "Close", "Adj Close", "Volume"):
            key = (field, symbol)
            if key in frame.columns:
                cols[field] = frame[key]
        try:
            normalized = _normalize_bar_frame(pd.DataFrame(cols), cutoff, min_bars)
        except DryScanError as exc:
            errors.append(f"{symbol}:{exc}")
            continue
        for field in normalized.columns:
            clean[(field, symbol)] = normalized[field]
    if errors:
        raise DryScanError(";".join(errors))
    result = pd.DataFrame(clean)
    result.columns = pd.MultiIndex.from_tuples(result.columns)
    return result.sort_index()


def _frame_from_alpaca(
    broker: ReadOnlyBroker,
    symbols: Iterable[str],
    context: MarketSessionContext,
    min_bars: int,
) -> pd.DataFrame:
    start = context.data_cutoff_date - timedelta(days=max(220, min_bars * 3))
    columns: dict[tuple[str, str], pd.Series] = {}
    for symbol in sorted(set(symbols)):
        rows = broker.get_bars(
            symbol,
            timeframe="1Day",
            start=start.isoformat(),
            end=(context.data_cutoff_date + timedelta(days=1)).isoformat(),
            limit=1000,
            feed="iex",
        ).items
        records = []
        for row in rows:
            records.append({
                "timestamp": row.get("t"), "Open": row.get("o"),
                "High": row.get("h"), "Low": row.get("l"),
                "Close": row.get("c"), "Adj Close": row.get("c"),
                "Volume": row.get("v", 0),
            })
        symbol_frame = pd.DataFrame(records)
        if symbol_frame.empty:
            raise DryScanError(f"{symbol}:EMPTY_BARS")
        symbol_frame = symbol_frame.set_index("timestamp")
        for field in symbol_frame.columns:
            columns[(field, symbol)] = symbol_frame[field]
    frame = pd.DataFrame(columns)
    frame.columns = pd.MultiIndex.from_tuples(frame.columns)
    return validate_market_frame(frame, symbols, context.data_cutoff_date, min_bars)


def _quote_mid_and_time(quote: Mapping[str, Any]) -> tuple[float, datetime]:
    try:
        bid = float(quote["bp"])
        ask = float(quote["ap"])
        stamp = pd.Timestamp(quote["t"]).to_pydatetime()
    except (KeyError, TypeError, ValueError) as exc:
        raise DryScanError("INVALID_QUOTE") from exc
    if bid <= 0 or ask <= 0 or ask < bid:
        raise DryScanError("INVALID_QUOTE")
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return (bid + ask) / 2.0, stamp


def _previous_z(frame: pd.DataFrame, setup: PointInTimeSetup) -> float | None:
    history = frame.loc[:pd.Timestamp(setup.target_date)]
    if len(history) < 2 or setup.spread_std <= 0:
        return None
    previous = history.iloc[-2]
    pa = previous.get(("Adj Close", setup.ticker_a), previous.get(("Close", setup.ticker_a)))
    pb = previous.get(("Adj Close", setup.ticker_b), previous.get(("Close", setup.ticker_b)))
    if pa is None or pb is None or not np.isfinite([pa, pb]).all():
        return None
    return float((pa - setup.hedge_ratio * pb - setup.spread_mean) / setup.spread_std)


def _market_volatility(frame: pd.DataFrame) -> float:
    field = "Adj Close" if "Adj Close" in frame.columns.get_level_values(0) else "Close"
    returns = frame[field].pct_change().mean(axis=1)
    value = returns.rolling(20).std().iloc[-1] * np.sqrt(252) * 100.0
    return 15.0 if not np.isfinite(value) else float(value)


def _current_drawdown_pct(history: Mapping[str, Any], current_equity: float) -> float:
    values = []
    for raw_value in history.get("equity", []):
        try:
            value = float(raw_value)
        except (TypeError, ValueError):
            continue
        if math.isfinite(value) and value > 0:
            values.append(value)
    if current_equity > 0 and math.isfinite(current_equity):
        values.append(current_equity)
    if not values:
        return 0.0
    peak = max(values)
    return max(0.0, (peak - current_equity) / peak * 100.0)


class StrategyV4DryScanner:
    def __init__(
        self,
        *,
        broker: ReadOnlyBroker | None = None,
        auto_config: AutoTradeConfig | None = None,
        strategy_config: StrategyV4Config | None = None,
        earnings_calendar: EarningsCalendar | None = None,
    ) -> None:
        self.auto_config = auto_config or load_auto_trade_config()
        self.strategy_config = strategy_config or StrategyV4Config.load()
        self.broker = broker or AlpacaPaperClient(self.auto_config)
        self.earnings_calendar = earnings_calendar or EarningsCalendar()

    def resolve_context(self) -> MarketSessionContext:
        clock = self.broker.get_clock()
        observed = pd.Timestamp(clock.timestamp).date()
        next_date = pd.Timestamp(clock.next_open).date()
        rows = self.broker.get_calendar(
            observed - timedelta(days=14), next_date + timedelta(days=45)
        ).items
        return resolve_market_session(clock, rows)

    def run(self, pairs: Sequence[Mapping[str, Any]] | None = None) -> dict[str, Any]:
        init_db()
        context = self.resolve_context()
        if context.market_is_open:
            raise DryScanError("MARKET_ALREADY_OPEN")
        if context.observed_at.date() != context.session_date:
            raise DryScanError("NO_PREMARKET_SESSION_TODAY")
        universe = list(pairs or load_elite_pairs())
        symbols = {
            str(pair[key]).strip().upper().replace(".", "-")
            for pair in universe for key in ("ticker_a", "ticker_b")
        }
        frame = _frame_from_alpaca(
            self.broker, symbols, context, self.strategy_config.lookback_days)
        account = self.broker.get_account()
        history = self.broker.get_portfolio_history(period="1M", timeframe="1D")
        return self.run_frozen(
            frame=frame,
            pairs=universe,
            context=context,
            current_drawdown_pct=_current_drawdown_pct(history, account.equity),
        )

    def run_frozen(
        self,
        *,
        frame: pd.DataFrame,
        pairs: Sequence[Mapping[str, Any]],
        context: MarketSessionContext,
        market_vol_pct: float | None = None,
        current_drawdown_pct: float = 0.0,
    ) -> dict[str, Any]:
        symbols = {
            str(pair[key]).strip().upper().replace(".", "-")
            for pair in pairs for key in ("ticker_a", "ticker_b")
        }
        clean_frame = validate_market_frame(
            frame, symbols, context.data_cutoff_date, self.strategy_config.lookback_days)
        cfg_hash = strategy_config_hash(self.strategy_config)
        resolved_market_vol_pct = (
            _market_volatility(clean_frame)
            if market_vol_pct is None else float(market_vol_pct)
        )
        ordered_frame = clean_frame.sort_index().sort_index(axis=1)
        frame_fingerprint = hashlib.sha256(
            pd.util.hash_pandas_object(ordered_frame, index=True).values.tobytes()
        ).hexdigest()
        universe_fingerprint = canonical_hash([
            dict(sorted(dict(pair).items()))
            for pair in sorted(
                pairs,
                key=lambda item: (str(item.get("ticker_a")), str(item.get("ticker_b"))),
            )
        ])
        risk_fingerprint = canonical_hash({
            "max_open_pairs": self.auto_config.max_open_pairs,
            "max_new_pairs_per_day": self.auto_config.max_new_pairs_per_day,
            "pair_capital_pct": self.auto_config.pair_capital_pct,
            "max_gross_exposure_pct": self.auto_config.max_gross_exposure_pct,
            "max_quote_age_seconds": self.auto_config.max_quote_age_seconds,
            "max_premarket_gap_pct": self.auto_config.max_premarket_gap_pct,
        })
        run_id = "v4-dry-" + canonical_hash({
            "session": context.session_date.isoformat(),
            "cutoff": context.data_cutoff_date.isoformat(),
            "config": cfg_hash,
            "data": frame_fingerprint,
            "universe": universe_fingerprint,
            "risk": risk_fingerprint,
            "market_vol_pct": round(resolved_market_vol_pct, 8),
            "current_drawdown_pct": round(float(current_drawdown_pct), 8),
            "snapshot_contract": 3,
        })[:24]
        claimed, status = repo.claim_run(
            run_id,
            session_date=context.session_date.isoformat(),
            config_hash=cfg_hash,
        )
        if not claimed:
            existing = repo.get_run_bundle(run_id)
            if existing and status == "complete":
                existing["idempotent_replay"] = True
                return existing
            raise DryScanError(f"dry scan {run_id} is already {status}")

        try:
            result = self._evaluate(
                run_id=run_id,
                frame=clean_frame,
                pairs=pairs,
                context=context,
                config_hash=cfg_hash,
                market_vol_pct=resolved_market_vol_pct,
                current_drawdown_pct=float(current_drawdown_pct),
            )
            repo.complete_run(run_id, result["summary"])
            bundle = repo.get_run_bundle(run_id)
            assert bundle is not None
            bundle["idempotent_replay"] = False
            return bundle
        except Exception as exc:
            safe_message = (
                str(exc) if isinstance(exc, DryScanError)
                else "Internal Strategy 4 dry scan failure"
            )
            repo.fail_run(run_id, type(exc).__name__, safe_message)
            raise

    def _evaluate(
        self,
        *,
        run_id: str,
        frame: pd.DataFrame,
        pairs: Sequence[Mapping[str, Any]],
        context: MarketSessionContext,
        config_hash: str,
        market_vol_pct: float,
        current_drawdown_pct: float,
    ) -> dict[str, Any]:
        pit = PointInTimeEngine(
            df=frame,
            pairs=[dict(pair) for pair in pairs],
            default_lookback=self.strategy_config.lookback_days,
        )
        setups = pit.scan_date(
            context.data_cutoff_date,
            top_n=max(1, len(pairs)),
            only_active_setups=False,
        )
        by_pair = {setup.pair_name: setup for setup in setups}
        rank_by_pair = {
            setup.pair_name: rank
            for rank, setup in enumerate(setups, start=1)
        }
        account = self.broker.get_account()
        positions = self.broker.list_positions().items
        orders = self.broker.list_orders(status="open").items
        current_gross = sum(abs(float(row.get("market_value", 0) or 0)) for row in positions)
        occupied = {
            str(row.get("symbol", "")).upper()
            for row in (*positions, *orders) if row.get("symbol")
        }
        existing_open = repo.open_pair_count()
        existing_today = repo.session_intent_count(context.session_date.isoformat())
        accepted = 0
        rejected = 0
        planned_gross = 0.0

        for pair in pairs:
            ta = str(pair["ticker_a"]).strip().upper().replace(".", "-")
            tb = str(pair["ticker_b"]).strip().upper().replace(".", "-")
            pair_name = f"{ta}/{tb}"
            setup = by_pair.get(pair_name)
            reason: str | None = None
            payload: dict[str, Any] = {
                "pair_name": pair_name,
                "strategy": "strategy_v4",
                "market_vol_pct": round(market_vol_pct, 4),
                "market_vol_state": (
                    "PANIC"
                    if market_vol_pct > self.strategy_config.vix_panic_threshold
                    else "NORMAL"
                ),
                "early_close": context.early_close,
            }
            entry = None
            if setup is None:
                reason = "PAIR_DATA_UNAVAILABLE"
            else:
                blackout, blackout_reason = self.earnings_calendar.is_in_blackout(
                    ta,
                    tb,
                    context.session_date,
                    blackout_days=self.strategy_config.earnings_blackout_days_pre,
                )
                entry = evaluate_strategy_v4_entry(
                    setup,
                    self.strategy_config,
                    previous_z=_previous_z(frame, setup),
                    market_vol_pct=market_vol_pct,
                    earnings_blackout=blackout,
                    current_drawdown_pct=current_drawdown_pct,
                )
                payload.update({
                    "z_score": setup.current_z_score,
                    "hedge_ratio": setup.hedge_ratio,
                    "spread": setup.current_spread,
                    "spread_mean": setup.spread_mean,
                    "spread_std": setup.spread_std,
                    "spread_vol_pct": setup.relative_spread_vol_pct,
                    "half_life_days": setup.half_life_days,
                    "composite_score": setup.composite_score,
                    "rank": rank_by_pair.get(pair_name),
                    "correlation": setup.correlation,
                    "r_squared": setup.r_squared,
                    "adf_pvalue": setup.adf_pvalue,
                    "adf_tstat": setup.adf_tstat,
                    "zero_crossings": setup.zero_crossings,
                    "checks": setup.checks,
                    "momentum_slope": entry.momentum_slope,
                    "drawdown_dampened": entry.is_dampened,
                    "earnings_blackout": blackout,
                    "earnings_blackout_reason": blackout_reason,
                    "chart_snapshot": _chart_snapshot(
                        frame, setup, context.data_cutoff_date,
                        self.strategy_config.lookback_days,
                    ),
                })
                # Check econometric gauntlet (excluding rolling Z which is handled by evaluate_strategy_v4_entry)
                econ_failed = [
                    k for k, passed in setup.checks.items()
                    if not passed and k != "z_score_divergence"
                ]
                if econ_failed:
                    reason = "GAUNTLET_FAILED"
                    payload["failed_checks"] = sorted(econ_failed)
                elif not entry.accepted:
                    reason = entry.reason
                    if hasattr(setup, "checks") and setup.checks:
                        failed = [k for k, passed in setup.checks.items() if not passed]
                        if failed:
                            payload["failed_checks"] = sorted(failed)

            if setup is not None and entry is not None and entry.accepted:
                try:
                    assets = {
                        symbol: self.broker.get_asset(symbol)
                        for symbol in (ta, tb)
                    }
                    quotes = {
                        symbol: self.broker.get_latest_quote(symbol, feed="iex")
                        for symbol in (ta, tb)
                    }
                    reason, execution = self._broker_eligibility(
                        setup=setup,
                        entry=entry,
                        account=account,
                        assets=assets,
                        quotes=quotes,
                        occupied=occupied,
                        context=context,
                        existing_open=existing_open + accepted,
                        existing_today=existing_today + accepted,
                        current_gross=current_gross + planned_gross,
                        frame=frame,
                    )
                except Exception as exc:
                    reason = "BROKER_MARKET_DATA_UNAVAILABLE"
                    execution = {"broker_data_error": type(exc).__name__}
                payload.update(execution)

            decision = "QUALIFIED" if reason is None else "REJECTED"
            if reason is not None:
                payload["rejection_details"] = _rejection_details(
                    reason, payload, self.strategy_config)
            signal_id = "sig-" + canonical_hash({
                "run_id": run_id,
                "pair": pair_name,
            })[:28]
            repo.save_signal({
                "signal_id": signal_id,
                "run_id": run_id,
                "session_date": context.session_date.isoformat(),
                "ticker_a": ta,
                "ticker_b": tb,
                "decision": decision,
                "rejection_reason": reason,
                "data_cutoff_at": context.data_cutoff_date.isoformat(),
                "config_version": self.strategy_config.version,
                "config_hash": config_hash,
                "payload": payload,
            })
            if decision == "QUALIFIED" and setup is not None and entry is not None:
                pair_trade_id = "pair-" + signal_id.removeprefix("sig-")
                legs = payload["proposed_legs"]
                repo.save_intent({
                    "pair_trade_id": pair_trade_id,
                    "signal_id": signal_id,
                    "session_date": context.session_date.isoformat(),
                    "ticker_a": ta,
                    "ticker_b": tb,
                    "target_z": self.strategy_config.z_score_exit_target,
                    "stop_z": entry.stop_z,
                    "max_holding_date": payload["max_holding_date"],
                    "idempotency_key": signal_id,
                    "legs": [
                        {**leg, "leg_id": f"{pair_trade_id}-{index}"}
                        for index, leg in enumerate(legs, start=1)
                    ],
                })
                accepted += 1
                planned_gross += float(payload["proposed_capital"])
                occupied.update((ta, tb))
            else:
                rejected += 1

        summary = {
            "strategy": "strategy_v4",
            "strategy_version": self.strategy_config.version,
            "config_hash": config_hash,
            "session_date": context.session_date.isoformat(),
            "data_cutoff_date": context.data_cutoff_date.isoformat(),
            "observed_at": context.observed_at.isoformat(),
            "next_market_open": context.next_open.isoformat(),
            "next_scheduled_scan_at": (
                context.next_open - timedelta(minutes=self.auto_config.premarket_minutes)
            ).isoformat(),
            "market_vol_pct": round(market_vol_pct, 4),
            "current_drawdown_pct": round(current_drawdown_pct, 4),
                    "current_drawdown_pct": round(current_drawdown_pct, 4),
            "evaluated_pairs": len(pairs),
            "qualified_pairs": accepted,
            "rejected_pairs": rejected,
            "trade_submission_available": False,
        }
        return {"run_id": run_id, "summary": summary}

    def _broker_eligibility(
        self,
        *,
        setup: PointInTimeSetup,
        entry: Any,
        account: AccountSnapshot,
        assets: Mapping[str, AssetSnapshot],
        quotes: Mapping[str, Mapping[str, Any]],
        occupied: set[str],
        context: MarketSessionContext,
        existing_open: int,
        existing_today: int,
        current_gross: float,
        frame: pd.DataFrame,
    ) -> tuple[str | None, dict[str, Any]]:
        ta, tb = setup.ticker_a, setup.ticker_b
        if account.trading_blocked or account.account_blocked:
            return "ACCOUNT_TRADING_BLOCKED", {}
        if account.equity < 2000:
            return "ACCOUNT_EQUITY_BELOW_SHORT_MINIMUM", {}
        if existing_open >= self.auto_config.max_open_pairs:
            return "MAX_OPEN_PAIRS", {}
        if existing_today >= self.auto_config.max_new_pairs_per_day:
            return "MAX_NEW_PAIRS_PER_DAY", {}
        if ta in occupied or tb in occupied:
            return "SYMBOL_ALREADY_OCCUPIED", {}
        if any(
            not assets[symbol].tradable or assets[symbol].status != "active"
            for symbol in (ta, tb)
        ):
            return "ASSET_NOT_TRADABLE", {}
        short_symbol = tb if setup.direction == "LONG_A_SHORT_B" else ta
        short_asset = assets[short_symbol]
        if not short_asset.shortable:
            return "SHORT_LEG_NOT_SHORTABLE", {}
        if not short_asset.easy_to_borrow:
            return "SHORT_LEG_NOT_EASY_TO_BORROW", {}

        mids: dict[str, float] = {}
        for symbol in (ta, tb):
            try:
                mid, stamp = _quote_mid_and_time(quotes[symbol])
            except DryScanError as exc:
                return str(exc), {}
            observed = context.observed_at
            if observed.tzinfo is None:
                observed = observed.replace(tzinfo=timezone.utc)
            age = abs(
                (
                    observed.astimezone(timezone.utc)
                    - stamp.astimezone(timezone.utc)
                ).total_seconds()
            )
            if age > self.auto_config.max_quote_age_seconds:
                return "STALE_PREMARKET_QUOTE", {}
            last_close = float(frame[("Adj Close", symbol)].iloc[-1])
            gap_pct = abs(mid / last_close - 1.0) * 100.0
            if gap_pct > self.auto_config.max_premarket_gap_pct:
                return "PREMARKET_GAP_LIMIT", {}
            mids[symbol] = mid

        proposed_capital = (
            account.portfolio_value
            * self.auto_config.pair_capital_pct
            * entry.sizing_multiplier
        )
        unit_gross = mids[ta] + abs(setup.hedge_ratio) * mids[tb]
        units = math.floor(proposed_capital / max(unit_gross, 0.01))
        if units < 1:
            return "PAIR_CAPITAL_TOO_SMALL", {}
        qty_a = units
        qty_b = max(1, math.floor(units * abs(setup.hedge_ratio)))
        gross = qty_a * mids[ta] + qty_b * mids[tb]
        reserve = account.portfolio_value * self.auto_config.min_buying_power_reserve_pct
        if account.buying_power - gross < reserve:
            return "INSUFFICIENT_BUYING_POWER_RESERVE", {}
        if (
            current_gross + gross
            > account.portfolio_value * self.auto_config.max_gross_exposure_pct
        ):
            return "GROSS_EXPOSURE_LIMIT", {}

        side_a = "BUY" if setup.direction == "LONG_A_SHORT_B" else "SHORT"
        side_b = "SHORT" if setup.direction == "LONG_A_SHORT_B" else "BUY"
        future_sessions = [
            session for session in context.trading_dates
            if session > context.session_date
        ]
        if len(future_sessions) >= entry.max_holding_days:
            max_holding_date = future_sessions[entry.max_holding_days - 1]
        else:
            max_holding_date = (
                pd.Timestamp(context.session_date)
                + pd.offsets.BDay(entry.max_holding_days)
            ).date()
        return None, {
            "sizing_multiplier": round(entry.sizing_multiplier, 6),
            "proposed_capital": round(gross, 2),
            "target_z": self.strategy_config.z_score_exit_target,
            "stop_z": round(entry.stop_z, 4),
            "max_holding_days": entry.max_holding_days,
            "max_holding_date": max_holding_date.isoformat(),
            "proposed_legs": [
                {
                    "symbol": ta,
                    "side": side_a,
                    "qty": qty_a,
                    "reference_price": round(mids[ta], 4),
                    "proposed_notional": round(qty_a * mids[ta], 2),
                },
                {
                    "symbol": tb,
                    "side": side_b,
                    "qty": qty_b,
                    "reference_price": round(mids[tb], 4),
                    "proposed_notional": round(qty_b * mids[tb], 2),
                },
            ],
        }


def format_dry_scan_telegram(bundle: Mapping[str, Any]) -> str:
    """Build a preview only; Phase 2 does not send it automatically."""
    summary = bundle.get("summary") or {}
    lines = [
        "Strategy 4 dry scan",
        f"Session: {summary.get('session_date', 'unknown')}",
        f"Data cutoff: {summary.get('data_cutoff_date', 'unknown')}",
        f"Qualified: {summary.get('qualified_pairs', 0)} / {summary.get('evaluated_pairs', 0)}",
        "DRY RUN ONLY — no orders submitted",
    ]
    for signal in bundle.get("signals", []):
        if signal.get("decision") != "QUALIFIED":
            continue
        payload = signal.get("payload") or {}
        legs = payload.get("proposed_legs") or []
        lines.append(f"\n{payload.get('pair_name')}: Z {payload.get('z_score')}")
        for leg in legs:
            lines.append(
                f"- {leg.get('side')} {leg.get('symbol')} x{leg.get('qty')} "
                f"@ ref {leg.get('reference_price')}"
            )
        lines.append(f"Target Z {payload.get('target_z')} | Stop Z {payload.get('stop_z')}")
    return "\n".join(lines)
