"""Per-stock profile loader + writer + refresh policy.

Profiles live at `watchlist/{SYMBOL}.md` as YAML frontmatter + markdown body.

Refresh policy (called from pipeline.py after each analysis):

    1. Cadence trigger — profile's `last_reviewed` is older than its
       `review_cadence_days` (default 30). Routine staleness refresh.
    2. Event trigger — material new information landed since last review:
         a. Earnings posted (FMP earnings calendar > last_reviewed)
         b. PM decision flipped vs prior analysis (e.g. APPROVE → REJECT,
            or REJECT → APPROVE) — regime shift.
       Either fires an out-of-cycle rebuild.

The rebuild preserves user-edited fields (historical_lessons, pm_notes,
long_form_notes) and refreshes the LLM-generated fields (pillars, KPIs,
red lines, commentary).

Format:
    ---
    symbol: NVDA
    name: NVIDIA Corporation
    sector: Technology
    ...all the structured fields from StockProfile schema...
    ---

    # NVDA — Long-form Research Notes

    Free-form markdown content here. Becomes `long_form_notes`.

The loader:
    - Parses YAML frontmatter into a dict
    - Validates it against StockProfile pydantic schema
    - Reads body as long_form_notes
    - Returns the validated StockProfile object

The writer does the inverse — model_dump() to YAML frontmatter + body.
"""
from __future__ import annotations

import logging
import re
from datetime import date
from pathlib import Path
from typing import Optional

import yaml
from pydantic import ValidationError

from ..config import WATCHLIST_PROFILE_DIR
from .schemas import StockProfile

log = logging.getLogger(__name__)

# Matches a YAML frontmatter block at the start of a markdown file.
_FRONTMATTER_RE = re.compile(
    r"^---\s*\n(?P<yaml>.*?)\n---\s*\n?(?P<body>.*)$",
    re.DOTALL,
)


# --------------------------------------------------------------------------- #
# File paths
# --------------------------------------------------------------------------- #


def profile_path(symbol: str) -> Path:
    return WATCHLIST_PROFILE_DIR / f"{symbol.upper()}.md"


def profile_exists(symbol: str) -> bool:
    return profile_path(symbol).exists()


def list_profile_symbols() -> list[str]:
    """All ticker symbols that currently have a profile on disk."""
    if not WATCHLIST_PROFILE_DIR.exists():
        return []
    return sorted(
        p.stem.upper()
        for p in WATCHLIST_PROFILE_DIR.glob("*.md")
        if not p.stem.startswith("_")
    )


# --------------------------------------------------------------------------- #
# Read
# --------------------------------------------------------------------------- #


def load_profile(symbol: str) -> Optional[StockProfile]:
    """Load and validate a profile from disk. Returns None if missing/corrupt."""
    path = profile_path(symbol)
    if not path.exists():
        return None
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as e:
        log.warning("profiles: could not read %s: %s", path, e)
        return None

    fields, body = _parse_frontmatter(text)
    if fields is None:
        log.warning("profiles: %s has no YAML frontmatter", path)
        return None

    # Body becomes long_form_notes if not explicitly set in the frontmatter
    if body and "long_form_notes" not in fields:
        fields["long_form_notes"] = body.strip()

    # Defensive: enforce symbol matches filename
    if not fields.get("symbol"):
        fields["symbol"] = symbol.upper()

    try:
        return StockProfile.model_validate(fields)
    except ValidationError as e:
        log.warning("profiles: %s failed validation: %s", path, e)
        return None


def _parse_frontmatter(text: str) -> tuple[Optional[dict], str]:
    """Split '---YAML---BODY' into (yaml_dict, body_text)."""
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return None, text
    try:
        yaml_dict = yaml.safe_load(m.group("yaml")) or {}
    except yaml.YAMLError as e:
        log.warning("profiles: YAML parse failed: %s", e)
        return None, text
    if not isinstance(yaml_dict, dict):
        return None, text
    return yaml_dict, m.group("body") or ""


# --------------------------------------------------------------------------- #
# Write
# --------------------------------------------------------------------------- #


def save_profile(profile: StockProfile) -> Path:
    """Persist a StockProfile to watchlist/{symbol}.md.

    Frontmatter holds the structured fields; long_form_notes goes in the body.
    """
    path = profile_path(profile.symbol)
    path.parent.mkdir(parents=True, exist_ok=True)

    data = profile.model_dump(mode="json")
    # Pop long_form_notes — it gets written as the markdown body, not in YAML
    body = (data.pop("long_form_notes", "") or "").strip()

    yaml_block = yaml.safe_dump(data, sort_keys=False, allow_unicode=True, width=88)
    text = f"---\n{yaml_block}---\n\n"
    if body:
        text += body
        if not body.endswith("\n"):
            text += "\n"
    else:
        text += f"# {profile.symbol} — Research Notes\n\n_(no long-form notes yet — edit this section to add narrative analysis)_\n"

    # Atomic write
    import os
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)
    return path


