# CLAUDE.md — Project Conventions

This file is read by Claude (and other LLMs) at the start of every session on this project.
It documents the architecture, conventions, and gotchas so you can contribute accurately without re-deriving them.

---

## Project in one line

A local Python web app that backtests a vol-normalized multi-horizon momentum strategy on US equities (S&P 100),
with a FastAPI backend, NiceGUI frontend, SQLite run history, and Parquet OHLCV cache.

---

## Tech stack

| Layer | Library | Notes |
|---|---|---|
| Data | httpx + tenacity | Async FMP client; retry on 429/5xx |
| Cache | pyarrow / pandas | Parquet per `{symbol}_{timeframe}.parquet` |
| Strategy | pandas / numpy | Vectorized indicators; per-bar event loop |
| Portfolio | pure Python | Custom Portfolio + HybridPortfolio classes |
| Metrics | pandas / numpy | CAGR, Sharpe, Sortino, MaxDD, MAR, profit factor |
| Persistence | sqlite3 | WAL mode; NO `detect_types` |
| API | FastAPI + uvicorn | ThreadPoolExecutor for background jobs |
| UI | NiceGUI + Plotly | Vue-backed; dark theme; all charts are Plotly |
| Tests | pytest | 57 tests; unit + integration; synthetic fixtures |

---

## Directory map (quick reference)

```
engine/
  config.py           — loads .env; exposes FMP_API_KEY, API_PORT, UI_PORT, etc.
  logging_setup.py    — INFO → console, DEBUG → rotating file in logs/
  core/
    types.py          — ALL dataclasses and enums (Bar, Position, Trade, EquityPoint,
                         StrategyParams, BacktestConfig, BacktestResult, RunStatus, ExitReason)
    portfolio.py      — Portfolio: cash, commission/slippage, open/add/close/mark_equity
    event_loop.py     — run_backtest(): the 8-step per-bar loop
  data/
    fmp_client.py     — FMP async client (STABLE endpoints only — see FMP section below)
    cache.py          — Parquet cache; refresh_universe() async
    universe.py       — SP100 (100 tickers) + SMOKE_TEST (5 tickers)
    resampler.py      — resample_to_weekly() via resample("W-FRI")
    loader.py         — load_universe_panel() → dict[symbol, DataFrame]
  strategy/
    indicators.py     — EMA, ATR, rolling_highest (shift(1) look-ahead guard),
                         skip_adjusted_return, realized_vol
    signal.py         — compute_signal_columns() → adds mom_score / bull_state / breakout_long
    sizer.py          — vol_scalar(), initial_qty(), add_qty()
    exits.py          — composite_stop_long() — stop only ratchets UP
  portfolio/
    hybrid.py         — filter_candidates(): slot cap + vol target + gross cap + whole-share
  metrics/
    returns.py        — cagr, total_return, daily_returns, equity_to_series
    risk.py           — sharpe_ratio, sortino_ratio, max_drawdown, drawdown_series, annualized_vol
    trade_stats.py    — trade_stats() → win_rate, profit_factor, largest_win/loss, etc.
    compute.py        — compute_all_metrics() → flat dict (all KPIs + time-series sub-dicts)
  db/
    schema.py         — init_db(); tables: runs, equity_curve, trades, per_symbol_stats, parameter_sets
    repo.py           — insert_run_pending, save_run_result, get_run, list_runs, etc.

api/
  main.py             — All FastAPI routes
  jobs.py             — JobManager (ThreadPoolExecutor, in-memory progress dict)
  schemas.py          — Pydantic v2 I/O schemas

ui/
  main.py             — NiceGUI routes; serve()
  api_client.py       — Sync httpx wrapper for all API calls
  charts.py           — All Plotly chart builders
  pages/
    new_backtest.py   — Parameter form + preset load/save + Run button
    run_detail.py     — Tabbed result viewer (polls at 0.5 s, immediate first call)
    runs_list.py      — Run history table with compare + delete
    compare.py        — Multi-run equity overlay + metric table
    data_page.py      — Data refresh UI
    params_page.py    — Saved parameter set manager

scripts/
  refresh_data.py     — CLI data refresh
  run_backtest_cli.py — CLI backtest with optional DB save
  capture_screenshots.py — Playwright screenshot automation

tests/
  conftest.py         — synthetic_uptrend_df / _downtrend / _sideways (400 bars each)
  unit/               — indicators, signal, sizer, exits, metrics, hybrid
  integration/        — engine (end-to-end), db (SQLite round-trip)
```

---

## Critical: FMP API endpoints

**Never use `/api/v3/`** — returns HTTP 403 "Legacy Endpoint" for post-Aug 2025 accounts.

Use the `/stable/` base URL for everything:

| Data type | Endpoint |
|---|---|
| Daily (adjusted) | `GET /stable/historical-price-eod/dividend-adjusted?symbol=AAPL&from=…&to=…` |
| Intraday | `GET /stable/historical-chart/{interval}?symbol=AAPL&from=…&to=…` |

Response field mapping (daily adjusted):
- `adjOpen`, `adjHigh`, `adjLow`, `adjClose` → renamed to `open`, `high`, `low`, `close`
- `volume` → kept as-is
- `date` → parsed to `timestamp` (UTC)

