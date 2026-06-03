"""Fundamental Analyst — Agent 2.

Consumes 8 FMP endpoints (profile, income_q, balance_q, cashflow_q, ratios_annual,
ratios_ttm, key_metrics_ttm, earnings) and produces a FundamentalReport.

The raw FMP responses are quite verbose (~50 fields per quarter on income alone).
This agent PROJECTS the raw data to a clean per-record shape before injecting
into the prompt — keeps tokens down and lets the LLM focus on signal, not schema.
"""
from __future__ import annotations

import json
from typing import Any, Optional

from ..renderers.fundamental import render as render_md
from ..schemas import FundamentalReport
from ..state import SignalState
from .base import Agent


class FundamentalAgent(Agent):
    NAME = "fundamental"
    LLM_TIER = "pro"
    REQUIRES_DATA = [
        "profile",
        "income_q",
        "balance_q",
        "cashflow_q",
        "ratios_annual",
        "ratios_ttm",
        "key_metrics_ttm",
        "earnings",
        "next_earnings_date",
        "peer_metrics",  # M16 — sector peer comparison
    ]
    OUTPUT_SCHEMA = FundamentalReport
    STAGE = "fundamental"
    PROMPT_FILE = "fundamental.md"

    # ----------------------------------------------------------------------- #
    # Prompt construction
    # ----------------------------------------------------------------------- #

    def build_prompt(self, state: SignalState) -> str:
        template = self.load_prompt_template()
        ctx = state.get("context", {})

        profile = ctx.get("profile") or {}
        income_q = ctx.get("income_q") or []
        balance_q = ctx.get("balance_q") or []
        cashflow_q = ctx.get("cashflow_q") or []
        ratios_annual = ctx.get("ratios_annual") or []
        ratios_ttm = ctx.get("ratios_ttm") or {}
        key_metrics_ttm = ctx.get("key_metrics_ttm") or {}
        earnings = ctx.get("earnings") or []
        next_earn = ctx.get("next_earnings_date")

        peer_metrics = ctx.get("peer_metrics") or {}

        # M17 — per-stock profile block (or "no profile yet" placeholder)
        from .. import profiles as live_profiles
        from .. import earnings_dynamics as live_earn
        stock_profile = ctx.get("stock_profile")
        profile_block = live_profiles.profile_block_for_agent(
            stock_profile, "fundamental",
        )

        # M19 — earnings dynamics: beat/miss streak, IV-crush flag, days to ER
        earnings_dynamics_block = live_earn.format_for_prompt(
            ctx.get("earnings_dynamics") or {}
        )

        return template.format(
            symbol=state["symbol"],
            as_of_date=state["signal_date"],
            earnings_days_away=str(_days_until(next_earn, state["signal_date"])),
            profile_json=_dump(_project_profile(profile)),
            income_json=_dump(_project_income(income_q)),
            balance_json=_dump(_project_balance(balance_q)),
            cashflow_json=_dump(_project_cashflow(cashflow_q)),
            ratios_annual_json=_dump(_project_ratios_annual(ratios_annual)),
            ratios_ttm_json=_dump(_project_ratios_ttm(ratios_ttm)),
            key_metrics_ttm_json=_dump(_project_key_metrics_ttm(key_metrics_ttm)),
            earnings_json=_dump(_project_earnings(earnings)),
            earnings_dynamics_block=earnings_dynamics_block,
            peer_metrics_json=_dump(peer_metrics),
            stock_profile_block=profile_block,
        )

    # ----------------------------------------------------------------------- #
    # Rendering
    # ----------------------------------------------------------------------- #

    def render(self, output: FundamentalReport) -> str:
        return render_md(output)


# --------------------------------------------------------------------------- #
# Projections — keep the prompt small, clean, and focused on signal.
# --------------------------------------------------------------------------- #


def _dump(obj: Any) -> str:
    return json.dumps(obj, indent=2, default=str, ensure_ascii=False)


def _safe_div(a: Optional[float], b: Optional[float]) -> Optional[float]:
    if a is None or b in (None, 0):
        return None
    try:
        return round(a / b, 4)
    except (TypeError, ZeroDivisionError):
        return None


def _project_profile(p: dict) -> dict:
    if not p:
        return {}
    return {
        "company_name": p.get("companyName"),
        "sector": p.get("sector"),
        "industry": p.get("industry"),
        "market_cap_usd": p.get("mktCap") or p.get("marketCap"),
        "price": p.get("price"),
        "beta": p.get("beta"),
        "exchange": p.get("exchange"),
        "ceo": p.get("ceo"),
        "ceo_note": "Trust this CEO field — FMP keeps it current. Your training "
                     "cutoff is older. Do NOT flag this as inaccurate based on "
                     "memory of prior CEO names.",
        "employees": p.get("fullTimeEmployees"),
        "country": p.get("country"),
        "ipo_date": p.get("ipoDate"),
        "currency": p.get("currency"),
        "is_etf": p.get("isEtf"),
    }


