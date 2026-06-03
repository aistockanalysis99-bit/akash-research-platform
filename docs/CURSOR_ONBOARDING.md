# Akash Research Platform — Complete Technical Onboarding

**For: Cursor & Developer teams picking up Phase 1 (live) or Phase 2 (skeleton)**

---

## Quick Facts

| Item | Value |
|------|-------|
| **Project** | Trend-following momentum backtester |
| **Status** | Phase 1: COMPLETE & TESTED (57/57 tests) |
| **Code Size** | ~3,500 LOC (engine + api + ui + tests) |
| **Test Time** | 0.85 seconds |
| **5-Stock Backtest** | ~8 seconds |
| **100-Stock Backtest** | ~45 seconds |
| **Location** | `G:\Akash Research Platform\` |
| **API Key** | In `.env` (FMP) |
| **Main Entry** | `engine/core/event_loop.py::run_backtest()` |

---

## 5-Minute Start

```bash
cd "G:\Akash Research Platform"
python -m venv .venv
.venv\Scripts\activate
pip install -e .

# First time only
python scripts/refresh_data.py --universe smoke --timeframe 1D --years 5

# Launch
python run.py
```

**Opens at:** http://127.0.0.1:8080 (UI) + http://127.0.0.1:8000 (API)

---

## Architecture Overview

### Three-Layer Stack

```
┌─────────────────────────────────────┐
│  Application Layer                  │
│  ├─ FastAPI backend (api/)          │
│  ├─ NiceGUI web frontend (ui/)      │
│  └─ SQLite persistence (runs.sqlite)│
├─────────────────────────────────────┤
│  Engine Layer                       │
│  ├─ Strategy & indicators           │
│  ├─ Portfolio & position mgmt       │
│  ├─ Event-driven backtest loop      │
│  └─ Metrics computation             │
├─────────────────────────────────────┤
│  Data Layer                         │
│  ├─ FMP async client (/stable/ only)│
│  ├─ Parquet cache (incremental)     │
│  └─ Universe definitions (SP100)    │
└─────────────────────────────────────┘
```

### Signal Flow: Entry to Exit

```
BAR T (CLOSE):
  1. Compute indicators (EMA, ATR, momentum)
  2. Generate entry/exit signals
  3. Schedule entries for next bar
  → DECISION: "Buy AAPL tomorrow"

BAR T+1 (OPEN):
  4. Execute pending entries
  5. Check hard stops/take-profits (intra-bar)
  6. Update trailing stops
  7. Compute pyramid adds
  8. Mark equity

BAR T+N:
  → Position exits via stop/TP/soft-exit
