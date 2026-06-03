"""Reflector — writes a short lesson from a closed paper position.

Runs in a background thread when a position closes (or via the "Reflect on
closed positions" button). Outputs a `Reflection` that goes into the lessons
table; future PM prompts get to read it.

Cheap LLM call (Claude Sonnet) — typically <$0.005 per closed trade.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Optional

from ..llm.claude import claude_sonnet
from ..llm.structured import invoke_structured_or_freetext
from ..schemas import Reflection

log = logging.getLogger(__name__)


PROMPT_TEMPLATE = """You are the **Reflector** for a $2,000,000 long-only US equity fund. A
paper position just closed; your job is to write a single short lesson
that will be injected into future PM prompts to inform similar decisions.

Be specific, calibrated, and brutally honest. The fund gets better only
if we name patterns — not if we hand-wave.

---

## Position that just closed

- **Symbol:** {symbol}
- **Entry:** {entry_date} @ ${entry_price}, {units} units
- **Exit:** {exit_date} @ ${exit_price}, reason = `{exit_reason}`
- **Held:** {days_held} days
- **Realized P&L:** {pnl_pct:+.2f}% (${pnl_usd:+,.0f})

## Original PM decision when entering

- **Verdict:** {decision_verdict}
- **Conviction at entry:** {decision_conviction}/10
- **Size taken:** {decision_size_pct}%

## Original full PM rationale (if available)

```json
{pm_rationale_json}
```

---

## Task

Produce a `Reflection` JSON matching the schema.

### category — pick the closest:
- `thesis_held` — entry thesis was correct, profit confirms it
- `thesis_broke` — entry thesis turned out wrong, regardless of P&L
- `entry_timing` — right name, wrong moment (e.g. bought peak, sold bottom)
- `exit_timing` — right thesis but exit was premature or too late
- `sector_call` — got the sector right/wrong (rotation, leadership)
- `macro_call` — macro regime was the dominant driver, not stock-specific
- `earnings_event` — earnings catalyst dominated the move
- `valuation` — multiple was decisive
- `size_judgment` — sizing decision (APPROVE vs RESIZE) was right/wrong
- `other` — only if none above fit

### lesson_text — 2-4 sentences, plain English

Write it as if the next CIO will read it before making a similar decision.
- Be calibrated (don't over-claim from one data point)
- Use specific numbers from the position
- State the pattern, not just the outcome
- One concrete actionable rule if you can identify one

Examples of good lessons:
- "MSFT exited at +12% on stop after 18 days when sector rotation hit XLK. Tech RESIZE positions during BULL_TRENDING regimes worked, but stops triggered on routine 8% sector pullbacks — consider trailing 12% instead of 10% for half-size tech trades."
- "TSLA closed at -7.2% in 4 days, stop hit. Bear conviction 8 vs Bull 4 at entry should have been REJECT not RESIZE — when bear conviction exceeds bull by >2, prefer skipping over half-sizing."

Return ONLY valid JSON matching the Reflection schema.
"""


async def reflect_on_position(position: dict[str, Any]) -> Optional[Reflection]:
    """Run the Reflector LLM on one closed position. Returns the Reflection
    or None if anything goes wrong (Reflector is best-effort).
    """
    try:
        client = claude_sonnet(temperature=0.3)
        prompt = _build_prompt(position)
        result = await invoke_structured_or_freetext(client, prompt, Reflection)
        return result.instance
    except Exception as e:  # noqa: BLE001
        log.warning("reflector failed for position %s: %s",
                     position.get("id"), e)
        return None


def _build_prompt(p: dict[str, Any]) -> str:
    # The PM rationale lives on disk in 06_pm_verdict.md / _raw.json — try to
    # pull a compact slice if available.
    rationale = _load_pm_rationale(p.get("symbol"), p.get("entry_date"))

    return PROMPT_TEMPLATE.format(
        symbol=p.get("symbol") or "?",
        entry_date=p.get("entry_date") or "?",
        entry_price=p.get("entry_price") or 0,
        units=p.get("units") or 0,
        exit_date=p.get("exit_date") or "?",
        exit_price=p.get("exit_price") or 0,
        exit_reason=p.get("exit_reason") or "?",
        days_held=p.get("days_held") or 0,
        pnl_pct=float(p.get("final_pnl_pct") or 0.0),
        pnl_usd=float(p.get("final_pnl_usd") or 0.0),
        decision_verdict=p.get("decision_verdict") or "?",
        decision_conviction=p.get("decision_conviction") or "?",
        decision_size_pct=p.get("decision_size_pct") or "?",
        pm_rationale_json=json.dumps(rationale, indent=2, default=str)[:3000],
    )


def _load_pm_rationale(symbol: Optional[str], date_iso: Optional[str]) -> dict:
    """Best-effort load of the PM rationale + exit thesis from disk."""
    if not symbol or not date_iso:
        return {}
    try:
        from ..file_store import FileStore
        fs = FileStore()
        folder = fs.folder(symbol, date_iso)
        raw_path = folder / "_raw.json"
        if not raw_path.exists():
            return {}
        raw = json.loads(raw_path.read_text(encoding="utf-8"))
        pm = raw.get("pm") or {}
        return {
            "decision": pm.get("decision"),
            "conviction_score": pm.get("conviction_score"),
            "recommended_size_pct": pm.get("recommended_size_pct"),
            "investment_rationale": pm.get("investment_rationale"),
            "exit_thesis": pm.get("exit_thesis"),
        }
    except Exception:  # noqa: BLE001
        return {}
