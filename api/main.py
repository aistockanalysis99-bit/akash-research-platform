"""FastAPI backend.

Endpoints:
  POST   /data/refresh            -- background refresh
  GET    /data/status             -- cache freshness per cached file
  GET    /universe/{name}         -- ticker list
  GET    /universes               -- list available universes
  POST   /backtest/run            -- launch backtest, returns run_id
  GET    /backtest/{run_id}       -- run summary + metrics
  GET    /backtest/{run_id}/equity
  GET    /backtest/{run_id}/trades
  GET    /backtest/{run_id}/per-symbol
  GET    /backtest/{run_id}/progress
  GET    /backtest/{run_id}/trades.csv  -- CSV export
  GET    /runs                    -- list runs
  DELETE /runs/{run_id}
  POST   /params/save
  GET    /params
  GET    /params/{name}
  DELETE /params/{name}
  POST   /compare
"""
from __future__ import annotations

import asyncio
import csv
import io
import json
import threading
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import BackgroundTasks, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse

from engine.config import API_HOST, API_PORT
from engine.core.types import BacktestConfig, StrategyParams
from engine.data.cache import list_cached, refresh_universe
from engine.data.universe import get_universe, list_universes
from engine.db import repo
from engine.db.schema import init_db
from engine.logging_setup import get_logger

from .ai_jobs import (
    ai_job_manager,
    list_decisions_on_disk,
    list_morning_dates,
    morning_job_manager,
    read_decision_files,
    read_morning_files,
)
from .jobs import job_manager

from engine.live import memory as live_memory
from engine.live import profiles as live_profiles
from engine.live import scheduler as live_scheduler
from engine.live import settings as live_settings
from engine.live import watchlist as wl
from engine.live.portfolio import VirtualPortfolio
from engine.live.telegram import recent_log as telegram_log_rows
from engine.live.telegram import telegram
from .schemas import (
    BacktestRequest,
    BacktestRunResponse,
    CompareRequest,
    EquityPointSchema,
    ParameterSetIn,
    ParameterSetOut,
    PerSymbolSchema,
    RefreshRequest,
    RunSummary,
    StrategyParamsSchema,
    TradeSchema,
)

log = get_logger("api.main")

app = FastAPI(
    title="Akash Research Platform — Backtester API",
    version="0.1.0",
    description="Trend-Following Momentum backtesting engine.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def strip_api_prefix(request, call_next):
    """The React SPA calls everything under /api/*. In production FastAPI
    serves both the API and the SPA, so we transparently strip the /api
    prefix and let the same handlers serve those requests.
    """
    path = request.scope.get("path", "")
    if path == "/api":
        request.scope["path"] = "/"
    elif path.startswith("/api/"):
        request.scope["path"] = path[4:]  # drop the leading '/api'
    return await call_next(request)


@app.on_event("startup")
async def startup() -> None:
    init_db()
    log.info("API ready at http://%s:%d", API_HOST, API_PORT)
    try:
        live_scheduler.start_scheduler()
    except Exception as e:  # noqa: BLE001 — scheduler is opt-in, never block startup
        log.warning("scheduler failed to start: %s", e)


@app.on_event("shutdown")
async def shutdown() -> None:
    try:
        live_scheduler.stop_scheduler()
    except Exception:  # noqa: BLE001
        pass


# --------------- Universe ---------------

@app.get("/universes")
async def get_universes() -> list[str]:
    return list_universes()


@app.get("/universe/{name}")
async def get_universe_endpoint(name: str) -> dict[str, Any]:
    try:
        symbols = get_universe(name)
    except ValueError as e:
        raise HTTPException(404, str(e))
    return {"name": name, "symbols": symbols, "count": len(symbols)}


# --------------- Data refresh / status ---------------

@app.post("/data/refresh")
async def refresh_data(req: RefreshRequest, bg: BackgroundTasks) -> dict[str, Any]:
    if req.symbols:
        symbols = req.symbols
        label = "custom"
    elif req.universe:
        try:
            symbols = get_universe(req.universe)
            label = req.universe
        except ValueError as e:
            raise HTTPException(400, str(e))
    else:
        raise HTTPException(400, "Either symbols or universe required.")

    job_id = str(uuid.uuid4())
    refresh_state[job_id] = {
        "status": "running",
        "done": 0,
        "total": len(symbols),
        "current_symbol": "",
        "label": label,
        "timeframe": req.timeframe,
        "started_at": datetime.utcnow().isoformat(),
    }

    def run_refresh() -> None:
        def progress(done: int, total: int, sym: str) -> None:
            refresh_state[job_id].update({"done": done, "total": total, "current_symbol": sym})

        try:
            asyncio.run(refresh_universe(
                symbols=symbols,
                timeframe=req.timeframe,
                years_back=req.years,
                incremental=not req.full,
                progress_cb=progress,
            ))
            refresh_state[job_id]["status"] = "done"
        except Exception as e:  # noqa: BLE001
            log.exception("Refresh failed")
            refresh_state[job_id].update({"status": "failed", "error": str(e)})

    threading.Thread(target=run_refresh, daemon=True).start()
    return {"job_id": job_id, "symbols": len(symbols), "label": label}


refresh_state: dict[str, dict[str, Any]] = {}


@app.get("/data/refresh/{job_id}")
async def get_refresh_status(job_id: str) -> dict[str, Any]:
    s = refresh_state.get(job_id)
    if s is None:
        raise HTTPException(404, "refresh job not found")
    return s


@app.get("/data/status")
async def data_status() -> list[dict[str, Any]]:
    out = []
    for s in list_cached():
        out.append({
            "symbol": s.symbol,
            "timeframe": s.timeframe,
            "bars": s.bars,
            "first_ts": s.first_ts.isoformat() if s.first_ts else None,
            "last_ts": s.last_ts.isoformat() if s.last_ts else None,
        })
    return out


# --------------- Backtest ---------------

@app.post("/backtest/run", response_model=BacktestRunResponse)
async def run_backtest_endpoint(req: BacktestRequest) -> BacktestRunResponse:
    # Resolve universe
    if req.custom_symbols:
        symbols = req.custom_symbols
        universe_label = "custom"
    else:
        try:
            symbols = get_universe(req.universe)
            universe_label = req.universe
        except ValueError as e:
            raise HTTPException(400, str(e))

    # Build config
    params = StrategyParams(**req.params.model_dump())
    config = BacktestConfig(
        universe=symbols,
        start_date=req.start_date,
        end_date=req.end_date,
        timeframe=req.timeframe,
        initial_capital=req.initial_capital,
        params=params,
        run_name=req.run_name,
        universe_name=universe_label,
    )
    run_id = str(uuid.uuid4())
    run_name = req.run_name or _auto_run_name(config)
    job_manager.submit_backtest(run_id, run_name, config)
    return BacktestRunResponse(run_id=run_id, name=run_name, status="running", progress=0.0)


@app.get("/backtest/{run_id}", response_model=RunSummary)
async def get_backtest(run_id: str) -> RunSummary:
    row = repo.get_run(run_id)
    if not row:
        raise HTTPException(404, "run not found")
    return RunSummary(
        id=row["id"],
        name=row.get("name"),
        status=row.get("status", ""),
        progress=row.get("progress", 0.0) or 0.0,
        progress_msg=row.get("progress_msg"),
        started_at=row.get("started_at"),
        finished_at=row.get("finished_at"),
        timeframe=row.get("timeframe", ""),
        universe_name=row.get("universe_name"),
        initial_capital=row.get("initial_capital", 0.0) or 0.0,
        metrics=row.get("metrics", {}) or {},
        error_message=row.get("error_message"),
    )


@app.get("/backtest/{run_id}/progress")
async def get_progress(run_id: str) -> dict[str, Any]:
    p = job_manager.get_progress(run_id)
    row = repo.get_run(run_id)
    return {
        "run_id": run_id,
        "progress": p.get("progress", 0.0),
        "msg": p.get("msg", ""),
        "status": (row or {}).get("status", "unknown"),
    }


@app.get("/backtest/{run_id}/equity", response_model=list[EquityPointSchema])
async def get_equity(run_id: str) -> list[EquityPointSchema]:
    rows = repo.get_equity_curve(run_id)
    return [EquityPointSchema(**r) for r in rows]


@app.get("/backtest/{run_id}/trades", response_model=list[TradeSchema])
async def get_trades(
    run_id: str,
    symbol: Optional[str] = None,
    exit_reason: Optional[str] = None,
    limit: int = Query(5000, le=20000),
    offset: int = 0,
) -> list[TradeSchema]:
    rows = repo.get_trades(run_id, symbol=symbol, exit_reason=exit_reason, limit=limit, offset=offset)
    return [TradeSchema(**r) for r in rows]


@app.get("/backtest/{run_id}/trades.csv")
async def get_trades_csv(run_id: str) -> StreamingResponse:
    rows = repo.get_trades(run_id, limit=100000)
    if not rows:
        raise HTTPException(404, "no trades")
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=list(rows[0].keys()))
    writer.writeheader()
    for r in rows:
        writer.writerow(r)
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="trades_{run_id}.csv"'},
    )


