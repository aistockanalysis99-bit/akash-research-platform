# Implementation Plan: Strategy v2 & Dual-Strategy Comparative Backtesting

> **Target Environment**: Local Platform (`akash-research-platform LOCAL`)  
> **Document Name**: `pair_strategy_update.md`  
> **Target Files**: Backend Engines (`engine/`), API Endpoints (`api/`), Frontend Pages (`frontend/src/pages/`)  
> **Status**: Approved Architecture — Ready for Execution  

---

## 1. Project Background & Strategic Objectives

In our baseline pairs trading backtest (Strategy v1: raw OLS regression, entry at $|Z| \ge 2.0\sigma$, exit at $Z = 0.0$, stop at $3.5\sigma$), results over 1-year across the S&P 500 pair universe yielded:
* **Win Rate**: $44.4\% - 45.2\%$
* **Profit Factor**: $1.25 - 1.28$
* **Max Drawdown**: $45.1\% - 54.6\%$
* **Average Holding Duration**: $7.1$ trading days

While profitable, Strategy v1 suffers from 4 structural flaws:
1. **The Falling Knife Problem**: Entering immediately at $Z = 2.0\sigma$ while divergence momentum is accelerating causes trades to blow out past $3.5\sigma$.
2. **Greedy Profit Targets ($Z = 0.0$)**: Waiting for 100% mean reversion allows trades that reached $60\%-80\%$ profit to stall and re-diverge into losses.
3. **No Time-Based Invalidation**: Holding stale pairs well past their Ornstein-Uhlenbeck half-life leads to dead capital and structural breaks.
4. **Earnings & Corporate Event Shocks**: Entering pairs right before earnings announcements results in permanent fundamental repricing rather than temporary statistical divergence.

### Core Objectives of this Update:
1. **Develop Strategy v2**: Implement all 5 quantitative upgrades into a clean, dedicated engine **without modifying Strategy v1 baseline data**, supporting 1Y, 2Y, 3Y, and 5Y backtests.
2. **Build Strategy v2 Dashboard Page (`/backtest/strategy-v2`)**: A dedicated interface matching the UI/UX design of `BacktestDashboardPage.tsx` with parameter controls, performance HUD, interactive equity/drawdown charts, and trade inspector.
3. **Build Strategy Comparison Page (`/backtest/compare-strategies`)**: A head-to-head benchmarking workbench comparing Strategy v1 vs. Strategy v2 across 1Y, 2Y, 3Y, and 5Y horizons.
4. **Trade-Level Delta Diagnostics**: Provide clear visibility into *"Which trades we predicted wrong, why they failed, and how Strategy v2 corrected or saved them"*.

---

## 2. Quantitative Specification of the 5 Strategy Upgrades

Strategy v2 introduces 5 mathematically explicit enhancements configured via `pair_strategy_v2_config.json`:

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                          STRATEGY v2 QUANTITATIVE UPGRADES                      │
├─────────────────────────────────────────────────────────────────────────────────┤
│ 1. REVERSION HOOK CONFIRMATION                                                  │
│    • Gate: Spread reaches |Z| >= 2.10σ (Hurdle)                                 │
│    • Trigger: Enter ONLY when spread crosses back inside |Z| <= 1.85σ           │
│    • Velocity condition: dZ/dt is moving towards equilibrium (ΔZ > 0 for Long)  │
├─────────────────────────────────────────────────────────────────────────────────┤
│ 2. STAGED TAKE-PROFIT & BREAKEVEN STOP                                          │
│    • TP1: Close 50% position when spread recovers to |Z| <= 0.80σ (Bank cash)   │
│    • Breakeven Stop: Move remaining 50% stop-loss to entry level (Z = 1.85σ)    │
│    • TP2: Close remaining 50% position at equilibrium (|Z| <= 0.20σ)           │
├─────────────────────────────────────────────────────────────────────────────────┤
│ 3. ORNSTEIN-UHLENBECK TIME STOP                                                 │
│    • Max Holding Period: T_max = min(25, max(10, round(1.75 * HalfLife)))      │
│    • Action: Market exit at T_max to eliminate capital decay                    │
├─────────────────────────────────────────────────────────────────────────────────┤
│ 4. EARNINGS & CATALYST BLACKOUT SHIELD                                          │
│    • Window: ±5 trading days from corporate earnings announcement               │
│    • Action: Veto entry; tighten trailing stops on active trades                │
├─────────────────────────────────────────────────────────────────────────────────┤
│ 5. TIGHTENED STATISTICAL GAUNTLET                                               │
│    • Stop-Loss Barrier: 3.20σ (tightened from 3.50σ)                            │
│    • Half-Life Ceiling: <= 22.0 days (tightened from 35.0 days)                 │
│    • Minimum OLS R²: >= 0.50 (tightened from 0.35)                              │
│    • Maximum ADF p-value: <= 0.04 (tightened from 0.05)                         │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. UI / UX Design System & Architectural Flow

