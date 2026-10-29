# Point-in-Time Backtest & Blind Replay Simulator: Implementation Plan

> **Strategy**: Cointegrated Statistical Arbitrage & Mean-Reverting Pairs Trading  
> **Target Environment**: Local Research Platform (`akash-research-platform`)  
> **Version**: 1.0.0 — Production-Grade Specification  
> **Status**: Ready for Implementation  

---

## Executive Summary & System Objectives

The goal of this project is to build an interactive, point-in-time **Blind Replay & Forward-Validation Simulator** for 5-year historical market data. 

In quantitative pairs trading, retrospective backtesting often suffers from lookahead bias and cherry-picking. This simulator solves that problem by introducing a **"Blind Walk-Forward Sandbox"**:
1. **Strict Temporal Isolation ($t \le T$)**: The engine truncates all market data to Date $T$. The scanner evaluates cointegration, hedge ratios ($\beta$), spread z-scores, and composite scores using *only* historical bars known on or before Date $T$.
2. **Actionable Setup Recommendations**: Displays the top ranked divergent pairs for Date $T$ with exact execution guidance (e.g., *Buy A at \$XX, Short B at \$YY*, target spread, expected reversion return, half-life).
3. **Step Forward / Backward Controls**: Ability to advance day-by-day (`+1 Day`) or step back (`-1 Day`) without ever going behind the chosen anchor date ($T_{\text{base}}$).
4. **The Blind "Reveal" Engine**: The future trajectory ($t > T$) remains hidden/blurred until explicitly revealed. Upon clicking **Reveal**, the forward 1-week, 1-month, or full trade resolution path is displayed with:
   * **Glowing GREEN stroke / highlight**: Mean-reversion target reached ($\ge 80\%$ or $z = 0.0$) prior to stop loss $\rightarrow$ **Profitable Trade**.
   * **Glowing RED stroke / highlight**: Divergence blowout or stop-loss reached ($|z| \ge 3.5\sigma$) prior to mean reversion $\rightarrow$ **Loss / Stopped Out**.
   * **Outcome Exit Pin**: Specific marker displaying exit day, duration in days, and realized percentage return.
5. **Day Batch Scorecard**: A one-click summary revealing the aggregate win rate, average profit, and trade duration across all setups generated for that day.

---

## System Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                           LOCAL DATA LAYER (Offline)                            │
│  5-Year Daily Adjusted OHLCV for all Master & Elite Pairs (~100 Tickers)        │
│  Stored in `data_cache/universe_5y_daily.parquet` (Compressed, ~6MB)            │
└──────────────────────────────────────┬──────────────────────────────────────────┘
                                       │ In-Memory Fast Slicing (< 5ms)
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                      SIMULATOR ENGINE (`engine/simulator.py`)                   │
│                                                                                 │
│   [Date Anchor: T] ────────► Truncates Matrix to t <= T                         │
│                                      │                                          │
│                                      ▼                                          │
│                       Point-in-Time Setup Detector                              │
│                       • 90-Day Rolling Hedge Ratio (OLS)                        │
│                       • Augmented Dickey-Fuller (ADF) p-value                   │
│                       • Z-Score & Volatility Tier Filtering                     │
│                       • Ranking by Composite Score                              │
│                                      │                                          │
│                                      ▼                                          │
│                         Forward Outcome Evaluator                               │
│                         (Target-First vs Stop-First Logic)                      │
│                         • 1-Week / 1-Month / Full Resolution                    │
│                         • Win (Green) / Loss (Red) Determination                │
└──────────────────────────────────────┬──────────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                       FASTAPI BACKEND (`api/simulator_router.py`)               │
│  • POST /api/simulator/init          • GET  /api/simulator/scan?date=YYYY-MM-DD │
│  • GET  /api/simulator/step?step=+1  • POST /api/simulator/reveal              │
│  • GET  /api/simulator/chart-data    • GET  /api/simulator/batch-scorecard     │
└──────────────────────────────────────┬──────────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                    REACT SIMULATOR DASHBOARD (`/simulator`)                     │
│  • Top VCR Control Bar (Date Picker, Anchor Lock, +1/-1 Day, Speed Toggle)      │
│  • Point-in-Time Setups Table (Buy/Short Tickers, Target %, Z-Score, Score)     │
│  • Chart Viewport: Solid History (t <= T) + Blurred / Hidden Future Zone        │
│  • Interactive "Reveal" Button -> Glowing Green / Red Trajectory + Exit Pin     │
│  • Day Batch Scorecard Modal (Success Rate %, Avg Duration, Portfolio PnL)      │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## Detailed 6-Phase Implementation Plan

