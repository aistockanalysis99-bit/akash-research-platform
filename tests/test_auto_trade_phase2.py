from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import date, datetime
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from engine.config import load_auto_trade_config
from engine.db import schema
from engine.live import auto_trade_repo as repo
from engine.live.alpaca import AccountSnapshot, AssetSnapshot, BrokerCollection, MarketClock
from engine.live.strategy_v4_live import (
    DryScanError,
    MarketSessionContext,
    StrategyV4DryScanner,
    _current_drawdown_pct,
    _previous_z,
    _rejection_details,
    format_dry_scan_telegram,
    resolve_market_session,
    validate_market_frame,
)
from engine.simulator_engine import PointInTimeEngine, PointInTimeSetup
from engine.earnings_calendar import EarningsCalendar
from engine.strategy_v4_engine import (
    StrategyV4Config,
    evaluate_strategy_v4_entry,
)


def auto_config(**overrides: str):
    env = {
        "AUTO_TRADE_ENABLED": "False",
        "AUTO_TRADE_PAPER_ONLY": "True",
        "ALPACA_API_KEY": "paper-key",
        "ALPACA_SECRET_KEY": "paper-secret",
        "ALPACA_BASE_URL": "https://paper-api.alpaca.markets",
        "TELEGRAM_ENABLED": "False",
    }
    env.update(overrides)
    return load_auto_trade_config(env)


def make_frame(cutoff: str = "2026-11-04", periods: int = 120) -> pd.DataFrame:
    index = pd.bdate_range(end=cutoff, periods=periods)
    rng = np.random.default_rng(42)
    b = 100 + np.cumsum(rng.normal(0, 0.15, periods))
    a = 1.1 * b + rng.normal(0, 0.25, periods)
    columns = {}
    for symbol, close in (("AAA", a), ("BBB", b)):
        columns[("Open", symbol)] = close * 0.999
        columns[("High", symbol)] = close * 1.003
        columns[("Low", symbol)] = close * 0.997
        columns[("Close", symbol)] = close
        columns[("Adj Close", symbol)] = close
        columns[("Volume", symbol)] = np.full(periods, 2_000_000.0)
    frame = pd.DataFrame(columns, index=index)
    frame.columns = pd.MultiIndex.from_tuples(frame.columns)
    return frame


def make_setup(frame: pd.DataFrame, **overrides) -> PointInTimeSetup:
    pa_prev = float(frame[("Adj Close", "AAA")].iloc[-2])
    pb_prev = float(frame[("Adj Close", "BBB")].iloc[-2])
    beta = 1.0
    std = 1.0
    mean = pa_prev - beta * pb_prev + 2.2 * std
    values = dict(
        ticker_a="AAA", ticker_b="BBB", pair_name="AAA/BBB",
        target_date=frame.index[-1].strftime("%Y-%m-%d"),
        direction="LONG_A_SHORT_B", hedge_ratio=beta, alpha=0.0,
        r_squared=0.9, correlation=0.95, current_z_score=-2.2,
        abs_z_score=2.2, current_spread=mean - 2.2 * std,
        spread_mean=mean, spread_std=std, target_spread_mean=mean,
        target_spread_80pct=mean - 0.44, stop_loss_spread=mean - 3.5,
        price_a_entry=float(frame[("Adj Close", "AAA")].iloc[-1]),
        price_b_entry=float(frame[("Adj Close", "BBB")].iloc[-1]),
        adf_tstat=-4.0, adf_pvalue=0.01, half_life_days=5.0,
        zero_crossings=20, relative_spread_vol_pct=3.0,
        spread_tier="Tight", composite_score=85.0, is_setup=True,
        window_bars=90, checks={"gauntlet": True}, passed_checks_count=10,
        is_perfect=True, is_tradeable=True, expected_reversion_return_pct=2.0,
        risk_reward_ratio=2.0, action_a="BUY AAA", action_b="SHORT BBB",
    )
    values.update(overrides)
    return PointInTimeSetup(**values)


def make_context() -> MarketSessionContext:
    return MarketSessionContext(
        observed_at=pd.Timestamp("2026-11-05T08:00:00-05:00").to_pydatetime(),
        session_date=date(2026, 11, 5),
        data_cutoff_date=date(2026, 11, 4),
        next_open=pd.Timestamp("2026-11-05T09:30:00-05:00").to_pydatetime(),
        next_close=pd.Timestamp("2026-11-05T16:00:00-05:00").to_pydatetime(),
        early_close=False,
    )


