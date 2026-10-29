# Akash Research Platform

**Institutional Equity Intelligence, Statistical Arbitrage & Systematic Trading Platform**

An institutional-grade decision-support and quantitative trading workbench designed for research, risk management, and execution across US equities, cointegrated statistical arbitrage pairs, and systematic options strategies.

---

## 1. What Is the Akash Research Platform?

The **Akash Research Platform** functions as an autonomous, full-stack quantitative research department and portfolio intelligence system. Rather than relying on speculative hunches or single-indicator heuristics, the platform combines **rigorous quantitative statistical arbitrage** with an **11-agent multi-persona AI research engine** and a **systematic options trading suite**.

The platform is designed around a strict philosophy:
1. **Decision-Support Over Blind Automation**: The platform performs exhaustive mathematical screening, econometric testing, and adversarial fundamental research, presenting clean, actionable trade setups with clear risk barriers. Final capital allocation and execution remain in the operator's hands.
2. **Mathematical Edge & Market Neutrality**: Through its Cointegrated Pairs Trading engine, the platform identifies statistical pricing inefficiencies in structurally correlated equities, generating returns independent of broad market direction.
3. **Adversarial Multi-Agent Validation**: Every equity idea is stress-tested through a structured Bull vs. Bear debate, guarded by hard risk constraints and verified against real-time institutional order flow and macro regimes.
4. **Institutional Risk Controls**: Enforces position sizing, beta-neutral weighting, stop-loss barriers ($3.5\sigma$), half-life reversion horizons, and portfolio concentration caps.

---

## 2. Core Architecture & How It Works

The platform operates across five synchronized modules:

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│                                 DATA FOUNDATION                                  │
│  Financial Modeling Prep (FMP) Enterprise API  •  yfinance Fallback Provider     │
│  High-Performance Local Parquet Cache  •  Dividend & Split Adjusted Daily OHLCV  │
└────────────────────────────────────────┬─────────────────────────────────────────┘
                                         │
    ┌────────────────────────────────────┼────────────────────────────────────┐
    ▼                                    ▼                                    ▼
┌─────────────────────────┐  ┌─────────────────────────┐  ┌─────────────────────────┐
│ STATISTICAL ARBITRAGE   │  │   11-AGENT AI RESEARCH  │  │   SYSTEMATIC OPTIONS    │
│  • 10-Point Gauntlet    │  │  • 6 Domain Specialists │  │  • Real-Time IV Scanner │
│  • Cointegration Tests  │  │  • Adversarial Debate   │  │  • Greeks Risk Surface  │
│  • Rolling OLS Beta     │  │  • PM Synthesis Verdict │  │  • The Wheel Strategy   │
│  • Divergence Detector  │  │  • Memory & Dossiers    │  │  • Double Calendars     │
└───────────┬─────────────┘  └───────────┬─────────────┘  └───────────┬─────────────┘
            │                            │                            │
            └────────────────────────────┼────────────────────────────┘
                                         ▼
┌──────────────────────────────────────────────────────────────────────────────────┐
│                         CENTRAL PORTFOLIO & WATCHLIST                            │
│  Live Account Mirroring  •  Cash & Equity Balance  •  Sector Exposure Guardrails │
└────────────────────────────────────────┬─────────────────────────────────────────┘
                                         ▼
┌──────────────────────────────────────────────────────────────────────────────────┐
│                     AUTOMATION & DISPATCH PIPELINE                               │
│  APScheduler 16:30 ET Scans  •  Multi-Channel Telegram Delivery (Stocks/Options) │
└──────────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Comprehensive Feature Breakdown

### 🎯 Feature Suite 1: Cointegrated Pairs Trading & Live Divergence Scanner

The flagship quantitative module identifies high-probability statistical arbitrage opportunities across US equities by exploiting temporary price divergences between cointegrated stock pairs.

#### 1. Curated S&P 500 Master Universe & Elite Pairs
* **S&P 500 Master Universe (`sp500_master_pairs.json`)**: Hundreds of institutionally vetted pairs across core sectors:
  * **Semiconductors**: `ADI / KLAC`, `LRCX / AMAT`, `NVDA / AMD`, `QCOM / TXN`
  * **Mega-Cap Technology**: `MSFT / GOOGL`, `AAPL / MSFT`, `META / GOOGL`
  * **Financials & Banking**: `JPM / BAC`, `GS / MS`, `BLK / BX`, `C / WFC`
  * **Healthcare & Pharma**: `UNH / ELV`, `ABBV / BMY`, `JNJ / PFE`, `ISRG / SYK`
  * **Industrials & Aerospace**: `CAT / DE`, `HON / GE`, `UPS / FDX`, `LMT / RTX`
  * **Energy & Utilities**: `XOM / CVX`, `EOG / COP`, `NEE / DUK`