---

### Phase 1: Local 5-Year Data Engine & Pre-Caching Architecture

#### Objective
Ensure all required historical data (daily Adjusted Close, Open, High, Low, Volume) for the entire universe of paired stocks is downloaded once, sanitized, validated, and stored in a high-performance local file format (`.parquet` or `.feather`). This guarantees zero API rate limits, 100% offline functionality, and microsecond slicing speeds.

#### Tasks & Steps
1. **Universe Extraction**:
   * Parse `sp500_master_pairs.json` and `elite_curated_pairs.json` to extract the full deduplicated list of unique stock tickers (~80–120 tickers).
2. **Bulk Data Harvester (`engine/harvest_5y_universe.py`)**:
   * Download 5 full calendar years of daily adjusted OHLCV data for all symbols.
   * Primary provider: FMP API (using existing project API key from `.env`).
   * Fallback provider: `yfinance` for any missing symbols or missing historical bars.
   * Enforce split and dividend adjustment to prevent false synthetic divergence spikes.
3. **Data Sanitization & Alignment**:
   * Align all price series to standard NYSE trading day calendar (drop non-trading days, forward-fill single-day holiday discrepancies if any).
   * Verify zero missing values in adjusted closing prices across the 5-year span.
4. **Local Parquet Persistence**:
   * Save unified multi-ticker DataFrame to `data_cache/universe_5y_daily.parquet`.
   * Create metadata header (`data_cache/universe_meta.json`) recording date ranges, ticker count, and timestamp of harvest.
5. **Benchmark Verification**:
   * Benchmark load time: Loading the entire 5-year universe from parquet into RAM must complete in $< 150\text{ ms}$.
   * Benchmark slice time: Slicing `df.loc[:T]` for 100 tickers must complete in $< 5\text{ ms}$.

#### Deliverables & Quality Gates
* File: `engine/harvest_5y_universe.py`
* File: `data_cache/universe_5y_daily.parquet`
* File: `data_cache/universe_meta.json`
* Automated test confirming zero lookahead leakage and zero `NaN` values across all universe symbols.

---

### Phase 2: Point-in-Time Setup Scanner & Forward Outcome Evaluator

#### Objective
Build the mathematical core that enforces strict historical truncation for any simulated date $T$, identifies active divergence setups, and evaluates forward performance when revealed using target-first vs. stop-first logic.

#### Tasks & Steps
1. **Strict Temporal Partitioning**:
   * Input: Base date $T$ (e.g., `2024-04-15`).
   * Engine creates slice: $D_T = \{ \text{bar} \in \text{UniverseData} \mid \text{bar.date} \le T \}$.
   * Guaranteed: Zero access to any bar where $\text{bar.date} > T$.
2. **Point-in-Time Statistical Engine**:
   * Lookback window: Configurable, defaulting to 90 trading days prior to $T$.
   * Calculate for every active pair in universe:
     * Dynamic Hedge Ratio ($\beta$) via Ordinary Least Squares (OLS) on $D_T$.
     * Rolling spread series: $\text{Spread}_t = \text{Price}_{A,t} - \beta \cdot \text{Price}_{B,t}$.
     * Current Spread Z-Score: $z_T = \frac{\text{Spread}_T - \mu_{90}}{\sigma_{90}}$.
     * Cointegration test: Augmented Dickey-Fuller (ADF) $t$-stat and $p$-value on residuals.
     * Pearson correlation coefficient $r$.
     * Spread Volatility Tier (`Ultra-Tight`, `Tight`, `Medium`, `High`).