@app.get("/backtest/{run_id}/per-symbol", response_model=list[PerSymbolSchema])
async def get_per_symbol(run_id: str) -> list[PerSymbolSchema]:
    rows = repo.get_per_symbol_stats(run_id)
    return [PerSymbolSchema(**r) for r in rows]


@app.get("/runs", response_model=list[RunSummary])
async def list_runs(limit: int = 200, offset: int = 0) -> list[RunSummary]:
    rows = repo.list_runs(limit=limit, offset=offset)
    return [
        RunSummary(
            id=r["id"],
            name=r.get("name"),
            status=r.get("status", ""),
            progress=r.get("progress", 0.0) or 0.0,
            progress_msg=r.get("progress_msg"),
            started_at=r.get("started_at"),
            finished_at=r.get("finished_at"),
            timeframe=r.get("timeframe", ""),
            universe_name=r.get("universe_name"),
            initial_capital=r.get("initial_capital", 0.0) or 0.0,
            metrics=r.get("metrics", {}) or {},
            error_message=r.get("error_message"),
        )
        for r in rows
    ]


@app.delete("/runs/{run_id}")
async def delete_run(run_id: str) -> dict[str, bool]:
    ok = repo.delete_run(run_id)
    if not ok:
        raise HTTPException(404, "run not found")
    return {"deleted": True}


# --------------- Parameter sets ---------------

@app.post("/params/save", response_model=ParameterSetOut)
async def save_param_set(p: ParameterSetIn) -> ParameterSetOut:
    params = StrategyParams(**p.params.model_dump())
    repo.save_parameter_set(p.name, params)
    sets = repo.list_parameter_sets()
    found = next((s for s in sets if s["name"] == p.name), None)
    if not found:
        raise HTTPException(500, "save failed")
    return ParameterSetOut(
        id=found["id"], name=found["name"],
        params=StrategyParamsSchema(**found["params"]),
        created_at=found["created_at"],
    )


@app.get("/params", response_model=list[ParameterSetOut])
async def list_params() -> list[ParameterSetOut]:
    sets = repo.list_parameter_sets()
    return [
        ParameterSetOut(
            id=s["id"], name=s["name"],
            params=StrategyParamsSchema(**s["params"]),
            created_at=s["created_at"],
        )
        for s in sets
    ]


@app.get("/params/{name}", response_model=ParameterSetOut)
async def get_param_set(name: str) -> ParameterSetOut:
    p = repo.get_parameter_set(name)
    if not p:
        raise HTTPException(404, "not found")
    sets = repo.list_parameter_sets()
    found = next((s for s in sets if s["name"] == name), None)
    return ParameterSetOut(
        id=found["id"], name=found["name"],
        params=StrategyParamsSchema(**found["params"]),
        created_at=found["created_at"],
    )


@app.delete("/params/{name}")
async def delete_param_set(name: str) -> dict[str, bool]:
    ok = repo.delete_parameter_set(name)
    if not ok:
        raise HTTPException(404, "not found")
    return {"deleted": True}


# --------------- Compare ---------------

@app.post("/compare")
async def compare(req: CompareRequest) -> dict[str, Any]:
    if not req.run_ids or len(req.run_ids) < 2:
        raise HTTPException(400, "Need at least 2 run_ids")
    if len(req.run_ids) > 5:
        raise HTTPException(400, "Max 5 runs per comparison")
    out = []
    for rid in req.run_ids:
        row = repo.get_run(rid)
        if not row:
            continue
        eq = repo.get_equity_curve(rid)
        out.append({
            "run_id": rid,
            "name": row.get("name"),
            "metrics": row.get("metrics", {}),
            "equity": eq,
        })
    return {"runs": out}


# --------------- AI Pipeline ---------------


@app.post("/ai/analyze")
async def ai_analyze(payload: dict[str, Any]) -> dict[str, str]:
    """Kick off a full 6-agent pipeline run for a symbol."""
    symbol = (payload.get("symbol") or "").strip().upper()
    if not symbol:
        raise HTTPException(400, "symbol required")
    source = payload.get("source", "manual")
    if source not in ("manual", "quant", "external"):
        raise HTTPException(400, "source must be one of: manual, quant, external")
    notes = payload.get("notes") or None
    job_id = ai_job_manager.submit(symbol, source, notes)
    return {"job_id": job_id, "symbol": symbol, "status": "queued"}