* **Elite Curated Subset (`elite_curated_pairs.json`)**: Pre-screened elite pairs with multi-year structural cointegration, high liquidity, and superior mean-reverting track records.

#### 2. The 10-Point Institutional Statistical Arbitrage Gauntlet
Every pair must pass strict econometric criteria before being admitted into the active watchlist:
1. **Engle-Granger Cointegration**: Augmented Dickey-Fuller (ADF) $p\text{-value} \le 0.05$ on spread residuals (stationarity confirmation).
2. **Pearson Price Correlation**: Minimum correlation $r \ge 0.85$ over the lookback window.
3. **Ornstein-Uhlenbeck Half-Life**: Mean-reversion half-life bounded strictly between $2.0$ and $35.0$ trading days (eliminates un-reverting pairs or chaotic high-frequency noise).
4. **Hurst Exponent ($H$)**: Bounded at $H < 0.48$ confirming strong anti-persistent (mean-reverting) price behavior.
5. **ADF $t$-Statistic**: Required $t\text{-stat} \le -2.8$ to reject the null hypothesis of a unit root with $95\%$ confidence.
6. **Zero-Crossings Frequency**: Minimum of $10$ mean crossings per calendar year, verifying continuous oscillations around the historical baseline.
7. **Liquidity & Average Daily Volume (ADV)**: Both legs must exceed $1,500,000$ shares/day to prevent execution slippage.
8. **OLS Goodness of Fit**: $R^2 \ge 0.35$ confirming meaningful explanatory power between the dependent and independent variables.
9. **Overlap / Structural Alignment**: Minimum overlap score of $50.0$ assessing shared fundamental business models and sector drivers.
10. **Spread Volatility Tiering**: Pairs are grouped into strict volatility risk tiers:
    * *Ultra-Tight*: Spread volatility $\le 2.5\%$
    * *Tight*: Spread volatility $\le 4.5\%$
    * *Medium*: Spread volatility $\le 7.0\%$
    * *Blowout Penalty*: Spreads exceeding $7.0\%$ volatility are flagged and penalized.

#### 3. Real-Time Divergence Setup Detection Engine (`engine/detect_setups.py`)
* **Dynamic Rolling OLS Beta**: Calibrates the exact hedge ratio ($\beta$) over a rolling 90-day window:
  $$\text{Spread}_t = \text{Price}_{A,t} - \beta \cdot \text{Price}_{B,t}$$
* **Standardized Divergence Metric (Z-Score)**:
  $$z_t = \frac{\text{Spread}_t - \mu_{90}}{\sigma_{90}}$$
* **Actionable Execution Trigger**: When $|z_t| \ge 2.0\sigma$:
  * **$z_t \le -2.0\sigma$ (Spread Undervalued)**: Generates **BUY Stock A / SHORT Stock B** recommendation.
  * **$z_t \ge +2.0\sigma$ (Spread Overvalued)**: Generates **SHORT Stock A / BUY Stock B** recommendation.
* **Risk Boundaries**:
  * **Target Reversion**: $z = 0.0$ (mean recovery).
  * **80% Partial Target**: Safe take-profit zone before full convergence.
  * **Hard Stop-Loss Barrier**: Set at $|z| = 3.5\sigma$ (guards against structural regime shifts or mergers/acquisitions divergence).

#### 4. Beta-Neutral Sizing & Capital Allocation Calculator
* Automatically calculates exact share quantities for both legs to neutralize directional market beta.
* Real-time interactive capital allocation calculator supporting presets (\$10,000, \$25,000, \$50,000, \$100,000) or custom position sizes, displaying exact capital deployed per leg, dollar exposure, and expected gross return.