3. **Setup Filter & Ranking**:
   * Trigger condition: $|z_T| \ge 2.0$.
   * Filter gates: Correlation $\ge 0.85$, ADF $p \le 0.05$, Half-Life $\in [2, 35]$ days.
   * Calculate Composite Setup Score (0–100) using weights defined in `pair_strategy_config.json`.
   * Generate clear trade instructions:
     * If $z_T \le -2.0$: **BUY Ticker A @ Close, SHORT Ticker B @ Close** (Spread is undervalued).
     * If $z_T \ge +2.0$: **SHORT Ticker A @ Close, BUY Ticker B @ Close** (Spread is overvalued).
4. **Forward Outcome Evaluator Engine (`engine/forward_evaluator.py`)**:
   * Takes the setup generated at Date $T$ and inspects future slice $F_T = \{ \text{bar} \mid \text{bar.date} > T \}$.
   * **Exit Evaluation Logic (Priority-Ordered)**:
     1. **Target Mean-Reversion (WIN / GREEN)**:
        * Check day-by-day: Does spread cross $z = 0.0$ or achieve $\ge 80\%$ reversion back to $\mu$?
        * If YES, mark as **WIN**. Record exit date $T_{\text{exit}}$, days held, and return percentage.
     2. **Stop-Loss Divergence (LOSS / RED)**:
        * Check day-by-day: Does spread expand beyond $|z| \ge 3.5\sigma$ (or custom stop threshold)?
        * If YES (and target was not previously hit), mark as **LOSS / STOPPED OUT**. Record $T_{\text{stop}}$, days held, and loss percentage.
     3. **Time-Horizon Expiry (NEUTRAL / MARK-TO-MARKET)**:
        * If neither target nor stop hit within chosen window (1 Week / 1 Month), record net gain/loss at window close.
5. **Day Batch Summary Calculator**:
   * Evaluates all top setups on Date $T$ simultaneously.
   * Computes: Total Setups, Win Rate %, Profit Factor, Average Reversion Duration (days), and Combined Net Simulated Return %.

#### Deliverables & Quality Gates
* File: `engine/simulator_engine.py` (Contains `PointInTimeEngine` and `ForwardOutcomeEvaluator`)
* Unit tests in `tests/test_simulator_engine.py` proving:
  * Running scanner for Date $T$ produces identical results regardless of whether future data is loaded in disk.
  * Stop-loss takes precedence over a late rebound that occurs after $3.5\sigma$ breach.
  * Target hit on Day 4 is properly locked in as a Win even if spread re-diverges on Day 20.

---

### Phase 3: Fast Simulator Backend API Endpoints

#### Objective
Expose clean, fast REST API endpoints in FastAPI (`api/simulator_router.py`) to drive the frontend dashboard. Endpoints must support session tracking, forward stepping, chart delivery with partition masks, and reveal payloads.

#### API Contract Specifications

1. **`POST /api/simulator/init`**
   * *Payload*: `{ "base_date": "2024-03-01", "lookback_days": 90, "entry_z": 2.0, "stop_z": 3.5 }`
   * *Returns*: Session ID, initial calendar anchor $T_{\text{base}}$, available date range (min/max), and total universe pair count.