def _project_income(rows: list[dict]) -> list[dict]:
    out: list[dict] = []
    for r in rows:
        revenue = r.get("revenue")
        out.append({
            "fiscal_date": r.get("date"),
            "period": r.get("period"),
            "fiscal_year": r.get("fiscalYear"),
            "revenue": revenue,
            "gross_profit": r.get("grossProfit"),
            "gross_margin": _safe_div(r.get("grossProfit"), revenue),
            "operating_income": r.get("operatingIncome"),
            "operating_margin": _safe_div(r.get("operatingIncome"), revenue),
            "net_income": r.get("netIncome"),
            "net_margin": _safe_div(r.get("netIncome"), revenue),
            "eps_diluted": r.get("epsDiluted"),
            "ebitda": r.get("ebitda"),
        })
    return out


def _project_balance(rows: list[dict]) -> list[dict]:
    out: list[dict] = []
    for r in rows:
        out.append({
            "fiscal_date": r.get("date"),
            "period": r.get("period"),
            "cash_and_equivalents": r.get("cashAndCashEquivalents"),
            "short_term_investments": r.get("shortTermInvestments"),
            "total_current_assets": r.get("totalCurrentAssets"),
            "total_assets": r.get("totalAssets"),
            "total_current_liabilities": r.get("totalCurrentLiabilities"),
            "short_term_debt": r.get("shortTermDebt"),
            "long_term_debt": r.get("longTermDebt"),
            "total_debt": r.get("totalDebt"),
            "net_debt": r.get("netDebt"),
            "stockholders_equity": r.get("totalStockholdersEquity"),
            "current_ratio": _safe_div(
                r.get("totalCurrentAssets"), r.get("totalCurrentLiabilities")
            ),
            "debt_to_equity": _safe_div(
                r.get("totalDebt"), r.get("totalStockholdersEquity")
            ),
        })
    return out


def _project_cashflow(rows: list[dict]) -> list[dict]:
    out: list[dict] = []
    for r in rows:
        out.append({
            "fiscal_date": r.get("date"),
            "period": r.get("period"),
            "operating_cash_flow": r.get("netCashProvidedByOperatingActivities"),
            "capex": r.get("capitalExpenditure"),
            "free_cash_flow": r.get("freeCashFlow"),
            "dividends_paid": r.get("commonDividendsPaid"),
            "stock_buybacks": r.get("commonStockRepurchased"),
        })
    return out


def _project_ratios_annual(rows: list[dict]) -> list[dict]:
    out: list[dict] = []
    for r in rows:
        out.append({
            "fiscal_year": r.get("fiscalYear"),
            "date": r.get("date"),
            "current_ratio": r.get("currentRatio"),
            "quick_ratio": r.get("quickRatio"),
            "cash_ratio": r.get("cashRatio"),
            "debt_to_equity": r.get("debtToEquityRatio"),
            "debt_to_assets": r.get("debtToAssetsRatio"),
            "asset_turnover": r.get("assetTurnover"),
            "gross_margin": r.get("grossProfitMargin"),
            "operating_margin": r.get("operatingProfitMargin"),
            "net_margin": r.get("netProfitMargin"),
            "ev_multiple": r.get("enterpriseValueMultiple"),
            "ebit_margin": r.get("ebitMargin"),
            "ebitda_margin": r.get("ebitdaMargin"),
            "dividend_yield": r.get("dividendYield"),
        })
    return out


def _project_ratios_ttm(r: dict) -> dict:
    if not r:
        return {}
    # TTM endpoint suffixes every field with TTM — strip for readability.
    return {
        k.removesuffix("TTM"): v
        for k, v in r.items()
        if k.endswith("TTM") and v is not None
    }


def _project_key_metrics_ttm(r: dict) -> dict:
    if not r:
        return {}
    return {
        k.removesuffix("TTM"): v
        for k, v in r.items()
        if k.endswith("TTM") and v is not None
    }


def _project_earnings(rows: list[dict]) -> list[dict]:
    out: list[dict] = []
    for r in rows:
        eps_a = r.get("epsActual")
        eps_e = r.get("epsEstimated")
        surprise_pct: Optional[float] = None
        if eps_a is not None and eps_e not in (None, 0):
            surprise_pct = round((eps_a - eps_e) / abs(eps_e) * 100, 2)
        out.append({
            "date": r.get("date"),
            "eps_actual": eps_a,
            "eps_estimated": eps_e,
            "surprise_pct": surprise_pct,
            "revenue_actual": r.get("revenueActual"),
            "revenue_estimated": r.get("revenueEstimated"),
        })
    return out


def _days_until(target_date: Optional[str], as_of: str) -> str:
    """Days from as_of -> target_date (positive = future). 'unknown' if missing."""
    if not target_date:
        return "unknown"
    try:
        from datetime import date
        t = date.fromisoformat(target_date[:10])
        a = date.fromisoformat(as_of[:10])
        return str((t - a).days)
    except (ValueError, TypeError):
        return "unknown"
