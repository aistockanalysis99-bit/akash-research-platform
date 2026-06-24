"""Pydantic output schemas for every Phase 2 agent.

Each schema is also the contract used by the LLM's structured output —
the same model class is passed as `response_schema=` to Gemini.

Naming convention: one schema per agent output, plus small reusable sub-models.
Keep field counts tight: every field is real signal the downstream agent reads.
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field


# ===========================================================================
# Common pieces
# ===========================================================================


class RedFlag(BaseModel):
    category: Literal[
        "accounting", "growth", "balance_sheet", "cash_flow",
        "valuation", "guidance", "governance", "other",
    ]
    detail: str = Field(..., max_length=600)


class CriticalNewsFlag(BaseModel):
    type: Literal[
        "earnings_miss", "guidance_cut", "downgrade", "litigation",
        "investigation", "fraud_allegation", "executive_departure",
        "merger_acquisition", "fda_event", "macro_event", "other",
    ]
    severity: Literal["critical", "high", "medium", "low"]
    detail: str = Field(..., max_length=600)


# ===========================================================================
# Entry: SignalInput — what kicks off the pipeline
# ===========================================================================


class SignalInput(BaseModel):
    """The payload that enters the pipeline. Same shape regardless of source."""

    symbol: str
    source: Literal["quant", "manual", "external"]
    signal_date: str        # ISO YYYY-MM-DD
    notes: Optional[str] = None

    # Quant-source enrichment (None for manual entries)
    quant_score: Optional[float] = None
    trend_ok: Optional[bool] = None
    breakout_ok: Optional[bool] = None
    current_price: Optional[float] = None
    atr: Optional[float] = None


# ===========================================================================
# Stage 1: Pre-Filter (deterministic Python, not LLM)
# ===========================================================================


class PreFilterResult(BaseModel):
    action: Literal["PASS", "SKIP"]
    reason: str = Field(..., max_length=240)
    rules_triggered: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    earnings_days_away: Optional[int] = None
    market_cap_usd: Optional[float] = None


# ===========================================================================
# Stage 2: Analysts
# ===========================================================================


class GrowthQuality(BaseModel):
    revenue_trend: Literal["accelerating", "stable", "decelerating", "declining"]
    margin_trend: Literal["expanding", "stable", "compressing"]
    fcf_conversion: Literal["strong", "adequate", "weak", "negative"]
    eps_acceleration: Literal["accelerating", "stable", "decelerating", "declining"]


class ValuationAssessment(BaseModel):
    pe_vs_sector: Literal["discount", "in_line", "premium", "extreme_premium", "unavailable"]
    justified: bool
    justification: str = Field(..., max_length=800)


class FundamentalReport(BaseModel):
    """Agent 2 — Fundamental Analyst (Gemini Pro)."""

    symbol: str
    as_of_date: str
    fundamental_score: int = Field(..., ge=1, le=10)
    growth_quality: GrowthQuality
    valuation_assessment: ValuationAssessment
    key_upside_driver: str = Field(..., max_length=600)
    key_downside_risk: str = Field(..., max_length=600)
    earnings_risk_days: Optional[int] = Field(
        None, description="Days until next earnings; negative = past; null = unknown"
    )
    red_flags: list[RedFlag] = Field(default_factory=list)
    summary: str = Field(..., max_length=1000, description="3 sentences, with numbers")


class EventRisk(BaseModel):
    event: str = Field(..., max_length=400)
    date: Optional[str] = None
    severity: Literal["critical", "high", "medium", "low"]


class NewsReport(BaseModel):
    """Agent 3 — News Analyst (Gemini Pro)."""

    symbol: str
    as_of_date: str
    news_risk_score: int = Field(..., ge=1, le=10)
    news_opportunity_score: int = Field(..., ge=1, le=10)
    critical_flags: list[CriticalNewsFlag] = Field(default_factory=list)
    analyst_consensus_direction: Literal["improving", "stable", "deteriorating", "unavailable"]
    institutional_flow_signal: Literal["accumulating", "neutral", "distributing", "unavailable"]
    recent_catalysts: list[str] = Field(default_factory=list, max_length=8)
    event_risk_next_7_days: list[EventRisk] = Field(default_factory=list, max_length=6)
    summary: str = Field(..., max_length=1000)


# ===========================================================================
# Stage 3: Bull / Bear researchers
# ===========================================================================


class TopHolder(BaseModel):
    """One row from UW /institution/{ticker}/ownership."""
    name: str = Field(..., max_length=120)
    units: Optional[float] = None
    units_changed: Optional[float] = Field(
        None, description="Q-over-Q change in shares held",
    )
    pct_change_qoq: Optional[float] = Field(
        None, description="units_changed / prior_units, signed",
    )
    value_usd: Optional[float] = None
    is_hedge_fund: Optional[bool] = None
    first_buy: Optional[str] = None


class InstitutionalFlowReport(BaseModel):
    """Agent 4b — Institutional Flow Analyst (Gemini Flash).

    Distills Unusual Whales data (13F + dark pool + options flow + insider $)
    into a single structured object the debate + PM agents can read.
    """

    symbol: str
    as_of_date: str

    # --- 13F snapshot ---
    smart_money_score: int = Field(
        ..., ge=1, le=10,
        description="1=heavy distribution, 5=neutral, 10=heavy accumulation",
    )
    smart_money_direction: Literal[
        "heavy_accumulating", "accumulating", "neutral",
        "distributing", "heavy_distributing", "unavailable",
    ]
    top_5_holders: list[TopHolder] = Field(default_factory=list, max_length=5)
    biggest_buyers_qoq: list[TopHolder] = Field(default_factory=list, max_length=5)
    biggest_sellers_qoq: list[TopHolder] = Field(default_factory=list, max_length=5)
    new_institutional_positions_count: Optional[int] = None
    exited_institutional_positions_count: Optional[int] = None
    inst_ownership_pct: Optional[float] = Field(
        None, description="Approx. % of float held by 13F filers",
    )

    # --- Dark pool ---
    dark_pool_30d_notional_usd: Optional[float] = None
    dark_pool_pct_of_volume: Optional[float] = Field(
        None, description="Off-exchange share of total dollar volume, last 30 sessions",
    )
    dark_pool_trend: Literal[
        "stealth_accumulation", "stealth_distribution", "neutral", "unavailable",
    ]

    # --- Options flow ---
    options_flow_call_put_premium_ratio: Optional[float] = Field(
        None, description="Sum of UOA call premium / put premium, last 5 sessions",
    )
    options_flow_sentiment: Literal[
        "very_bullish", "bullish", "neutral", "bearish", "very_bearish", "unavailable",
    ]
    biggest_uoa_prints: list[str] = Field(
        default_factory=list, max_length=5,
        description="Plain-text descriptions of the 3-5 most notional UOA prints",
    )

    # --- Insider net flow (UW version of FMP insider) ---
    insider_30d_net_notional_usd: Optional[float] = Field(
        None, description="Sum(purchases) - Sum(sells) over last 30 days",
    )
    insider_30d_signal: Literal[
        "net_buying", "balanced", "net_selling", "heavy_selling", "unavailable",
    ]

    # --- Aggregate read ---
    convergence_notes: str = Field(
        ..., max_length=800,
        description="Do the 4 signals (13F, dark pool, options, insider) agree or conflict?",
    )
    summary: str = Field(..., max_length=1000)


class OptionsStructureReport(BaseModel):
    """Agent 4c — Options Structure / Dealer Positioning (Gemini Flash).

    Distills UW greek-exposure + max-pain + IV term structure into a single
    structured read. Tells the PM "what price will dealers hedge this to?"
    """

    symbol: str
    as_of_date: str

    current_price: Optional[float] = None
    gamma_flip_price: Optional[float] = Field(
        None, description="Spot price where net dealer gamma crosses zero",
    )
    dealer_positioning: Literal[
        "long_gamma", "neutral_gamma", "short_gamma", "unavailable",
    ] = Field(
        ...,
        description=(
            "Long gamma = dealers buy dips/sell rips (mean-reverting price). "
            "Short gamma = dealers sell dips/buy rips (trend-amplifying)."
        ),
    )

    call_wall_strike: Optional[float] = Field(
        None, description="Largest call OI / gamma cluster — resistance",
    )
    put_wall_strike: Optional[float] = Field(
        None, description="Largest put OI / gamma cluster — support",
    )
    max_pain_nearest_expiry: Optional[float] = None
    max_pain_30dte: Optional[float] = None

    iv_term_structure: Literal[
        "contango", "flat", "backwardation", "unavailable",
    ] = Field(
        ...,
        description=(
            "Contango = normal, far-dated IV higher. Backwardation = stress, "
            "near-dated IV higher (usually pre-event)."
        ),
    )
    iv_regime: Literal["low", "normal", "elevated", "high", "unavailable"]

    structural_signal: Literal[
        "pin_risk", "breakout_setup", "breakdown_setup", "neutral", "unavailable",
    ]
    summary: str = Field(..., max_length=1000)


class MacroRegimeReport(BaseModel):
    """Agent 4d — Macro Regime per Ticker (Gemini Flash).

    Reads broad market context (yield curve, VIX proxy, sector rotation,
    upcoming macro events) and tells the PM how this ticker is likely to
    behave in the current regime.
    """

    symbol: str
    as_of_date: str

    market_regime: Literal[
        "risk_on", "risk_off", "rotation", "choppy", "unavailable",
    ]
    leading_sectors: list[str] = Field(default_factory=list, max_length=4)
    lagging_sectors: list[str] = Field(default_factory=list, max_length=4)

    ticker_sector: Optional[str] = None
    sector_relative_strength: Literal[
        "leading", "neutral", "lagging", "unavailable",
    ]
    ticker_alignment: Literal[
        "with_regime", "fighting_regime", "neutral", "unavailable",
    ] = Field(
        ...,
        description="Is the ticker's setup aligned with the current macro regime?",
    )

    upcoming_macro_events: list[str] = Field(
        default_factory=list, max_length=8,
        description="Top 3-8 known upcoming events with date (e.g. 'FOMC 2026-06-19')",
    )
    next_high_impact_event_days: Optional[int] = Field(
        None, description="Days until next high-impact macro event",
    )

    market_tide_signal: Literal[
        "bullish", "neutral", "bearish", "unavailable",
    ] = Field(..., description="UW market-tide net premium read")

    regime_risk_score: int = Field(
        ..., ge=1, le=10,
        description="1 = macro tailwind for this ticker, 10 = macro headwind",
    )
    summary: str = Field(..., max_length=900)


class TechnicalContext(BaseModel):
    """Agent 4 — Technical Context (Gemini Flash)."""

    symbol: str
    as_of_date: str
    technical_strength: int = Field(..., ge=1, le=10)
    volume_confirmation: Literal["strong", "moderate", "weak", "unavailable"]
    sector_alignment: Literal["with_sector", "leading_sector",
                               "fighting_sector", "unavailable"]
    broader_market_supportive: bool
    return_vs_sector_20d_pct: Optional[float] = None
    return_vs_spy_20d_pct: Optional[float] = None
    warning_flags: list[str] = Field(default_factory=list, max_length=6)
    summary: str = Field(..., max_length=800)


class MacroContextSnapshot(BaseModel):
    """Phase 2 macro overlay — derived from today's morning regime if it ran,
    else None. Injected into the PM prompt as a one-paragraph regime read.
    """

    as_of_date: str
    regime: str
    confidence: int = Field(..., ge=1, le=10)
    new_entries_throttle: Literal["full", "half", "blocked"]
    sector_tailwinds: list[str] = Field(default_factory=list, max_length=8)
    sector_headwinds: list[str] = Field(default_factory=list, max_length=8)
    summary: str = Field(..., max_length=800)


class RiskManagerVerdict(BaseModel):
    """Agent 8 — Risk Manager (Claude Sonnet + deterministic gates).

    Hard rules (earnings 3-day block, sector cap, gross exposure cap,
    position count cap) are enforced in code BEFORE the LLM call. The LLM
    contributes the soft-judgment piece (sector concentration concern,
    correlation worry, position-sizing nuance).

    PM treats `verdict` and `recommended_size_pct` as binding constraints.
    """

    symbol: str
    as_of_date: str
    verdict: Literal["CLEAR", "REDUCE_SIZE", "BLOCK"]
    recommended_size_pct: int = Field(..., ge=0, le=100)
    rules_triggered: list[str] = Field(default_factory=list, max_length=12)
    deterministic_block_reason: Optional[str] = None

    sector: Optional[str] = None
    sector_concentration_now_pct: float = 0.0
    sector_concentration_after_pct: float = 0.0
    gross_exposure_now_pct: float = 0.0
    open_position_count: int = 0
    earnings_risk_days: Optional[int] = None

    reasoning: str = Field(..., max_length=3500)


class DebateScores(BaseModel):
    """Five-dimensional scoring used by the Debate Judge (Agent 7)."""

    fundamental_quality: int = Field(..., ge=1, le=10)
    news_handling: int = Field(..., ge=1, le=10)
    technical_reasoning: int = Field(..., ge=1, le=10)
    timing_assessment: int = Field(..., ge=1, le=10)
    rebuttal_quality: int = Field(..., ge=1, le=10)


class DebateJudgment(BaseModel):
    """Agent 7 — Debate Judge (Claude Sonnet).

    Reads Bull and Bear cases, scores each on 5 dimensions, and outputs a
    final conviction the PM uses as input. PM no longer has to judge the
    debate AND make the call — only the call.
    """

    symbol: str
    as_of_date: str
    bull_scores: DebateScores
    bear_scores: DebateScores
    winner: Literal["bull", "bear", "tie"]
    conviction_score: int = Field(..., ge=1, le=10,
                                    description="8-10=strong approve, 5-7=moderate, 1-4=strong reject")
    deciding_factor: str = Field(..., max_length=600,
                                  description="Single most important point that swung the verdict")
    synthesis: str = Field(..., max_length=1500,
                            description="3-sentence summary of the debate outcome")


class BullCase(BaseModel):
    """Agent 5 — Bull Researcher (Claude Sonnet)."""

    symbol: str
    as_of_date: str
    business_quality: str = Field(..., max_length=1500)
    momentum_validity: str = Field(..., max_length=1500)
    catalyst: str = Field(..., max_length=1500)
    valuation_context: str = Field(..., max_length=1500)
    strongest_point: str = Field(..., max_length=800)
    biggest_vulnerability: str = Field(..., max_length=800)
    price_target_6m_usd: Optional[float] = None
    upside_pct: Optional[float] = None
    conviction_self_rated: int = Field(..., ge=1, le=10)


class BearCase(BaseModel):
    """Agent 6 — Bear Researcher (Claude Sonnet). Mirrors BullCase."""

    symbol: str
    as_of_date: str
    business_quality_concerns: str = Field(..., max_length=1500)
    momentum_skepticism: str = Field(..., max_length=1500)
    catalyst_counter: str = Field(..., max_length=1500)
    valuation_concerns: str = Field(..., max_length=1500)
    strongest_point: str = Field(..., max_length=800)
    biggest_weakness: str = Field(..., max_length=800)
    downside_target_6m_usd: Optional[float] = None
    downside_pct: Optional[float] = None
    conviction_self_rated: int = Field(..., ge=1, le=10)


# ===========================================================================
# Stage 4: Portfolio Manager — the final voice
# ===========================================================================


class InvestmentRationale(BaseModel):
    why_now: str = Field(..., max_length=1500)
    what_validates_signal: str = Field(..., max_length=1500)
    key_risk_and_management: str = Field(..., max_length=1500)


# ===========================================================================
# Morning loop (Phase 4 of Phase 2 — daily position review + regime check)
# ===========================================================================


class MarketRegime(BaseModel):
    """Agent 10 — Market Regime Detector (Gemini Pro)."""

    as_of_date: str
    regime: Literal["BULL_TRENDING", "BULL_CHOPPY", "NEUTRAL", "RISK_OFF", "BEAR"]
    regime_confidence: int = Field(..., ge=1, le=10)
    new_entries_throttle: Literal["full", "half", "blocked"]
    trailing_stops_adjustment: Literal["normal", "tighten"]
    score_threshold_bump: float = Field(..., ge=0.0, le=0.5,
                                         description="Add this to quant threshold today")
    key_observation: str = Field(..., max_length=800)
    watch_today: str = Field(..., max_length=800)


class PositionReview(BaseModel):
    symbol: str
    action: Literal["HOLD", "WATCH", "EXIT"]
    thesis_status: Literal["intact", "weakening", "broken"]
    momentum_status: Literal["strengthening", "stable", "fading"]
    reason: str = Field(..., max_length=1000)
    # Daily lifecycle risk re-rating (AI-managed, notify-only — never executed)
    risk_action: Literal["hold", "trim", "add", "tighten_stop", "widen_stop"] = "hold"
    new_stop_price: Optional[float] = Field(
        None, description="updated stop for this position, on current volatility")
    risk_note: Optional[str] = Field(
        None, max_length=600, description="one-line reason for the risk_action / new stop")


class PositionMonitorReport(BaseModel):
    """Agent 11 — Batch position review (Gemini Pro)."""

    as_of_date: str
    reviews: list[PositionReview]
    portfolio_observation: str = Field(..., max_length=1200)


class ExitConfirmation(BaseModel):
    """Agent 12 — Exit Confirmer (Claude Sonnet)."""

    symbol: str
    as_of_date: str
    verdict: Literal["CONFIRM_EXIT", "DOWNGRADE_TO_WATCH", "HOLD"]
    urgency: Literal["immediate", "next_open", "monitor"]
    exit_reasoning: str = Field(..., max_length=1500)
    lesson_for_memory: str = Field(..., max_length=800)


class MorningBriefing(BaseModel):
    """Agent 13 — Daily client briefing (Gemini Flash)."""

    as_of_date: str
    headline: str = Field(..., max_length=400)
    telegram_message: str = Field(..., max_length=3000)


# ===========================================================================
# AI Memory — Reflector lessons from closed positions
# ===========================================================================


class Reflection(BaseModel):
    """Output of the Reflector agent that runs after a position closes.

    The 2-4 sentence lesson is the artifact future PM prompts get to see.
    """

    symbol: str
    position_id: int
    outcome_pnl_pct: float
    days_held: int
    exit_reason: str
    category: Literal[
        "thesis_held", "thesis_broke", "entry_timing", "exit_timing",
        "sector_call", "macro_call", "earnings_event", "valuation",
        "size_judgment", "other",
    ]
    lesson_text: str = Field(..., max_length=600,
                              description="2-4 sentences in plain English")


# ===========================================================================
# Weekly Performance Review (Agent 14)
# ===========================================================================


class AccuracyBucket(BaseModel):
    label: str
    n_trades: int
    win_rate_pct: float = Field(..., ge=0.0, le=100.0)
    avg_pnl_pct: float


class WeeklyReviewReport(BaseModel):
    """Agent 14 — Weekly Performance Reviewer (Claude Sonnet)."""

    week_start: str
    week_end: str
    weekly_grade: Literal["A", "B", "C", "D", "F"]
    grade_justification: str = Field(..., max_length=600)

    n_decisions: int
    n_approved: int
    n_resized: int
    n_rejected: int
    n_positions_closed: int

    accuracy_by_sector: list[AccuracyBucket] = Field(default_factory=list, max_length=15)
    accuracy_by_conviction: list[AccuracyBucket] = Field(default_factory=list, max_length=5)

    top_lessons: list[str] = Field(default_factory=list, max_length=5,
                                    description="One sentence each")
    process_observations: str = Field(..., max_length=1500,
                                       description="What went well, what didn't, why")

    telegram_weekly_report: str = Field(..., max_length=3000)


# ===========================================================================
# Quant Source — what the live scanner emits per candidate
# ===========================================================================


# ===========================================================================
# Per-stock Profile (the dossier)
# ===========================================================================


class RevenueSegment(BaseModel):
    """One product/business segment of a company's revenue."""
    name: str
    pct_of_revenue: Optional[float] = Field(None, ge=0.0, le=1.0)
    description: Optional[str] = Field(None, max_length=400)