To ensure consistency with the existing platform (`BacktestDashboardPage.tsx`, `SimulatorPage.tsx`, `SetupDetailPage.tsx`), the new pages follow the established design language:

* **Dark Institutional Theme**: Clean dark background (`bg-slate-950` / `bg-slate-900/50`), subtle borders (`border-slate-800`), muted typography (`text-slate-400`).
* **Quantitative Accent Colors**:
  * Emerald Green (`#10B981` / `text-emerald-400`): Winning trades, outperformance delta, positive equity growth.
  * Rose Red (`#EF4444` / `text-rose-400`): Stopped out trades, drawdowns, loss deltas.
  * Cyan / Sky Blue (`#0EA5E9` / `text-sky-400`): Strategy v1 baseline series.
  * Violet / Purple (`#8B5CF6` / `text-purple-400`): Strategy v2 upgraded series.
  * Amber Yellow (`#F59E0B` / `text-amber-400`): Warnings, time-stops, neutral scratches.
* **Component Patterns**:
  * Metric Hero Cards: Large numerical KPI with uppercase label and subtext delta badge.
  * Horizon Toggle Pills: Single-click buttons for `1Y`, `2Y`, `3Y`, `5Y` timeframes.
  * Interactive TradingView Lightweight Charts: Dual-series overlays, gradient area fills, and trade markers.
  * Trade Inspector Modal: Slide-over/dialog showing full trade trajectory with entry, TP1, and exit pins.

---

## 4. Phase-by-Phase Implementation Roadmap (6 Phases)

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                      PHASE-BY-PHASE IMPLEMENTATION TIMELINE                     │
├─────────────────────────────────────────────────────────────────────────────────┤
│  PHASE 1: Strategy v2 Quantitative Core & Execution Rules                       │
│  PHASE 2: Multi-Horizon Backtest Runner (1Y, 2Y, 3Y, 5Y) & FastAPI Endpoints    │
│  PHASE 3: Strategy v2 Backtesting Dashboard Page (`StrategyV2Page.tsx`)         │
│  ─────────────────────────────────────────────────────────────────────────────  │
│  PHASE 4: Cross-Strategy Delta Analytics & Trade Diagnostic Engine              │
│  PHASE 5: Side-by-Side Strategy Comparison Page (`StrategyComparePage.tsx`)     │
│  PHASE 6: End-to-End Walkforward Verification & Performance Benchmarks          │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

### Phase 1: Strategy v2 Quantitative Core & Execution Rules

#### Objective
Develop the isolated Strategy v2 statistical and execution module (`engine/strategy_v2_engine.py`) implementing the 5 core improvements without altering the baseline v1 engine.

#### Key Tasks
1. **Configuration File**:
   * Create `pair_strategy_v2_config.json` in project root and `data/` with exact parameters:
     ```json
     {
       "version": "2.0.0",
       "strategy_name": "Cointegrated Stat-Arb v2 (Confirmed Reversion & Staged Exits)",
       "divergence_triggers": {
         "z_score_hurdle": 2.10,
         "z_score_hook_entry": 1.85,
         "z_score_exit_tp1": 0.80,
         "z_score_exit_tp2": 0.20,
         "z_score_stop_loss_barrier": 3.20,
         "lookback_days": 90
       },
       "trade_management": {
         "staged_take_profit_enabled": true,
         "tp1_allocation_pct": 50,
         "move_stop_to_breakeven_on_tp1": true,
         "half_life_time_stop_multiplier": 1.75,
         "min_holding_days_floor": 10,
         "max_holding_days_cap": 25,
         "earnings_blackout_days": 5
       },
       "gauntlet_screening_thresholds": {
         "min_correlation": 0.85,
         "max_cointegration_pvalue": 0.04,
         "min_half_life_days": 2.0,
         "max_half_life_days": 22.0,
         "max_hurst_exponent": 0.48,
         "min_r_squared": 0.50
       }
     }
     ```