The client is in `engine/data/fmp_client.py`. Semaphore throttles to 250 requests/min.
Tenacity retries on 429 (rate limit) and 5xx with exponential backoff.

---

## Critical: SQLite connection

**Do NOT add `detect_types=sqlite3.PARSE_DECLTYPES`** to `get_connection()`.

SQLite's built-in TIMESTAMP adapter expects `"YYYY-MM-DD HH:MM:SS"` (space-separated).
Python's `datetime.isoformat()` produces `"YYYY-MM-DDTHH:MM:SS"` (T-separator) which raises a `ValueError`.
The fix: omit `detect_types` entirely; timestamps are stored/retrieved as plain ISO strings.

---

## Backtest event loop — look-ahead protection

The loop in `engine/core/event_loop.py` enforces:
- **Signal computed at close of bar T** (all indicators use `shift(1)` where needed)
- **Entry executed at open of bar T+1**
- **Stops checked intra-bar** using `low` of bar T+1

Key: `rolling_highest` in `indicators.py` uses `shift(1)` before rolling max so bar T's high
is NOT included in its own breakout signal.

---

## StrategyParams defaults (from `engine/core/types.py`)

All defaults match the spec. Key values:

| Param | Default | Meaning |
|---|---|---|
| `momentum_weights` | [0.4, 0.3, 0.2, 0.1] | 4-horizon weights (252/126/63/21 bars) |
| `score_threshold` | 0.25 | Min vol-norm score to be eligible |
| `ema_short` | 50 | Fast EMA for trend filter |
| `ema_long` | 150 | Slow EMA for trend filter |
| `breakout_bars` | 20 | Prior N-bar high for entry |
| `stop_atr` | 2.5 | Initial stop in ATR |
| `trail_atr` | 3.0 | Trailing stop in ATR |
| `partial_tp_r` | 2.0 | Partial TP at 2R |
| `partial_tp_frac` | 0.5 | Sell 50% at TP |
| `pyramid_adds` | 2 | Max add-ons per trade |
| `risk_pct` | 0.005 | 0.5% equity per unit |
| `max_concurrent_positions` | 20 | Hybrid slot cap |
| `portfolio_vol_target` | 0.15 | 15% annualized portfolio vol |
| `max_portfolio_gross` | 1.5 | 150% gross exposure cap |
| `commission_per_share` | 0.005 | $0.005/share |
| `slippage_pct` | 0.001 | 0.1% slippage on fill |
| `fractional_shares` | False | Whole shares by default |

---

## Run detail page — polling pattern

`ui/pages/run_detail.py` must call `refresh()` **immediately** on page load, then again every 0.5s:

```python
refresh()                         # immediate first load
ui.timer(0.5, refresh)            # then poll
```

Do not rely solely on the timer — NiceGUI won't fire it until 0.5s have elapsed,
causing a blank "Loading…" state in the initial screenshot.

---

## Adding a new page to the UI

1. Create `ui/pages/your_page.py` — define an `async def your_page()` function
2. Register the route in `ui/main.py`: `@ui.page("/your-route") async def _your_page(): await your_page()`
3. Add a nav link in the shared header (see `ui/main.py` `_nav_header()`)

---

## Adding a new API endpoint

1. Add the route function to `api/main.py`
2. Add request/response schemas to `api/schemas.py` (Pydantic v2 — use `model_validator` not `root_validator`)
3. Add a sync wrapper to `ui/api_client.py`

---

## Adding a new metric

1. Compute it in the appropriate `engine/metrics/*.py` module
2. Add it to the flat dict returned by `engine/metrics/compute.py::compute_all_metrics()`
3. Display it in `ui/pages/run_detail.py` (Summary tab KPI cards or stats table)
4. Add a column to the compare table in `ui/pages/compare.py` if it's a top-level KPI

---

## Tests

Run all: `python -m pytest tests/ -v`
Expected: **57 passed** in < 1 second (all synthetic data, no network).

Fixtures are in `tests/conftest.py` — synthetic DataFrames with 400 bars each.
Use `monkeypatch.setattr(repo, "DB_PATH", tmp_path / "t.sqlite")` for DB tests
(must also patch `engine.db.schema.DB_PATH` — both modules hold the path).

When writing tests that create `Position` objects, use the full constructor —
do not use `object()` mocks because `filter_candidates()` reads `pos.qty` and `pos.avg_price`.

---

## Environment variables (`.env`)

```
FMP_API_KEY=<key>
API_HOST=127.0.0.1
API_PORT=8000
UI_PORT=8080
LOG_LEVEL=INFO
DB_PATH=runs.sqlite
CACHE_DIR=data_cache
```

All loaded via `engine/config.py` using `python-dotenv`.

---

## Phase 2 skeleton (do not implement yet)

Reserved path: `engine/live/live_runner.py`
Reuses: `MomentumStrategy`, `compute_signal_columns()`, all sizer/exit logic
Trigger: APScheduler at 16:30 ET daily
Output: signal dict → Claude API analysis → Telegram bot message

See `docs/NEXT_STEPS.md` for the full handoff plan.