#### 5. Interactive Setups Board (`/setups`) & Pair Deep-Dive View (`/setups/:tickerA/:tickerB`)
* **Active Divergence Cards**: Real-time cards displaying pair names, current Z-Score, Composite Quality Score (0–100), Spread Volatility Tier, and expected mean-reversion return percentage.
* **Filter & Search Bar**: Filter setups by sector, minimum Z-Score threshold, or "Perfect 10/10" gauntlet status.
* **Unified TradingView-Grade Visualizer**:
  * **Normalized Price Comparison**: Synchronized percentage rebased price series for both tickers.
  * **Historical Spread & Z-Score Chart**: Interactive area chart showing the spread relative to mean $\mu$ with horizontal threshold lines at $+2.0\sigma$, $-2.0\sigma$, and stop-loss barriers ($\pm 3.5\sigma$).
  * **Relative Returns Overlay**: Side-by-side performance comparison over 60D, 90D, 1Y, 3Y, 5Y, and ALL timeframes.

#### 6. Dynamic Strategy Configuration (`pair_strategy_config.json`)
* Strategy parameters are externalized into a central JSON schema, allowing instant live updates without code refactoring:
  * Entry Z-Score threshold (default: `2.0`)
  * Exit Z-Score target (default: `0.0`)
  * Stop-Loss barrier (default: `3.5`)
  * Rolling lookback window (default: `90` days)
  * Minimum correlation, maximum cointegration $p$-value, and half-life limits.

---

### 🤖 Feature Suite 2: 11-Persona Multi-Agent AI Equity Research

For single-stock equity ideas, the platform deploys a 3-stage consensus pipeline featuring 11 specialized AI personas powered by Claude 3.5 Sonnet:

```
[ Stage 1: Domain Analysis ]
Fundamental • News/Sentiment • Technical • Institutional Flow • Options Structure • Macro Regime
                               │
                               ▼
[ Stage 2: Socratic Adversarial Debate ]
             Bull Case vs. Bear Case  <───>  Neutral Judge
                               │
                       [ Risk Manager ]  (Hard Veto Filters)
                               │
                               ▼
[ Stage 3: Portfolio Manager Verdict ]
🟢 BUY  |  ⚠️ WATCH  |  🔴 AVOID
Confidence: 1-10  •  Price Target  •  Invalidation Cut-Off
```

#### Stage 1: Six Domain Specialist Analysts
1. **Fundamental Analyst**: Evaluates balance sheet strength, free cash flow conversion, ROIC, debt maturities, revenue quality, and gross margin trends.
2. **News & Sentiment Analyst**: Scans breaking news, regulatory filings, analyst consensus revisions, insider transactions (Form 4), and executive commentary.
3. **Technical Analyst**: Evaluates price structure, multi-timeframe moving average alignments (EMA 20/50/200), volume profiles, key support/resistance levels, and ATR volatility.
4. **Institutional Flow Analyst**: Tracks 13F institutional ownership shifts, dark pool prints, block trading velocity, and hedge fund accumulation/distribution patterns.
5. **Options Structure Analyst**: Dissects open interest distribution, put/call ratios, implied volatility skew, options gamma pinning levels, and dealer positioning.
6. **Macro Regime Analyst**: Assesses prevailing yield curve dynamics, dollar index ($DXY$), sector rotation flows, credit spreads, and market regime conditions.

#### Stage 2: Socratic Debate & Risk Gatekeeping
* **The Bull Analyst**: Builds the highest-conviction thesis for long positioning, identifying asymmetric catalysts and upside convexity.
* **The Bear Analyst**: Systematically uncovers hidden risks, accounting irregularities, valuation extremes, and downside triggers.
* **The Neutral Judge**: Evaluates both arguments, identifying fallacies, unverified assumptions, and evidential weight.
* **The Risk Manager**: Applies non-negotiable safety guardrails (e.g., vetoing long entries within 7 days of binary earnings announcements, or penalizing high beta holdings in hostile macro regimes).

#### Stage 3: Portfolio Manager Final Verdict (`/decisions`)
* Synthesizes all inputs and evaluates the recommendation against the user's **existing portfolio holdings** to prevent sector overconcentration.
* Emits a definitive, unambiguous verdict:
  * 🟢 **BUY**: High conviction, favorable risk/reward.
  * ⚠️ **WATCH**: Strong company, but current price or timing is suboptimal.
  * 🔴 **AVOID**: Asymmetric downside or unresolved risk factors.