class FakeBroker:
    def __init__(self, frame: pd.DataFrame) -> None:
        self.frame = frame
        self.account = AccountSnapshot(
            account_id="paper", status="ACTIVE", currency="USD", cash=100_000,
            portfolio_value=100_000, equity=100_000, buying_power=200_000,
            pattern_day_trader=False, trading_blocked=False,
            account_blocked=False, raw={},
        )
        self.assets = {
            symbol: AssetSnapshot(
                asset_id=symbol, symbol=symbol, name=symbol, exchange="NYSE",
                status="active", tradable=True, marginable=True, shortable=True,
                easy_to_borrow=True, borrow_status="easy_to_borrow", raw={},
            )
            for symbol in ("AAA", "BBB")
        }
        stamp = "2026-11-05T08:00:00-05:00"
        self.quotes = {
            symbol: {
                "bp": float(frame[("Adj Close", symbol)].iloc[-1]) - 0.01,
                "ap": float(frame[("Adj Close", symbol)].iloc[-1]) + 0.01,
                "t": stamp,
            }
            for symbol in ("AAA", "BBB")
        }
        self.positions: tuple[dict, ...] = ()
        self.orders: tuple[dict, ...] = ()

    def get_account(self):
        return self.account

    def get_clock(self):
        return MarketClock(
            timestamp="2026-11-05T08:00:00-05:00", is_open=False,
            next_open="2026-11-05T09:30:00-05:00",
            next_close="2026-11-05T16:00:00-05:00",
        )

    def get_calendar(self, start=None, end=None):
        return BrokerCollection((
            {"date": "2026-11-04", "open": "09:30", "close": "16:00"},
            {"date": "2026-11-05", "open": "09:30", "close": "16:00"},
        ))

    def get_asset(self, symbol: str):
        return self.assets[symbol]

    def get_latest_quote(self, symbol: str, **kwargs):
        return self.quotes[symbol]

    def list_positions(self):
        return BrokerCollection(self.positions)

    def list_orders(self, status="all", limit=500):
        return BrokerCollection(self.orders)

    def get_bars(self, symbol: str, **kwargs):
        rows = []
        for stamp, row in self.frame.xs(symbol, axis=1, level=1).iterrows():
            rows.append({
                "t": stamp.isoformat(), "o": row["Open"], "h": row["High"],
                "l": row["Low"], "c": row["Adj Close"], "v": row["Volume"],
            })
        return BrokerCollection(tuple(rows))


@pytest.fixture
def phase2_db(tmp_path, monkeypatch):
    monkeypatch.setattr(schema, "DB_PATH", tmp_path / "phase2.sqlite")
    schema.init_db()


@pytest.fixture
def fixed_setup(monkeypatch):
    frame = make_frame()
    setup = make_setup(frame)
    monkeypatch.setattr(PointInTimeEngine, "scan_date", lambda self, *args, **kwargs: [setup])
    return frame, setup


def test_shared_entry_rules_cover_all_strategy_v4_gates(fixed_setup) -> None:
    _, setup = fixed_setup
    config = StrategyV4Config()

    def decide(candidate=setup, **kwargs):
        values = dict(
            previous_z=-2.2, market_vol_pct=15.0,
            earnings_blackout=False, current_drawdown_pct=0.0,
        )
        values.update(kwargs)
        return evaluate_strategy_v4_entry(candidate, config, **values)

    assert decide().accepted
    assert decide(replace(setup, current_z_score=-1.9)).reason == "ENTRY_Z_BELOW_HURDLE"
    assert decide(replace(setup, current_z_score=-3.0)).reason == "ENTRY_Z_ABOVE_MAX"
    assert decide(replace(setup, relative_spread_vol_pct=6.0)).reason == "SPREAD_VOLATILITY_CAP"
    assert decide(market_vol_pct=30.0).reason == "VIX_PANIC_FREEZE"
    assert decide(earnings_blackout=True).reason == "EARNINGS_BLACKOUT"
    assert decide(previous_z=-1.8).reason == "MOMENTUM_NOT_FLATTENING"
    dampened = decide(current_drawdown_pct=25.0)
    assert dampened.accepted and dampened.is_dampened


def test_current_drawdown_uses_valid_portfolio_peak() -> None:
    history = {"equity": [100_000, None, "bad", 120_000, 110_000]}
    assert _current_drawdown_pct(history, 90_000) == 25.0
    assert _current_drawdown_pct({"equity": []}, 100_000) == 0.0