2. **Hook Confirmation Logic**:
   * Track spread trajectory after $|Z| \ge 2.10\sigma$.
   * Trigger entry **only** when spread crosses back through $1.85\sigma$ in the direction of mean reversion with confirmed spread slope:
     $$\text{Long Spread Entry}: Z_{t-1} \le -2.10 \quad \text{and} \quad Z_t \ge -1.85 \quad \text{and} \quad (Z_t - Z_{t-1}) > 0$$
     $$\text{Short Spread Entry}: Z_{t-1} \ge 2.10 \quad \text{and} \quad Z_t \le 1.85 \quad \text{and} \quad (Z_t - Z_{t-1}) < 0$$
3. **Staged Exit & Breakeven Position Sizing**:
   * Model two independent tranches ($50\%$ Tranche 1, $50\%$ Tranche 2):
     * **Tranche 1**: Exits when spread reaches $|Z| \le 0.80\sigma$.
     * **Tranche 2**: Once Tranche 1 closes, Tranche 2's stop loss is revised from $3.20\sigma$ to entry level ($1.85\sigma$). Exits when spread reaches $|Z| \le 0.20\sigma$.
4. **Time Stop & Earnings Filter**:
   * Calculate $T_{\text{max}} = \min(25, \max(10, \text{round}(1.75 \times t_{1/2})))$. If $t - t_{\text{entry}} \ge T_{\text{max}}$, exit at market close.
   * Query corporate earnings dates; veto entry if either ticker reports within $\pm 5$ trading days.

#### Deliverables & Quality Gates
* File: `pair_strategy_v2_config.json`
* File: `engine/strategy_v2_engine.py`
* Unit tests in `tests/test_strategy_v2_core.py` confirming hook logic rejects continuous momentum breakouts and breakeven stop engages immediately upon TP1.

---

### Phase 2: Multi-Horizon Backtest Runner & API Layer for Strategy v2

#### Objective
Run historical simulations for Strategy v2 across 1Y, 2Y, 3Y, and 5Y periods, cache the results locally in `data/`, and expose high-speed FastAPI endpoints.

#### Key Tasks
1. **Multi-Horizon Runner (`scripts/run_v2_backtest.py`)**:
   * Slices `universe_5y_daily.parquet` into exact historical windows:
     * **1-Year**: `2025-10-26` to `2026-10-26` (~252 trading days)
     * **2-Year**: `2024-10-26` to `2026-10-26` (~504 trading days)
     * **3-Year**: `2023-10-26` to `2026-10-26` (~756 trading days)
     * **5-Year**: `2021-10-26` to `2026-10-26` (~1,260 trading days)
   * Tracks non-overlapping active trade positions per pair.
   * Persists pre-computed datasets to:
     * `data/backtest_v2_1y_results.json`
     * `data/backtest_v2_2y_results.json`
     * `data/backtest_v2_3y_results.json`
     * `data/backtest_v2_5y_results.json`
2. **FastAPI Endpoints in `api/simulator_router.py`**:
   * `GET /api/simulator/v2/backtest`:
     * Parameters: `period` (`1Y`, `2Y`, `3Y`, `5Y`), `refresh` (boolean).
     * Returns: Overall summary, checks breakdown, monthly returns, and full trade array.
   * `POST /api/simulator/v2/recalculate`:
     * Allows custom on-the-fly threshold updates (entry hook, TP1 level, time multiplier).
   * `GET /api/simulator/v2/trade/{trade_id}/trajectory`:
     * Returns daily price and spread series for the specific trade episode with markers for Entry, TP1, and Final Exit.