2. **`GET /api/simulator/scan`**
   * *Query Params*: `current_date=YYYY-MM-DD`
   * *Function*: Runs point-in-time detection on data up to `current_date`.
   * *Returns*:
     ```json
     {
       "date": "2024-03-01",
       "anchor_date": "2024-03-01",
       "can_step_backward": false,
       "total_setups": 4,
       "setups": [
         {
           "pair": "ADI/KLAC",
           "ticker_a": "ADI",
           "ticker_b": "KLAC",
           "action_a": "BUY",
           "action_b": "SHORT",
           "price_a": 182.40,
           "price_b": 694.10,
           "hedge_ratio": 0.261,
           "z_score": -2.42,
           "adf_pvalue": 0.012,
           "half_life_days": 8.4,
           "composite_score": 87.5,
           "expected_reversion_pct": 3.8,
           "spread_vol_tier": "Tight"
         }
       ]
     }
     ```

3. **`GET /api/simulator/step`**
   * *Query Params*: `direction=+1 | -1`
   * *Validation*: Rejects `-1` if current date $\le T_{\text{base}}$. Advances to the next NYSE trading day if `+1`.
   * *Returns*: Updated scan results for the new date.

4. **`GET /api/simulator/pair-chart`**
   * *Query Params*: `ticker_a=ADI&ticker_b=KLAC&current_date=2024-03-01&reveal=false`
   * *Behavior*:
     * When `reveal=false`: Returns OHLCV and spread series **only** up to `current_date`.
     * Future timestamps are returned as null/empty (preventing client-side inspection leakage).

5. **`POST /api/simulator/reveal`**
   * *Payload*:
     ```json
     {
       "ticker_a": "ADI",
       "ticker_b": "KLAC",
       "current_date": "2024-03-01",
       "horizon": "1M" // "1W" | "1M" | "FULL"
     }
     ```
   * *Returns*:
     ```json
     {
       "outcome": "WIN", // "WIN" | "LOSS" | "NEUTRAL"
       "color": "#10B981", // Emerald green for profit, Rose red for loss
       "return_pct": 3.42,
       "exit_date": "2024-03-11",
       "days_held": 7,
       "exit_reason": "Mean reversion target reached (z = 0.08)",
       "future_bars": [
         { "date": "2024-03-04", "price_a": 184.1, "price_b": 690.2, "z_score": -1.8 },
         { "date": "2024-03-11", "price_a": 189.5, "price_b": 682.0, "z_score": 0.08 }
       ]
     }
     ```

6. **`GET /api/simulator/batch-scorecard`**
   * *Query Params*: `current_date=YYYY-MM-DD&horizon=1M`
   * *Returns*: Aggregate statistics across all setups triggered on `current_date`.

#### Deliverables & Quality Gates
* File: `api/simulator_router.py`
* Registration in `api/main.py`: Mount router under `/api/simulator`.
* Swagger docs verification at `http://localhost:8000/docs`.
* Sub-100ms response time per endpoint.

---

### Phase 4: Blind Replay Simulator Dashboard UI & VCR Controls

#### Objective
Create an intuitive, focused React dashboard page (`/simulator`) in the frontend application. Provide clean VCR-style playback controls, strict anchor locks, and a top setups inspection table.

#### Tasks & Steps
1. **Route & Layout Setup**:
   * Add route `/simulator` to `frontend/src/App.tsx`.
   * Add navigation tab **"Replay Simulator"** to main navigation header with an indicator badge (e.g. `[Lab/Testing]`).
2. **Master VCR Playback Control Bar**:
   * **Calendar Date Picker**: Set initial anchor date $T_{\text{base}}$.
   * **Anchor Lock Indicator**: Displays $T_{\text{base}}$ with a padlock icon. Backward navigation stops here.
   * **Step Buttons**:
     * `[-1 Day]`: Disabled when `current_date == anchor_date`.
     * `[+1 Day]`: Steps forward one trading session, dynamically running the scan.
   * **Play / Pause Auto-Stepper**:
     * Auto-advances day by day with adjustable interval (`0.5s`, `1s`, `2s` per day).
     * Automatically pauses if an exceptional high-score setup ($\ge 90$) triggers.
   * **Quick Date Jump**: Select preset regimes (e.g. *Q1 2023 Tech Rally*, *Oct 2023 Correction*, *Q1 2024 Semis Boom*).