```

### Critical: No Look-Ahead Bias

- **Signals computed** at CLOSE of bar T (using only data up to close T)
- **Entry executed** at OPEN of bar T+1
- **Stops checked** using LOW of bar T+1
- **All indicators use `shift(1)`** to guard current bar from its own high/low

Example: `rolling_highest(20).shift(1).rolling(20).max()` ensures bar T's high is **NOT** in its own breakout signal.

---

## Directory Map (Critical Files)

### `engine/` — Core Library

| File | Purpose |
|------|---------|
| `core/types.py` | **ALL dataclasses** (Position, Trade, EquityPoint, StrategyParams) + defaults |
| `core/event_loop.py` | **`run_backtest()` — 8-step per-bar loop** ⭐ MAIN ENTRY |
| `core/portfolio.py` | Portfolio class: fills, cash mgmt, position CRUD |
| `data/fmp_client.py` | FMP `/stable/` endpoints (NO `/api/v3/` — returns 403) |
| `data/cache.py` | Parquet cache (per `{symbol}_{timeframe}.parquet`), incremental refresh |
| `strategy/signal.py` | `compute_signal_columns()` — adds momentum, bull_state, breakout |
| `strategy/sizer.py` | Position sizing: `units = (risk% × equity) / (atr × price)` |
| `strategy/exits.py` | `composite_stop_long()` — max(initial, trail, breakeven), ratchets UP only |
| `portfolio/hybrid.py` | `filter_candidates()` — slot cap, vol target, gross cap, whole shares |
| `metrics/compute.py` | `compute_all_metrics()` — CAGR, Sharpe, MaxDD, profit factor, etc. |
| `db/schema.py` | SQLite schema, WAL mode. **⚠️ NO `detect_types` (timestamp parse fix)** |
| `db/repo.py` | CRUD: insert/get/list runs, trades, presets |

### `api/` — FastAPI Backend

| File | Routes |
|------|--------|
| `main.py` | `/health`, `/data/*`, `/backtest/*`, `/runs`, `/params`, `/compare` |
| `jobs.py` | `JobManager` (ThreadPoolExecutor, in-memory progress dict) |
| `schemas.py` | Pydantic v2 request/response schemas |

### `ui/` — NiceGUI Frontend

| File | Purpose |
|------|---------|
| `main.py` | All routes, dark theme, nav header |
| `pages/new_backtest.py` | Parameter form (6 groups), preset load/save, Run button |
| `pages/run_detail.py` | **7 tabs**: Summary, Equity, Returns, Trades, Per-Symbol, Diagnostics, Params |
| `pages/runs_list.py` | Run history table, compare, delete |
| `pages/compare.py` | Multi-run equity overlay, metric table |
| `charts.py` | Plotly builders (equity, heatmap, MAE/MFE, etc.) |

### `tests/`

| File | Coverage |
|------|----------|
| `conftest.py` | Synthetic fixtures (uptrend, downtrend, sideways 400-bar DataFrames) |
| `unit/` | Indicators, signal, sizer, exits, metrics, hybrid (6 test files) |
| `integration/` | End-to-end engine, SQLite round-trip (2 test files) |

---

## Core Concepts

### Event Loop: 8 Steps Per Bar

```python
for bar_index in range(start, end):
    # Step 1: Execute pending entries at bar open
    fill_pending_entries(bar_index)
    
    # Step 2: Execute soft-exit pending (score decay, trend break)
    execute_soft_exits(bar_index)
    
    # Step 3: Check hard stops/take-profits intra-bar
    check_stops(df.loc[bar_index, 'low'], df.loc[bar_index, 'high'])
    
    # Step 4: Update trailing stop (ratchets UP only)
    update_trailing_stops(df.loc[bar_index, 'high'])
    
    # Step 5: Update MAE/MFE for diagnostics
    update_mae_mfe()
    
    # Step 6: Compute pyramid add candidates at close
    pyramid_adds = compute_adds(bar_index)
    
    # Step 7: Compute entry signals, hybrid filter, schedule for next bar
    signals = compute_signal_columns(df, bar_index)
    candidates = hybrid_filter(signals, current_positions)
    schedule_entries(candidates)
    
    # Step 8: Mark equity, cash, metrics
    mark_equity(bar_index)
```

### Position Sizing Formula

```
Units = (Risk% × Equity) / (ATR × Entry_Price)

Example:
  Equity = $100,000
  Risk% = 0.5%
  Entry_Price = $150
  ATR = $2.40
  
  Units = (0.005 × $100,000) / ($2.40 × $150)
        = $500 / $360
        = 1.39 units → floor to 1 share (whole shares default)
```

### Stops & Exits

| Exit Type | Trigger | Notes |
|-----------|---------|-------|
| **Initial Stop** | `Entry - (2.5 × ATR)` | Set at entry, can be hit anytime |
| **Trailing Stop** | `Max_Price_Since_Entry - (3.0 × ATR)` | Only ratchets UP, never down |
| **Breakeven Stop** | If at 2R profit, move to entry price | Locks in breakeven |
| **Partial TP** | At 2R (2× initial risk), sell 50% | Other 50% trails |
| **Soft Exit (Score)** | Score drops below 0.15 | Exit at close |
| **Soft Exit (Trend)** | EMA(50) < EMA(150) | Exit at close |
| **Soft Exit (Time)** | Bars held > 20 | Time-based exit |

---

## Critical Gotchas

### 1. **FMP Endpoints — ALL `/api/v3/` Return 403**
- Your account uses `/stable/` endpoints only (post-Aug 2025)
- `fmp_client.py` is already configured correctly
- Historical daily: `GET /stable/historical-price-eod/dividend-adjusted`
- Intraday: `GET /stable/historical-chart/{interval}`

### 2. **SQLite Timestamp Parsing — NO `detect_types`**
- `PARSE_DECLTYPES` fails on ISO-8601 with `T` separator (`"2026-04-30T19:26:35"`)
- **Fix:** Removed `detect_types` from `get_connection()` in `schema.py`
- Timestamps stored as plain ISO strings, parsed back by `datetime.fromisoformat()`

### 3. **Run Detail Page — MUST Call `refresh()` Immediately**
```python
async def render_run_detail():
    refresh()                  # ← CRITICAL: immediate first call
    ui.timer(0.5, refresh)     # then poll every 0.5s
```
Without the immediate call, NiceGUI won't fire the timer until 0.5s elapsed → blank "Loading..." page

### 4. **Trailing Stops — Only Ratchet UP, Never DOWN**
```
Entry: $100
High: $105 → Trail stop: $105 - (3.0 × ATR) = $102
High: $103 (lower than $105) → Trail stop: $102 (UNCHANGED, not $100)
```

### 5. **Whole Shares — Floor After Sizing**
```python
units = (0.005 * equity) / (atr * price)  # returns float, e.g. 1.39
if fractional_shares:
    qty = units
else:
    qty = int(units)  # floor to 1.39 → 1
    if qty < 1:
        skip_entry()  # don't buy if < 1 share
```

### 6. **Vol Target — Zero-Correlation Assumption**
- Portfolio vol target assumes stocks are uncorrelated
- Real correlations spike in downturns → actual vol > target
- Monitor actual portfolio volatility; adjust target if drifting

### 7. **Soft Exits — Exit at CLOSE, Not Next Open**
- Score decay: exit at close of bar where score drops below 0.15
- Trend break: exit at close when EMA(50) crosses below EMA(150)
- Time exit: exit at close if bars_held > 20

### 8. **Position Mocks in Tests — Never Use `object()`**
- ❌ `test_drops_existing_open_positions` used `object()` as Position mock
- ✅ **Fixed:** Use real `Position` instances via `_pos()` helper (test_hybrid.py)
- Reason: `filter_candidates()` accesses `pos.qty` and `pos.avg_price`

---

## API Reference (Key Endpoints)

### Backtest

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/backtest/run` | POST | Start backtest (background job). Request: `BacktestRequest`. Returns: `run_id`, `status` |
| `/backtest/{run_id}` | GET | Poll job: `{"status":"running"\|"done", "progress":0-100}` |
| `/backtest/{run_id}/equity` | GET | Returns: `list[EquityPoint]` |
| `/backtest/{run_id}/trades` | GET | Returns: `list[Trade]` (sortable, filterable) |
| `/backtest/{run_id}/trades.csv` | GET | Export trades as CSV |
| `/backtest/{run_id}/per-symbol` | GET | Per-symbol stats |

### Runs & Compare

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/runs` | GET | List all saved runs (paginated) |
| `/runs/{id}` | DELETE | Delete a run |
| `/compare?run_ids=id1,id2,...` | GET | Multi-run comparison |

### Parameters

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/params` | GET | List saved parameter presets |
| `/params` | POST | Save new preset |
| `/params/{name}` | DELETE | Delete preset |

---

## Running & Testing

### Tests

```bash
python -m pytest tests/ -v
# Expected: 57 passed in 0.85s
```

**Test organization:**
- `tests/unit/`: Indicators, signal, sizer, exits, metrics, hybrid
- `tests/integration/`: Full backtest engine, SQLite persistence
- `tests/conftest.py`: Synthetic fixtures (400-bar DataFrames with predictable patterns)

### CLI Backtest

```bash
python scripts/run_backtest_cli.py --universe smoke --years 5 --save
# Outputs KPIs to console, saves run to SQLite
```

### Data Refresh

```bash
python scripts/refresh_data.py --universe sp100 --timeframe 1D --years 5
# Fetches missing bars from FMP, appends to Parquet cache
```

---

## Common Development Tasks

### Add a New Metric

1. Compute in `engine/metrics/*.py` (returns.py, risk.py, or trade_stats.py)
2. Add to the dict in `engine/metrics/compute.py::compute_all_metrics()`
3. Display in `ui/pages/run_detail.py` (Summary tab KPI cards or stats table)
4. Add column to compare table if top-level KPI

### Modify Signal Logic

1. Edit `engine/strategy/signal.py::compute_signal_columns()`
2. Update momentum weights, EMA periods, breakout bars, or add new columns
3. Make sure new columns are initialized before indexing (avoid NaN head)
4. Run tests: `python -m pytest tests/unit/test_signal.py`

### Adjust StrategyParams Defaults

1. Edit `engine/core/types.py` — `StrategyParams` dataclass
2. Update `@dataclass` fields with new defaults
3. Defaults auto-populate in UI form (`ui/pages/new_backtest.py`)

### Add a UI Page

1. Create `ui/pages/your_page.py` with `async def your_page()` function
2. Register route in `ui/main.py`: 
   ```python
   @ui.page("/your-route")
   async def _your_page():
       await your_page()
   ```
3. Add nav link in `_nav_header()` function

### Add an API Endpoint

1. Add route to `api/main.py` (use `@app.get` or `@app.post`)
2. Add schemas to `api/schemas.py` (Pydantic v2)
3. Add sync wrapper to `ui/api_client.py` (clients don't use async)

---

## Phase 2: Live Signal Delivery

### Workflow

```
16:30 ET (daily):
  1. Pull latest EOD data from FMP (incremental cache update)
  2. Compute momentum signals for 100-stock universe
  3. For each NEW entry signal:
     a. Send to Claude API for analysis (2-3 sentence breakdown)
     b. Deliver signal + analysis to Telegram channel
```

### Files to Create

| File | Purpose |
|------|---------|
| `engine/live/live_runner.py` | Main daily runner (refresh data, compute signals, send to Claude) |
| `engine/live/claude_client.py` | Claude API integration |
| `engine/live/telegram_client.py` | Telegram bot delivery |
| `engine/live/scheduler.py` | APScheduler: daily job at 16:30 ET |

### .env Additions

```
ENABLE_LIVE_SIGNALS=false  # flip to true when ready
CLAUDE_API_KEY=sk-ant-...
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...
```

### New Dependencies

```bash
pip install apscheduler>=3.10 anthropic>=0.25
```

### Effort

Estimated **4–5 hours** of development:
- 1–2 hours: Live runner + signal filtering
- 30 min: Claude API integration
- 30 min: Telegram bot setup
- 30 min: APScheduler configuration
- 1 hour: End-to-end testing

**Full skeleton & instructions:** `docs/NEXT_STEPS.md`

---

## Technology Stack

| Layer | Libraries |
|-------|-----------|
| **Data** | httpx (async), tenacity (retry), pyarrow (Parquet), pandas, numpy |
| **Strategy** | pandas, numpy (vectorized) |
| **Portfolio** | Pure Python (no libs) |
| **Metrics** | pandas, numpy |
| **Persistence** | sqlite3 (built-in) |
| **Backend** | FastAPI, uvicorn, python-dotenv, click (CLI) |
| **Frontend** | NiceGUI, Plotly, Vue (via NiceGUI) |
| **Testing** | pytest, pytest-asyncio |
| **Logging** | Python logging, rotating file handler |

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| **FMP 403 "Legacy Endpoint"** | Use `/stable/` endpoints. `fmp_client.py` is configured. |
| **No bars cached** | Run: `python scripts/refresh_data.py --universe smoke` |
| **ModuleNotFoundError: engine** | Run: `pip install -e .` for editable install |
| **Port 8000/8080 in use** | Edit `.env`: `API_PORT=8001`, `UI_PORT=8081`, restart |
| **UI blank "Loading..."** | Page missing immediate `refresh()` call. Check `run_detail.py` |
| **SQLite "database is locked"** | WAL mode prevents this. Restart API if stuck. |
| **Tests fail with DB errors** | Monkeypatch BOTH `repo.DB_PATH` and `schema_mod.DB_PATH` |
| **Backtest runs slowly** | S&P 100 = 45s; smoke (5 stocks) = 8s. Use smoke for dev. |
| **Charts don't render** | Wait 2–3s for Plotly + WebSocket handshake |
| **Parameter form empty** | API `/params` endpoint missing. Check `api/main.py` has all routes. |

---

## Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| Event-driven loop | Matches real trading: signals at close, fills at next open. No look-ahead. |
| Vol-normalized momentum | Adjusts for market volatility; prevents high-vol stocks from dominating signal list. |
| Trailing stops that ratchet | Locks in gains while staying in trends; prevents whipsaws on small retracements. |
| Hybrid portfolio constraints | Caps slots, vol target, gross exposure to manage correlation risk. |
| Whole shares (default) | Simpler execution; fractional toggle for experimentation. |
| Parquet cache | Fast incremental refresh; easy to inspect with pandas. |
| SQLite WAL mode | Supports concurrent reads during writes; no blocking. |
| ThreadPoolExecutor (not async) | Background jobs don't need async; blocking I/O to disk is fine. |
| Pydantic v2 | Type safety for API schemas; built-in validation. |
| NiceGUI (not React/Vue) | Pure Python UI; no JS build step; live refresh via WebSocket. |

---

## Performance Profile

| Scenario | Time |
|----------|------|
| 5 stocks, 5 years (daily) | ~8 seconds |
| 100 stocks, 5 years (daily) | ~45 seconds |
| 100 stocks, 1 year (daily) | ~12 seconds |
| Full test suite | 0.85 seconds |
| Memory usage (100 stocks, 5y) | ~500 MB peak |

---

## Documentation Files

- **`README.md`** — Quick start, feature status, smoke test results
- **`CLAUDE.md`** — LLM conventions, critical gotchas, project-specific patterns
- **`NEXT_STEPS.md`** — Phase 2 skeleton, full implementation instructions
- **`Strategy_Discussion_Guide.docx`** — Non-technical strategy overview for client discussions

---

## Questions?

- **Setup issues?** See "Troubleshooting" section above
- **Architecture questions?** See `CLAUDE.md` for detailed patterns
- **Phase 2?** See `NEXT_STEPS.md` for skeleton code & implementation guide
- **Quick start?** See `README.md` for 5-minute installation

---

**Status:** ✅ Phase 1 Complete & Production-Ready | 📋 Phase 2 Skeleton Provided | 🚀 Ready for Cursor/Developer Onboarding
