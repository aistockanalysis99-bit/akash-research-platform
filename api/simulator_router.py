"""FastAPI Simulator Router for Point-in-Time Statistical Arbitrage Backtest & Replay.

Endpoints:
  POST /api/simulator/init            -- Initialize anchor date and parameters
  GET  /api/simulator/scan            -- Point-in-time setup scan for target date (sub-100ms)
  GET  /api/simulator/step            -- Step forward (+1) or backward (-1) by trading day
  GET  /api/simulator/pair-chart      -- Historical OHLCV & spread; strips future data if reveal=False
  POST /api/simulator/reveal          -- Evaluate forward outcome (WIN/LOSS/NEUTRAL) and trajectory
  GET  /api/simulator/batch-scorecard -- Summary scorecard across all setups on target date

Guarantees:
  - Constraint 1: Zero future data in /pair-chart when reveal=False.
  - Constraint 2: Fast, RFC-8259-compliant JSON serialization (no NaN / Infinity, recursive sanitization).
  - Constraint 3: Sub-100ms response latency on /scan endpoint.
"""

from __future__ import annotations

import collections
import json
import math
import threading
import time
from datetime import date
from typing import Any, Dict, List, Optional, Union

import pandas as pd
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from engine.simulator_engine import (
    DayBatchScorecard,
    ForwardEvaluationResult,
    ForwardOutcomeEvaluator,
    PointInTimeEngine,
    PointInTimeSetup,
)
from engine.logging_setup import get_logger

logger = get_logger("api.simulator")

router = APIRouter()

# --------------------------------------------------------------------------- #
# Module Singletons & Thread-Safe Caching
# --------------------------------------------------------------------------- #
_engine_instance: Optional[PointInTimeEngine] = None
_evaluator_instance: Optional[ForwardOutcomeEvaluator] = None
_instance_lock = threading.Lock()

# Thread-safe bounded LRU cache for scan responses
_scan_cache_lock = threading.Lock()
_scan_cache: collections.OrderedDict[str, SimulatorScanResponse] = collections.OrderedDict()


def get_cached_scan(key: str) -> Optional[SimulatorScanResponse]:
    """Retrieve cached scan results if present, maintaining LRU order."""
    with _scan_cache_lock:
        if key in _scan_cache:
            _scan_cache.move_to_end(key)
            return _scan_cache[key]
    return None


def set_cached_scan(key: str, val: SimulatorScanResponse, max_size: int = 128) -> None:
    """Store scan results in bounded thread-safe LRU cache."""
    with _scan_cache_lock:
        _scan_cache[key] = val
        _scan_cache.move_to_end(key)
        if len(_scan_cache) > max_size:
            _scan_cache.popitem(last=False)


# Active simulation session state
_sim_state: Dict[str, Any] = {
    "anchor_date": "2024-01-16",
    "current_date": "2024-01-16",
    "lookback_days": 90,
    "min_z_score": 2.0,
    "max_adf_pvalue": 0.05,
    "min_correlation": 0.85,
    "max_horizon_days": 30,
}


def get_engine() -> PointInTimeEngine:
    """Return shared warm PointInTimeEngine instance with cached Parquet."""
    global _engine_instance
    if _engine_instance is None:
        with _instance_lock:
            if _engine_instance is None:
                _engine_instance = PointInTimeEngine()
                _engine_instance.load_data()
    return _engine_instance


def get_evaluator() -> ForwardOutcomeEvaluator:
    """Return shared warm ForwardOutcomeEvaluator instance."""
    global _evaluator_instance
    if _evaluator_instance is None:
        with _instance_lock:
            if _evaluator_instance is None:
                eng = get_engine()
                _evaluator_instance = ForwardOutcomeEvaluator(df=eng.load_data())
    return _evaluator_instance


def clean_float(val: Any, default: float = 0.0) -> float:
    """Sanitize floats to guarantee RFC 8259 JSON compliance (no NaN/Infinity)."""
    if val is None:
        return default
    try:
        f = float(val)
        if math.isnan(f) or math.isinf(f):
            return default
        return f
    except (ValueError, TypeError):
        return default