# --------------------------------------------------------------------------- #
# Helpers for prompt injection
# --------------------------------------------------------------------------- #


# --------------------------------------------------------------------------- #
# Refresh policy
# --------------------------------------------------------------------------- #


def should_refresh_profile(
    profile: StockProfile,
    state: dict,
) -> tuple[bool, str]:
    """Decide whether an existing profile is due for a rebuild.

    Returns (refresh_flag, reason). reason is a short human-readable string
    that the pipeline logs as the trigger so the audit trail is clear.

    Inputs from `state` (filled by prefetch_pipeline_context):
      - state["context"]["earnings"]  — FMP earnings rows (most recent at [0])
      - state.get("pm")               — current run's PMDecision
      - state["context"].get("previous_pm_decision")  — last run's decision
    """
    today = date.today()

    # 1) Cadence trigger ------------------------------------------------------
    cadence_days = profile.review_cadence_days or 30
    last_reviewed = profile.last_reviewed
    if last_reviewed is None:
        return True, "cadence: no last_reviewed on profile"
    if isinstance(last_reviewed, str):
        try:
            last_reviewed = date.fromisoformat(last_reviewed)
        except ValueError:
            return True, "cadence: unparseable last_reviewed"

    age_days = (today - last_reviewed).days
    if age_days >= cadence_days:
        return True, f"cadence: profile is {age_days}d old (cadence={cadence_days}d)"

    # 2a) Event trigger — earnings posted since last review -------------------
    earnings = (state.get("context") or {}).get("earnings") or []
    latest_eps_date = _latest_actual_earnings_date(earnings)
    if latest_eps_date and latest_eps_date > last_reviewed:
        return (
            True,
            f"event: earnings posted {latest_eps_date} after last review {last_reviewed}",
        )

    # 2b) Event trigger — PM decision flipped vs prior run --------------------
    pm = state.get("pm")
    prior = (state.get("context") or {}).get("previous_pm_decision")
    if pm is not None and prior:
        current = getattr(pm, "decision", None)
        if current and prior != current:
            # Flip is meaningful: APPROVE/RESIZE ↔ REJECT/HOLD changes the thesis
            return (
                True,
                f"event: PM decision flipped {prior} → {current}",
            )

    return False, f"fresh ({age_days}d old, cadence={cadence_days}d)"


def _latest_actual_earnings_date(earnings_rows: list) -> Optional[date]:
    """Pull the most recent reported (actual EPS present) earnings date.

    Accepts FMP-style rows with `date` + `epsActual` fields.
    """
    if not earnings_rows:
        return None
    latest: Optional[date] = None
    for row in earnings_rows:
        if not isinstance(row, dict):
            continue
        # Only count rows with an actual reported EPS (not future estimates)
        if row.get("epsActual") is None and row.get("eps") is None:
            continue
        ds = row.get("date") or row.get("fiscalDateEnding")
        if not ds:
            continue
        try:
            d = date.fromisoformat(str(ds)[:10])
        except ValueError:
            continue
        if latest is None or d > latest:
            latest = d
    return latest


def _preserve_user_edits(
    new_profile: StockProfile,
    old_profile: StockProfile,
) -> StockProfile:
    """Carry forward fields the user (not the LLM) is meant to own."""
    # historical_lessons accumulate across rebuilds — never overwrite,
    # just append anything new the LLM produced.
    seen = set(old_profile.historical_lessons or [])
    merged_lessons = list(old_profile.historical_lessons or [])
    for lesson in new_profile.historical_lessons or []:
        if lesson not in seen:
            merged_lessons.append(lesson)
            seen.add(lesson)
    new_profile.historical_lessons = merged_lessons

    # pm_notes and long_form_notes are user-editable scratchpads — preserve.
    if old_profile.pm_notes and not new_profile.pm_notes:
        new_profile.pm_notes = old_profile.pm_notes
    if old_profile.long_form_notes and not new_profile.long_form_notes:
        new_profile.long_form_notes = old_profile.long_form_notes

    # Held / position_intent / priority are user-managed (the LLM may guess
    # them on first build, but on rebuild we trust the existing values).
    new_profile.held = old_profile.held
    new_profile.position_intent = old_profile.position_intent
    new_profile.priority = old_profile.priority
    new_profile.review_cadence_days = old_profile.review_cadence_days

    # Stamp the refresh date
    new_profile.last_reviewed = date.today()
    new_profile.auto_built = True
    return new_profile