def test_rejection_details_show_measured_values_and_strategy_thresholds() -> None:
    details = _rejection_details(
        "GAUNTLET_FAILED",
        {
            "failed_checks": ["correlation", "r_squared"],
            "correlation": 0.61,
            "r_squared": 0.2025,
        },
        StrategyV4Config(),
    )
    assert details == [
        {
            "rule": "correlation", "actual": "0.610", "required": "≥ 0.850",
            "explanation": "The two stocks are not moving together closely enough for this pair model.",
        },
        {
            "rule": "r_squared", "actual": "0.203", "required": "≥ 0.350",
            "explanation": "The hedge regression explains too little of the relationship between the stocks.",
        },
    ]


def test_dry_scan_parity_idempotency_and_no_orders(
    phase2_db, fixed_setup,
) -> None:
    frame, setup = fixed_setup
    broker = FakeBroker(frame)
    scanner = StrategyV4DryScanner(
        broker=broker,
        auto_config=auto_config(),
        strategy_config=StrategyV4Config(),
        earnings_calendar=EarningsCalendar(custom_earnings={}),
    )
    direct = evaluate_strategy_v4_entry(
        setup,
        scanner.strategy_config,
        previous_z=_previous_z(frame, setup),
        market_vol_pct=15.0,
        earnings_blackout=False,
    )
    first = scanner.run_frozen(
        frame=frame, pairs=[{"ticker_a": "AAA", "ticker_b": "BBB"}],
        context=make_context(), market_vol_pct=15.0,
    )
    second = scanner.run_frozen(
        frame=frame, pairs=[{"ticker_a": "AAA", "ticker_b": "BBB"}],
        context=make_context(), market_vol_pct=15.0,
    )
    assert direct.accepted
    assert first["summary"]["qualified_pairs"] == 1
    assert first["signals"][0]["payload"]["sizing_multiplier"] == round(direct.sizing_multiplier, 6)
    chart = first["signals"][0]["payload"]["chart_snapshot"]
    assert chart["source"] == "strategy_v4_scan_snapshot"
    assert chart["ticker_a"] == "AAA" and chart["ticker_b"] == "BBB"
    assert chart["current_date"] == "2026-11-04"
    assert len(chart["historical_bars"]) == scanner.strategy_config.lookback_days
    assert chart["historical_bars"][-1]["date"] == "2026-11-04"
    assert first["signals"][0]["payload"].get("rejection_details") is None
    assert first["run_id"] == second["run_id"]
    assert first["signals"][0]["signal_id"] == second["signals"][0]["signal_id"]
    assert second["idempotent_replay"] is True
    assert first["summary"]["trade_submission_available"] is False
    assert not hasattr(broker, "submit_order")
    assert "DRY RUN ONLY" in format_dry_scan_telegram(first)


def test_run_identity_covers_full_history_and_risk_config(
    phase2_db, fixed_setup,
) -> None:
    frame, _ = fixed_setup
    broker = FakeBroker(frame)
    pairs = [{"ticker_a": "AAA", "ticker_b": "BBB"}]
    scanner = StrategyV4DryScanner(
        broker=broker,
        auto_config=auto_config(),
        strategy_config=StrategyV4Config(),
        earnings_calendar=EarningsCalendar(custom_earnings={}),
    )
    baseline = scanner.run_frozen(
        frame=frame, pairs=pairs, context=make_context(), market_vol_pct=15.0,
    )

    revised_frame = frame.copy()
    revised_frame.loc[revised_frame.index[10], ("Adj Close", "AAA")] *= 1.001
    data_revision = scanner.run_frozen(
        frame=revised_frame,
        pairs=pairs,
        context=make_context(),
        market_vol_pct=15.0,
    )
    risk_revision = StrategyV4DryScanner(
        broker=broker,
        auto_config=auto_config(AUTO_TRADE_PAIR_CAPITAL_PCT="0.11"),
        strategy_config=StrategyV4Config(),
        earnings_calendar=EarningsCalendar(custom_earnings={}),
    ).run_frozen(
        frame=frame, pairs=pairs, context=make_context(), market_vol_pct=15.0,
    )
    drawdown_revision = scanner.run_frozen(
        frame=frame,
        pairs=pairs,
        context=make_context(),
        market_vol_pct=15.0,
        current_drawdown_pct=25.0,
    )

    assert len({
        baseline["run_id"], data_revision["run_id"], risk_revision["run_id"],
        drawdown_revision["run_id"],
    }) == 4
    assert len({
        baseline["signals"][0]["signal_id"],
        data_revision["signals"][0]["signal_id"],
        risk_revision["signals"][0]["signal_id"],
        drawdown_revision["signals"][0]["signal_id"],
    }) == 4
    assert drawdown_revision["signals"][0]["payload"]["drawdown_dampened"] is True