3. **Point-in-Time Setups Table**:
   * Clean table listing pairs meeting divergence criteria on `current_date`:
     * **Pair**: e.g., `ADI / KLAC` (with sector badge `Semiconductors`).
     * **Action**: Vibrant badges: `BUY ADI @ $182.40` | `SHORT KLAC @ $694.10`.
     * **Z-Score**: Divergence meter (e.g. `-2.42σ`).
     * **Composite Score**: Circular radial badge (e.g. `88 / 100`).
     * **Target Return**: Expected mean-reversion gain (e.g. `+3.8%`).
     * **Action Column**: `[ Inspect Chart ]` button.
   * Empty State: Friendly notice if no pairs pass criteria on that day (*"No pairs exceeded 2.0σ divergence on this session. Click +1 Day to advance"*).

#### Deliverables & Quality Gates
* File: `frontend/src/pages/SimulatorPage.tsx`
* File: `frontend/src/components/simulator/SimulatorControlBar.tsx`
* File: `frontend/src/components/simulator/SimulatorSetupsTable.tsx`
* Responsive UI with smooth loading states and zero layout shifts during day-stepping.

---

### Phase 5: Visual "Reveal" Engine & Outcome Glow/Pinpoint System

#### Objective
Build the split-screen chart viewport and the interactive "Reveal" mechanics. Implement the frosted/blurred future mask, the reveal trigger, and the dynamic glowing Green/Red trajectory strokes with outcome pinpoints.

#### Tasks & Steps
1. **Dual-Zone Chart Viewport (`frontend/src/components/simulator/ReplayPairChart.tsx`)**:
   * Built on `lightweight-charts` (matching current platform charts).
   * **Left Zone ($t \le T$)**:
     * Displays real historical normalized price curves and spread z-score.
     * Clean vertical divider at Date $T$ with label: `ENTRY DATE (T)`.
   * **Right Zone ($t > T$)**:
     * *Before Reveal*: Frosted glass overlay with centered call-to-action button:
       `[ 👁️ Reveal 1-Month Outcome ]`.
     * Dropdown toggle on the reveal card: `[ 1 Week ]` | `[ 1 Month (Default) ]` | `[ Full Resolution ]`.
2. **The "Reveal" Animation & Trajectory Coloring**:
   * Upon clicking **Reveal**:
     * Frosted glass overlay dissolves with a smooth fade.
     * The future price path draws dynamically.
     * **If Outcome == WIN**:
       * Spread and price lines render with **Glowing Emerald Green stroke** (`#10B981`, with drop-shadow glow).
       * Pinpoint marker placed at $T_{\text{exit}}$: `🎯 Target Hit (+3.4% in 7 Days)`.
     * **If Outcome == LOSS**:
       * Spread and price lines render with **Glowing Rose Red stroke** (`#EF4444`, with alert styling).
       * Pinpoint marker placed at $T_{\text{stop}}$: `🛑 Stop Loss Hit (-2.9% in 11 Days)`.
     * **If Outcome == NEUTRAL**:
       * Neutral amber/slate line showing unrealized PnL at window close.
3. **Day Batch Scorecard Modal**:
   * Header button: **"Reveal All Pairs for [Date T]"**.
   * Opens high-impact summary modal:
     * Overall accuracy circle: e.g. **4 / 5 Succeeded (80% Win Rate)**.
     * Total Net Return: e.g. **+8.4% Cumulative**.
     * Average Time in Trade: e.g. **6.5 Days**.
     * Mini cards for each pair showing their green/red mini-sparkline.

#### Deliverables & Quality Gates
* File: `frontend/src/components/simulator/ReplayPairChart.tsx`
* File: `frontend/src/components/simulator/OutcomeScorecardModal.tsx`
* Seamless visual transition when revealing; zero glitching or chart re-renders.