def profile_block_for_agent(
    profile: Optional[StockProfile], agent: str,
) -> str:
    """Render the slice of the profile relevant to one agent's prompt.

    `agent` is one of: "fundamental", "news", "technical", "bull", "bear", "pm".
    Returns a plain-text block ready to drop into a prompt. Returns a brief
    "(no profile)" marker if profile is None.
    """
    if profile is None:
        return ("(no per-stock profile exists yet for this ticker — this is "
                "the FIRST analysis; one will be auto-built after this run "
                "completes so future analyses can use it)")

    parts: list[str] = [
        f"### Profile facts for {profile.symbol} ({profile.name})",
        f"- Sector: {profile.sector}" + (f", Industry: {profile.industry}" if profile.industry else ""),
        f"- Priority tier: {profile.priority}, position intent: {profile.position_intent}",
        f"- Last reviewed: {profile.last_reviewed} (auto_built={profile.auto_built})",
    ]
    if profile.business_model:
        parts += ["", "**Business model:**", profile.business_model.strip()]

    # Per-agent payload
    if agent == "fundamental":
        if profile.revenue_segments:
            parts += ["", "**Revenue by product segment** (anchor your analysis here, not generic):"]
            for s in profile.revenue_segments:
                pct = f"{s.pct_of_revenue*100:.1f}%" if s.pct_of_revenue is not None else "?"
                parts.append(f"- {s.name}: {pct}" + (f" — {s.description}" if s.description else ""))
        if profile.geographic_revenue:
            parts += ["", "**Revenue by geography:**"]
            for g in profile.geographic_revenue:
                pct = f"{g.pct_of_revenue*100:.1f}%" if g.pct_of_revenue is not None else "?"
                parts.append(f"- {g.region}: {pct}")
        if profile.key_kpis:
            parts += ["", "**Stock-specific KPIs to track this quarter:**"]
            parts += [f"- {k}" for k in profile.key_kpis]
        if profile.analyst_questions.fundamental:
            parts += ["", "**Specific questions to answer this run:**"]
            parts += [f"- {q}" for q in profile.analyst_questions.fundamental]

    elif agent == "news":
        if profile.recent_management_commentary:
            parts += ["", "**Recent management commentary on record (use as context):**"]
            for c in profile.recent_management_commentary[:5]:
                parts.append(f'- {c.date} [{c.speaker}] "{c.quote}" ({c.source})')
        if profile.analyst_questions.news:
            parts += ["", "**Specific questions to answer this run:**"]
            parts += [f"- {q}" for q in profile.analyst_questions.news]

    elif agent == "technical":
        if profile.preferred_peers:
            parts += ["", f"**Preferred peer set:** {', '.join(profile.preferred_peers)}"]
        if profile.analyst_questions.technical:
            parts += ["", "**Specific questions to answer this run:**"]
            parts += [f"- {q}" for q in profile.analyst_questions.technical]

    elif agent == "bull":
        if profile.bull_thesis_pillars:
            parts += ["", "**Existing bull pillars (engage with these — confirm or challenge):**"]
            for p in profile.bull_thesis_pillars:
                parts.append(f"- [{p.confidence}] {p.text}")

    elif agent == "bear":
        if profile.bear_thesis_pillars:
            parts += ["", "**Existing bear pillars (engage with these — confirm or challenge):**"]
            for p in profile.bear_thesis_pillars:
                parts.append(f"- {p.text}")
        if profile.red_lines:
            parts += ["", "**Hard exit conditions already on the dossier:**"]
            for r in profile.red_lines:
                parts.append(f"- {r.condition} — _why:_ {r.rationale}")

    elif agent == "pm":
        if profile.pm_notes:
            parts += ["", "**PM-level notes for this name:**", profile.pm_notes.strip()]
        if profile.red_lines:
            parts += ["", "**Hard exit conditions for this name:**"]
            for r in profile.red_lines:
                parts.append(f"- {r.condition} — _why:_ {r.rationale}")
        if profile.historical_lessons:
            parts += ["", "**Historical lessons from owning this name:**"]
            parts += [f"- {l}" for l in profile.historical_lessons[:8]]

    return "\n".join(parts)