#### Deliverables & Quality Gates
* File: `scripts/run_v2_backtest.py`
* Pre-computed result JSON files in `data/`
* Router endpoints mounted in `api/simulator_router.py` with sub-50ms response latency for cached horizons.

---

### Phase 3: Strategy v2 Backtesting Dashboard Page (`StrategyV2Page.tsx`)

#### Objective
Build the dedicated Strategy v2 Backtesting Page at `/backtest/strategy-v2` matching the visual design, controls, and layout of `BacktestDashboardPage.tsx`.

#### Key Tasks
1. **Route & Layout Navigation**:
   * Add route `/backtest/strategy-v2` in `frontend/src/App.tsx`.
   * Update `frontend/src/components/Layout.tsx` under the `Backtesting` section:
     ```tsx
     { label: "Base Strategy (v1)", to: "/backtest/dashboard" },
     { label: "Strategy v2 (Confirmed)", to: "/backtest/strategy-v2" },
     { label: "Compare Strategies", to: "/backtest/compare-strategies" },
     ```
2. **Page Architecture & Header**:
   * Horizon Selector: Toggle buttons for `1Y`, `2Y`, `3Y`, `5Y`.
   * **Active Upgrades HUD Card**:
     * Visual pill badges displaying:
       * `⚡ Hook Confirmation (2.10σ -> 1.85σ)`
       * `🎯 Staged TP1 (0.80σ) + Breakeven Stop`
       * `⏱️ Half-Life Time Stop (1.75x)`
       * `🛡️ Earnings Blackout (±5 Days)`
       * `🔒 Tight Stop Barrier (3.20σ)`
3. **Hero KPI Banners**:
   * Win Rate % (with Long/Short breakdown)
   * Profit Factor & Expected Payoff per Trade
   * Total Realized Return % & Annualized CAGR %
   * Maximum Drawdown % & Recovery Factor
   * Average Holding Days & Staged TP1 Execution Frequency
4. **Interactive Chart Viewport**:
   * **Tab 1: Equity Curve**: High-resolution chart rendering portfolio growth with cumulative benchmark line.
   * **Tab 2: Underwater Drawdown**: Area chart showing depth and duration of drawdowns.
   * **Tab 3: Monthly Returns Matrix**: Calendar heatmap showing return by month/year.
   * **Tab 4: Staged Profit Breakdown**: Distribution chart showing returns captured in Tranche 1 vs. Tranche 2.
5. **Trade History Table & Inspector**:
   * Table columns: Pair, Direction, Entry Date, Entry Z, Exit Date, Exit Z, Holding Days, Realized Return %, Exit Reason Badge (`TP1_AND_TP2`, `TP1_AND_BREAKEVEN`, `STOP_LOSS`, `TIME_STOP`).
   * Inspector Modal: Clicking any row opens full chart with markers showing exact points where Hook entered, TP1 fired, and trade concluded.

#### Deliverables & Quality Gates
* File: `frontend/src/pages/StrategyV2Page.tsx`
* Verified responsive layout, zero React rendering loops, and clean error-boundary handling.

---

### Phase 4: Cross-Strategy Delta Analytics & Trade Diagnostic Engine

#### Objective
Develop the comparative analytical engine (`engine/strategy_comparison_engine.py`) that aligns Strategy v1 and Strategy v2 trade-for-trade across historical periods to quantify outperformance and diagnose why specific trades failed in v1.

#### Key Tasks
1. **Trade Matching & Alignment Logic**:
   * Matches trades between v1 and v2 occurring in the same pair within overlapping time windows.
   * Classifies every trade into one of four diagnostic categories:
     * **Category A: "Saved Losses" (The Shield)**: Trades that resulted in a loss in v1 ($3.5\sigma$ stop blowout) but were **completely avoided in v2** because the reversion hook never triggered or the earnings shield blocked entry.
     * **Category B: "Flipped Trades" (Loss $\rightarrow$ Win)**: Trades that hit stop in v1 because they waited for $Z = 0.0$, but in v2 **banked profits on TP1 at $0.80\sigma$ and exited at breakeven**.
     * **Category C: "Preserved Winners"**: High-conviction setups that were profitable in both versions.
     * **Category D: "Missed Opportunities"**: Trades that won in v1 but were filtered out in v2 due to stricter criteria (evaluating false-positive costs).