def test_broker_data_failure_rejects_pair_and_is_persisted(
    phase2_db, fixed_setup, monkeypatch,
) -> None:
    frame, _ = fixed_setup
    broker = FakeBroker(frame)

    def unavailable(_symbol: str):
        raise RuntimeError("temporary broker failure")

    monkeypatch.setattr(broker, "get_asset", unavailable)
    result = StrategyV4DryScanner(
        broker=broker,
        auto_config=auto_config(),
        strategy_config=StrategyV4Config(),
        earnings_calendar=EarningsCalendar(custom_earnings={}),
    ).run_frozen(
        frame=frame,
        pairs=[{"ticker_a": "AAA", "ticker_b": "BBB"}],
        context=make_context(),
        market_vol_pct=15.0,
    )

    signal = result["signals"][0]
    assert signal["rejection_reason"] == "BROKER_MARKET_DATA_UNAVAILABLE"
    assert signal["payload"]["broker_data_error"] == "RuntimeError"


@pytest.mark.parametrize(
    ("mutation", "expected"),
    [
        ("blocked", "ACCOUNT_TRADING_BLOCKED"),
        ("low_equity", "ACCOUNT_EQUITY_BELOW_SHORT_MINIMUM"),
        ("occupied", "SYMBOL_ALREADY_OCCUPIED"),
        ("not_tradable", "ASSET_NOT_TRADABLE"),
        ("not_shortable", "SHORT_LEG_NOT_SHORTABLE"),
        ("htb", "SHORT_LEG_NOT_EASY_TO_BORROW"),
        ("stale_quote", "STALE_PREMARKET_QUOTE"),
        ("gap", "PREMARKET_GAP_LIMIT"),
        ("buying_power", "INSUFFICIENT_BUYING_POWER_RESERVE"),
        ("gross", "GROSS_EXPOSURE_LIMIT"),
    ],
)
def test_broker_and_risk_rejections(
    phase2_db, fixed_setup, mutation: str, expected: str,
) -> None:
    frame, _ = fixed_setup
    broker = FakeBroker(frame)
    config = auto_config()
    if mutation == "blocked":
        broker.account = replace(broker.account, trading_blocked=True)
    elif mutation == "low_equity":
        broker.account = replace(broker.account, equity=1_000)
    elif mutation == "occupied":
        broker.positions = ({"symbol": "AAA", "market_value": "100"},)
    elif mutation == "not_tradable":
        broker.assets["AAA"] = replace(broker.assets["AAA"], tradable=False)
    elif mutation == "not_shortable":
        broker.assets["BBB"] = replace(broker.assets["BBB"], shortable=False)
    elif mutation == "htb":
        broker.assets["BBB"] = replace(
            broker.assets["BBB"], easy_to_borrow=False, borrow_status="hard_to_borrow")
    elif mutation == "stale_quote":
        broker.quotes["AAA"]["t"] = "2026-11-05T06:00:00-05:00"
    elif mutation == "gap":
        broker.quotes["AAA"]["ap"] *= 1.1
        broker.quotes["AAA"]["bp"] *= 1.1
    elif mutation == "buying_power":
        broker.account = replace(broker.account, buying_power=1_000)
    elif mutation == "gross":
        config = auto_config(AUTO_TRADE_MAX_GROSS_EXPOSURE_PCT="0.01")

    scanner = StrategyV4DryScanner(
        broker=broker, auto_config=config,
        strategy_config=StrategyV4Config(),
        earnings_calendar=EarningsCalendar(custom_earnings={}),
    )
    result = scanner.run_frozen(
        frame=frame, pairs=[{"ticker_a": "AAA", "ticker_b": "BBB"}],
        context=make_context(), market_vol_pct=15.0,
    )
    assert result["summary"]["qualified_pairs"] == 0
    assert result["signals"][0]["rejection_reason"] == expected


