"""Compute earnings dynamics from FMP earnings rows.

Pure computation (no LLM). Produces a small dict the Fundamental analyst
and PM consume in their prompts:
    - beat_miss_streak: last N quarters EPS surprises
    - surprise_pattern: "beating", "missing", "mixed", or "no_data"
    - days_to_next_er: countdown to next earnings
    - iv_crush_risk: True if days_to_er <= 14
    - guidance_pattern: "raising", "cutting", "in-line", "no_data"

Fed in alongside the existing earnings JSON; agents can reason about
"this is the 6th straight beat" vs "guidance has been cut for 3 quarters."
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Optional


def compute(earnings_rows: list[dict], next_earnings_date: Optional[str]) -> dict[str, Any]:
    if not earnings_rows:
        return {"available": False}

    # FMP rows are typically newest first
    rows = sorted(
        earnings_rows,
        key=lambda r: r.get("date") or "",
        reverse=True,
    )

    # 1. Beat/miss streak over the last 8 reported quarters
    streak = []
    for r in rows[:8]:
        eps_actual = _f(r.get("epsActual") or r.get("eps"))
        eps_estimated = _f(r.get("epsEstimated"))
        if eps_actual is None or eps_estimated is None:
            continue
        surprise_pct = None
        if eps_estimated != 0:
            surprise_pct = ((eps_actual - eps_estimated) / abs(eps_estimated)) * 100
        streak.append({
            "date": r.get("date"),
            "eps_actual": eps_actual,
            "eps_estimated": eps_estimated,
            "surprise_pct": round(surprise_pct, 2) if surprise_pct is not None else None,
            "beat": eps_actual > eps_estimated,
        })

    beats = sum(1 for s in streak if s["beat"])
    n = len(streak) or 1
    beat_rate = beats / n

    if beat_rate >= 0.75:
        surprise_pattern = "beating"
    elif beat_rate <= 0.25:
        surprise_pattern = "missing"
    elif streak:
        surprise_pattern = "mixed"
    else:
        surprise_pattern = "no_data"

    # 2. Days to next earnings
    days_to_er: Optional[int] = None
    if next_earnings_date:
        try:
            ne = date.fromisoformat(next_earnings_date[:10])
            days_to_er = (ne - date.today()).days
        except (ValueError, TypeError):
            pass

    # 3. IV crush risk: earnings within 14 days
    iv_crush_risk = days_to_er is not None and 0 <= days_to_er <= 14

    return {
        "available": True,
        "beat_miss_streak": streak[:8],
        "beat_rate_pct": round(beat_rate * 100, 1),
        "surprise_pattern": surprise_pattern,
        "days_to_next_er": days_to_er,
        "iv_crush_risk": iv_crush_risk,
        "post_er_window": days_to_er is not None and -7 <= days_to_er < 0,
    }


def format_for_prompt(dynamics: dict[str, Any]) -> str:
    """Pretty render for injection into Fundamental + PM prompts."""
    if not dynamics or not dynamics.get("available"):
        return "(earnings dynamics unavailable)"

    lines = [
        f"- Surprise pattern: **{dynamics['surprise_pattern']}** "
        f"({dynamics['beat_rate_pct']}% beat rate over {len(dynamics['beat_miss_streak'])} quarters)",
    ]
    if dynamics.get("days_to_next_er") is not None:
        d = dynamics["days_to_next_er"]
        if d >= 0:
            lines.append(f"- Next earnings in **{d} days**" +
                          (" ⚠ IV-crush risk if you enter now" if dynamics.get("iv_crush_risk") else ""))
        else:
            lines.append(f"- Just reported {abs(d)} days ago" +
                          (" — post-ER drift window" if dynamics.get("post_er_window") else ""))

    if dynamics.get("beat_miss_streak"):
        lines.append("- Recent prints:")
        for s in dynamics["beat_miss_streak"][:5]:
            tag = "BEAT" if s["beat"] else "MISS"
            sp = f"{s['surprise_pct']:+.1f}%" if s.get("surprise_pct") is not None else "?"
            lines.append(f"    · {s['date']}: {tag} {sp} "
                         f"(${s['eps_actual']:.2f} vs ${s['eps_estimated']:.2f} est)")

    return "\n".join(lines)


def _f(v) -> Optional[float]:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None