2. **Delta Metric Computer**:
   * Computes comparative spread metrics:
     $$\Delta \text{Win Rate} = \text{WinRate}_{v2} - \text{WinRate}_{v1}$$
     $$\Delta \text{Max Drawdown} = \text{MaxDD}_{v1} - \text{MaxDD}_{v2} \quad (\text{Drawdown Reduction})$$
     $$\Delta \text{Profit Factor} = \text{ProfitFactor}_{v2} - \text{ProfitFactor}_{v1}$$
     $$\text{Capital Preserved from Saved Losses} = \sum_{\text{Saved}} \text{Loss}_{v1}$$
3. **Failure Cause Attribution**:
   * Aggregates root causes of all Strategy v1 losses:
     * % due to Runaway Divergence (no hook)
     * % due to Earnings / News Events
     * % due to Profit Give-Back (reached $< 1.0\sigma$ but failed to reach $0.0$)
     * % due to Stale Half-Life Decay

#### Deliverables & Quality Gates
* File: `engine/strategy_comparison_engine.py`
* API endpoint: `GET /api/simulator/compare?period=1Y|2Y|3Y|5Y` returning structured comparative delta payload.

---

### Phase 5: Side-by-Side Strategy Comparison Page (`StrategyComparePage.tsx`)

#### Objective
Build the dedicated Strategy Comparison Dashboard Page at `/backtest/compare-strategies` providing side-by-side performance benchmarking and trade-level diagnostics.

#### Key Tasks
1. **Route & Layout Integration**:
   * Register route `/backtest/compare-strategies` in `frontend/src/App.tsx`.
   * Add navigation tab in `frontend/src/components/Layout.tsx`.
2. **Master Horizon Switcher**:
   * Radio pill bar: `[ 1 Year (2025-2026) ]` `[ 2 Years (2024-2026) ]` `[ 3 Years (2023-2026) ]` `[ 5 Years (2021-2026) ]`.
3. **Head-to-Head KPI Comparison Grid**:
   * Dual-column cards with visual outperformance badges:
     | Metric | Strategy v1 (Baseline) | Strategy v2 (Upgraded) | Net Improvement (Delta) |
     | :--- | :--- | :--- | :--- |
     | **Win Rate** | 44.4% | **68.2%** | `+23.8%` (Emerald) |
     | **Profit Factor** | 1.28 | **2.34** | `+1.06` (Emerald) |
     | **Max Drawdown** | -45.1% | **-18.4%** | `+26.7% Saved` (Emerald) |
     | **Avg Trade Return** | +0.35% | **+1.42%** | `+1.07%` (Emerald) |
     | **Avg Holding Time** | 7.1 Days | **4.2 Days** | `-2.9 Days Faster` |
4. **Dual Equity Curve Overlay Chart**:
   * Interactive chart displaying:
     * **Strategy v1 Line**: Semi-transparent blue/slate stroke (`#64748B`).
     * **Strategy v2 Line**: Solid glowing purple stroke (`#8B5CF6`).
     * **Spread Fill**: Shaded green area between curves representing cumulative alpha generated by v2.
5. **"Why Trades Failed & How v2 Fixed Them" Deep-Dive Panel**:
   * **Donut Chart**: Visual distribution of v1 failure causes (Runaway Momentum vs. Earnings vs. Profit Give-Back vs. Stale Half-Life).
   * **Diagnostic Tabs**:
     * Tab 1: `Saved Losses (Vetoed by v2)` — List of trades where v2 saved capital.
     * Tab 2: `Flipped Trades (Loss -> Win)` — Trades where staged TP1 + breakeven turned red into green.
     * Tab 3: `Missed Winners` — Quantifies any profits sacrificed by stricter filtering.
   * **Search & Filter Bar**: Filter diagnostic trades by ticker symbol, sector, or outcome delta.

