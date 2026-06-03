"""ProfileBuilder — auto-creates a per-stock dossier (StockProfile) on first
analysis of a new ticker.

Uses Claude Opus because the profile is consumed by every future analysis
of this ticker — it's a one-time investment that pays off across many runs.

Inputs:
    - Full FMP data bundle (profile, financials, segments, transcripts,
      price targets, institutional, news, etc.)
    - The outputs of the *first* analysis (fundamental, news, technical,
      bull, bear, PM) — these inform what the profile should capture

Output: StockProfile pydantic instance, persisted via profiles.save_profile()
"""
from __future__ import annotations

import json
import logging
from datetime import date
from typing import Any, Optional

from ..llm.claude import claude_opus
from ..llm.structured import invoke_structured_or_freetext
from ..schemas import StockProfile

log = logging.getLogger(__name__)


PROMPT_TEMPLATE = """You are building a research dossier for **{symbol}**. This dossier will
prime every future analysis of this ticker by the firm's AI research system.
A well-built dossier is the difference between generic analysis and
institutional-grade tailored analysis.

## What you have

This is the COMPLETE data bundle for this stock plus the outputs from the
first AI analysis run. Use ALL of it to build the most accurate possible
dossier.

### Company profile

```json
{profile_json}
```

### Revenue segments (product breakdown)

```json
{revenue_segments_product_json}
```

### Revenue segments (geographic breakdown)

```json
{revenue_segments_geo_json}
```

### Quarterly income (last 4Q, compact)

```json
{income_compact_json}
```

### Most recent earnings call transcript (truncated)

```text
{earnings_transcript_excerpt}
```

### Analyst price target distribution

```json
{price_target_summary_json}
```

### Recent price target revisions

```json
{price_target_news_json}
```

### Institutional holders (top 10 by share count)

```json
{institutional_holders_json}
```

### What the first AI analysis found

- Fundamental score / summary:
  {fundamental_summary}

- News risk / opportunity:
  {news_summary}

- Bull strongest point:
  {bull_strongest}

- Bear strongest point:
  {bear_strongest}

- Final PM verdict + exit thesis:
  {pm_verdict}

---

## Task

Produce a `StockProfile` matching the schema. Be specific. Cite real data,
real percentages from segments, real numbers from financials. Do NOT
fabricate. If a field genuinely cannot be derived from the data above,
leave it blank — partial truth beats invented truth.

### Field guidance

- **symbol, name, sector, industry, exchange, is_etf, market_cap_usd** —
  copy directly from the profile data.

- **last_reviewed**: today's date, {today}.

- **auto_built**: true (this is being built by the system, not a human).

- **review_cadence_days**: 30 for tier_1 priority, 60 for tier_2, 90 for tier_3.

- **priority**: tier_1 if this is a major position the fund holds, tier_2
  if a watchlist name, tier_3 if speculative/screened. Infer from
  whether the position is held (look at the data — assume tier_2 if uncertain).

- **held**: leave false here; the system tracks this separately via portfolio.

- **position_intent**: "watch" by default; "core" if it's a large mega-cap
  with clear long-term moat, "satellite" if mid-cap or thematic.

- **business_model**: 3-5 sentences. Specific. What does this company
  actually do? Where does revenue come from? What's the moat?

- **revenue_segments**: parse the revenue_segments_product data into
  RevenueSegment objects. `name` is the segment name, `pct_of_revenue` is
  a 0-1 decimal (not a percentage), `description` is 1 line if useful.
  If the data is missing, leave empty.

- **geographic_revenue**: same, from revenue_segments_geo data.

- **key_kpis**: 5-8 metrics SPECIFIC to this company that matter beyond
  generic financials. For NVDA: data_center_revenue_yoy, hbm_allocation.
  For CCJ: uranium_realized_price, contracted_volume. For a bank: NIM,
  deposit_beta. NOT generic things like "revenue growth."

- **bull_thesis_pillars**: 3-5 specific arguments FOR owning this stock.
  Each ThesisPillar has text (one sentence, specific), confidence
  (high/moderate/low), and last_updated = today.

- **bear_thesis_pillars**: 3-5 specific arguments AGAINST owning this
  stock. Same shape. These should be REAL risks visible in the data,
  not generic ("macro uncertainty"). Tie to specific numbers when possible.

- **red_lines**: 3-5 measurable exit conditions. Format:
  - condition: specific testable claim (e.g. "Gross margin falls below
    60% for one quarter")
  - rationale: why this triggers exit
  - measurable: true if a number that's directly in financials, false
    if requires judgment

- **analyst_questions**: stock-specific questions each agent should ask.
  For NVDA fundamental: "Is data center sequential growth turning negative?"
  For PLTR news: "Government bookings growth — accelerating or slowing?"

- **preferred_peers**: 4-6 ticker symbols of direct competitors / closest
  comps. Use these for relative-value framing. Include the major ones in
  the same industry.

- **correlation_notes**: 2-3 sentences on how this stock interacts with
  others in a portfolio (e.g. "Moves 0.85+ with NVDA on AI capex news").

- **recent_management_commentary**: extract 2-4 of the most important
  forward-looking statements from the earnings transcript provided.
  Format: date, speaker (CEO/CFO/etc.), quote (exact words ≤500 chars),
  source (e.g. "Q1 2026 earnings call").

- **historical_lessons**: empty for now (first build — no history yet).

- **pm_notes**: 3-4 sentences of CIO-level context: what's the right way
  to think about owning this stock? When to add? When to trim? What's
  the role in a portfolio (core / satellite / hedge)?

- **long_form_notes**: leave as empty string; will be human-edited later.

Return ONLY valid JSON matching the StockProfile schema.
"""