---

### Phase 6: Verification, End-to-End Walk-Forward Testing & Performance Optimization

#### Objective
Conduct rigorous walk-forward test scenarios across diverse historical periods (bull market, bear market, sideways choppy regimes) to verify execution accuracy, absence of lookahead leaks, and smooth client performance.

#### Test Regimes & Walk-Forward Scenarios
1. **Regime A: High Volatility Bear Market (Q1–Q2 2022)**
   * Verify how cointegrated pairs behave during broad market selloffs.
   * Confirm stop-loss triggers accurately when fundamental decoupling occurs.
2. **Regime B: Mega-Cap Tech Dispersal (Q3–Q4 2023)**
   * Verify pairs in the Semiconductor sector (e.g., ADI vs. KLAC, LRCX vs. AMAT).
   * Confirm high mean-reversion win rates in trending sectors.
3. **Regime C: Choppy Range-Bound Consolidation (Summer 2024)**
   * Validate quick mean-reversion snaps within 1-week horizons.

#### Acceptance Criteria & Quality Metrics
* [ ] **Temporal Integrity**: Hash check confirming that historical bar outputs at Date $T$ match exactly whether Date $T$ was run in isolation or during a step-forward sequence.
* [ ] **Speed Benchmarks**:
  * Stepping +1 Day: $< 300\text{ ms}$ total roundtrip (backend calculation + UI update).
  * Clicking Reveal: $< 150\text{ ms}$ to fetch outcome and animate future stroke.
* [ ] **Accuracy Audit**:
  * Every green trade verified to have reached mean reversion without violating stop loss.
  * Every red trade verified to have crossed the stop-loss barrier before any reversion.
* [ ] **Code Cleanliness & Isolation**:
  * Simulator engine completely decoupled from live production scanner so it can be enabled or deprecated without affecting existing production endpoints.

---

## Technical File Tree & Architecture

```
akash-research-platform/
├── backtest_update_plan.md               # [This Document]
├── data_cache/
│   ├── universe_5y_daily.parquet        # 5-Year Master Cleaned Daily OHLCV
│   └── universe_meta.json               # Universe metadata & harvest timestamp
├── engine/
│   ├── harvest_5y_universe.py           # 5-Year Bulk Downloader & Formatter
│   ├── simulator_engine.py              # Point-in-Time Scanner & Forward Evaluator
│   └── pair_strategy_config.json        # Unified Strategy Configuration
├── api/
│   ├── simulator_router.py              # FastAPI Endpoints for Simulator
│   └── main.py                          # Mounts /api/simulator router
├── frontend/
│   └── src/
│       ├── pages/
│       │   └── SimulatorPage.tsx        # Main Replay & Simulator Dashboard Page
│       └── components/
│           └── simulator/
│               ├── SimulatorControlBar.tsx   # Date Picker, Anchor Lock, +1/-1 Day
│               ├── SimulatorSetupsTable.tsx  # Point-in-Time Recommendations
│               ├── ReplayPairChart.tsx       # Dual-Zone Chart with Reveal Mechanism
│               └── OutcomeScorecardModal.tsx # Day Batch Accuracy Scorecard
└── tests/
    └── test_simulator_engine.py         # Temporal Integrity & Logic Test Suite
```

---

## Next Steps

With this document finalized and placed in the project root:
1. **Phase 1 Execution**: Run `engine/harvest_5y_universe.py` to create `data_cache/universe_5y_daily.parquet`.
2. **Phase 2 & 3 Execution**: Build `simulator_engine.py` and mount `api/simulator_router.py`.
3. **Phase 4 & 5 Execution**: Construct the React frontend `/simulator` UI and test the Blind Reveal mechanism.
4. **Phase 6 Verification**: Run walk-forward benchmark tests across 2022–2025 data.