@pytest.mark.parametrize(
    ("kind", "expected"),
    [
        ("duplicate", "DUPLICATE_BARS"),
        ("non_monotonic", "NON_MONOTONIC_BARS"),
        ("stale", "STALE_DAILY_BARS"),
        ("missing", "MISSING_OHLC_FIELDS"),
        ("split", "SPLIT_LIKE_DISCONTINUITY"),
        ("insufficient", "INSUFFICIENT_BARS"),
    ],
)
def test_market_data_quality_rejections(kind: str, expected: str) -> None:
    frame = make_frame()
    if kind == "duplicate":
        frame = pd.concat([frame, frame.iloc[[-1]]])
    elif kind == "non_monotonic":
        frame = frame.iloc[::-1]
    elif kind == "stale":
        frame = frame.iloc[:-1]
    elif kind == "missing":
        frame = frame.drop(columns=[("High", "AAA")])
    elif kind == "split":
        frame.loc[frame.index[-1], ("Adj Close", "AAA")] *= 0.4
    elif kind == "insufficient":
        frame = frame.iloc[-20:]
    with pytest.raises(DryScanError, match=expected):
        validate_market_frame(frame, ("AAA", "BBB"), date(2026, 11, 4), 90)


def test_incomplete_current_session_bar_is_excluded() -> None:
    frame = make_frame()
    future = frame.iloc[[-1]].copy()
    future.index = pd.DatetimeIndex(["2026-11-05"])
    future.loc[:, ("Adj Close", "AAA")] = 9999
    extended = pd.concat([frame, future])
    clean = validate_market_frame(extended, ("AAA", "BBB"), date(2026, 11, 4), 90)
    assert clean.index[-1].date() == date(2026, 11, 4)
    assert clean[("Adj Close", "AAA")].iloc[-1] != 9999


@pytest.mark.parametrize(
    ("timestamp", "next_open", "calendar", "cutoff", "early"),
    [
        (
            "2026-01-05T08:00:00-05:00", "2026-01-05T09:30:00-05:00",
            ({"date": "2026-01-02", "close": "16:00"}, {"date": "2026-01-05", "close": "16:00"}),
            date(2026, 1, 2), False,
        ),
        (
            "2026-06-08T08:00:00-04:00", "2026-06-08T09:30:00-04:00",
            ({"date": "2026-06-05", "close": "16:00"}, {"date": "2026-06-08", "close": "16:00"}),
            date(2026, 6, 5), False,
        ),
        (
            "2026-07-06T08:00:00-04:00", "2026-07-06T09:30:00-04:00",
            ({"date": "2026-07-02", "close": "13:00"}, {"date": "2026-07-06", "close": "16:00"}),
            date(2026, 7, 2), False,
        ),
        (
            "2026-11-27T08:00:00-05:00", "2026-11-27T09:30:00-05:00",
            ({"date": "2026-11-25", "close": "16:00"}, {"date": "2026-11-27", "close": "13:00"}),
            date(2026, 11, 25), True,
        ),
    ],
)
def test_market_calendar_dst_holidays_and_early_close(
    timestamp, next_open, calendar, cutoff, early,
) -> None:
    clock = MarketClock(
        timestamp=timestamp, is_open=False, next_open=next_open,
        next_close=next_open.replace("09:30", "16:00"),
    )
    context = resolve_market_session(clock, calendar)
    assert context.data_cutoff_date == cutoff
    assert context.early_close is early


@pytest.mark.parametrize(
    ("clock", "expected"),
    [
        (
            MarketClock(
                timestamp="2026-11-05T10:00:00-05:00",
                is_open=True,
                next_open="2026-11-06T09:30:00-05:00",
                next_close="2026-11-05T16:00:00-05:00",
            ),
            "MARKET_ALREADY_OPEN",
        ),
        (
            MarketClock(
                timestamp="2026-11-07T08:00:00-05:00",
                is_open=False,
                next_open="2026-11-09T09:30:00-05:00",
                next_close="2026-11-09T16:00:00-05:00",
            ),
            "NO_PREMARKET_SESSION_TODAY",
        ),
    ],
)
def test_live_run_skips_open_market_and_non_trading_days(
    phase2_db, fixed_setup, monkeypatch, clock, expected,
) -> None:
    frame, _ = fixed_setup
    broker = FakeBroker(frame)
    monkeypatch.setattr(broker, "get_clock", lambda: clock)
    monkeypatch.setattr(
        broker,
        "get_calendar",
        lambda *args, **kwargs: BrokerCollection((
            {"date": "2026-11-04", "close": "16:00"},
            {"date": "2026-11-05", "close": "16:00"},
            {"date": "2026-11-06", "close": "16:00"},
            {"date": "2026-11-09", "close": "16:00"},
        )),
    )
    scanner = StrategyV4DryScanner(
        broker=broker,
        auto_config=auto_config(),
        strategy_config=StrategyV4Config(),
        earnings_calendar=EarningsCalendar(custom_earnings={}),
    )
    with pytest.raises(DryScanError, match=expected):
        scanner.run(pairs=[{"ticker_a": "AAA", "ticker_b": "BBB"}])