class GeographicSegment(BaseModel):
    """One geographic region of a company's revenue."""
    region: str
    pct_of_revenue: Optional[float] = Field(None, ge=0.0, le=1.0)


class ThesisPillar(BaseModel):
    """One bull or bear argument that the system uses as a prior."""
    text: str = Field(..., max_length=400)
    confidence: Literal["high", "moderate", "low"] = "moderate"
    last_updated: Optional[str] = None


class RedLine(BaseModel):
    """An exit condition specific to this stock — system uses as a hard prior."""
    condition: str = Field(..., max_length=300)
    rationale: str = Field(..., max_length=300)
    measurable: bool = Field(False,
                              description="True if auto-checkable from data")


class AnalystQuestions(BaseModel):
    """Stock-specific questions each analyst agent should consider."""
    fundamental: list[str] = Field(default_factory=list, max_length=10)
    news: list[str] = Field(default_factory=list, max_length=10)
    technical: list[str] = Field(default_factory=list, max_length=10)


class ManagementCommentary(BaseModel):
    """A captured quote from management — earnings call, investor day, etc."""
    date: str
    speaker: str = Field(..., max_length=120)
    quote: str = Field(..., max_length=500)
    source: str = Field(..., max_length=200)


class StockProfile(BaseModel):
    """Per-stock dossier — primes every agent before analysis runs.

    Auto-built by the ProfileBuilder agent after the first analysis of a
    new ticker. Stored as YAML frontmatter + markdown body at
    watchlist/{symbol}.md. Hand-editable.
    """

    # ---- Identity (required) ----
    symbol: str
    name: str = Field(..., max_length=200)
    sector: str = Field(..., max_length=100)
    industry: Optional[str] = Field(None, max_length=200)
    exchange: Optional[str] = Field(None, max_length=50)
    is_etf: bool = False

    # ---- Metadata ----
    last_reviewed: str
    auto_built: bool = True
    review_cadence_days: int = Field(30, ge=1, le=365)
    priority: Literal["tier_1", "tier_2", "tier_3"] = "tier_2"
    held: bool = False
    position_intent: Literal["core", "satellite", "trade", "watch"] = "watch"
    market_cap_usd: Optional[float] = None

    # ---- Business identity ----
    business_model: str = Field("", max_length=1500)
    revenue_segments: list[RevenueSegment] = Field(default_factory=list, max_length=12)
    geographic_revenue: list[GeographicSegment] = Field(default_factory=list, max_length=12)

    # ---- KPIs to track every quarter ----
    key_kpis: list[str] = Field(default_factory=list, max_length=12,
                                  description="Stock-specific metrics beyond standard financials")

    # ---- Pillars ----
    bull_thesis_pillars: list[ThesisPillar] = Field(default_factory=list, max_length=8)
    bear_thesis_pillars: list[ThesisPillar] = Field(default_factory=list, max_length=8)

    # ---- Red lines (exit triggers) ----
    red_lines: list[RedLine] = Field(default_factory=list, max_length=8)

    # ---- Per-agent questions ----
    analyst_questions: AnalystQuestions = Field(default_factory=AnalystQuestions)

    # ---- Peers + cross-references ----
    preferred_peers: list[str] = Field(default_factory=list, max_length=10)
    correlation_notes: str = Field("", max_length=1200)

    # ---- Recent management commentary ----
    recent_management_commentary: list[ManagementCommentary] = Field(default_factory=list, max_length=10)

    # ---- Memory ----
    historical_lessons: list[str] = Field(default_factory=list, max_length=15)

    # ---- PM-level notes ----
    pm_notes: str = Field("", max_length=2000)

    # ---- Free-form long-form (markdown body) ----
    long_form_notes: str = Field("", max_length=15000)