* Provides:
  * **Conviction Score**: Calibrated 1 to 10 scale.
  * **Price Target**: Scientifically grounded upside objective.
  * **Invalidation Level ("Cut Your Losses")**: Specific price at which the investment thesis is broken.
  * **Executive PDF Export**: Generates a downloadable, beautifully formatted institutional research dossier for the stock.

#### Continuous Intelligence Features
* **Daily Morning Briefing (`/morning`)**: Pre-market intelligence report summarizing overnight index futures, economic calendar releases, top pair divergence opportunities, and key stock catalysts.
* **Weekly Strategic Outlook (`/weekly`)**: Macro review of sector rotation, portfolio exposure health, and upcoming earnings plays.
* **Long-Term Agentic Memory Core (`/memory`)**: Maintains a persistent memory bank of past theses, tracking whether previous stock forecasts and risk warnings played out accurately over time.
* **Model Lab & Pipeline Bake-Off (`/model-lab`, `/pipeline-test`)**: Diagnostic playground to test prompts, compare LLM reasoning quality, and audit token usage across analysis pipelines.

---

### ⚡ Feature Suite 3: Systematic Options Suite

An institutional options desk engineered for volatility harvesting, income generation, and risk-defined premium selling:

#### 1. Real-Time Options Scanner (`/options`)
* Scans options chains across US equities, calculating:
  * Implied Volatility (IV) Rank & IV Percentile over 52 weeks.
  * Historical Volatility (HV) vs. Implied Volatility spreads.
  * Put/Call volume and open interest skew.
  * Unusual options volume anomalies.

#### 2. Position Monitor & Greeks Risk Surface (`/options/positions`)
* Real-time portfolio Greeks tracking:
  * **Delta ($\Delta$)**: Net directional exposure in dollar terms.
  * **Gamma ($\Gamma$)**: Acceleration of delta risk.
  * **Theta ($\Theta$)**: Daily portfolio time-decay earnings.
  * **Vega ($\nu$)**: Portfolio sensitivity to a 1% shift in market implied volatility.
* Visual exposure heatmaps identifying single-stock concentration and margin utilization.

#### 3. The Options Wheel Strategy Module (`/options/wheel`)
* Complete lifecycle management for systematic cash-secured put $\rightarrow$ covered call execution:
  * **Stage 1 (Cash-Secured Put)**: Screens optimal strike prices (typically $0.20$ to $0.30$ Delta) with attractive annualized return on capital ($\ge 18\%$).
  * **Stage 2 (Assignment & Stock Holding)**: Automatically transitions assigned lots into covered call candidates.
  * **Stage 3 (Covered Call Selling)**: Recommends strike selection based on technical resistance and net cost-basis recovery.

#### 4. Double Calendar Spread Engine (`/options/double-calendar`)
* Purpose-built strategy for earnings volatility crush:
  * Exploits the term structure of implied volatility by selling near-term expensive options while buying longer-dated cheaper options.
  * Provides visual P&L risk graphs, breakeven tents, and automated exit rules before earnings release.

#### 5. Options Rulebook & League Table (`/options/rulebook`, `/options/league`)
* **Quantitative Rulebook**: Codifies strict parameters (profit-taking rules at 50% max profit, 21-DTE rolling protocols, assignment handling).
* **Strategy League Table**: Ranks active option strategies and ticker opportunities by historical win rate, Sharpe ratio, and profit factor.

---

### 🗂️ Feature Suite 4: Institutional Portfolio & Watchlist Core

#### 1. Live Portfolio Mirroring (`/`)
* Seamlessly mirrors real-world brokerage holdings:
  * Real-time equity valuation, cash balances, and daily P&L.
  * Unrealized and realized gains/losses across all held assets.
  * **Sector & Asset Allocation Breakdown**: Visual pie charts identifying sector concentration (e.g., Tech, Industrials, Financials).
  * **Concentration Warning System**: Alerts the operator before adding positions that would push a single sector over safe portfolio thresholds.

#### 2. Dynamic Research Watchlist (`/watchlist`, `/watchlist/:symbol`)
* Comprehensive asset watchlists categorized by strategic intent (Core Holdings, Growth Candidates, Mean-Reversion Watches).
* In-depth symbol profile pages showing fundamentals, historical charts, corporate earnings schedules, and associated AI research memos.

---

### ⏱️ Feature Suite 5: Daily Autonomous Automation & Cross-Platform Alerts