def test_concurrent_run_claim_is_atomic(phase2_db) -> None:
    def claim():
        return repo.claim_run("same-run", session_date="2026-11-05", config_hash="hash")[0]

    with ThreadPoolExecutor(max_workers=2) as pool:
        claimed = list(pool.map(lambda _: claim(), range(2)))
    assert sorted(claimed) == [False, True]


@pytest.mark.parametrize(
    ("state", "config_overrides", "expected"),
    [
        ("OPEN", {"AUTO_TRADE_MAX_OPEN_PAIRS": "1"}, "MAX_OPEN_PAIRS"),
        ("CLOSED", {"AUTO_TRADE_MAX_NEW_PAIRS_PER_DAY": "1"}, "MAX_NEW_PAIRS_PER_DAY"),
    ],
)
def test_pair_count_risk_limits(
    phase2_db, fixed_setup, state, config_overrides, expected,
) -> None:
    frame, _ = fixed_setup
    conn = schema.get_connection()
    try:
        conn.execute(
            "INSERT INTO pair_trade_intents "
            "(pair_trade_id, session_date, ticker_a, ticker_b, state, "
            "idempotency_key, created_at, updated_at) "
            "VALUES ('existing', '2026-11-05', 'CCC', 'DDD', ?, 'existing-key', 'now', 'now')",
            (state,),
        )
        conn.commit()
    finally:
        conn.close()
    scanner = StrategyV4DryScanner(
        broker=FakeBroker(frame), auto_config=auto_config(**config_overrides),
        strategy_config=StrategyV4Config(),
        earnings_calendar=EarningsCalendar(custom_earnings={}),
    )
    result = scanner.run_frozen(
        frame=frame, pairs=[{"ticker_a": "AAA", "ticker_b": "BBB"}],
        context=make_context(), market_vol_pct=15.0,
    )
    assert result["signals"][0]["rejection_reason"] == expected


def test_draft_intents_do_not_consume_open_pair_limit(phase2_db) -> None:
    conn = schema.get_connection()
    try:
        conn.execute(
            "INSERT INTO pair_trade_intents "
            "(pair_trade_id, session_date, ticker_a, ticker_b, state, "
            "idempotency_key, created_at, updated_at) "
            "VALUES ('draft', '2026-11-05', 'AAA', 'BBB', 'DRAFT', "
            "'draft-key', 'now', 'now')"
        )
        conn.commit()
    finally:
        conn.close()
    assert repo.open_pair_count() == 0


def test_dry_scan_api_contract_remains_in_phase3(phase2_db, monkeypatch) -> None:
    import api.main as api_main

    fake_result = {
        "run_id": "v4-dry-fake", "status": "complete", "signals": [],
        "summary": {"trade_submission_available": False},
    }

    class FakeScanner:
        def run(self):
            return fake_result

    monkeypatch.setattr(api_main, "StrategyV4DryScanner", FakeScanner)
    assert api_main.auto_trade_dry_scan() == fake_result
    paths = {route.path for route in api_main.app.routes if hasattr(route, "path")}
    assert "/auto-trade/status" in paths
    assert "/auto-trade/dry-scan" in paths
    assert "/auto-trade/dry-runs/{run_id}" in paths
    assert "/auto-trade/pairs/{pair_trade_id}/submit" in paths
    assert "/auto-trade/reconcile" in paths


def test_phase2_frontend_contract_remains_available_in_phase3() -> None:
    root = Path(__file__).resolve().parents[1]
    page = (root / "frontend/src/pages/AutoTradePage.tsx").read_text(encoding="utf-8")
    app = (root / "frontend/src/App.tsx").read_text(encoding="utf-8")
    api = (root / "frontend/src/lib/api.ts").read_text(encoding="utf-8")
    assert "Run dry scan" in page
    assert 'path="/auto-trade"' in app
    assert 'post<AutoTradeRun>("/auto-trade/dry-scan")' in api
    assert "/auto-trade/dry-scan" in api

