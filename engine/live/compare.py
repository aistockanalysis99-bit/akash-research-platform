"""Model Lab — Compare Mode.

Runs the SAME stock analysis through several models (DeepSeek-R1, GLM-5.2,
Qwen, Claude…) via OpenRouter and returns structured results side by side, so
we can judge whether an open/local model matches Claude's quality — BEFORE
buying any hardware.

This is an evaluation harness; it does NOT touch the live pipeline or portfolio.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Optional

from ..data.fmp_client import FMPClient
from .data.fmp_research import FMPResearchClient
from .llm.openrouter import OpenRouterClient, extract_json

log = logging.getLogger(__name__)


# Testable models — all reachable through the single OpenRouter key.
# `key` is our short id; `id` is the OpenRouter model id (verified live).
MODELS: list[dict[str, str]] = [
    {"key": "deepseek-r1", "id": "deepseek/deepseek-r1",        "name": "DeepSeek-R1",      "tagline": "Deep reasoning / skeptic"},
    {"key": "glm-5.2",     "id": "z-ai/glm-5.2",                "name": "GLM-5.2",          "tagline": "All-rounder / long context"},
    {"key": "qwen-3.7",    "id": "qwen/qwen3.7-plus",           "name": "Qwen 3.7 Plus",    "tagline": "News & filings reader"},
    {"key": "claude-opus", "id": "anthropic/claude-opus-4.8",   "name": "Claude Opus 4.8",  "tagline": "Gold-standard baseline"},
]
_BY_KEY = {m["key"]: m for m in MODELS}


SYSTEM = (
    "You are a senior equity analyst at a long-only fund. You are given a data "
    "bundle for one stock. Analyze it and return ONLY a JSON object — no prose, "
    "no markdown fences. Be specific and cite numbers from the data."
)

PROMPT_TEMPLATE = """Analyze {symbol} for a potential long position using ONLY the data below.

DATA BUNDLE:
{bundle}

Return ONLY this JSON object (no other text):
{{
  "verdict": "BUY | WATCH | AVOID",
  "conviction": <integer 1-10>,
  "target_price": <number, 6-month price target>,
  "stop_price": <number, where to cut losses>,
  "bull_points": ["<specific point with a number>", "..."],
  "bear_points": ["<specific risk with a number>", "..."],
  "key_risk": "<the single biggest risk, one sentence>",
  "summary": "<3-sentence plain-English verdict for a non-trader>"
}}"""


async def _build_bundle(symbol: str) -> dict[str, Any]:
    """Compact, identical-for-all-models fact sheet for one stock."""
    symbol = symbol.upper().strip()
    out: dict[str, Any] = {"symbol": symbol}
    async with FMPClient() as fmp:
        research = FMPResearchClient(fmp)
        prof, ratios, news, grades = await asyncio.gather(
            research.fetch_profile(symbol),
            research.fetch_ratios_ttm(symbol),
            research.fetch_news(symbol, limit=10, hours=120),
            research.fetch_grades(symbol, days=30),
            return_exceptions=True,
        )
        # Price action from daily bars
        try:
            df = await fmp.fetch_daily(symbol)
        except Exception:  # noqa: BLE001
            df = None

    def _data(x):
        return getattr(x, "data", None) if not isinstance(x, Exception) else None

    p = _data(prof) or {}
    out["profile"] = {
        "name": p.get("companyName"),
        "sector": p.get("sector"),
        "industry": p.get("industry"),
        "price": p.get("price"),
        "market_cap": p.get("marketCap" if "marketCap" in p else "mktCap"),
        "description": (p.get("description") or "")[:600],
    }

    r = _data(ratios) or {}
    if isinstance(r, list) and r:
        r = r[0]
    out["valuation_ttm"] = {
        k: r.get(k) for k in (
            "peRatioTTM", "priceToSalesRatioTTM", "netProfitMarginTTM",
            "grossProfitMarginTTM", "debtToEquityTTM", "returnOnEquityTTM",
        )
    } if isinstance(r, dict) else {}

    if df is not None and not df.empty:
        closes = df["close"].astype(float)
        last = float(closes.iloc[-1])

        def ret(days: int) -> Optional[float]:
            if len(closes) > days:
                base = float(closes.iloc[-days - 1])
                return round((last / base - 1) * 100, 1) if base else None
            return None

        out["price_action"] = {
            "last_close": round(last, 2),
            "return_1m_pct": ret(21),
            "return_3m_pct": ret(63),
            "return_6m_pct": ret(126),
            "high_52w": round(float(closes.tail(252).max()), 2),
            "low_52w": round(float(closes.tail(252).min()), 2),
        }

    nws = _data(news) or []
    out["recent_news"] = [
        {"title": n.get("title"), "date": (n.get("publishedDate") or "")[:10]}
        for n in (nws if isinstance(nws, list) else [])[:8]
    ]

    gr = _data(grades) or []
    out["analyst_grades"] = [
        {"firm": g.get("gradingCompany"), "action": g.get("action"),
         "to": g.get("newGrade")}
        for g in (gr if isinstance(gr, list) else [])[:8]
    ]
    return out


async def _run_one(client: OpenRouterClient, model: dict, symbol: str, bundle_json: str) -> dict[str, Any]:
    prompt = PROMPT_TEMPLATE.format(symbol=symbol, bundle=bundle_json)
    res = await client.complete(model["id"], prompt, system=SYSTEM)
    parsed = extract_json(res["text"]) if res.get("text") else None
    row: dict[str, Any] = {
        "key": model["key"],
        "model": model["name"],
        "tagline": model["tagline"],
        "ok": parsed is not None and res.get("error") is None,
        "cost_usd": res.get("cost_usd"),
        "latency_s": res.get("latency_s"),
        "error": res.get("error"),
        "valid_json": parsed is not None,
    }
    if parsed:
        row.update({
            "verdict": parsed.get("verdict"),
            "conviction": parsed.get("conviction"),
            "target_price": parsed.get("target_price"),
            "stop_price": parsed.get("stop_price"),
            "bull_points": parsed.get("bull_points") or [],
            "bear_points": parsed.get("bear_points") or [],
            "key_risk": parsed.get("key_risk"),
            "summary": parsed.get("summary"),
        })
    else:
        row["raw_text"] = (res.get("text") or "")[:500]
    return row


async def run_compare(symbol: str, model_keys: list[str]) -> dict[str, Any]:
    """Run `symbol` through each requested model. Returns bundle + results."""
    symbol = symbol.upper().strip()
    chosen = [_BY_KEY[k] for k in model_keys if k in _BY_KEY] or MODELS
    bundle = await _build_bundle(symbol)
    bundle_json = json.dumps(bundle, indent=2, default=str)

    client = OpenRouterClient()
    results = await asyncio.gather(
        *[_run_one(client, m, symbol, bundle_json) for m in chosen]
    )
    return {
        "symbol": symbol,
        "company": (bundle.get("profile") or {}).get("name"),
        "bundle": bundle,
        "results": list(results),
        "total_cost_usd": round(sum((r.get("cost_usd") or 0) for r in results), 4),
    }