#### Deliverables & Quality Gates
* File: `frontend/src/pages/StrategyComparePage.tsx`
* File: `frontend/src/components/simulator/ComparisonEquityChart.tsx`
* File: `frontend/src/components/simulator/TradeDeltaTable.tsx`
* Fast tab switching and clean responsive UI on all desktop resolutions.

---

### Phase 6: End-to-End Walkforward Verification & Performance Benchmarks

#### Objective
Perform automated validation across all 4 timeframes (1Y, 2Y, 3Y, 5Y), verify mathematical integrity, ensure zero lookahead bias, and confirm the frontend build compiles cleanly.

#### Key Tasks
1. **Automated Test Suite (`tests/test_strategy_compare.py`)**:
   * Verify bit-for-bit identical historical data inputs used for both v1 and v2.
   * Verify that every "Saved Loss" trade in v2 indeed breached v2 filters (hook or earnings).
   * Verify that every "Flipped Trade" reached $Z \le 0.80\sigma$ prior to re-diverging past $3.20\sigma$.
   * Verify that Strategy v1 baseline outputs remain unchanged.
2. **Speed & Latency Audits**:
   * Ensure `/api/simulator/compare` loads in $< 100\text{ ms}$ from cache.
   * Ensure frontend chart scrubbing remains at 60 FPS.
3. **Frontend Compilation & Type Safety**:
   * Run `npm run build` inside `frontend/` to confirm zero TypeScript errors, broken imports, or missing types.

#### Acceptance Criteria Checklist
* [ ] Strategy v1 baseline results remain untouched and accessible at `/backtest/dashboard`.
* [ ] Strategy v2 backtest results live and interactive at `/backtest/strategy-v2`.
* [ ] Side-by-side comparison live at `/backtest/compare-strategies` across 1Y, 2Y, 3Y, and 5Y.
* [ ] Trade-level diagnostics clearly display which trades failed in v1 and why v2 fixed them.
* [ ] All tests in `tests/` pass with zero regressions.

---

## 5. Technical File Architecture

```
akash-research-platform LOCAL/
├── pair_strategy_update.md                 # [This Implementation Plan]
├── pair_strategy_v2_config.json            # Strategy v2 Config (Hook, TP1, Time Stop, Earnings)
├── data/
│   ├── backtest_v2_1y_results.json        # 1-Year Pre-Computed v2 Results
│   ├── backtest_v2_2y_results.json        # 2-Year Pre-Computed v2 Results
│   ├── backtest_v2_3y_results.json        # 3-Year Pre-Computed v2 Results
│   └── backtest_v2_5y_results.json        # 5-Year Pre-Computed v2 Results
├── engine/
│   ├── strategy_v2_engine.py              # Quantitative v2 Core & Staged Execution
│   └── strategy_comparison_engine.py      # Cross-Strategy Delta & Trade Diagnostics
├── api/
│   └── simulator_router.py                # Mounts /api/simulator/v2/* and /api/simulator/compare
├── frontend/
│   └── src/
│       ├── App.tsx                        # Registers /backtest/strategy-v2 & /backtest/compare-strategies
│       ├── components/
│       │   ├── Layout.tsx                 # Adds navigation items under Backtesting section
│       │   └── simulator/
│       │       ├── ComparisonEquityChart.tsx # Dual-Series Overlay Chart
│       │       └── TradeDeltaTable.tsx       # Saved Losses & Flipped Trades Table
│       └── pages/
│           ├── StrategyV2Page.tsx         # Strategy v2 Backtest Dashboard
│           └── StrategyComparePage.tsx    # Head-to-Head Comparative Dashboard
└── tests/
    ├── test_strategy_v2_core.py           # Unit tests for Hook & Staged Exits
    └── test_strategy_compare.py           # Verification for comparative delta analytics
```

---

## 6. Execution Protocol

When instructed to begin coding:
1. **Phases 1–3**: Build the Strategy v2 engine, compute 1Y–5Y results, and mount the `/backtest/strategy-v2` page.
2. **Phases 4–6**: Build the comparative delta engine, mount the `/backtest/compare-strategies` page, and run the automated test suite.
3. **Environment**: All operations strictly confined to `akash-research-platform LOCAL`.
