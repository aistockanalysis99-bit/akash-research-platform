"""Full Phase-2 AI research pipeline — orchestrates all 6 agents.

Topology:
                            START
                              |
                       Pre-fetch FMP bundle
                              |
                  +-----------+-----------+
                  |                       |
            Fundamental                 News      ← parallel (Gemini)
                  |                       |
                  +-----------+-----------+
                              |
                  +-----------+-----------+
                  |                       |
                Bull                     Bear     ← parallel (Claude Sonnet)
                  |                       |
                  +-----------+-----------+
                              |
                             PM                   ← Claude Sonnet
                              |
                          Summary                 ← Gemini Flash (cheap rollup)
                              |
                            END

We don't use LangGraph for Phase-2 — asyncio.gather is enough at this scale
and the control flow is dead-simple. LangGraph comes in Phase-3 when we add
conditional routing (regime throttle, debate rounds, etc.).
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import date
from typing import Any, Optional

from ..data.fmp_client import FMPClient
from .agents.bear import BearAgent
from .agents.bull import BullAgent
from .agents.fundamental import FundamentalAgent
from .agents.judge import JudgeAgent
from .agents.news import NewsAgent
from .agents.pm import PMAgent
from .agents.risk_manager import RiskManagerAgent
from .agents.summary import SummaryAgent
from .agents.technical import TechnicalAgent
from .agents.institutional_flow import InstitutionalFlowAgent
from .agents.options_structure import OptionsStructureAgent
from .agents.macro_regime import MacroRegimeAgent
from . import analyst_tracker
from . import earnings_dynamics
from .data.fmp_research import FMPResearchClient
from .data.market_data import SECTOR_ETFS
from .data.peer_metrics import fetch_peer_comparison
from .file_store import FileStore
from .llm.claude import claude_opus, claude_sonnet
from .llm.gemini import gemini_flash, gemini_pro
from . import profiles as live_profiles
from . import settings as live_settings
from .agents.profile_builder import build_profile as build_stock_profile
from .macro_context import load_macro_context_for_today
from .portfolio import VirtualPortfolio
from .renderers.risk_manager import render as render_risk
from .schemas import SignalInput
from .state import SignalState, new_signal_state


# Sector → SPDR ETF mapping. Falls back to SPY when the sector isn't matched.
SECTOR_TO_ETF: dict[str, str] = {
    "Technology":              "XLK",
    "Financial Services":      "XLF",
    "Financials":              "XLF",
    "Energy":                  "XLE",
    "Consumer Cyclical":       "XLY",
    "Consumer Discretionary":  "XLY",
    "Consumer Defensive":      "XLP",
    "Consumer Staples":        "XLP",
    "Healthcare":              "XLV",
    "Health Care":             "XLV",
    "Industrials":             "XLI",
    "Utilities":               "XLU",
    "Communication Services":  "XLK",  # no XLC fetched; approximate w/ XLK
    "Basic Materials":         "XLI",
    "Materials":               "XLI",
    "Real Estate":             "XLF",
}

log = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Pre-fetch — union of FMP endpoints needed by Fundamental + News
# --------------------------------------------------------------------------- #


async def prefetch_pipeline_context(
    research: FMPResearchClient, fmp: FMPClient, symbol: str
) -> dict[str, Any]:
    """Fetch every FMP endpoint the pipeline's analysts need, in parallel.

    Adds price history (symbol + SPY + sector ETF) for the Technical agent.
    """
    (
        profile, income, balance, cashflow,
        ratios_annual, ratios_ttm, km_ttm, earnings,
        news, press_releases, grades, sec_filings, insider_trades,
    ) = await asyncio.gather(
        research.fetch_profile(symbol),
        research.fetch_income_quarterly(symbol, limit=8),
        research.fetch_balance_quarterly(symbol, limit=4),
        research.fetch_cashflow_quarterly(symbol, limit=4),
        research.fetch_ratios_annual(symbol, limit=5),
        research.fetch_ratios_ttm(symbol),
        research.fetch_key_metrics_ttm(symbol),
        research.fetch_earnings(symbol, limit=8),
        research.fetch_news(symbol, limit=15),
        research.fetch_press_releases(symbol, limit=15),
        research.fetch_grades(symbol, days=30),
        research.fetch_sec_filings(symbol, days=60),
        research.fetch_insider_trades(symbol, days=60),
    )
    next_earnings = await research.fetch_next_earnings_date(symbol)

    # Sector → ETF for the technical agent
    sector = (profile.data or {}).get("sector", "")
    sector_etf = SECTOR_TO_ETF.get(sector, "SPY")

    # Price history + peer comparison + Tier 1 profile data (M17) + UW (M18),
    # all in parallel.
    from .data.unusual_whales import UnusualWhalesClient, UWError
    uw_inst_r = uw_dp_r = uw_flow_r = uw_volume_r = uw_insider_r = None
    uw_greek_r = uw_pain_r = uw_volterm_r = uw_short_r = None
    uw_sectors_r = uw_tide_r = uw_econ_r = None
    try:
        async with UnusualWhalesClient() as uw:
            (
                symbol_df, sector_df, spy_df, peer_metrics,
                segs_prod_r, segs_geo_r, transcript_r,
                pt_summary_r, pt_news_r, inst_holders_r,
                uw_inst_r, uw_dp_r, uw_flow_r, uw_volume_r, uw_insider_r,
                uw_greek_r, uw_pain_r, uw_volterm_r, uw_short_r,
                uw_sectors_r, uw_tide_r, uw_econ_r,
            ) = await asyncio.gather(
                _safe_history(fmp, symbol),
                _safe_history(fmp, sector_etf),
                _safe_history(fmp, "SPY"),
                fetch_peer_comparison(research, fmp, symbol, profile.data or {}, n_peers=5),
                research.fetch_revenue_segments_product(symbol),
                research.fetch_revenue_segments_geographic(symbol),
                research.fetch_earnings_transcript(symbol),
                research.fetch_price_target_summary(symbol),
                research.fetch_price_target_news(symbol, limit=15),
                research.fetch_institutional_holders(symbol, limit=20),
                uw.fetch_institutional_ownership(symbol, limit=50),
                uw.fetch_dark_pool(symbol, limit=200),
                uw.fetch_options_flow(symbol, limit=100),
                uw.fetch_options_volume(symbol),
                uw.fetch_insider_flow(symbol),
                # M19 — options structure + macro regime + short interest
                uw.fetch_greek_exposure(symbol),
                uw.fetch_max_pain(symbol),
                uw.fetch_vol_term_structure(symbol),
                uw.fetch_short_interest(symbol),
                uw.fetch_sector_etfs(),
                uw.fetch_market_tide(),
                uw.fetch_economic_calendar(),
            )
    except UWError as e:
        log.warning("UW unavailable, falling back to FMP-only prefetch: %s", e)
        # UW key missing or invalid — fall back gracefully. uw_*_r stays None
        # (already initialised above), so the return dict will mark them
        # unavailable and the M18+M19 UW-backed agents will see empty inputs.
        (
            symbol_df, sector_df, spy_df, peer_metrics,
            segs_prod_r, segs_geo_r, transcript_r,
            pt_summary_r, pt_news_r, inst_holders_r,
        ) = await asyncio.gather(
            _safe_history(fmp, symbol),
            _safe_history(fmp, sector_etf),
            _safe_history(fmp, "SPY"),
            fetch_peer_comparison(research, fmp, symbol, profile.data or {}, n_peers=5),
            research.fetch_revenue_segments_product(symbol),
            research.fetch_revenue_segments_geographic(symbol),
            research.fetch_earnings_transcript(symbol),
            research.fetch_price_target_summary(symbol),
            research.fetch_price_target_news(symbol, limit=15),
            research.fetch_institutional_holders(symbol, limit=20),
        )

    return {
        "profile": profile.data,
        "income_q": income.data,
        "balance_q": balance.data,
        "cashflow_q": cashflow.data,
        "ratios_annual": ratios_annual.data,
        "ratios_ttm": ratios_ttm.data,
        "key_metrics_ttm": km_ttm.data,
        "earnings": earnings.data,
        "news": news.data,
        "press_releases": press_releases.data,
        "grades": grades.data,
        "sec_filings": sec_filings.data,
        "insider_trades": insider_trades.data,
        "next_earnings_date": next_earnings.isoformat() if next_earnings else None,
        # Technical agent inputs
        "price_history_60d": symbol_df,
        "sector_etf_history": sector_df,
        "sector_etf_symbol": sector_etf,
        "spy_history": spy_df,
        # M16 — peer comparison + ETF flag
        "peer_metrics": peer_metrics,
        "is_etf": bool((profile.data or {}).get("isEtf")),
        # M17 — Tier 1 profile-building data
        "revenue_segments_product": segs_prod_r.data,
        "revenue_segments_geo": segs_geo_r.data,
        "earnings_transcript": transcript_r.data,
        "price_target_summary": pt_summary_r.data,
        "price_target_news": pt_news_r.data,
        "institutional_holders": inst_holders_r.data,
        # M18 — Unusual Whales institutional flow data
        "uw_inst_ownership": (uw_inst_r.data if uw_inst_r else None),
        "uw_darkpool": (uw_dp_r.data if uw_dp_r else None),
        "uw_options_flow": (uw_flow_r.data if uw_flow_r else None),
        "uw_options_volume": (uw_volume_r.data if uw_volume_r else None),
        "uw_insider": (uw_insider_r.data if uw_insider_r else None),
        # M19 — Options Structure + Macro Regime + Short Interest
        "uw_greek_exposure": (uw_greek_r.data if uw_greek_r else None),
        "uw_max_pain":       (uw_pain_r.data if uw_pain_r else None),
        "uw_vol_term":       (uw_volterm_r.data if uw_volterm_r else None),
        "uw_short_interest": (uw_short_r.data if uw_short_r else None),
        "uw_sector_etfs":    (uw_sectors_r.data if uw_sectors_r else None),
        "uw_market_tide":    (uw_tide_r.data if uw_tide_r else None),
        "uw_econ_calendar":  (uw_econ_r.data if uw_econ_r else None),
        "_availability": {
            "profile": profile.available,
            "income_q": income.available,
            "balance_q": balance.available,
            "cashflow_q": cashflow.available,
            "ratios_annual": ratios_annual.available,
            "ratios_ttm": ratios_ttm.available,
            "key_metrics_ttm": km_ttm.available,
            "earnings": earnings.available,
            "news": news.available,
            "press_releases": press_releases.available,
            "grades": grades.available,
            "sec_filings": sec_filings.available,
            "insider_trades": insider_trades.available,
            "price_history_60d": bool(symbol_df),
            "sector_etf_history": bool(sector_df),
            "spy_history": bool(spy_df),
            "revenue_segments_product": segs_prod_r.available,
            "revenue_segments_geo": segs_geo_r.available,
            "earnings_transcript": transcript_r.available,
            "price_target_summary": pt_summary_r.available,
            "price_target_news": pt_news_r.available,
            "institutional_holders": inst_holders_r.available,
            "uw_inst_ownership": bool(uw_inst_r and uw_inst_r.available),
            "uw_darkpool": bool(uw_dp_r and uw_dp_r.available),
            "uw_options_flow": bool(uw_flow_r and uw_flow_r.available),
            "uw_options_volume": bool(uw_volume_r and uw_volume_r.available),
            "uw_insider": bool(uw_insider_r and uw_insider_r.available),
            "uw_greek_exposure": bool(uw_greek_r and uw_greek_r.available),
            "uw_max_pain":       bool(uw_pain_r and uw_pain_r.available),
            "uw_vol_term":       bool(uw_volterm_r and uw_volterm_r.available),
            "uw_short_interest": bool(uw_short_r and uw_short_r.available),
            "uw_sector_etfs":    bool(uw_sectors_r and uw_sectors_r.available),
            "uw_market_tide":    bool(uw_tide_r and uw_tide_r.available),
            "uw_econ_calendar":  bool(uw_econ_r and uw_econ_r.available),
        },
    }


async def _safe_history(fmp: FMPClient, sym: str) -> list[dict]:
    """Last 60 daily bars as compact records. Returns [] on failure."""
    try:
        df = await fmp.fetch_daily(sym)
        if df is None or df.empty:
            return []
        tail = df.tail(60)
        return [
            {
                "date": str(row["timestamp"])[:10],
                "close": float(row["close"]),
                "volume": int(row["volume"]) if row["volume"] == row["volume"] else 0,
            }
            for _, row in tail.iterrows()
        ]
    except Exception as e:  # noqa: BLE001
        log.warning("history fetch failed for %s: %s", sym, e)
        return []


# --------------------------------------------------------------------------- #
# Signal markdown (00_signal.md)
# --------------------------------------------------------------------------- #


def quant_signal_block(state: SignalState) -> str:
    """Return a short text block describing the quant signal origin of this job.

    Injected into every agent prompt so all 11 agents know whether this came
    from the systematic strategy (and its score/rank) or was triggered manually.
    """
    sig: Optional[SignalInput] = state.get("signal_input")  # type: ignore
    src = state.get("source", "manual")

    if src == "manual":
        return (
            "**Signal origin: MANUAL** — this analysis was triggered manually "
            "by the portfolio manager, not by the systematic strategy."
        )
    if src == "quant" and sig and sig.quant_score is not None:
        rank_txt = f"Rank #{state['context'].get('quant_rank', '?')} in universe · " \
                   if state.get("context", {}).get("quant_rank") else ""
        breakout = "breakout confirmed (YES)" if sig.breakout_ok else "no breakout yet"
        trend = "trend filter passed (YES)" if sig.trend_ok else "trend filter marginal"
        return (
            f"**Signal origin: QUANT STRATEGY** — the systematic momentum model "
            f"flagged {state['symbol']} as a top candidate today.\n"
            f"- Momentum score: **{sig.quant_score:.3f}** (threshold 0.25 to qualify)\n"
            f"- Technicals: {breakout}, {trend}\n"
            f"- This score is one of the highest in the S&P 100 universe today.\n"
            f"Use this to weight your conviction: a high quant score means "
            f"price momentum and trend are objectively strong — this is not "
            f"a speculative or contra-trend idea."
        )
    if src == "quant":
        return (
            "**Signal origin: QUANT STRATEGY** — the systematic momentum model "
            "flagged this stock. Momentum and trend filters were satisfied."
        )
    return f"**Signal origin: {src}**"


def _render_signal_md(state: SignalState) -> str:
    sym = state["symbol"]
    src = state["source"]
    d = state["signal_date"]
    sig: Optional[SignalInput] = state.get("signal_input")  # type: ignore[assignment]
    lines = [
        f"# Signal — {sym}",
        "",
        f"_Date: {d}_  ",
        f"_Source: **{src}**_",
        "",
    ]
    if sig:
        if sig.notes:
            lines += ["## Notes", "", sig.notes, ""]
        if sig.quant_score is not None:
            lines += [
                "## Quant snapshot",
                "",
                f"- Score: `{sig.quant_score}`",
                f"- Trend OK: `{sig.trend_ok}`",
                f"- Breakout OK: `{sig.breakout_ok}`",
                f"- Current price: `{sig.current_price}`",
                f"- ATR: `{sig.atr}`",
                "",
            ]
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Public entry: run the whole pipeline for one symbol
# --------------------------------------------------------------------------- #


async def run_full_pipeline(
    symbol: str,
    source: str = "manual",
    notes: Optional[str] = None,
    progress: Optional[callable] = None,
) -> SignalState:
    """Run all 6 agents end-to-end for one ticker. Returns the final state.

    `progress` is an optional callable: progress(stage_name: str, msg: str)
    so callers (CLI, web UI) can stream stage transitions to the user.
    """
    symbol = symbol.upper()
    today = date.today().isoformat()
    fs = FileStore()

    def _step(name: str, msg: str, **extra) -> None:
        log.info("[pipeline:%s] %s", name, msg)
        if progress:
            try:
                progress(name, msg, **extra)
            except TypeError:
                # Backward-compat: older callers may not accept **extra
                try:
                    progress(name, msg)
                except Exception:  # noqa: BLE001
                    pass
            except Exception:  # noqa: BLE001 — progress must never break pipeline
                pass

    # 0. State + input signal.
    # If notes carries a quant payload (from the evening scheduler), parse it
    # into structured fields so every agent can see the signal context.
    quant_score: Optional[float] = None
    quant_rank: Optional[int] = None
    trend_ok: Optional[bool] = None
    breakout_ok: Optional[bool] = None
    if notes and source == "quant":
        import re as _re
        m = _re.search(r"score\s+([\d.]+)", notes, _re.I)
        if m:
            quant_score = float(m.group(1))
        m = _re.search(r"rank\s+(\d+)", notes, _re.I)
        if m:
            quant_rank = int(m.group(1))
        breakout_ok = "breakout=Y" in (notes or "")
        trend_ok = "trend=Y" in (notes or "")

    state = new_signal_state(symbol, today, source)
    state["signal_input"] = SignalInput(
        symbol=symbol,
        source=source,  # type: ignore[arg-type]
        signal_date=today,
        notes=notes,
        quant_score=quant_score,
        trend_ok=trend_ok,
        breakout_ok=breakout_ok,
    )
    # Store quant_rank in context so quant_signal_block() can reference it
    state.setdefault("context", {})["quant_rank"] = quant_rank
    fs.write_markdown(symbol, today, "signal", _render_signal_md(state))
    _step("init", f"state ready for {symbol} ({source})"
          + (f" [quant rank={quant_rank} score={quant_score:.3f} breakout={'Y' if breakout_ok else 'N'}]"
             if quant_score is not None else ""))

    # 1. Pre-fetch FMP bundle + portfolio snapshot + macro overlay
    _step("prefetch", "fetching FMP data + portfolio snapshot...")
    async with FMPClient() as raw:
        research = FMPResearchClient(raw)
        state["context"] = await prefetch_pipeline_context(research, raw, symbol)

    # Portfolio state needed by Risk Manager
    portfolio = VirtualPortfolio()
    try:
        open_positions = portfolio.list_open()
        snap = portfolio.equity_snapshot()
    finally:
        portfolio.close_conn()

    # Build sector breakdown from open positions (% of equity per sector)
    # Sectors come from the profile of each held symbol — we don't have those
    # cached, so fall back to "Unknown" if not present. Risk Manager will
    # still apply hard rules correctly.
    sector_breakdown: dict[str, float] = {}
    equity = snap.get("equity", 1.0) or 1.0
    for p in open_positions:
        # We don't store sector per position; approximate using ticker
        sec = p.get("sector") or "Unknown"
        mv = (p.get("units") or 0) * (p.get("current_price") or p.get("entry_price") or 0)
        sector_breakdown[sec] = sector_breakdown.get(sec, 0.0) + (mv / equity * 100.0)

    state["context"]["portfolio_snapshot"] = snap
    state["context"]["open_positions"] = open_positions
    state["context"]["sector_breakdown"] = sector_breakdown

    # ---- Per-stock profile (M17) — load if exists; auto-build later if not ---
    stock_profile = live_profiles.load_profile(symbol)
    state["context"]["stock_profile"] = stock_profile
    state["context"]["stock_profile_exists"] = stock_profile is not None
    if stock_profile is not None:
        _step("prefetch", f"loaded existing profile (tier {stock_profile.priority})")
    else:
        _step("prefetch", "no profile on disk — will auto-build after analysis")

    # ---- Prior PM decision (used by profile refresh policy) ----------------
    state["context"]["previous_pm_decision"] = _load_prior_pm_decision(symbol, today)

    # ---- Pricing context: a single source of truth for all downstream agents ---
    # Every agent that talks about price (Bull, Bear, PM) must anchor to these
    # numbers — eliminates the "$175 target on a $751 stock" failure mode and
    # the "PM says $50K, engine creates $250K" sizing mismatch.
    state["context"]["pricing_context"] = _build_pricing_context(
        state["context"], snap,
    )

    # Macro overlay (from today's morning cycle if it ran)
    macro = load_macro_context_for_today()
    if macro is not None:
        state["macro"] = macro
        # Also persist a small _macro_context.md artifact for audit
        fs.write_markdown(
            symbol, today, "macro_context",
            _render_macro_md(macro),
        )

    avail = state["context"].get("_availability", {})
    fetched_ok = [k for k, v in avail.items() if v]
    _step("prefetch",
          f"fetched: {len(fetched_ok)} sources, portfolio: {snap.get('open_positions', 0)} open"
          + (f", macro: {macro.regime}" if macro else ", macro: n/a"))

    # 2a. Data layer prep (no LLM): earnings dynamics + analyst track-record.
    #     Computed pre-analysts so Fundamental + News can read them.
    pricing_for_layer = state.get("context", {}).get("pricing_context") or {}
    current_price_for_layer = pricing_for_layer.get("current_price")
    try:
        dynamics = earnings_dynamics.compute(
            state["context"].get("earnings") or [],
            state["context"].get("next_earnings_date"),
        )
        state["context"]["earnings_dynamics"] = dynamics
    except Exception as e:  # noqa: BLE001
        log.warning("earnings_dynamics failed: %s", e)
        state["context"]["earnings_dynamics"] = {"available": False}

    try:
        analyst_tracker.record_calls(
            symbol, state["context"].get("grades") or [],
            current_price_for_layer,
        )
        analyst_tracker.update_call_outcomes(symbol, current_price_for_layer or 0)
        state["context"]["grades_annotated"] = analyst_tracker.annotate_grades(
            symbol, state["context"].get("grades") or [],
        )
    except Exception as e:  # noqa: BLE001
        log.warning("analyst_tracker failed: %s", e)
        state["context"]["grades_annotated"] = state["context"].get("grades") or []

    # 2b. Analyst layer — 6 agents in parallel (Gemini Flash):
    #     Fundamental + News + Technical + Institutional Flow (M18)
    #   + Options Structure + Macro Regime (M19)
    _step("analysts",
          "Fundamental + News + Technical + Institutional Flow + Options + Macro "
          "(6 parallel, Gemini Flash)",
          model="gemini-2.5-flash", action="start",
          agents=["fundamental", "news", "technical", "institutional_flow",
                  "options_structure", "macro_regime"])
    fund_agent = FundamentalAgent(gemini_flash(), fs)
    news_agent = NewsAgent(gemini_flash(), fs)
    tech_agent = TechnicalAgent(gemini_flash(), fs)
    inst_agent = InstitutionalFlowAgent(gemini_flash(), fs)
    opts_agent = OptionsStructureAgent(gemini_flash(), fs)
    macro_agent = MacroRegimeAgent(gemini_flash(), fs)
    (fund_state, news_state, tech_state, inst_state,
     opts_state, macro_state) = await asyncio.gather(
        fund_agent.run(state),
        news_agent.run(state),
        tech_agent.run(state),
        inst_agent.run(state),
        opts_agent.run(state),
        macro_agent.run(state),
    )
    state["fundamental"] = fund_state.get("fundamental")  # type: ignore[typeddict-item]
    state["news"] = news_state.get("news")                # type: ignore[typeddict-item]
    state["technical"] = tech_state.get("technical")      # type: ignore[typeddict-item]
    state["institutional_flow"] = inst_state.get("institutional_flow")  # type: ignore[typeddict-item]
    state["options_structure"] = opts_state.get("options_structure")    # type: ignore[typeddict-item]
    state["macro_regime"] = macro_state.get("macro_regime")             # type: ignore[typeddict-item]
    state["meta"] = _merge_meta(state["meta"], fund_state["meta"],
                                  news_state["meta"], tech_state["meta"],
                                  inst_state["meta"], opts_state["meta"],
                                  macro_state["meta"])
    fund_score = getattr(state.get("fundamental"), "fundamental_score", None)
    news_risk = getattr(state.get("news"), "news_risk_score", None)
    tech_strength = getattr(state.get("technical"), "technical_strength", None)
    smart_money = getattr(state.get("institutional_flow"), "smart_money_score", None)
    dealer_pos = getattr(state.get("options_structure"), "dealer_positioning", None)
    regime_risk = getattr(state.get("macro_regime"), "regime_risk_score", None)
    _step("analysts",
          f"complete — fund {fund_score}/10, news risk {news_risk}/10, "
          f"technical {tech_strength}/10, smart money {smart_money}/10, "
          f"dealer {dealer_pos}, macro risk {regime_risk}/10",
          action="complete",
          metrics={"fundamental": fund_score, "news_risk": news_risk,
                   "technical": tech_strength, "smart_money": smart_money,
                   "dealer_positioning": dealer_pos, "macro_risk": regime_risk})

    # 3. Debate layer in parallel (Claude Sonnet)
    _step("debate", "Bull + Bear (parallel, Claude Sonnet)",
          model="claude-sonnet-4-6", action="start",
          agents=["bull", "bear"])
    bull_agent = BullAgent(claude_sonnet(), fs)
    bear_agent = BearAgent(claude_sonnet(), fs)
    bull_state, bear_state = await asyncio.gather(
        bull_agent.run(state),
        bear_agent.run(state),
    )
    state["bull"] = bull_state.get("bull")  # type: ignore[typeddict-item]
    state["bear"] = bear_state.get("bear")  # type: ignore[typeddict-item]
    state["meta"] = _merge_meta(state["meta"], bull_state["meta"], bear_state["meta"])
    bull_c = getattr(state.get("bull"), "conviction_self_rated", None)
    bear_c = getattr(state.get("bear"), "conviction_self_rated", None)
    _step("debate",
          f"complete — bull {bull_c}/10 vs bear {bear_c}/10",
          action="complete",
          metrics={"bull_conviction": bull_c, "bear_conviction": bear_c})

    # 3b. Debate Judge (M16) — scores Bull vs Bear so PM doesn't have to
    _step("judge", "Debate Judge scoring Bull vs Bear (Claude Sonnet)",
          model="claude-sonnet-4-6", action="start", agent="judge")
    judge_agent = JudgeAgent(claude_sonnet(), fs)
    state = await judge_agent.run(state)
    judge = state.get("judge")
    if judge:
        _step("judge",
              f"winner: {judge.winner}, conviction {judge.conviction_score}/10",
              action="complete",
              metrics={"winner": judge.winner,
                       "conviction": judge.conviction_score})

    # 4. Risk Manager (deterministic gates + Claude Sonnet for soft judgment)
    _step("risk_manager",
          "Risk Manager checking portfolio caps + soft concentration risk",
          model="claude-sonnet-4-6", action="start", agent="risk")
    risk_agent = RiskManagerAgent(claude_sonnet(), fs)
    state = await risk_agent.run(state)
    risk = state.get("risk")
    if risk:
        det_note = " (deterministic)" if risk.deterministic_block_reason else ""
        _step("risk_manager",
              f"verdict: {risk.verdict}, size cap {risk.recommended_size_pct}%{det_note}",
              action="complete",
              metrics={"verdict": risk.verdict,
                       "size_cap": risk.recommended_size_pct,
                       "rules_count": len(risk.rules_triggered)})

    # 5. PM verdict (M16 — Claude Opus for fiduciary-grade reasoning)
    _step("pm", "Portfolio Manager deliberating (Claude Opus)",
          model="claude-opus-4-7", action="start", agent="pm")
    pm_agent = PMAgent(claude_opus(), fs)
    state = await pm_agent.run(state)
    pm = state["pm"]
    _step("pm",
          f"verdict: {pm.decision}, conviction {pm.conviction_score}/10, size {pm.recommended_size_pct}%",
          action="complete",
          metrics={"decision": pm.decision, "conviction": pm.conviction_score,
                   "size_pct": pm.recommended_size_pct})

    # 5. Summary rollup (Gemini Flash)
    _step("summary", "writing executive summary (Gemini Flash)",
          model="gemini-2.5-flash", action="start", agent="summary")
    summary_agent = SummaryAgent(gemini_flash(), fs)
    state = await summary_agent.run(state)
    _step("summary", "complete", action="complete")

    # 6. Dump raw state for audit
    fs.write_raw_state(symbol, today, state)

    # 6b. Per-stock profile — build on first run, refresh on cadence/event (M17)
    existing = state["context"].get("stock_profile")
    refresh_reason = None
    if existing is None:
        refresh_reason = "first analysis (no profile on disk)"
    else:
        should, reason = live_profiles.should_refresh_profile(existing, state)
        if should:
            refresh_reason = reason

    if refresh_reason:
        action_label = "build" if existing is None else "refresh"
        _step("profile_build",
              f"{action_label} triggered: {refresh_reason}",
              model="claude-opus-4-7", action="start", agent="profile_builder")
        try:
            new_profile = await build_stock_profile(symbol, state)
            if new_profile is not None:
                # If refreshing, carry forward user-edited fields
                if existing is not None:
                    new_profile = live_profiles._preserve_user_edits(
                        new_profile, existing,
                    )
                live_profiles.save_profile(new_profile)
                _step("profile_build",
                      f"profile {action_label}ed at watchlist/{symbol}.md "
                      f"({len(new_profile.bull_thesis_pillars)} bull pillars, "
                      f"{len(new_profile.bear_thesis_pillars)} bear pillars, "
                      f"{len(new_profile.red_lines)} red lines)",
                      action="complete")
            else:
                _step("profile_build", "builder returned None — skipped",
                      action="complete")
        except Exception as e:  # noqa: BLE001 — never break the pipeline
            _step("profile_build", f"failed: {e}", action="complete")
    else:
        # Profile is fresh — log it so the run trace is self-documenting
        age = ""
        try:
            from datetime import date as _date
            if existing and existing.last_reviewed:
                lr = existing.last_reviewed
                if isinstance(lr, str):
                    lr = _date.fromisoformat(lr)
                age = f" ({(_date.today() - lr).days}d old, "
                age += f"cadence={existing.review_cadence_days}d)"
        except Exception:  # noqa: BLE001
            pass
        _step("profile_build", f"profile fresh — no rebuild{age}",
              action="complete")

    # 7. Telegram notification — fire on every decision that produced a message.
    # The split-message design (stock view + portfolio fit) is informative on
    # REJECT/HOLD too: the user sees the thesis we wrote and why we didn't
    # execute. Skip only if both message fields are empty (nothing to say).
    pm = state.get("pm")
    if pm is not None:
        stock_msg = (getattr(pm, "telegram_message", "") or "").strip()
        port_msg = (getattr(pm, "telegram_portfolio_message", "") or "").strip()
        if stock_msg or port_msg:
            try:
                from .telegram import telegram as _telegram
                client = _telegram()
                ok = await client.send_pm_verdict(symbol, pm)
                _step(
                    "notify",
                    f"telegram {'sent' if ok else 'skipped'} ({pm.decision})",
                )
            except Exception as e:  # noqa: BLE001 — must not break the pipeline
                _step("notify", f"telegram error: {e}")
        else:
            _step(
                "notify",
                f"telegram skipped — no message body ({pm.decision})",
            )

    _step("done", f"all artifacts written to ai_research/{symbol}/{today}/")

    return state


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _load_prior_pm_decision(symbol: str, today_iso: str) -> Optional[str]:
    """Return the PM decision string from the most recent prior run on disk.

    Used by the profile-refresh policy to detect APPROVE↔REJECT flips. Returns
    None if no prior run exists or the file is unreadable.
    """
    from ..config import AI_RESEARCH_DIR
    sym_dir = AI_RESEARCH_DIR / symbol.upper()
    if not sym_dir.exists():
        return None
    # All date folders for this symbol, newest first, excluding today's
    candidates = sorted(
        (p for p in sym_dir.iterdir()
         if p.is_dir() and p.name != today_iso),
        reverse=True,
    )
    for folder in candidates:
        raw = folder / "_raw.json"
        if not raw.exists():
            continue
        try:
            data = json.loads(raw.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        pm = data.get("pm") or {}
        decision = pm.get("decision")
        if decision:
            return str(decision)
    return None


def _build_pricing_context(ctx: dict, snap: dict) -> dict:
    """One source of truth for current price + scenario sizes.

    Computed once at prefetch; injected into Bull/Bear/PM prompts so they all
    cite the same numbers. Without this, Bull would write "$175 target" while
    the stock trades at $751 (real bug observed in the MU run).
    """
    price_history = ctx.get("price_history_60d") or []
    last_close = None
    if price_history:
        try:
            last_close = float(price_history[-1].get("close") or 0) or None
        except (TypeError, ValueError):
            last_close = None

    # If we somehow have no price, return a degraded snapshot — agents must
    # know they're flying blind.
    if not last_close or last_close <= 0:
        return {
            "current_price": None,
            "data_available": False,
            "_note": "Current price unavailable — do NOT fabricate price targets.",
        }

    # ---- Volatility from recent closes (ATR-style proxy) -------------------
    # We feed the AI the stock's OWN volatility so it can size + stop per name,
    # instead of a flat 8% / 25% formula.
    closes = []
    for row in price_history:
        try:
            c = float(row.get("close") or 0)
            if c > 0:
                closes.append(c)
        except (TypeError, ValueError):
            continue

    def _ret(days: int):
        if len(closes) > days:
            base = closes[-days - 1]
            return round((last_close / base - 1) * 100, 1) if base else None
        return None

    atr_pct = None
    if len(closes) >= 6:
        window = closes[-21:] if len(closes) >= 21 else closes
        moves = [abs(window[i] / window[i - 1] - 1) for i in range(1, len(window)) if window[i - 1]]
        if moves:
            atr_pct = round(sum(moves) / len(moves) * 100, 2)  # avg daily % move

    # Volatility-based stop guidance: ~3× the average daily move, floored/capped.
    suggested_stop_pct = None
    if atr_pct:
        suggested_stop_pct = round(min(22.0, max(6.0, atr_pct * 3.0)), 1)

    equity = float(snap.get("equity") or 0.0)
    current_mv = float(snap.get("open_market_value") or 0.0)
    max_gross_pct = live_settings.get_max_gross_pct()
    room_usd = max(max_gross_pct * equity - current_mv, 0.0)

    cap_pct = live_settings.get_max_single_name_pct() * 100.0   # e.g. 10.0
    cap_usd = round(live_settings.get_max_single_name_pct() * equity, 0)

    return {
        "data_available": True,
        "current_price": round(last_close, 2),
        # --- the stock's own volatility (drives YOUR size + stop) ---
        "volatility": {
            "avg_daily_move_pct": atr_pct,               # "ATR%" — how much it swings/day
            "return_1m_pct": _ret(21),
            "return_3m_pct": _ret(63),
            "return_6m_pct": _ret(126),
            "high_recent": round(max(closes), 2) if closes else None,
            "low_recent": round(min(closes), 2) if closes else None,
            "suggested_stop_pct_guide": suggested_stop_pct,  # ~3× daily move, guidance only
        },
        # --- your hard limits (size MUST stay within these) ---
        "max_single_name_pct": round(cap_pct, 1),
        "max_single_name_usd": cap_usd,
        "equity_usd": round(equity, 0),
        "available_room_usd": round(room_usd, 0),
        "_note": (
            "Current price is AUTHORITATIVE; price targets MUST be relative to it. "
            "YOU choose position_pct_of_fund (≤ max_single_name_pct) and a "
            "volatility-based stop_price — there is no fixed sizing formula. "
            "Use avg_daily_move_pct: calm stock → tighter stop, jumpy stock → wider."
        ),
    }


def _render_macro_md(m) -> str:
    """Render a MacroContextSnapshot as a small markdown artifact."""
    lines = [
        f"# Macro Context — {m.as_of_date}",
        "",
        f"**Regime:** {m.regime}  (confidence {m.confidence}/10)",
        f"**New entries throttle:** {m.new_entries_throttle}",
        "",
        f"**Sector tailwinds (top 3 by 20d return):** {', '.join(m.sector_tailwinds) or '—'}",
        "",
        f"**Sector headwinds (bottom 3):** {', '.join(m.sector_headwinds) or '—'}",
        "",
        "## Summary",
        "",
        f"> {m.summary}",
        "",
        "---",
        "",
        "_Loaded from today's morning cycle — no separate LLM call._",
        "",
    ]
    return "\n".join(lines)


def _merge_meta(*metas: dict) -> dict:
    """Merge multiple meta dicts, concatenating agents_run and errors."""
    merged: dict[str, Any] = {}
    agents_run: list[str] = []
    errors: list = []
    for m in metas:
        for k, v in m.items():
            if k == "agents_run":
                agents_run.extend(v or [])
            elif k == "errors":
                errors.extend(v or [])
            else:
                merged[k] = v
    merged["agents_run"] = sorted(set(agents_run))
    merged["errors"] = errors
    return merged