class QuantCandidate(BaseModel):
    """One ticker that passed the quant scanner's filters today."""

    symbol: str
    as_of_date: str
    score: float                 # weighted momentum score
    trend_ok: bool               # EMA50 > EMA150 AND slope positive
    breakout_ok: bool            # close > prior 20-bar highest close
    current_price: float
    atr: float                   # ATR(20) for sizing
    rank: int                    # 1 = highest score in today's scan


class SummaryReport(BaseModel):
    """One-page narrative rollup of the whole pipeline (Gemini Flash).

    Writes the `_summary.md` file — the "executive summary" view a human
    reads first before diving into the per-agent reports.
    """

    symbol: str
    as_of_date: str
    headline: str = Field(..., max_length=400, description="One-line verdict")
    summary_markdown: str = Field(..., max_length=6000,
                                   description="Full markdown summary (1 page)")


class PMDecision(BaseModel):
    """Agent 9 — Portfolio Manager / CIO (Claude Sonnet). Final verdict.

    Originally specced for Claude Opus; downgraded to Sonnet for cost reasons.
    Sonnet handles fiduciary-grade reasoning well at ~10× lower cost than Opus.
    """

    symbol: str
    as_of_date: str
    decision: Literal["APPROVE", "RESIZE", "REJECT"]
    conviction_score: int = Field(..., ge=1, le=10)
    recommended_size_pct: int = Field(..., ge=0, le=100,
                                       description="legacy: 100=full, 50=half, 0=skip")
    # Dynamic, AI-decided risk plan (per-stock, set by the PM within guardrails)
    position_pct_of_fund: Optional[float] = Field(
        None, ge=0, le=100,
        description="AI-chosen target weight as % of the TOTAL fund (≤ single-name cap)")
    stop_price: Optional[float] = Field(
        None, description="AI-chosen stop price, placed on the stock's own volatility")
    stop_pct: Optional[float] = Field(
        None, description="how far below current price the stop sits, as a positive %")
    sizing_rationale: Optional[str] = Field(
        None, max_length=400, description="one sentence: why this size for THIS stock")
    stop_rationale: Optional[str] = Field(
        None, max_length=400, description="one sentence: why this stop (cite volatility)")
    investment_rationale: InvestmentRationale
    exit_thesis: str = Field(..., max_length=1000)
    monitoring_flags: list[str] = Field(default_factory=list, max_length=8)
    telegram_message: str = Field(..., max_length=2500,
                                   description="STOCK view — why this name, "
                                   "entry/exit plan, what to watch. ~10 lines.")
    telegram_portfolio_message: Optional[str] = Field(
        None, max_length=2500,
        description="PORTFOLIO view — how this slots into the existing book. "
                    "Sector impact, replacement candidates, rotation suggestions. "
                    "Optional — older verdicts won't have it.",
    )
    audit_note: str = Field(..., max_length=1000,
                             description="2-sentence internal decision log entry")