@app.get("/ai/analyze/{job_id}")
async def ai_get_job(job_id: str) -> dict[str, Any]:
    j = ai_job_manager.get(job_id)
    if j is None:
        raise HTTPException(404, "job not found")
    return j


@app.get("/ai/jobs")
async def ai_list_jobs() -> list[dict[str, Any]]:
    return ai_job_manager.list()


@app.get("/ai/decisions")
async def ai_list_decisions() -> list[dict[str, Any]]:
    """List every (symbol, date) folder under AI_RESEARCH_DIR."""
    return list_decisions_on_disk()


@app.get("/ai/decisions/{symbol}/{date_iso}")
async def ai_get_decision(symbol: str, date_iso: str) -> dict[str, str]:
    """Return all markdown stages for one (symbol, date)."""
    try:
        return read_decision_files(symbol, date_iso)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))


@app.get("/ai/decisions/{symbol}/{date_iso}/scorecards")
async def ai_get_scorecards(symbol: str, date_iso: str) -> list[dict[str, Any]]:
    """Per-agent scorecards parsed from _raw.json — for the dashboard.

    Returns one entry per agent with the agent name, a numerical score,
    a one-line summary, a stage label, and the markdown stage file the
    decision-detail page can navigate to.
    """
    from engine.config import AI_RESEARCH_DIR
    raw_path = AI_RESEARCH_DIR / symbol.upper() / date_iso / "_raw.json"
    if not raw_path.exists():
        raise HTTPException(404, f"No raw state for {symbol} on {date_iso}")
    try:
        raw = json.loads(raw_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise HTTPException(500, f"raw.json corrupt: {e}")

    cards: list[dict[str, Any]] = []

    def add(name: str, emoji: str, label: str, score_label: str,
             score_value: Any, summary: str, stage: str) -> None:
        cards.append({
            "name": name,
            "emoji": emoji,
            "label": label,
            "score_label": score_label,
            "score_value": score_value,
            # Full summary — the agents already cap these at ~1000 chars in
            # their schemas. Do NOT truncate here (was cutting mid-sentence).
            "summary": (summary or "").strip(),
            "stage": stage,
        })

    fund = raw.get("fundamental") or {}
    if fund:
        add("fundamental", "📊", "Fundamental Analyst",
            "score", fund.get("fundamental_score"),
            fund.get("summary"), "fundamental")

    news = raw.get("news") or {}
    if news:
        add("news", "📰", "News Analyst",
            "risk", news.get("news_risk_score"),
            news.get("summary"), "news")

    tech = raw.get("technical") or {}
    if tech:
        add("technical", "📈", "Technical Analyst",
            "strength", tech.get("technical_strength"),
            tech.get("summary"), "technical")

    inst = raw.get("institutional_flow") or {}
    if inst:
        add("institutional_flow", "🏦", "Institutional Flow",
            "smart $", inst.get("smart_money_score"),
            inst.get("summary"), "institutional_flow")

    opts = raw.get("options_structure") or {}
    if opts:
        add("options_structure", "📉", "Options Structure",
            "dealer", opts.get("dealer_positioning"),
            opts.get("summary"), "options_structure")

    macro = raw.get("macro_regime") or {}
    if macro:
        add("macro_regime", "🌐", "Macro Regime",
            "risk", macro.get("regime_risk_score"),
            macro.get("summary"), "macro_regime")

    bull = raw.get("bull") or {}
    if bull:
        # Single strongest argument — concise + complete for the tile.
        # The full 4-pillar case is in the expandable report below.
        add("bull", "🟢", "Bull Researcher",
            "conviction", bull.get("conviction_self_rated"),
            bull.get("strongest_point") or bull.get("business_quality"), "bull")

    bear = raw.get("bear") or {}
    if bear:
        add("bear", "🔴", "Bear Researcher",
            "conviction", bear.get("conviction_self_rated"),
            bear.get("strongest_point") or bear.get("biggest_weakness"), "bear")

    judge = raw.get("judge") or {}
    if judge:
        add("judge", "⚖️", "Debate Judge",
            "winner", judge.get("winner"),
            judge.get("synthesis") or judge.get("deciding_factor"), "judge")

    risk = raw.get("risk") or {}
    if risk:
        risk_summary = risk.get("reasoning") or risk.get("deterministic_block_reason")
        if risk.get("rules_triggered"):
            risk_summary = f"Rules: {', '.join(risk['rules_triggered'][:3])} · {risk_summary or ''}"
        add("risk", "🛡️", "Risk Manager",
            "verdict", risk.get("verdict"),
            risk_summary, "risk_manager")

    pm = raw.get("pm") or {}
    if pm:
        pm_summary = pm.get("audit_note") or pm.get("exit_thesis") or ""
        cards.append({
            "name": "pm",
            "emoji": "👔",
            "label": "Portfolio Manager",
            "score_label": "decision",
            "score_value": pm.get("decision"),
            "summary": pm_summary.strip(),
            "stage": "pm",
            # Expose the telegram messages so the frontend can show them.
            "telegram_message": (pm.get("telegram_message") or "").strip(),
            "telegram_portfolio_message": (pm.get("telegram_portfolio_message") or "").strip(),
        })

    return cards


# --------------- Morning Cycle (Path A) ---------------


@app.post("/ai/morning/run")
async def ai_morning_run() -> dict[str, str]:
    job_id = morning_job_manager.submit()
    return {"job_id": job_id, "status": "queued"}


@app.get("/ai/morning/jobs")
async def ai_morning_jobs() -> list[dict[str, Any]]:
    return morning_job_manager.list()


@app.get("/ai/morning/jobs/{job_id}")
async def ai_morning_job(job_id: str) -> dict[str, Any]:
    j = morning_job_manager.get(job_id)
    if j is None:
        raise HTTPException(404, "morning job not found")
    return j


@app.get("/ai/morning/dates")
async def ai_morning_dates() -> list[str]:
    return list_morning_dates()


@app.get("/ai/morning/{date_iso}")
async def ai_morning_files(date_iso: str) -> dict[str, str]:
    files = read_morning_files(date_iso)
    if not files:
        raise HTTPException(404, f"no morning artifacts for {date_iso}")
    return files


# --------------- Virtual Portfolio (Phase 3) ---------------


@app.get("/portfolio/snapshot")
async def portfolio_snapshot() -> dict[str, Any]:
    p = VirtualPortfolio()
    try:
        return p.equity_snapshot()
    finally:
        p.close_conn()


@app.get("/portfolio/open")
async def portfolio_open() -> list[dict[str, Any]]:
    p = VirtualPortfolio()
    try:
        return p.list_open()
    finally:
        p.close_conn()


@app.get("/portfolio/closed")
async def portfolio_closed(limit: int = 200) -> list[dict[str, Any]]:
    p = VirtualPortfolio()
    try:
        return p.list_closed(limit=limit)
    finally:
        p.close_conn()


@app.get("/portfolio/today")
async def portfolio_today() -> list[dict[str, Any]]:
    p = VirtualPortfolio()
    try:
        return p.list_today()
    finally:
        p.close_conn()


@app.post("/portfolio/refresh")
async def portfolio_refresh() -> dict[str, Any]:
    """Re-fetch the latest close price for every open position; update P&L; auto-close stops."""
    p = VirtualPortfolio()
    try:
        summary = await p.refresh_all()
    finally:
        p.close_conn()
    return summary


@app.post("/portfolio/close/{position_id}")
async def portfolio_close(position_id: int, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    reason = (payload or {}).get("reason", "manual")
    p = VirtualPortfolio()
    try:
        ok = p.manual_close(position_id, exit_reason=reason)
    finally:
        p.close_conn()
    if not ok:
        raise HTTPException(404, "position not found or already closed")
    return {"closed": True, "position_id": position_id}


@app.post("/portfolio/reopen/{position_id}")
async def portfolio_reopen(position_id: int) -> dict[str, Any]:
    """Undo a close — reopen a closed position and reverse its cash proceeds."""
    p = VirtualPortfolio()
    try:
        ok = p.reopen_position(position_id)
    finally:
        p.close_conn()
    if not ok:
        raise HTTPException(404, "position not found or not closed")
    return {"reopened": True, "position_id": position_id}


@app.post("/portfolio/close-all")
async def portfolio_close_all() -> dict[str, Any]:
    """Close every open position at current last-known price."""
    p = VirtualPortfolio()
    try:
        n = p.close_all(exit_reason="manual_close_all")
    finally:
        p.close_conn()
    return {"closed_count": n}


@app.get("/portfolio/history")
async def portfolio_history(limit: int = 400) -> list[dict[str, Any]]:
    """Daily portfolio value snapshots for the value-over-time chart."""
    p = VirtualPortfolio()
    try:
        hist = p.equity_history(limit=limit)
        # If empty, seed with a snapshot of the current state so the chart
        # isn't blank on first load.
        if not hist:
            p.record_equity_snapshot()
            hist = p.equity_history(limit=limit)
    finally:
        p.close_conn()
    return hist


@app.post("/portfolio/buy")
async def portfolio_buy(payload: dict[str, Any]) -> dict[str, Any]:
    """Manual market-buy: {symbol, amount_usd}. Fetches current price, opens position."""
    symbol = str(payload.get("symbol", "")).upper().strip()
    amount = float(payload.get("amount_usd", 0) or 0)
    if not symbol or amount <= 0:
        raise HTTPException(400, "symbol and positive amount_usd required")

    from engine.live.portfolio import fetch_latest_close
    price = await fetch_latest_close(symbol)
    if price is None or price <= 0:
        raise HTTPException(400, f"could not fetch a price for {symbol}")

    p = VirtualPortfolio()
    try:
        max_pos = live_settings.get_max_positions()
        if len(p.list_open()) >= max_pos and not p.has_open_for_symbol(symbol):
            raise HTTPException(
                400,
                f"Portfolio is at its {max_pos}-position maximum. "
                f"Raise the limit in Settings or remove a position first.",
            )
        pos_id = p.create_manual(symbol, amount, price)
    finally:
        p.close_conn()
    if pos_id is None:
        raise HTTPException(400, f"{symbol} is already held or the buy was rejected")
    return {"position_id": pos_id, "symbol": symbol, "price": price,
            "units": round(amount / price, 4)}


@app.get("/portfolio/quote/{symbol}")
async def portfolio_quote(symbol: str) -> dict[str, Any]:
    """Live quote + company name for the position-entry form (validate ticker,
    auto-fill current price)."""
    symbol = symbol.upper().strip()
    if not symbol:
        raise HTTPException(400, "symbol required")
    from engine.data.fmp_client import FMPClient
    from engine.live.data.fmp_research import FMPResearchClient
    name = None
    sector = None
    price = None
    try:
        async with FMPClient() as fmp:
            research = FMPResearchClient(fmp)
            prof = await research.fetch_profile(symbol)
            data = prof.data or {}
            name = data.get("companyName")
            sector = data.get("sector")
            price = data.get("price")
            if price is None:
                df = await fmp.fetch_daily(symbol)
                if df is not None and not df.empty:
                    price = float(df["close"].iloc[-1])
    except Exception as e:  # noqa: BLE001
        raise HTTPException(404, f"no quote for {symbol}: {str(e)[:120]}")
    if not price or price <= 0:
        raise HTTPException(404, f"no price found for {symbol}")
    return {"symbol": symbol, "name": name, "sector": sector, "price": float(price)}


@app.get("/quote/{symbol}/bars")
async def quote_bars(symbol: str, days: int = 130) -> list[dict[str, Any]]:
    """Recent daily closes for any symbol — powers the decision PDF price chart."""
    symbol = symbol.upper().strip()
    if not symbol:
        raise HTTPException(400, "symbol required")
    from engine.data.fmp_client import FMPClient
    try:
        async with FMPClient() as fmp:
            df = await fmp.fetch_daily(symbol)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(404, f"no bars for {symbol}: {str(e)[:120]}")
    if df is None or df.empty:
        return []
    df = df.tail(max(10, min(int(days), 400)))
    return [
        {"date": str(ts)[:10], "close": round(float(c), 2)}
        for ts, c in zip(df["timestamp"], df["close"])
    ]


@app.post("/portfolio/reset")
async def portfolio_reset(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    """Wipe ALL positions + equity history and set the cash balance.
    Use before importing a real account for a clean slate.
    """
    payload = payload or {}
    from engine.db.schema import get_connection
    conn = get_connection()
    try:
        n_pos = conn.execute("SELECT COUNT(*) FROM virtual_positions").fetchone()[0]
        conn.execute("DELETE FROM virtual_positions")
        conn.execute("DELETE FROM portfolio_equity_history")
        conn.commit()
    finally:
        conn.close()

    # Accept `cash` (new model) or legacy `initial_capital` as the cash seed.
    cash = payload.get("cash", payload.get("initial_capital"))
    if cash is not None:
        try:
            live_settings.set_cash_balance(float(cash))
        except Exception as e:  # noqa: BLE001
            raise HTTPException(400, f"bad cash value: {e}")

    return {
        "reset": True,
        "positions_cleared": int(n_pos),
        "cash": live_settings.get_cash_balance(),
    }


@app.post("/portfolio/cash")
async def portfolio_set_cash(payload: dict[str, Any]) -> dict[str, Any]:
    """Set the editable cash balance without touching positions."""
    if "cash" not in payload:
        raise HTTPException(400, "cash required")
    try:
        live_settings.set_cash_balance(float(payload["cash"]))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(400, f"bad cash value: {e}")
    return {"cash": live_settings.get_cash_balance()}


@app.post("/portfolio/import")
async def portfolio_import(payload: dict[str, Any]) -> dict[str, Any]:
    """Bulk-import existing real-account holdings.

    Body: {positions: [{symbol, shares, entry_price, entry_date?}]}
    Fetches a live quote per symbol so current P&L is real. Returns a
    per-row result (added / skipped / error).
    """
    rows = payload.get("positions") or []
    if not isinstance(rows, list) or not rows:
        raise HTTPException(400, "positions[] required")

    stock_syms = {str(r.get("symbol", "")).upper().strip()
                  for r in rows if (r.get("instrument_type") or "stock") != "option"
                  and r.get("symbol")}
    option_rows = [r for r in rows if (r.get("instrument_type") or "stock") == "option"]

    # Stock quotes via FMP (parallel)
    quotes: dict[str, float] = {}
    if stock_syms:
        from engine.data.fmp_client import FMPClient
        async with FMPClient() as fmp:
            async def q(sym: str) -> tuple[str, float | None]:
                try:
                    df = await fmp.fetch_daily(sym)
                    if df is not None and not df.empty:
                        return sym, float(df["close"].iloc[-1])
                except Exception:  # noqa: BLE001
                    pass
                return sym, None
            for sym, price in await asyncio.gather(*[q(s) for s in stock_syms]):
                if price is not None:
                    quotes[sym] = price

    # Option premiums via UW (per contract)
    opt_marks: dict[int, float] = {}  # index in rows -> premium
    if option_rows:
        from engine.live.data.unusual_whales import UnusualWhalesClient, UWError
        try:
            async with UnusualWhalesClient() as uw:
                async def oq(idx: int, r: dict) -> tuple[int, float | None]:
                    try:
                        m = await uw.fetch_option_quote(
                            str(r.get("symbol")), str(r.get("expiry") or ""),
                            float(r.get("strike") or 0), str(r.get("option_type") or "call"),
                        )
                        return idx, m
                    except Exception:  # noqa: BLE001
                        return idx, None
                idx_rows = [(i, r) for i, r in enumerate(rows)
                            if (r.get("instrument_type") or "stock") == "option"]
                for idx, m in await asyncio.gather(*[oq(i, r) for i, r in idx_rows]):
                    if m is not None:
                        opt_marks[idx] = m
        except UWError as e:
            log.warning("UW unavailable for option import marks: %s", e)

    results: list[dict[str, Any]] = []
    p = VirtualPortfolio()
    try:
        max_pos = live_settings.get_max_positions()
        open_count = len(p.list_open())
        for idx, r in enumerate(rows):
            sym = str(r.get("symbol", "")).upper().strip()
            is_opt = (r.get("instrument_type") or "stock") == "option"
            label = sym
            try:
                if open_count >= max_pos:
                    results.append({"symbol": sym or "?", "status": "skipped",
                                    "detail": f"portfolio at its {max_pos}-position max — "
                                              "raise the limit in Settings"})
                    continue
                shares = float(r.get("shares", 0) or 0)
                entry_price = float(r.get("entry_price", 0) or 0)
                entry_date = r.get("entry_date") or None
                if not sym or shares <= 0 or entry_price <= 0:
                    results.append({"symbol": sym or "?", "status": "error",
                                    "detail": "symbol, shares/contracts, entry price required"})
                    continue
                if is_opt:
                    otype = str(r.get("option_type") or "call")
                    strike = float(r.get("strike") or 0)
                    expiry = str(r.get("expiry") or "")
                    label = f"{sym} ${strike:g}{otype[0].upper()} {expiry}"
                    if strike <= 0 or not expiry:
                        results.append({"symbol": label, "status": "error",
                                        "detail": "option needs strike + expiry"})
                        continue
                    pos_id = p.import_position(
                        sym, shares, entry_price, entry_date,
                        current_price=opt_marks.get(idx),
                        instrument_type="option", option_type=otype,
                        strike=strike, expiry=expiry,
                    )
                    mark = opt_marks.get(idx)
                else:
                    pos_id = p.import_position(
                        sym, shares, entry_price, entry_date,
                        current_price=quotes.get(sym),
                    )
                    mark = quotes.get(sym)
                if pos_id is None:
                    results.append({"symbol": label, "status": "skipped",
                                    "detail": "already held or invalid"})
                else:
                    open_count += 1
                    results.append({"symbol": label, "status": "added",
                                    "position_id": pos_id, "price": mark})
            except Exception as e:  # noqa: BLE001
                results.append({"symbol": label or "?", "status": "error", "detail": str(e)[:120]})
        p.record_equity_snapshot()
    finally:
        p.close_conn()

    added = sum(1 for r in results if r["status"] == "added")
    return {"added": added, "total": len(results), "results": results}


@app.get("/portfolio/position/{position_id}")
async def portfolio_position_detail(position_id: int) -> dict[str, Any]:
    """Full detail for one holding: the position, ~90d price bars, and the
    AI decision context (target, conviction, rationale) that opened it.
    """
    p = VirtualPortfolio()
    try:
        pos = p.get(position_id)
    finally:
        p.close_conn()
    if pos is None:
        raise HTTPException(404, "position not found")

    symbol = pos["symbol"]

    # Price bars for the chart
    bars: list[dict[str, Any]] = []
    try:
        from engine.data.fmp_client import FMPClient
        async with FMPClient() as fmp:
            df = await fmp.fetch_daily(symbol)
        if df is not None and not df.empty:
            tail = df.tail(120)
            bars = [
                {"date": str(r["timestamp"])[:10], "close": float(r["close"])}
                for _, r in tail.iterrows()
            ]
    except Exception as e:  # noqa: BLE001
        log.warning("position detail bars failed for %s: %s", symbol, e)

    # AI decision context (if this came from an AI verdict)
    ai: dict[str, Any] | None = None
    dsym = pos.get("decision_symbol")
    ddate = pos.get("decision_date")
    if dsym and ddate:
        from engine.config import AI_RESEARCH_DIR
        raw_path = AI_RESEARCH_DIR / str(dsym).upper() / str(ddate) / "_raw.json"
        if raw_path.exists():
            try:
                raw = json.loads(raw_path.read_text(encoding="utf-8"))
                pm = raw.get("pm") or {}
                bull = raw.get("bull") or {}
                rationale = pm.get("investment_rationale") or {}
                ai = {
                    "decision_date": ddate,
                    "verdict": pm.get("decision"),
                    "conviction": pm.get("conviction_score"),
                    "target_6m_usd": bull.get("price_target_6m_usd"),
                    "upside_pct": bull.get("upside_pct"),
                    "why_now": rationale.get("why_now"),
                    "exit_thesis": pm.get("exit_thesis"),
                }
            except Exception:  # noqa: BLE001
                ai = None

    return {"position": pos, "bars": bars, "ai": ai}


@app.post("/portfolio/position/{position_id}/add")
async def portfolio_position_add(position_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    """Buy more of an existing holding at the latest price."""
    amount = float(payload.get("amount_usd", 0) or 0)
    if amount <= 0:
        raise HTTPException(400, "positive amount_usd required")
    p = VirtualPortfolio()
    try:
        pos = p.get(position_id)
        if pos is None:
            raise HTTPException(404, "position not found")
        from engine.live.portfolio import fetch_latest_close
        price = await fetch_latest_close(pos["symbol"])
        if price is None or price <= 0:
            raise HTTPException(400, "could not fetch price")
        ok = p.add_to_position(position_id, amount, price)
    finally:
        p.close_conn()
    if not ok:
        raise HTTPException(400, "add failed")
    return {"ok": True, "price": price}


@app.post("/portfolio/position/{position_id}/trim")
async def portfolio_position_trim(position_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    """Sell a fraction (0-1) of a holding at the latest price."""
    fraction = float(payload.get("fraction", 0) or 0)
    if not (0 < fraction <= 1):
        raise HTTPException(400, "fraction must be between 0 and 1")
    p = VirtualPortfolio()
    try:
        pos = p.get(position_id)
        if pos is None:
            raise HTTPException(404, "position not found")
        from engine.live.portfolio import fetch_latest_close
        price = await fetch_latest_close(pos["symbol"])
        if price is None or price <= 0:
            raise HTTPException(400, "could not fetch price")
        ok = p.trim_position(position_id, fraction, price)
    finally:
        p.close_conn()
    if not ok:
        raise HTTPException(400, "trim failed")
    return {"ok": True, "price": price, "fraction": fraction}


# --------------- Watchlist (Phase 4) ---------------


@app.get("/watchlist")
async def watchlist_list() -> list[dict[str, Any]]:
    return wl.list_all()


@app.post("/watchlist")
async def watchlist_add(payload: dict[str, Any]) -> dict[str, Any]:
    sym = (payload.get("symbol") or "").strip().upper()
    if not sym:
        raise HTTPException(400, "symbol required")
    notes = payload.get("notes")
    added = wl.add_symbol(sym, notes)
    return {"symbol": sym, "added": added}


@app.delete("/watchlist/{symbol}")
async def watchlist_remove(symbol: str) -> dict[str, Any]:
    ok = wl.remove_symbol(symbol)
    if not ok:
        raise HTTPException(404, "symbol not in watchlist")
    return {"symbol": symbol.upper(), "removed": True}


@app.post("/watchlist/{symbol}/toggle")
async def watchlist_toggle(symbol: str, payload: dict[str, Any]) -> dict[str, Any]:
    enabled = bool(payload.get("enabled", True))
    ok = wl.set_enabled(symbol, enabled)
    if not ok:
        raise HTTPException(404, "symbol not in watchlist")
    return {"symbol": symbol.upper(), "enabled": enabled}


# --------------- Scheduler (Phase 4) ---------------


@app.get("/scheduler/status")
async def scheduler_status() -> dict[str, Any]:
    return live_scheduler.get_status()


@app.post("/scheduler/start")
async def scheduler_start() -> dict[str, Any]:
    """Force-start the scheduler (UI button). Persists enable=true."""
    live_settings.set_many({"enable_scheduler": "true"})
    live_scheduler.start_scheduler(force=True)
    return live_scheduler.get_status()


@app.post("/scheduler/stop")
async def scheduler_stop() -> dict[str, Any]:
    """Stop the scheduler. Persists enable=false."""
    live_settings.set_many({"enable_scheduler": "false"})
    live_scheduler.stop_scheduler()
    return live_scheduler.get_status()


@app.post("/scheduler/restart")
async def scheduler_restart() -> dict[str, Any]:
    """Rebuild the scheduler from current settings (after editing times)."""
    live_scheduler.restart_scheduler()
    return live_scheduler.get_status()


@app.post("/scheduler/run/morning")
async def scheduler_run_morning() -> dict[str, Any]:
    job_id = await live_scheduler.trigger_morning_now()
    return {"job_id": job_id, "kind": "morning"}


@app.post("/scheduler/run/evening")
async def scheduler_run_evening() -> dict[str, Any]:
    return await live_scheduler.trigger_evening_now()


@app.post("/scheduler/run/weekly")
async def scheduler_run_weekly() -> dict[str, Any]:
    return await live_scheduler.trigger_weekly_now()


@app.post("/scheduler/quant-scan")
async def scheduler_quant_scan() -> list[dict[str, Any]]:
    """Run the quant scanner and return today's candidates (don't submit)."""
    return await live_scheduler.trigger_quant_scan_now()


# --------------- AI Memory (Phase 4) ---------------


@app.get("/memory/lessons")
async def memory_lessons(limit: int = 100) -> list[dict[str, Any]]:
    return live_memory.list_recent(limit=limit)


@app.get("/memory/pending")
async def memory_pending() -> list[dict[str, Any]]:
    """Closed positions whose Reflector hasn't written a lesson yet."""
    return live_memory.list_pending_reflection()


@app.post("/memory/reflect")
async def memory_reflect() -> dict[str, Any]:
    """Run Reflector on every pending closed position."""
    from engine.live.agents.reflector import reflect_on_position

    pending = live_memory.list_pending_reflection()
    saved = 0
    failed = 0
    for pos in pending:
        try:
            refl = await reflect_on_position(pos)
            if refl is not None:
                live_memory.save_lesson(refl)
                saved += 1
            else:
                failed += 1
        except Exception:  # noqa: BLE001
            failed += 1
    return {"pending": len(pending), "saved": saved, "failed": failed}


# --------------- Weekly review (Phase 4) ---------------


@app.get("/ai/weekly")
async def ai_weekly_list() -> list[str]:
    """List week_end ISO dates that have a weekly review on disk."""
    from engine.config import AI_RESEARCH_DIR
    folder = AI_RESEARCH_DIR / "_weekly"
    if not folder.exists():
        return []
    return sorted(
        (p.name for p in folder.iterdir() if p.is_dir()), reverse=True,
    )


@app.get("/ai/weekly/{date_iso}")
async def ai_weekly_get(date_iso: str) -> dict[str, str]:
    from engine.config import AI_RESEARCH_DIR
    folder = AI_RESEARCH_DIR / "_weekly" / date_iso
    if not folder.exists():
        raise HTTPException(404, f"no weekly review for {date_iso}")
    out: dict[str, str] = {}
    for p in sorted(folder.glob("*.md")):
        out[p.stem] = p.read_text(encoding="utf-8")
    return out


# --------------- Live Settings (Phase 4) ---------------


@app.get("/settings")
async def settings_get() -> dict[str, Any]:
    return live_settings.get_all()


@app.post("/settings")
async def settings_update(payload: dict[str, Any]) -> dict[str, Any]:
    """Bulk update. Unknown keys silently dropped (whitelist enforced).

    If any scheduler-affecting key is updated, the scheduler is rebuilt
    so the new times take effect immediately.
    """
    result = live_settings.set_many(payload)
    scheduler_keys = {
        "scheduler_timezone", "scheduler_morning_hour", "scheduler_morning_minute",
        "scheduler_evening_hour", "scheduler_evening_minute",
        "scheduler_evening_gap_secs", "enable_scheduler",
    }
    if any(k in scheduler_keys for k in result["applied"]):
        if live_settings.get_scheduler_enabled():
            live_scheduler.restart_scheduler()
        else:
            live_scheduler.stop_scheduler()
    return result


# --------------- Model Lab (Compare Mode) ---------------


@app.get("/compare/models")
async def compare_models() -> list[dict[str, Any]]:
    """The models available to test in Compare Mode."""
    from engine.live.compare import MODELS
    return MODELS


@app.post("/compare/run")
async def compare_run(payload: dict[str, Any]) -> dict[str, Any]:
    """Run the same stock analysis through several models, side by side.

    Body: {symbol, models: [keys]}. Returns the shared data bundle + per-model
    structured verdicts + cost/latency.
    """
    symbol = str(payload.get("symbol", "")).upper().strip()
    if not symbol:
        raise HTTPException(400, "symbol required")
    model_keys = payload.get("models") or []
    from engine.config import OPENROUTER_API_KEY
    if not OPENROUTER_API_KEY:
        raise HTTPException(400, "OPENROUTER_API_KEY not configured on the server")
    from engine.live.compare import run_compare
    try:
        return await run_compare(symbol, model_keys)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(500, f"compare failed: {str(e)[:200]}")


@app.post("/compare/full")
async def compare_full_start(payload: dict[str, Any]) -> dict[str, Any]:
    """Start a full-pipeline bake-off: run the COMPLETE 11-agent pipeline on
    each model stack (Production + DeepSeek + GLM + Qwen) for one stock.
    Long-running — returns a job_id to poll."""
    symbol = str(payload.get("symbol", "")).upper().strip()
    if not symbol:
        raise HTTPException(400, "symbol required")
    from engine.config import OPENROUTER_API_KEY
    if not OPENROUTER_API_KEY:
        raise HTTPException(400, "OPENROUTER_API_KEY not configured on the server")
    from engine.live.bakeoff import start_bakeoff
    model_keys = payload.get("models") or None
    return {"job_id": start_bakeoff(symbol, model_keys), "symbol": symbol}


@app.get("/compare/stacks")
async def compare_stacks() -> list[dict[str, Any]]:
    """Available pipeline-bake-off stacks + their default selection."""
    from engine.live.bakeoff import list_stacks
    return list_stacks()


@app.get("/compare/history")
async def compare_history(limit: int = 60) -> list[dict[str, Any]]:
    """Past bake-off runs (persisted), newest first."""
    from engine.live.bakeoff import list_bakeoffs
    return list_bakeoffs(limit)


@app.get("/compare/scorecard")
async def compare_scorecard() -> dict[str, Any]:
    """Aggregate model scorecard across all stored bake-off runs."""
    from engine.live.bakeoff import compute_scorecard
    return compute_scorecard()


@app.get("/compare/full/{job_id}")
async def compare_full_status(job_id: str) -> dict[str, Any]:
    from engine.live.bakeoff import get_job
    job = get_job(job_id)
    if job is None:
        raise HTTPException(404, "job not found")
    return job


# --------------- Options module (earnings straddles) ---------------


@app.post("/options/scan")
async def options_scan(payload: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """Run the earnings-straddle scan now. notify=false to skip the digest."""
    from engine.config import POLYGON_API_KEY
    if not POLYGON_API_KEY:
        raise HTTPException(400, "POLYGON_API_KEY not configured on the server")
    from engine.live.options.scanner import run_scan
    notify = bool((payload or {}).get("notify", False))
    try:
        return await run_scan(notify=notify)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(500, f"scan failed: {str(e)[:200]}")


@app.get("/options/candidates")
async def options_candidates() -> list[dict[str, Any]]:
    """Latest scan's candidates (qualified + rejected with reasons)."""
    from engine.live.options.store import latest_candidates
    return latest_candidates()


@app.post("/options/track")
async def options_track(payload: dict[str, Any]) -> dict[str, Any]:
    """Track a scanner candidate as a paper straddle position."""
    candidate_id = int(payload.get("candidate_id") or 0)
    contracts = max(1, int(payload.get("contracts") or 1))
    if not candidate_id:
        raise HTTPException(400, "candidate_id required")
    from engine.live import settings as live_settings
    from engine.live.options.store import get_candidate, open_sleeve
    cand = get_candidate(candidate_id)
    if not cand or not cand.get("straddle_cost"):
        raise HTTPException(400, "candidate not found or not priceable")
    # Options-sleeve caps (0 = OFF) — kept entirely separate from equity cash.
    sleeve = open_sleeve()
    max_conc = live_settings.get_options_max_concurrent()
    if max_conc and sleeve["count"] >= max_conc:
        raise HTTPException(400, f"options sleeve is at its {max_conc}-position "
                                 f"limit — close one or raise the cap in settings")
    max_cap = live_settings.get_options_max_sleeve_capital()
    add_cost = (cand.get("straddle_cost") or 0) * 100 * contracts
    if max_cap and sleeve["capital"] + add_cost > max_cap:
        raise HTTPException(400, f"tracking this would put the options sleeve at "
                                 f"${sleeve['capital'] + add_cost:,.0f}, over your "
                                 f"${max_cap:,.0f} cap — reduce contracts or raise "
                                 f"the cap in settings")
    from engine.live.options.positions import track_candidate
    pos_id = track_candidate(candidate_id, contracts)
    if pos_id is None:
        raise HTTPException(400, "candidate not found or not priceable")
    return {"position_id": pos_id}


@app.get("/options/positions")
async def options_positions(status: Optional[str] = None) -> dict[str, Any]:
    from engine.live.options.store import list_positions, open_sleeve, stats
    return {
        "open": list_positions("open"),
        "closed": list_positions("closed", limit=100) if status != "open" else [],
        "stats": stats(),
        "sleeve": open_sleeve(),
    }


@app.post("/options/positions/refresh")
async def options_positions_refresh() -> dict[str, Any]:
    """Re-mark all open straddles now (no Telegram)."""
    from engine.live.options.positions import mark_open_positions
    try:
        return await mark_open_positions(notify=False)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(500, f"refresh failed: {str(e)[:200]}")


@app.get("/options/backtest/{symbol}")
async def options_backtest(symbol: str, refresh: bool = False,
                           entry_days: int = 10) -> dict[str, Any]:
    """Per-ticker historical straddle backtest (Phase 3). Cached; pass
    refresh=true to recompute from live Polygon history."""
    from engine.config import POLYGON_API_KEY
    if not POLYGON_API_KEY:
        raise HTTPException(400, "POLYGON_API_KEY not configured on the server")
    from engine.live.options.store import load_backtest, save_backtest
    if not refresh:
        cached = load_backtest(symbol)
        if cached:
            return cached
    from engine.live.options.backtest import backtest_symbol
    try:
        result = await backtest_symbol(symbol, entry_days=entry_days)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(500, f"backtest failed: {str(e)[:200]}")
    save_backtest(symbol, entry_days, result)
    result["computed_at"] = datetime.utcnow().isoformat()
    return result


@app.post("/options/position/{position_id}/close")
async def options_position_close(position_id: int,
                                 payload: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    from engine.live.options.positions import close_position
    reason = (payload or {}).get("reason", "manual")
    pos = await close_position(position_id, reason=reason, notify=True)
    if pos is None:
        raise HTTPException(404, "position not found or already closed")
    return pos


# --------------- Telegram (Phase 4) ---------------


@app.post("/telegram/test")
async def telegram_test(payload: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    text = (payload or {}).get("text") or (
        "Akash Research Platform — Telegram test message. "
        "If you can read this, the bot is wired correctly."
    )
    client = telegram()
    ok = await client.send_message(text, kind="manual")
    return {"sent": ok, "configured": client.enabled}


@app.get("/telegram/log")
async def telegram_log(limit: int = 50) -> list[dict[str, Any]]:
    return telegram_log_rows(limit=limit)


# --------------- Per-stock Profiles (M17) ---------------


@app.get("/profiles")
async def profiles_list() -> list[dict[str, Any]]:
    """All profiles on disk — compact summary."""
    out: list[dict[str, Any]] = []
    for sym in live_profiles.list_profile_symbols():
        p = live_profiles.load_profile(sym)
        if p is None:
            continue
        out.append({
            "symbol": p.symbol,
            "name": p.name,
            "sector": p.sector,
            "industry": p.industry,
            "priority": p.priority,
            "held": p.held,
            "position_intent": p.position_intent,
            "last_reviewed": p.last_reviewed,
            "auto_built": p.auto_built,
            "bull_pillar_count": len(p.bull_thesis_pillars),
            "bear_pillar_count": len(p.bear_thesis_pillars),
            "red_line_count": len(p.red_lines),
            "n_kpis": len(p.key_kpis),
        })
    return out


@app.get("/profiles/{symbol}")
async def profile_get(symbol: str) -> dict[str, Any]:
    """Full profile (structured fields + long-form body)."""
    p = live_profiles.load_profile(symbol)
    if p is None:
        raise HTTPException(404, f"no profile for {symbol}")
    return p.model_dump(mode="json")


@app.get("/profiles/{symbol}/raw")
async def profile_get_raw(symbol: str) -> dict[str, str]:
    """Raw markdown file content (for editing)."""
    path = live_profiles.profile_path(symbol)
    if not path.exists():
        raise HTTPException(404, f"no profile for {symbol}")
    return {"symbol": symbol.upper(), "content": path.read_text(encoding="utf-8")}


@app.put("/profiles/{symbol}/raw")
async def profile_put_raw(symbol: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Overwrite the raw markdown file. Re-parses to validate."""
    content = payload.get("content")
    if not isinstance(content, str) or not content.strip():
        raise HTTPException(400, "content required")
    path = live_profiles.profile_path(symbol)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    # Validate the new content by reloading
    p = live_profiles.load_profile(symbol)
    if p is None:
        raise HTTPException(400, "saved file is not a valid profile (YAML or schema error)")
    return {"saved": True, "symbol": p.symbol, "name": p.name}


@app.delete("/profiles/{symbol}")
async def profile_delete(symbol: str) -> dict[str, bool]:
    path = live_profiles.profile_path(symbol)
    if not path.exists():
        raise HTTPException(404, f"no profile for {symbol}")
    path.unlink()
    return {"deleted": True}


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


# --------------------------------------------------------------------------- #
# Static SPA serving — the React frontend (frontend/dist). Mounted LAST so all
# API routes take precedence; any unmatched path returns index.html for
# client-side routing.
# --------------------------------------------------------------------------- #
from pathlib import Path as _Path  # noqa: E402
from fastapi.responses import FileResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402

_FRONTEND_DIST = _Path(__file__).resolve().parent.parent / "frontend" / "dist"
if (_FRONTEND_DIST / "index.html").exists():
    app.mount(
        "/assets",
        StaticFiles(directory=str(_FRONTEND_DIST / "assets")),
        name="assets",
    )

    @app.get("/{full_path:path}")
    async def spa_fallback(full_path: str):  # noqa: ANN001
        """Serve index.html for any non-API, non-asset route (SPA routing)."""
        candidate = _FRONTEND_DIST / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(_FRONTEND_DIST / "index.html")

    log.info("Serving React SPA from %s", _FRONTEND_DIST)
else:
    log.warning("frontend/dist not found — run `npm run build` in frontend/")


def _auto_run_name(config: BacktestConfig) -> str:
    sig = config.params.signature()
    days = (config.end_date - config.start_date).days
    years = max(1, round(days / 365))
    return f"{datetime.now().strftime('%Y-%m-%d_%H%M')}_{sig}_{years}y_{config.timeframe}"


def serve() -> None:
    """Run the API with uvicorn."""
    import uvicorn
    uvicorn.run("api.main:app", host=API_HOST, port=API_PORT, log_level="info", reload=False)


if __name__ == "__main__":
    serve()
