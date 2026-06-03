"""Agent 14 — Weekly Performance Reviewer (Claude Sonnet).

Runs every Friday after market close. Pulls a week's worth of decisions
and closed positions, scores accuracy by sector + by conviction range,
distills the top 3-5 lessons, and writes a client-facing weekly digest.
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta
from typing import Any

from ...db.schema import get_connection
from ..llm.claude import claude_sonnet
from ..llm.structured import invoke_structured_or_freetext
from ..schemas import WeeklyReviewReport

log = logging.getLogger(__name__)


PROMPT_TEMPLATE = """You are the **Weekly Performance Reviewer** for a $2,000,000 long-only US
equity fund. Every Friday after the close you run a structured post-mortem
on the week's activity. The output goes to the client and into the system's
memory.

You are calibrated: identify real patterns, not anecdotes. Be willing to
hand out low grades when the process underperformed; be willing to praise
discipline when bad markets were navigated well.

---

## Week being reviewed

- **Window:** {week_start} → {week_end}

## Decisions made this week

```json
{decisions_json}
```

## Positions closed this week (with realized P&L)

```json
{closed_positions_json}
```

## Open positions at end of week

```json
{open_positions_json}
```

## Existing memory (recent lessons)

{lessons_block}

---

## Task

Produce a `WeeklyReviewReport` matching the schema.

### weekly_grade — assign one of A/B/C/D/F based on:
- Was the process applied consistently? (rules respected, RM heeded, sizing right)
- Did high-conviction decisions perform better than low-conviction ones?
- Were any preventable losses taken? (entering near earnings, sector overconcentration)
- Did the team show discipline in bad regimes?

A: Excellent application of process AND/OR strong returns from disciplined trades
B: Process applied well, mixed outcomes
C: Some process drift OR moderate process with poor outcomes
D: Multiple process violations
F: Reckless behavior or systemic failure

### accuracy_by_sector
For each sector that had ≥1 closed trade this week, emit one bucket with
n_trades, win_rate_pct (% with positive P&L), avg_pnl_pct.

### accuracy_by_conviction
Bucket closed trades by their original PM conviction_score:
- "high (8-10)", "moderate (5-7)", "low (1-4)"
For each non-empty bucket, emit n_trades, win_rate_pct, avg_pnl_pct.

### top_lessons
3-5 specific lessons distilled from this week. One sentence each. These
will feed the memory store and influence future PM prompts. Be calibrated.

### process_observations
3-5 short paragraphs describing:
- What went well in our process this week (specific examples)
- What broke or drifted (specific examples)
- Whether conviction predicted P&L (look at accuracy_by_conviction)
- Recommendations for next week's posture

### telegram_weekly_report
Client-facing summary, ~12-18 lines, plain English:
- Headline: grade + one-line summary
- This week's activity (entries, exits, P&L)
- What worked, what didn't
- Notable lessons
- Outlook for next week

Return ONLY valid JSON matching the WeeklyReviewReport schema.
"""


async def run_weekly_review(
    week_start: date, week_end: date,
) -> WeeklyReviewReport | None:
    """Build the week's review. Returns the report or None on failure."""
    decisions = _load_decisions(week_start, week_end)
    closed = _load_closed(week_start, week_end)
    opens = _load_open()
    lessons_block = _load_lessons_block()

    if not decisions and not closed:
        log.info("weekly_reviewer: no activity to review for %s–%s",
                  week_start, week_end)
        return None

    prompt = PROMPT_TEMPLATE.format(
        week_start=week_start.isoformat(),
        week_end=week_end.isoformat(),
        decisions_json=_dump(decisions),
        closed_positions_json=_dump(closed),
        open_positions_json=_dump(opens),
        lessons_block=lessons_block or "(no prior lessons yet)",
    )

    client = claude_sonnet(temperature=0.2, max_tokens=6000)
    try:
        result = await invoke_structured_or_freetext(
            client, prompt, WeeklyReviewReport,
        )
        return result.instance
    except Exception as e:  # noqa: BLE001
        log.exception("weekly_reviewer failed: %s", e)
        return None


# --------------------------------------------------------------------------- #
# Disk + DB readers
# --------------------------------------------------------------------------- #


def _load_decisions(start: date, end: date) -> list[dict[str, Any]]:
    """All PM decisions for the week, from ai_research/*/{date}/_raw.json."""
    from pathlib import Path
    from ..config import AI_RESEARCH_DIR

    out: list[dict[str, Any]] = []
    if not AI_RESEARCH_DIR.exists():
        return out
    for sym_dir in AI_RESEARCH_DIR.iterdir():
        if not sym_dir.is_dir() or sym_dir.name.startswith("_"):
            continue
        for date_dir in sym_dir.iterdir():
            if not date_dir.is_dir():
                continue
            try:
                d = date.fromisoformat(date_dir.name)
            except ValueError:
                continue
            if not (start <= d <= end):
                continue
            raw_path = date_dir / "_raw.json"
            if not raw_path.exists():
                continue
            try:
                raw = json.loads(raw_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            pm = raw.get("pm") or {}
            if not pm:
                continue
            out.append({
                "symbol": sym_dir.name,
                "date": date_dir.name,
                "source": raw.get("source"),
                "decision": pm.get("decision"),
                "conviction": pm.get("conviction_score"),
                "size_pct": pm.get("recommended_size_pct"),
                "exit_thesis": pm.get("exit_thesis"),
            })
    out.sort(key=lambda r: (r["date"], r["symbol"]))
    return out


def _load_closed(start: date, end: date) -> list[dict[str, Any]]:
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT id, symbol, entry_date, entry_price, units,
                   exit_date, exit_price, exit_reason,
                   final_pnl_usd, final_pnl_pct, days_held,
                   decision_verdict, decision_conviction, decision_size_pct
            FROM virtual_positions
            WHERE status='closed' AND exit_date BETWEEN ? AND ?
            ORDER BY exit_date ASC, id ASC
            """,
            (start.isoformat(), end.isoformat()),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def _load_open() -> list[dict[str, Any]]:
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT id, symbol, entry_date, entry_price, units,
                   current_price, current_pnl_pct,
                   days_held, decision_verdict, decision_conviction,
                   decision_size_pct
            FROM virtual_positions
            WHERE status='open'
            ORDER BY entry_date ASC, id ASC
            """,
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def _load_lessons_block() -> str:
    from ..memory import format_lessons_for_prompt
    return format_lessons_for_prompt(symbol=None, limit=15)


def _dump(obj: Any) -> str:
    return json.dumps(obj, indent=2, default=str, ensure_ascii=False)