#### 1. Background Automation Engine (`/automation`)
* Built with `APScheduler` running reliable background cron cycles:
  * **16:30 ET Daily Market-Close Scan**: Triggers immediately after US market close to ingest latest adjusted prices, recompute rolling cointegration statistics, update Z-scores, and detect new divergence setups.
  * **Morning Intelligence Job**: Generates the daily morning brief prior to market open.

#### 2. Multi-Channel Telegram Bot Dispatcher
* Routes real-time notifications directly to mobile devices:
  * **Pairs Arbitrage Channel**: Dispatches immediate alerts when a pair triggers a $|z| \ge 2.0\sigma$ divergence with exact buy/short prices and target levels.
  * **AI Decisions Channel**: Dispatches high-conviction BUY / AVOID verdicts and morning briefs.
  * **Options Channel**: Dispatches wheel strategy adjustments and profit-taking targets.

---

## 4. Technology Stack & Technical Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                                 FRONTEND                                    │
│  React 18  •  TypeScript  •  Vite  •  Tailwind CSS  •  Lucide Icons         │
│  Lightweight Charts (TradingView)  •  TanStack React Query  •  Shadcn UI   │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │ REST / JSON (HTTP)
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                                 BACKEND                                     │
│  Python 3.11+  •  FastAPI  •  Uvicorn  •  Pydantic v2  •  APScheduler       │
│  Econometrics: Statsmodels (ADF, OLS)  •  SciPy  •  NumPy  •  Pandas        │
│  Database: SQLite 3 / SQLAlchemy  •  Parquet / PyArrow Local Storage        │
│  Authentication: PyJWT (JSON Web Tokens)  •  Passlib / Bcrypt  •  OAuth 2.0 │
│  External APIs: Financial Modeling Prep (FMP)  •  yfinance  •  Anthropic    │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 5. Project Directory Structure

```
akash-research-platform/
├── api/                                # FastAPI backend service
│   ├── auth/                           # JWT auth, user stores, password hashing
│   ├── jobs.py                         # APScheduler background tasks & cron triggers
│   ├── main.py                         # Main FastAPI app & endpoint registration
│   ├── schemas.py                      # Pydantic request/response data contracts
│   └── simulator_router.py             # Point-in-time calculation router
├── data/                               # Reference universe datasets
│   ├── active_setups.json              # Cached active statistical setups
│   ├── elite_curated_pairs.json        # Curated institutional pairs list
│   ├── pair_strategy_config.json       # Live strategy parameters & weights
│   └── sp500_master_pairs.json         # Master S&P 500 pair universe
├── data_cache/                         # High-performance local data storage
│   ├── universe_5y_daily.parquet       # Pre-cached 5Y daily adjusted OHLCV
│   └── universe_meta.json              # Dataset metadata & cache timestamps
├── engine/                             # Core quantitative & analytical engines
│   ├── config.py                       # Paths, constants, and environment loader
│   ├── detect_setups.py                # Divergence detection, OLS beta & Z-scores
│   ├── generate_universe_pairs.py      # Universe generation & pair extraction
│   ├── logging_setup.py                # Structured system logging
│   ├── pair_filter_gauntlet.py         # 10-point econometric gauntlet screener
│   ├── core/                           # Trading primitives, events, and portfolio
│   ├── data/                           # FMP data client, cache managers, loaders
│   ├── live/                           # Live runner, memory stores, Telegram bot
│   ├── metrics/                        # Risk, returns, volatility calculations
│   └── strategy/                       # Signal generators, position sizers
├── frontend/                           # React 18 + TypeScript web client
│   ├── src/
│   │   ├── components/                 # Reusable UI components & layouts
│   │   │   ├── TradingViewPairChart.tsx # Synchronized multi-asset interactive chart
│   │   │   └── ui/                     # Cards, buttons, badges, modals
│   │   ├── lib/                        # API clients, types, and utility helpers
│   │   │   └── api.ts                  # Typed Axios/Fetch backend interface
│   │   └── pages/                      # Application route pages
│   │       ├── DecisionsPage.tsx       # AI Analysis & Verdicts
│   │       ├── MorningPage.tsx         # Daily Morning Briefing
│   │       ├── OptionsScannerPage.tsx  # Options IV & Chain Scanner
│   │       ├── PairsPage.tsx           # Master Pairs Directory
│   │       ├── PortfolioPage.tsx       # Real-Time Account Mirror
│   │       ├── SetupDetailPage.tsx     # Single Pair Deep Dive & Execution Calculator
│   │       ├── SetupsPage.tsx          # Live Active Divergence Setups Board
│   │       ├── WatchlistPage.tsx       # Research Watchlist & Symbol Profiles
│   │       └── WheelPage.tsx           # Options Wheel Strategy Desk
│   ├── package.json
│   └── vite.config.ts
├── logs/                               # Application log files
├── scripts/                            # Operational & data management scripts
│   ├── refresh_data.py                 # FMP historical price fetcher
│   └── run.py                          # Unified platform launcher
├── .env.example                        # Environment variable template
├── pyproject.toml                      # Python dependencies & package configuration
├── requirements.txt                    # Production pip requirements
└── render.yaml                         # Production Render cloud deployment config
```