async def build_profile(
    symbol: str,
    full_state: dict[str, Any],
) -> Optional[StockProfile]:
    """Run the Profile Builder on the final state of an analysis run.

    Returns the new StockProfile or None on failure. Never raises —
    profile-build is best-effort; failure must not break the pipeline.
    """
    try:
        prompt = _build_prompt(symbol, full_state)
        client = claude_opus(max_tokens=6000)
        result = await invoke_structured_or_freetext(client, prompt, StockProfile)
        return result.instance
    except Exception as e:  # noqa: BLE001
        log.warning("ProfileBuilder failed for %s: %s", symbol, e)
        return None


def _build_prompt(symbol: str, state: dict[str, Any]) -> str:
    ctx = state.get("context", {}) or {}
    profile = ctx.get("profile") or {}
    segs_prod = ctx.get("revenue_segments_product") or []
    segs_geo = ctx.get("revenue_segments_geo") or []
    income_q = ctx.get("income_q") or []
    transcript = ctx.get("earnings_transcript") or {}
    pt_summary = ctx.get("price_target_summary") or {}
    pt_news = ctx.get("price_target_news") or []
    inst_holders = ctx.get("institutional_holders") or []

    # Pull agent outputs for the "what we learned" inputs
    fund = state.get("fundamental")
    news = state.get("news")
    bull = state.get("bull")
    bear = state.get("bear")
    pm = state.get("pm")

    return PROMPT_TEMPLATE.format(
        symbol=symbol,
        today=date.today().isoformat(),
        profile_json=_dump(_project_profile_facts(profile)),
        revenue_segments_product_json=_dump(segs_prod),
        revenue_segments_geo_json=_dump(segs_geo),
        income_compact_json=_dump(_project_income_compact(income_q)),
        earnings_transcript_excerpt=_truncate_transcript(transcript, max_chars=8000),
        price_target_summary_json=_dump(pt_summary),
        price_target_news_json=_dump(pt_news[:10] if isinstance(pt_news, list) else []),
        institutional_holders_json=_dump(inst_holders[:10] if isinstance(inst_holders, list) else []),
        fundamental_summary=getattr(fund, "summary", "n/a"),
        news_summary=getattr(news, "summary", "n/a"),
        bull_strongest=getattr(bull, "strongest_point", "n/a"),
        bear_strongest=getattr(bear, "strongest_point", "n/a"),
        pm_verdict=(
            f"{pm.decision} conviction {pm.conviction_score}/10, size {pm.recommended_size_pct}%; "
            f"exit thesis: {pm.exit_thesis}"
            if pm else "n/a"
        ),
    )


def _dump(obj: Any) -> str:
    return json.dumps(obj, indent=2, default=str, ensure_ascii=False)


def _project_profile_facts(p: dict) -> dict:
    if not p:
        return {}
    return {
        "symbol": p.get("symbol"),
        "company_name": p.get("companyName"),
        "sector": p.get("sector"),
        "industry": p.get("industry"),
        "exchange": p.get("exchange"),
        "is_etf": bool(p.get("isEtf")),
        "market_cap_usd": p.get("mktCap") or p.get("marketCap"),
        "ceo": p.get("ceo"),
        "ipo_date": p.get("ipoDate"),
        "country": p.get("country"),
        "description": (p.get("description") or "")[:800],
    }


def _project_income_compact(rows: list[dict]) -> list[dict]:
    out: list[dict] = []
    for r in rows[:4]:
        rev = r.get("revenue")
        out.append({
            "date": r.get("date"),
            "period": r.get("period"),
            "revenue": rev,
            "gross_margin": (
                (r.get("grossProfit") or 0) / rev if rev else None
            ),
            "operating_margin": (
                (r.get("operatingIncome") or 0) / rev if rev else None
            ),
            "net_income": r.get("netIncome"),
            "eps_diluted": r.get("epsDiluted"),
        })
    return out


def _truncate_transcript(transcript: dict, max_chars: int) -> str:
    if not transcript:
        return "(no transcript available)"
    content = transcript.get("content") or transcript.get("transcript") or ""
    if not content:
        return "(transcript field empty)"
    if len(content) <= max_chars:
        return content
    # Keep the head + tail (Q&A often at the tail)
    head = content[: max_chars * 2 // 3]
    tail = content[-(max_chars // 3):]
    return head + "\n\n[... mid-transcript omitted for length ...]\n\n" + tail
