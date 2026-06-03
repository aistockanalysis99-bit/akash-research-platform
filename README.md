# Akash Research Platform

**Trend-Following Momentum Backtester** — local web app for researching a vol-normalized, multi-horizon momentum strategy on US equities.

Phase 1 (this codebase): full backtester with interactive UI.
Phase 2 (future): live signals → Claude analysis → Telegram delivery.

---

## Quick start

### 1. Install
```bash
cd "G:\Akash Research Platform"
python -m venv .venv
.venv\Scripts\activate
pip install -e .
# or:  pip install pandas numpy pyarrow httpx fastapi "uvicorn[standard]" nicegui plotly pydantic python-dotenv tenacity tqdm click
```

### 2. Configure
Edit `.env` (already created with your FMP key):
```
FMP_API_KEY=your_key
```

### 3. Refresh data (first time)
```bash
# Smoke test universe (5 stocks, fast)
python scripts/refresh_data.py --universe smoke --timeframe 1D --years 5

# Full S&P 100 (~2-3 minutes)
python scripts/refresh_data.py --universe sp100 --timeframe 1D --years 5
```

### 4. Launch the platform
```bash
python run.py
```

Browser opens automatically at **http://127.0.0.1:8080**.

API runs at http://127.0.0.1:8000 (Swagger UI: http://127.0.0.1:8000/docs).

### 5. CLI alternative
```bash
python scripts/run_backtest_cli.py --universe smoke --years 5 --save
```

---

## Project layout

```
.
├── engine/                  # Core library (data + strategy + engine + metrics + db)
│   ├── data/                # FMP client, cache, universe, resampler, loader
│   ├── core/                # Types, portfolio, event loop
│   ├── strategy/            # Signal, sizer, exits, momentum_strategy
│   ├── portfolio/           # Hybrid portfolio layer (caps, vol target)
│   ├── metrics/             # Returns, risk, trade stats, compute
│   └── db/                  # SQLite schema and repo
├── api/                     # FastAPI backend (jobs.py, main.py, schemas.py)
├── ui/                      # NiceGUI frontend (pages, charts, theme, api_client)
├── scripts/                 # CLI: refresh_data.py, run_backtest_cli.py, capture_screenshots.py
├── tests/                   # 57 tests (unit + integration)
├── docs/screenshots/        # UI screenshots (after a run)
├── data_cache/              # Parquet OHLCV cache
├── runs.sqlite              # Run history + trades
├── logs/                    # INFO console + DEBUG file
├── pyproject.toml
├── run.py                   # Launcher (API + UI)
└── .env
```

---

## What works

| Feature | Status |
|---|---|
| FMP integration (new `/stable/` endpoints, dividend-adjusted) | Verified: 5/5 smoke symbols |
| Local Parquet cache, incremental refresh | Working |
| Full event-driven backtest engine (long-only, hybrid portfolio) | Working |
| All metrics: CAGR, Sharpe, Sortino, MaxDD, MAR, profit factor, etc. | Working |
| FastAPI backend with all endpoints | Working |
| NiceGUI UI: 6 pages, all charts, all tables | Working |
| Run history + parameter presets | Working |
| Multi-run comparison | Working |
| 57/57 tests passing | Verified |

See `docs/screenshots/` for UI screenshots after a real run.

---

## Strategy summary

A trend-following momentum strategy gated by:
1. Vol-normalized weighted multi-horizon momentum score (`S_t > 0.25`)
2. Trend filter: EMA(50) > EMA(150), slope rising
3. Breakout entry: close > prior 20-bar high

With:
- Risk-based sizing (0.5% equity per unit) × vol-target scalar
- Hybrid portfolio constraints (max concurrent positions, gross exposure cap)
- Initial 2.5×ATR stop, 50% take-profit at 2R, 3.0×ATR trailing stop
- Pyramiding (up to 2 adds at 0.75×ATR each)
- Soft exits on score decay, EMA failure, max bars in trade

Long-only in v1. See full spec in `docs/Trend-Momentum-Backtester-Spec.md`.

---

## Smoke test result (real data, 5 stocks, 5 years daily)

| Metric | Value |
|---|---|
| Final Equity | $109,170 |
| Total Return | +9.17% |
| CAGR | +1.77% |
| Sharpe | 0.80 |
| Sortino | 0.67 |
| Max Drawdown | -2.67% |
| MAR / Calmar | 0.66 |
| # Trades | 60 |
| Win Rate | 36.67% |
| Profit Factor | 2.30 |
| Avg Trade | $152.74 |
| Annualized Vol | 2.24% |

The very low vol reflects that only 5 stocks rarely produce concurrent positions; on the full S&P 100, vol and CAGR both rise materially.

---

## Run tests
```bash
python -m pytest tests/ -v
```

Expect: **57 passed** in <1s.

---

## Troubleshooting

**No bars cached:** Run `python scripts/refresh_data.py --universe smoke` first.

**FMP 403 "Legacy Endpoint":** Your FMP plan must use the new `/stable/` endpoints. The client is already configured for these.

**Port already in use:** Edit `.env` to change `API_PORT` or `UI_PORT`.

**UI doesn't load charts:** Wait 2-3 seconds for Plotly + websocket handshake.

---

## Phase 2 placeholder

When you're ready for live signals:
1. Add Claude API key + Telegram bot token to `.env`
2. Implement `engine/live/live_runner.py` (skeleton path reserved)
3. APScheduler job runs at 16:30 ET daily — reuses `MomentumStrategy`
4. Each new signal → Claude analysis → Telegram message

See `docs/NEXT_STEPS.md` for the developer handoff plan.

---

## License
Proprietary. Internal use only.