---

## 6. Installation & Quick Start

### 1. Prerequisites
* **Python**: Version `3.10` or `3.11+`
* **Node.js**: Version `18.x` or `20.x` with `npm`
* **FMP API Key**: Financial Modeling Prep account for market data

### 2. Environment Configuration
Clone the repository and create your local environment configuration:
```bash
cp .env.example .env
```
Edit `.env` and provide your credentials:
```env
FMP_API_KEY=your_fmp_api_key_here
ANTHROPIC_API_KEY=your_claude_api_key_here     # Optional for AI research
TELEGRAM_BOT_TOKEN=your_telegram_bot_token    # Optional for alerts
TELEGRAM_CHAT_ID=your_chat_id                 # Optional for alerts
JWT_SECRET=your_secure_random_jwt_secret
```

### 3. Backend Setup
Create a virtual environment and install dependencies:
```bash
python -m venv .venv
# On Windows:
.venv\Scripts\activate
# On macOS / Linux:
source .venv/bin/activate

pip install -r requirements.txt
```

### 4. Frontend Setup
Install frontend dependencies:
```bash
cd frontend
npm install
cd ..
```

### 5. Launch the Platform
Start the FastAPI backend server:
```bash
# Starts API on http://127.0.0.1:8000
python run.py
```
In a separate terminal, start the frontend development server:
```bash
cd frontend
npm run dev
```
Open your browser at **http://localhost:5173** (or port specified by Vite).  
API Swagger documentation is accessible at **http://127.0.0.1:8000/docs**.

---

## 7. Key API Endpoints Reference

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/api/pairs/active-setups` | Returns current active divergence setups meeting $Z \ge 2.0\sigma$ criteria |
| `GET` | `/api/pairs/{ticker_a}/{ticker_b}/history` | Fetches historical adjusted prices, OLS spread, and rolling Z-score |
| `GET` | `/api/pairs/config` | Retrieves the current active pairs trading strategy configuration |
| `POST`| `/api/pairs/config` | Updates strategy thresholds (entry Z, stop Z, lookback days) dynamically |
| `GET` | `/api/pairs/elite` | Retrieves pre-filtered elite cointegrated pairs |
| `GET` | `/api/pairs` | Queries the complete S&P 500 pairs database with sector and correlation filters |
| `GET` | `/api/portfolio/summary` | Returns real-time portfolio holdings, equity, cash, and sector weights |
| `GET` | `/api/decisions/latest` | Returns recent AI research verdicts and thesis memos |
| `GET` | `/api/options/scanner` | Scans market for high IV percentile and attractive premium selling opportunities |

---

## 8. Strategy Disclaimers & Risk Notice

The Akash Research Platform is an advanced quantitative research and decision-support tool created for informational and educational purposes. 

1. **Market Risk**: Statistical arbitrage and options trading involve substantial risk of loss. Past cointegration or historical mean-reversion does not guarantee future price convergence. Corporate events (mergers, acquisitions, bankruptcies, fundamental restructuring) can cause permanent spread divergence.
2. **Execution Responsibility**: The platform does not place automated live orders with brokerages. All trades must be reviewed, sized, and executed manually by the operator.
3. **Model Limitations**: Statistical indicators (Z-scores, ADF tests, half-life estimations) are sensitive to lookback window selection and sample frequency. Always adhere to strict stop-loss rules.

---

## 9. License
Proprietary & Confidential. Internal use only. Unauthorized distribution, copying, or public hosting is strictly prohibited.