def sanitize_json_data(obj: Any) -> Any:
    """Recursively sanitize floats in dicts/lists to guarantee RFC 8259 JSON compliance."""
    if isinstance(obj, float):
        return clean_float(obj)
    if isinstance(obj, dict):
        return {k: sanitize_json_data(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [sanitize_json_data(v) for v in obj]
    return obj


def validate_target_date(date_str: str, engine: PointInTimeEngine) -> pd.Timestamp:
    """Parse date string, normalize to midnight, and verify bounds in dataset."""
    try:
        ts = pd.to_datetime(date_str).normalize()
    except Exception:
        raise HTTPException(400, f"Invalid date format: {date_str}. Expected YYYY-MM-DD.")

    trading_dates = engine.get_trading_dates()
    if not trading_dates:
        raise HTTPException(500, "No trading dates loaded in dataset.")

    if ts < trading_dates[0] or ts > trading_dates[-1]:
        raise HTTPException(
            400,
            f"Date {date_str} is out of bounds. Available range: "
            f"{trading_dates[0].strftime('%Y-%m-%d')} to {trading_dates[-1].strftime('%Y-%m-%d')}."
        )
    return ts


# --------------------------------------------------------------------------- #
# Pydantic Schemas
# --------------------------------------------------------------------------- #
class SimulatorInitRequest(BaseModel):
    anchor_date: Optional[str] = Field(None, description="Anchor Date (YYYY-MM-DD)")
    lookback_days: int = Field(90, ge=30, le=252)
    min_z_score: float = Field(2.0, ge=0.5, le=5.0)
    max_adf_pvalue: float = Field(0.05, ge=0.001, le=0.50)
    min_correlation: float = Field(0.85, ge=0.0, le=1.0)
    max_horizon_days: int = Field(30, ge=5, le=120)


class PointInTimeSetupSchema(BaseModel):
    model_config = ConfigDict(extra="ignore")

    ticker_a: str
    ticker_b: str
    pair_name: str
    target_date: str
    direction: str
    hedge_ratio: float
    alpha: float
    r_squared: float
    correlation: float
    current_z_score: float
    abs_z_score: float
    current_spread: float
    spread_mean: float
    spread_std: float
    target_spread_mean: float
    target_spread_80pct: float
    stop_loss_spread: float
    price_a_entry: float
    price_b_entry: float
    adf_tstat: float
    adf_pvalue: float
    half_life_days: float
    zero_crossings: int
    relative_spread_vol_pct: float
    spread_tier: str
    composite_score: float
    is_setup: bool
    window_bars: int
    sector: str = "Institutional Equities"
    checks: Dict[str, bool] = Field(default_factory=dict)
    passed_checks_count: int = 0
    is_perfect: bool = False
    is_tradeable: bool = False
    expected_reversion_return_pct: float = 0.0
    risk_reward_ratio: float = 0.0
    action_a: str = ""
    action_b: str = ""


class SimulatorInitResponse(BaseModel):
    status: str
    anchor_date: str
    current_date: str
    min_date: str
    max_date: str
    total_trading_days: int
    current_index: int
    intact_pairs_count: int
    parameters: Dict[str, Any]


class SimulatorScanResponse(BaseModel):
    current_date: str
    total_setups_found: int
    setups: List[PointInTimeSetupSchema]
    scan_latency_ms: float
    trading_date_used: str = ""
    total_pairs_evaluated: int = 0
    perfect_count: int = 0
    tradeable_count: int = 0
    tradeable_setups: List[PointInTimeSetupSchema] = Field(default_factory=list)


class SimulatorStepResponse(BaseModel):
    previous_date: str
    current_date: str
    direction: str
    current_index: int
    total_dates: int
    is_min_date: bool
    is_max_date: bool


class HistoricalBarSchema(BaseModel):
    date: str
    price_a: float
    price_b: float
    spread: float
    z_score: float


class ForwardBarSchema(BaseModel):
    date: str
    days_elapsed: int
    price_a: float
    price_b: float
    spread: float
    z_score: float


class ForwardEvaluationResultSchema(BaseModel):
    model_config = ConfigDict(extra="ignore")

    pair_name: str
    target_date: str
    direction: str
    outcome: str
    status_reason: str
    entry_price_a: float
    entry_price_b: float
    entry_spread: float
    entry_z_score: float
    exit_date: Optional[str] = None
    exit_days_held: int = 0
    exit_price_a: Optional[float] = None
    exit_price_b: Optional[float] = None
    exit_spread: Optional[float] = None
    exit_z_score: Optional[float] = None
    realized_pnl_pct: float = 0.0
    max_favorable_z: float = 0.0
    max_adverse_z: float = 0.0
    path: List[Dict[str, Any]] = Field(default_factory=list)


class PairChartResponse(BaseModel):
    ticker_a: str
    ticker_b: str
    current_date: str
    reveal: bool
    setup: Optional[PointInTimeSetupSchema] = None
    historical_bars: List[HistoricalBarSchema]
    forward_bars: Optional[List[ForwardBarSchema]] = None
    forward_outcome: Optional[ForwardEvaluationResultSchema] = None


class DayBatchScorecardSchema(BaseModel):
    model_config = ConfigDict(extra="ignore")

    target_date: str
    total_setups: int
    win_count: int
    loss_count: int
    neutral_count: int
    win_rate_pct: float
    avg_return_pct: float
    median_return_pct: float
    avg_days_held: float
    profit_factor: float
    total_gross_profit_pct: float
    total_gross_loss_pct: float
    evaluations: List[ForwardEvaluationResultSchema] = Field(default_factory=list)


class RevealRequest(BaseModel):
    ticker_a: str
    ticker_b: str
    target_date: str
    max_horizon_days: Optional[int] = 30
    lookback_days: Optional[int] = 90


# --------------------------------------------------------------------------- #
# Endpoints
# --------------------------------------------------------------------------- #
@router.post("/init", response_model=SimulatorInitResponse)
def initialize_simulator(req: SimulatorInitRequest) -> SimulatorInitResponse:
    """Initialize or update the point-in-time simulation anchor date and parameters."""
    engine = get_engine()
    trading_dates = engine.get_trading_dates()

    if not trading_dates:
        raise HTTPException(500, "No trading dates found in universe Parquet.")

    min_date_ts = trading_dates[0]
    max_date_ts = trading_dates[-1]
    min_date_str = min_date_ts.strftime("%Y-%m-%d")
    max_date_str = max_date_ts.strftime("%Y-%m-%d")

    # Determine anchor date: default to ~1 year before max date if unspecified
    if req.anchor_date:
        requested_ts = pd.to_datetime(req.anchor_date).normalize()
        valid_dates = [d for d in trading_dates if d <= requested_ts]
        anchor_ts = valid_dates[-1] if valid_dates else trading_dates[engine.default_lookback]
    else:
        idx = max(engine.default_lookback, len(trading_dates) - 250)
        anchor_ts = trading_dates[idx]

    anchor_date_str = anchor_ts.strftime("%Y-%m-%d")
    current_idx = trading_dates.index(anchor_ts)

    # Save session state
    _sim_state["anchor_date"] = anchor_date_str
    _sim_state["current_date"] = anchor_date_str
    _sim_state["lookback_days"] = req.lookback_days
    _sim_state["min_z_score"] = req.min_z_score
    _sim_state["max_adf_pvalue"] = req.max_adf_pvalue
    _sim_state["min_correlation"] = req.min_correlation
    _sim_state["max_horizon_days"] = req.max_horizon_days

    pairs = engine.get_pairs()

    return SimulatorInitResponse(
        status="initialized",
        anchor_date=anchor_date_str,
        current_date=anchor_date_str,
        min_date=min_date_str,
        max_date=max_date_str,
        total_trading_days=len(trading_dates),
        current_index=current_idx,
        intact_pairs_count=len(pairs),
        parameters={
            "lookback_days": req.lookback_days,
            "min_z_score": req.min_z_score,
            "max_adf_pvalue": req.max_adf_pvalue,
            "min_correlation": req.min_correlation,
            "max_horizon_days": req.max_horizon_days,
        },
    )


@router.get("/scan", response_model=SimulatorScanResponse)
def scan_point_in_time(
    current_date: str = Query(..., description="Target date (YYYY-MM-DD)"),
    top_n: int = Query(20, ge=1, le=100),
    only_active_setups: bool = Query(True, description="Filter by active setup rules"),
    min_z: Optional[float] = Query(None, description="Override min Z-score"),
    max_adf: Optional[float] = Query(None, description="Override max ADF p-value"),
    min_corr: Optional[float] = Query(None, description="Override min correlation"),
    lookback_days: Optional[int] = Query(None, description="Override lookback window in days"),
) -> SimulatorScanResponse:
    """Scan point-in-time divergence setups strictly using t <= current_date (< 100ms)."""
    t0 = time.perf_counter()
    engine = get_engine()

    # Validate target date and bounds
    target_ts = validate_target_date(current_date, engine)
    norm_date_str = target_ts.strftime("%Y-%m-%d")

    # Thread-safe cache check
    cache_key = f"{norm_date_str}_{top_n}_{only_active_setups}_{min_z}_{max_adf}_{min_corr}_{lookback_days}"
    cached_resp = get_cached_scan(cache_key)
    if cached_resp is not None:
        latency = (time.perf_counter() - t0) * 1000.0
        return cached_resp.model_copy(update={"scan_latency_ms": round(latency, 2)})

    # Execute high-performance scan with flexible threshold support
    z_floor = min_z if min_z is not None else engine.z_threshold
    adf_ceiling = max_adf if max_adf is not None else engine.max_adf_pvalue
    corr_floor = min_corr if min_corr is not None else engine.min_correlation

    scan_active = only_active_setups if (min_z is None or min_z >= engine.z_threshold) else False
    raw_setups = engine.scan_date(
        target_date=target_ts,
        top_n=top_n if not scan_active else top_n * 2,
        only_active_setups=scan_active,
    )

    filtered_setups: List[PointInTimeSetupSchema] = []
    for s in raw_setups:
        # Prevent NaN comparison bypass
        if math.isnan(s.abs_z_score) or math.isnan(s.correlation) or math.isnan(s.adf_pvalue):
            continue

        if only_active_setups:
            if s.abs_z_score < z_floor or s.adf_pvalue > adf_ceiling or s.correlation < corr_floor:
                continue

        d = sanitize_json_data(s.to_dict())
        filtered_setups.append(PointInTimeSetupSchema(**d))

    tradeable_setups = [s for s in filtered_setups if s.is_tradeable or s.abs_z_score >= z_floor]
    perfect_count = sum(1 for s in filtered_setups if s.is_perfect)

    latency_ms = (time.perf_counter() - t0) * 1000.0

    scan_response = SimulatorScanResponse(
        current_date=norm_date_str,
        trading_date_used=norm_date_str,
        total_setups_found=len(tradeable_setups) if only_active_setups else len(filtered_setups),
        total_pairs_evaluated=len(filtered_setups),
        perfect_count=perfect_count,
        tradeable_count=len(tradeable_setups),
        setups=filtered_setups,
        tradeable_setups=tradeable_setups,
        scan_latency_ms=round(latency_ms, 2),
    )

    # Store in thread-safe LRU cache
    set_cached_scan(cache_key, scan_response)

    return scan_response


@router.get("/step", response_model=SimulatorStepResponse)
def step_simulation(
    current_date: str = Query(..., description="Current simulated date (YYYY-MM-DD)"),
    direction: str = Query("+1", description="Step direction: +1, -1, next, prev, +5, -5"),
    step_size: int = Query(1, ge=1, le=20),
) -> SimulatorStepResponse:
    """Step forward or backward across NYSE trading sessions."""
    engine = get_engine()
    trading_dates = engine.get_trading_dates()

    curr_ts = validate_target_date(current_date, engine)

    # Find closest trading day index
    indices = [i for i, d in enumerate(trading_dates) if d <= curr_ts]
    curr_idx = indices[-1] if indices else 0

    # Parse direction with resilience to URL encoding (+ becomes space)
    raw_dir = str(direction).strip().lower()
    if raw_dir.startswith(" ") or raw_dir.startswith("+"):
        dir_clean = "+" + raw_dir.lstrip(" +")
    elif raw_dir.isdigit():
        dir_clean = "+" + raw_dir
    elif raw_dir.startswith("-"):
        dir_clean = raw_dir
    else:
        dir_clean = raw_dir

    if dir_clean in ("+1", "next", "forward", "+"):
        delta = step_size
    elif dir_clean in ("-1", "prev", "backward", "-"):
        delta = -step_size
    elif dir_clean.startswith("+"):
        try:
            delta = int(dir_clean[1:])
        except ValueError:
            delta = step_size
    elif dir_clean.startswith("-"):
        try:
            delta = -int(dir_clean[1:])
        except ValueError:
            delta = -step_size
    else:
        delta = step_size

    new_idx = max(engine.default_lookback, min(len(trading_dates) - 1, curr_idx + delta))
    new_ts = trading_dates[new_idx]
    new_date_str = new_ts.strftime("%Y-%m-%d")

    _sim_state["current_date"] = new_date_str

    return SimulatorStepResponse(
        previous_date=current_date,
        current_date=new_date_str,
        direction=dir_clean,
        current_index=new_idx,
        total_dates=len(trading_dates),
        is_min_date=bool(new_idx <= engine.default_lookback),
        is_max_date=bool(new_idx >= len(trading_dates) - 1),
    )


@router.get("/pair-chart", response_model=PairChartResponse)
def get_pair_chart(
    ticker_a: str = Query(..., description="Primary ticker symbol"),
    ticker_b: str = Query(..., description="Hedge ticker symbol"),
    current_date: str = Query(..., description="Simulated current date T"),
    lookback_days: int = Query(90, ge=30, le=252),
    reveal: bool = Query(False, description="Reveal future trajectory (t > T)"),
    forward_days: int = Query(30, ge=5, le=90),
) -> PairChartResponse:
    """Retrieve historical chart and spread series.
    
    CRITICAL CONSTRAINT 1:
      When reveal=False, future bars (t > current_date) are COMPLETELY STRIPPED from JSON.
    """
    engine = get_engine()
    ta = ticker_a.strip().upper().replace(".", "-")
    tb = ticker_b.strip().upper().replace(".", "-")

    if ta == tb:
        raise HTTPException(400, "ticker_a and ticker_b cannot be identical.")

    t_ts = validate_target_date(current_date, engine)
    norm_date_str = t_ts.strftime("%Y-%m-%d")

    # Compute point-in-time setup using ONLY t <= T
    setup = engine.calculate_pair_pit(ta, tb, target_date=t_ts, lookback_days=lookback_days)
    if setup is None:
        raise HTTPException(404, f"Pair {ta}/{tb} has insufficient history on or before {current_date}")

    # Build historical bars strictly bounded by t <= current_date
    history_df = engine.slice_history(t_ts)
    fields = history_df.columns.levels[0].tolist()
    p_field = "Adj Close" if "Adj Close" in fields else "Close"

    price_matrix = history_df[p_field]
    if ta not in price_matrix.columns or tb not in price_matrix.columns:
        raise HTTPException(404, f"Tickers {ta} or {tb} missing in price matrix.")

    window = price_matrix[[ta, tb]].dropna().tail(lookback_days)
    beta = setup.hedge_ratio
    mu = setup.spread_mean
    sigma = setup.spread_std

    historical_bars: List[HistoricalBarSchema] = []
    for dt, row in window.iterrows():
        pa = float(row[ta])
        pb = float(row[tb])
        s = float(pa - beta * pb)
        z = float((s - mu) / sigma) if sigma > 1e-12 else 0.0

        bar_date_str = dt.strftime("%Y-%m-%d")
        # Strict enforcement: bar date must never exceed target date
        if dt > t_ts:
            raise ValueError(f"Constraint 1 Violation: Found historical bar {bar_date_str} > {norm_date_str}")

        historical_bars.append(HistoricalBarSchema(
            date=bar_date_str,
            price_a=round(clean_float(pa), 2),
            price_b=round(clean_float(pb), 2),
            spread=round(clean_float(s), 4),
            z_score=round(clean_float(z), 4),
        ))

    # Constraint 1: When reveal=False, forward data MUST BE None
    forward_bars: Optional[List[ForwardBarSchema]] = None
    forward_outcome: Optional[ForwardEvaluationResultSchema] = None

    if reveal:
        evaluator = get_evaluator()
        eval_result = evaluator.evaluate_setup(setup, max_horizon_days=forward_days)
        eval_dict = sanitize_json_data(eval_result.to_dict())

        forward_outcome = ForwardEvaluationResultSchema(**eval_dict)

        forward_bars = []
        for p in eval_result.path:
            forward_bars.append(ForwardBarSchema(
                date=p["date"],
                days_elapsed=p["days_elapsed"],
                price_a=round(clean_float(p["price_a"]), 2),
                price_b=round(clean_float(p["price_b"]), 2),
                spread=round(clean_float(p["spread"]), 4),
                z_score=round(clean_float(p["z_score"]), 4),
            ))

    setup_dict = sanitize_json_data(setup.to_dict())

    return PairChartResponse(
        ticker_a=ta,
        ticker_b=tb,
        current_date=norm_date_str,
        reveal=reveal,
        setup=PointInTimeSetupSchema(**setup_dict),
        historical_bars=historical_bars,
        forward_bars=forward_bars,
        forward_outcome=forward_outcome,
    )


@router.post("/reveal", response_model=ForwardEvaluationResultSchema)
def reveal_forward_outcome(req: RevealRequest) -> ForwardEvaluationResultSchema:
    """Evaluate forward performance (WIN/LOSS/NEUTRAL) and future trajectory for a pair."""
    engine = get_engine()
    evaluator = get_evaluator()

    ta = req.ticker_a.strip().upper().replace(".", "-")
    tb = req.ticker_b.strip().upper().replace(".", "-")

    if ta == tb:
        raise HTTPException(400, "ticker_a and ticker_b cannot be identical.")

    t_ts = validate_target_date(req.target_date, engine)

    setup = engine.calculate_pair_pit(ta, tb, target_date=t_ts, lookback_days=req.lookback_days or 90)
    if setup is None:
        raise HTTPException(404, f"Setup not found for {ta}/{tb} on {req.target_date}")

    eval_result = evaluator.evaluate_setup(setup, max_horizon_days=req.max_horizon_days or 30)
    res_dict = sanitize_json_data(eval_result.to_dict())

    return ForwardEvaluationResultSchema(**res_dict)


@router.get("/batch-scorecard", response_model=DayBatchScorecardSchema)
def get_batch_scorecard(
    target_date: str = Query(..., description="Target date (YYYY-MM-DD)"),
    max_horizon_days: int = Query(30, ge=5, le=90),
    top_n: int = Query(10, ge=1, le=50),
) -> DayBatchScorecardSchema:
    """Calculate aggregate batch scorecard (Win Rate, Profit Factor, PnL) for setups on target date."""
    engine = get_engine()
    evaluator = get_evaluator()

    t_ts = validate_target_date(target_date, engine)

    setups = engine.scan_date(target_date=t_ts, top_n=top_n, only_active_setups=False)
    scorecard = evaluator.evaluate_batch(setups, max_horizon_days=max_horizon_days)

    res_dict = sanitize_json_data(scorecard.to_dict())
    return DayBatchScorecardSchema(**res_dict)


from fastapi.responses import Response

# In-memory raw bytes cache for sub-5ms backtest responses keyed by settings
_runs_bytes_cache: Dict[str, bytes] = {}
_cached_1y_lock = threading.Lock()
_last_1y_recalc_ts: float = 0.0


@router.get("/backtest-1y")
@router.get("/v1/backtest")
def get_backtest_1y(
    period: Optional[str] = Query(None, description="Preset horizon period: 1Y, 2Y, 3Y, 5Y"),
    refresh: bool = Query(False, description="Force re-computation of walkforward backtest"),
    start_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD), min 6M, max 5Y"),
    end_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    entry_z: Optional[float] = Query(None, description="Entry Z-score barrier threshold"),
    stop_z: Optional[float] = Query(None, description="Stop-loss barrier threshold"),
    max_horizon_days: Optional[int] = Query(None, description="Maximum holding duration horizon"),
) -> Response:
    """Retrieve historical walkforward backtest results, trade list, and 10/10 metrics.
    
    Supports parameter-aware caching: loads cached results instantly (sub-5ms) if the same
    settings have already been calculated.
    """
    global _runs_bytes_cache, _last_1y_recalc_ts
    import json
    from scripts.run_1y_backtest import (
        ROOT_DIR,
        get_run_key,
        load_cached_backtest_run,
        run_1y_walkforward_backtest,
    )

    if period:
        p_up = period.strip().upper()
        if p_up == "1Y":
            s_clean = "2025-10-26"
            e_clean = "2026-10-26"
        elif p_up == "2Y":
            s_clean = "2024-10-26"
            e_clean = "2026-10-26"
        elif p_up == "3Y":
            s_clean = "2023-10-26"
            e_clean = "2026-10-26"
        elif p_up == "5Y":
            s_clean = "2021-10-27"
            e_clean = "2026-10-26"
        else:
            s_clean = (start_date or "2025-10-26").strip()
            e_clean = (end_date or "2026-10-26").strip()
    else:
        s_clean = (start_date or "2025-10-26").strip()
        e_clean = (end_date or "2026-10-26").strip()

    try:
        s_ts = pd.to_datetime(s_clean).tz_localize(None).normalize()
        e_ts = pd.to_datetime(e_clean).tz_localize(None).normalize()
    except Exception:
        raise HTTPException(400, "Invalid date format. Expected YYYY-MM-DD.")

    if e_ts <= s_ts:
        raise HTTPException(400, "end_date must be strictly after start_date.")

    calendar_days = (e_ts - s_ts).days
    if calendar_days < 180:
        raise HTTPException(
            400,
            f"Minimum backtest period is 6 months (180 calendar days). Provided: {calendar_days} days.",
        )
    if calendar_days > 1827:
        raise HTTPException(
            400,
            f"Maximum backtest period is 5 years (1826 calendar days). Provided: {calendar_days} days.",
        )

    ez = round(float(entry_z if entry_z is not None else 2.0), 2)
    sz = round(float(stop_z if stop_z is not None else 3.5), 2)
    h = int(max_horizon_days if max_horizon_days is not None else 30)
    s_str = s_ts.strftime("%Y-%m-%d")
    e_str = e_ts.strftime("%Y-%m-%d")

    run_key = get_run_key(s_str, e_str, ez, sz, h)

    with _cached_1y_lock:
        now = time.time()
        # Debounce rapid duplicate refresh calls within 3s for identical settings
        if refresh and (now - _last_1y_recalc_ts) < 3.0 and run_key in _runs_bytes_cache:
            return Response(content=_runs_bytes_cache[run_key], media_type="application/json")

        if not refresh and run_key in _runs_bytes_cache:
            return Response(content=_runs_bytes_cache[run_key], media_type="application/json")

        if not refresh:
            cached_data = load_cached_backtest_run(s_str, e_str, ez, sz, h)
            if cached_data is not None:
                cached_bytes = json.dumps(sanitize_json_data(cached_data)).encode("utf-8")
                _runs_bytes_cache[run_key] = cached_bytes
                return Response(content=cached_bytes, media_type="application/json")

        # Recalculate walkforward backtest using warm components
        try:
            result = run_1y_walkforward_backtest(
                start_date=s_str,
                end_date=e_str,
                entry_z=ez,
                stop_z=sz,
                max_horizon_days=h,
                use_cache=False,
                refresh=True,
            )
        except Exception as e:
            logger.error(f"Error executing backtest: {e}", exc_info=True)
            raise HTTPException(500, f"Error calculating backtest: {str(e)}")

        sanitized = sanitize_json_data(result)
        res_bytes = json.dumps(sanitized).encode("utf-8")
        _runs_bytes_cache[run_key] = res_bytes
        _last_1y_recalc_ts = time.time()
        return Response(content=res_bytes, media_type="application/json")


@router.post("/backtest-1y/recalculate")
def recalculate_backtest_1y(
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    entry_z: Optional[float] = Query(None),
    stop_z: Optional[float] = Query(None),
    max_horizon_days: Optional[int] = Query(None),
) -> Response:
    """Explicit POST endpoint to force recalculation of the walkforward backtest with settings."""
    return get_backtest_1y(
        refresh=True,
        start_date=start_date,
        end_date=end_date,
        entry_z=entry_z,
        stop_z=stop_z,
        max_horizon_days=max_horizon_days,
    )


@router.get("/backtest-1y/saved-runs")
def list_saved_backtest_runs() -> Dict[str, Any]:
    """Retrieve catalog list of all cached/saved backtest runs for strategy comparison."""
    from scripts.run_1y_backtest import get_saved_runs_list
    runs = get_saved_runs_list()
    return {"runs": runs, "total": len(runs)}


@router.get("/backtest-1y/run/{run_id}")
def get_saved_backtest_run_by_id(run_id: str) -> Response:
    """Retrieve a specific cached backtest run by run_id."""
    from scripts.run_1y_backtest import RUNS_CACHE_DIR
    clean_id = run_id.strip()
    file_path = RUNS_CACHE_DIR / f"{clean_id}.json"
    if not file_path.exists():
        raise HTTPException(404, f"Run '{clean_id}' not found in runs cache.")
    return Response(content=file_path.read_bytes(), media_type="application/json")


@router.delete("/backtest-1y/run/{run_id}")
def delete_saved_backtest_run(run_id: str) -> Dict[str, Any]:
    """Delete a saved backtest run from cache and manifest."""
    from scripts.run_1y_backtest import delete_saved_run, get_saved_runs_list
    clean_id = run_id.strip()
    with _cached_1y_lock:
        if clean_id in _runs_bytes_cache:
            del _runs_bytes_cache[clean_id]
        success = delete_saved_run(clean_id)
        if not success:
            raise HTTPException(404, f"Run '{clean_id}' not found.")
        remaining = get_saved_runs_list()
        return {"status": "deleted", "run_id": clean_id, "remaining": len(remaining)}


# =========================================================================== #
# Strategy v2 Endpoints (/simulator/v2/* and /api/simulator/v2/*)
# =========================================================================== #

_v2_bytes_cache: Dict[str, bytes] = {}
_v2_cache_lock = threading.Lock()


class StrategyV2RecalculateRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")
    period: Optional[str] = "1Y"
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    z_score_hurdle: Optional[float] = None
    z_score_hook_entry: Optional[float] = None
    z_score_exit_tp1: Optional[float] = None
    z_score_exit_tp2: Optional[float] = None
    z_score_stop_loss_barrier: Optional[float] = None
    half_life_multiplier: Optional[float] = None


@router.get("/v2/backtest")
def get_strategy_v2_backtest(
    period: str = Query("1Y", description="Horizon period: 1Y, 2Y, 3Y, 5Y"),
    refresh: bool = Query(False, description="Force recalculation"),
) -> Response:
    """Retrieve Strategy v2 backtest results, trade array, and staged exit diagnostics."""
    global _v2_bytes_cache
    p = period.strip().upper()
    if p not in ("1Y", "2Y", "3Y", "5Y"):
        raise HTTPException(400, f"Invalid period '{period}'. Expected 1Y, 2Y, 3Y, or 5Y.")

    cache_key = f"v2_horizon_{p}"

    with _v2_cache_lock:
        if not refresh and cache_key in _v2_bytes_cache:
            return Response(content=_v2_bytes_cache[cache_key], media_type="application/json")

        file_name = f"backtest_v2_{p.lower()}_results.json"
        from engine.config import PROJECT_ROOT
        file_path = PROJECT_ROOT / "data" / file_name

        if not refresh and file_path.exists():
            try:
                b = file_path.read_bytes()
                _v2_bytes_cache[cache_key] = b
                return Response(content=b, media_type="application/json")
            except Exception as e:
                logger.warning(f"Failed to read cached v2 file {file_path}: {e}")

        # Recalculate if refresh or file missing
        from scripts.run_v2_backtest import HORIZON_CONFIGS, run_strategy_v2_backtest
        cfg = HORIZON_CONFIGS.get(p)
        if not cfg:
            raise HTTPException(400, f"Configuration for period {p} not found.")

        try:
            res = run_strategy_v2_backtest(
                start_date=cfg["start_date"],
                end_date=cfg["end_date"],
            )
            from scripts.run_v2_backtest import save_v2_results_atomically
            save_v2_results_atomically(res, cfg["output_file"])
            sanitized = sanitize_json_data(res)
            res_bytes = json.dumps(sanitized).encode("utf-8")
            _v2_bytes_cache[cache_key] = res_bytes
            return Response(content=res_bytes, media_type="application/json")
        except Exception as err:
            logger.error(f"Error computing Strategy v2 backtest: {err}", exc_info=True)
            raise HTTPException(500, f"Error calculating Strategy v2 backtest: {str(err)}")


@router.post("/v2/recalculate")
def recalculate_strategy_v2(
    req: StrategyV2RecalculateRequest,
) -> Response:
    """Run on-the-fly custom parameter recalculation for Strategy v2."""
    p = (req.period or "1Y").strip().upper()
    from scripts.run_v2_backtest import HORIZON_CONFIGS, run_strategy_v2_backtest
    from engine.strategy_v2_engine import load_strategy_v2_config

    base_cfg = load_strategy_v2_config()
    cfg_copy = json.loads(json.dumps(base_cfg))

    if req.z_score_hurdle is not None:
        cfg_copy["divergence_triggers"]["z_score_hurdle"] = float(req.z_score_hurdle)
    if req.z_score_hook_entry is not None:
        cfg_copy["divergence_triggers"]["z_score_hook_entry"] = float(req.z_score_hook_entry)
    if req.z_score_exit_tp1 is not None:
        cfg_copy["divergence_triggers"]["z_score_exit_tp1"] = float(req.z_score_exit_tp1)
    if req.z_score_exit_tp2 is not None:
        cfg_copy["divergence_triggers"]["z_score_exit_tp2"] = float(req.z_score_exit_tp2)
    if req.z_score_stop_loss_barrier is not None:
        cfg_copy["divergence_triggers"]["z_score_stop_loss_barrier"] = float(req.z_score_stop_loss_barrier)
    if req.half_life_multiplier is not None:
        cfg_copy["trade_management"]["half_life_time_stop_multiplier"] = float(req.half_life_multiplier)

    horizon_meta = HORIZON_CONFIGS.get(p, HORIZON_CONFIGS["1Y"])
    start_date = req.start_date or horizon_meta["start_date"]
    end_date = req.end_date or horizon_meta["end_date"]

    try:
        res = run_strategy_v2_backtest(
            start_date=start_date,
            end_date=end_date,
            config=cfg_copy,
        )
        sanitized = sanitize_json_data(res)
        res_bytes = json.dumps(sanitized).encode("utf-8")
        return Response(content=res_bytes, media_type="application/json")
    except Exception as err:
        logger.error(f"Error recalculating Strategy v2: {err}", exc_info=True)
        raise HTTPException(500, f"Error recalculating Strategy v2: {str(err)}")


@router.get("/v2/trade/{trade_id}/trajectory")
def get_strategy_v2_trade_trajectory(
    trade_id: str,
    period: str = Query("1Y", description="Horizon period where trade occurred"),
) -> Dict[str, Any]:
    """Retrieve detailed time-series trajectory with Entry Hook, TP1, and Final Exit pins."""
    clean_id = trade_id.strip()
    from engine.config import PROJECT_ROOT

    periods_to_check = [period.strip().upper()] + [x for x in ("1Y", "2Y", "3Y", "5Y") if x != period.strip().upper()]

    found_trade = None
    for p in periods_to_check:
        f_path = PROJECT_ROOT / "data" / f"backtest_v2_{p.lower()}_results.json"
        if f_path.exists():
            try:
                with open(f_path, "r", encoding="utf-8") as fp:
                    data = json.load(fp)
                for t in data.get("trades", []):
                    if t.get("id") == clean_id:
                        found_trade = t
                        break
            except Exception:
                pass
        if found_trade:
            break

    if not found_trade:
        raise HTTPException(404, f"Trade with id '{clean_id}' not found.")

    trajectory = found_trade.get("trajectory", [])
    entry_pin = {
        "date": found_trade.get("entry_date"),
        "label": f"Entry Hook: {found_trade.get('direction_label')}",
        "z_score": found_trade.get("entry_z"),
        "price_a": found_trade.get("entry_price_a"),
        "price_b": found_trade.get("entry_price_b"),
    }
    tp1_pin = None
    if found_trade.get("tp1_hit"):
        tp1_pin = {
            "date": found_trade.get("tp1_date"),
            "label": f"TP1 Executed (Banked +{found_trade.get('tranche1_pnl_pct')}%)",
            "z_score": found_trade.get("tp1_z_score"),
            "days_held": found_trade.get("tp1_days_held"),
        }
    exit_pin = {
        "date": found_trade.get("exit_date"),
        "label": f"Final Exit: {found_trade.get('exit_reason')} ({found_trade.get('realized_return_pct'):+.2f}%)",
        "z_score": found_trade.get("exit_z"),
        "price_a": found_trade.get("exit_price_a"),
        "price_b": found_trade.get("exit_price_b"),
        "outcome": found_trade.get("outcome"),
    }

    return {
        "trade_id": clean_id,
        "pair_name": found_trade.get("pair_name"),
        "direction": found_trade.get("direction"),
        "direction_label": found_trade.get("direction_label"),
        "outcome": found_trade.get("outcome"),
        "exit_reason": found_trade.get("exit_reason"),
        "realized_return_pct": found_trade.get("realized_return_pct"),
        "holding_days": found_trade.get("holding_days"),
        "pins": {
            "entry": entry_pin,
            "tp1": tp1_pin,
            "exit": exit_pin,
        },
        "trajectory": trajectory,
    }


# =========================================================================== #
# Strategy Comparison Endpoints (/simulator/compare and /api/simulator/compare)
# =========================================================================== #

_compare_bytes_cache: Dict[str, bytes] = {}
_compare_cache_lock = threading.Lock()
_comparison_engine_instance = None


def get_comparison_engine():
    global _comparison_engine_instance
    if _comparison_engine_instance is None:
        from engine.strategy_comparison_engine import StrategyComparisonEngine
        _comparison_engine_instance = StrategyComparisonEngine()
    return _comparison_engine_instance


@router.get("/compare")
def get_strategy_comparison(
    period: str = Query("1Y", description="Horizon period: 1Y, 2Y, 3Y, 5Y"),
    refresh: bool = Query(False, description="Force re-computation"),
) -> Response:
    """Retrieve side-by-side Strategy v1 vs Strategy v2 delta analytics and trade diagnostics."""
    global _compare_bytes_cache
    p = period.strip().upper()
    if p not in ("1Y", "2Y", "3Y", "5Y"):
        raise HTTPException(400, f"Invalid period '{period}'. Expected 1Y, 2Y, 3Y, or 5Y.")

    with _compare_cache_lock:
        if not refresh and p in _compare_bytes_cache:
            return Response(content=_compare_bytes_cache[p], media_type="application/json")

        engine = get_comparison_engine()
        try:
            res_dict = engine.compare(p)
        except Exception as e:
            logger.error(f"Error computing strategy comparison for {p}: {e}", exc_info=True)
            raise HTTPException(500, f"Failed to compute comparison for {p}: {str(e)}")

        res_bytes = json.dumps(res_dict, default=str, allow_nan=False).encode("utf-8")
        _compare_bytes_cache[p] = res_bytes
        return Response(content=res_bytes, media_type="application/json")


# =========================================================================== #
# Strategy v3 Endpoints (/simulator/v3/* and /api/simulator/v3/*)
# =========================================================================== #

_v3_bytes_cache: Dict[str, bytes] = {}
_v3_cache_lock = threading.Lock()
_v3_engine_instance = None


def get_v3_engine():
    global _v3_engine_instance
    if _v3_engine_instance is None:
        from engine.strategy_v3_engine import StrategyV3Engine
        _v3_engine_instance = StrategyV3Engine()
    return _v3_engine_instance


class StrategyV3RecalculateRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")
    period: Optional[str] = "1Y"
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    z_score_entry: Optional[float] = None
    z_score_stop_loss: Optional[float] = None
    tier1_multiplier: Optional[float] = None
    tier3_multiplier: Optional[float] = None
    protected_stop_z: Optional[float] = None
    activation_recovery_z: Optional[float] = None
    max_holding_days: Optional[int] = None


@router.get("/v3/backtest")
def get_strategy_v3_backtest(
    period: str = Query("1Y", description="Horizon period: 1Y, 2Y, 3Y, 5Y"),
    refresh: bool = Query(False, description="Force recalculation"),
) -> Response:
    """Retrieve pre-computed Strategy v3 backtest results and performance scorecard."""
    global _v3_bytes_cache
    p = period.strip().upper()
    if p not in ("1Y", "2Y", "3Y", "5Y"):
        raise HTTPException(400, f"Invalid period '{period}'. Expected 1Y, 2Y, 3Y, or 5Y.")

    cache_key = f"v3_horizon_{p}"

    with _v3_cache_lock:
        if not refresh and cache_key in _v3_bytes_cache:
            return Response(content=_v3_bytes_cache[cache_key], media_type="application/json")

        file_name = f"backtest_v3_{p.lower()}_results.json"
        from engine.config import PROJECT_ROOT
        file_path = PROJECT_ROOT / "data" / file_name

        if not refresh and file_path.exists():
            try:
                b = file_path.read_bytes()
                _v3_bytes_cache[cache_key] = b
                return Response(content=b, media_type="application/json")
            except Exception as e:
                logger.warning(f"Failed to read cached v3 file {file_path}: {e}")

        # If file missing or refresh forced, compute on the fly
        horizon_dates = {
            "1Y": ("2025-10-26", "2026-10-26"),
            "2Y": ("2024-10-26", "2026-10-26"),
            "3Y": ("2023-10-26", "2026-10-26"),
            "5Y": ("2021-10-26", "2026-10-26"),
        }
        s_date, e_date = horizon_dates[p]
        engine = get_v3_engine()
        res_dict = engine.run_backtest(s_date, e_date)
        res_bytes = json.dumps(res_dict, default=str, allow_nan=False).encode("utf-8")
        _v3_bytes_cache[cache_key] = res_bytes
        return Response(content=res_bytes, media_type="application/json")


@router.post("/v3/recalculate")
def recalculate_strategy_v3_backtest(
    req: StrategyV3RecalculateRequest,
) -> Response:
    """Execute on-the-fly backtest simulation with custom Strategy v3 parameters."""
    from engine.strategy_v3_engine import StrategyV3Config, StrategyV3Engine
    config = StrategyV3Config.load()

    if req.z_score_entry is not None:
        config.z_score_entry = req.z_score_entry
    if req.z_score_stop_loss is not None:
        config.z_score_stop_loss = req.z_score_stop_loss
    if req.tier1_multiplier is not None:
        config.tier1_multiplier = req.tier1_multiplier
    if req.tier3_multiplier is not None:
        config.tier3_multiplier = req.tier3_multiplier
    if req.protected_stop_z is not None:
        config.protected_stop_z = req.protected_stop_z
    if req.activation_recovery_z is not None:
        config.activation_recovery_z = req.activation_recovery_z
    if req.max_holding_days is not None:
        config.max_holding_days = req.max_holding_days

    horizon_dates = {
        "1Y": ("2025-10-26", "2026-10-26"),
        "2Y": ("2024-10-26", "2026-10-26"),
        "3Y": ("2023-10-26", "2026-10-26"),
        "5Y": ("2021-10-26", "2026-10-26"),
    }
    p = (req.period or "1Y").strip().upper()
    s_date, e_date = horizon_dates.get(p, ("2025-10-26", "2026-10-26"))
    if req.start_date:
        s_date = req.start_date
    if req.end_date:
        e_date = req.end_date

    engine = StrategyV3Engine(config)
    res_dict = engine.run_backtest(s_date, e_date)
    res_bytes = json.dumps(res_dict, default=str, allow_nan=False).encode("utf-8")
    return Response(content=res_bytes, media_type="application/json")


