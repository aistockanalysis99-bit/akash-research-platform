"""Phase 6 — the season report: everything the options program did, in one
markdown document. This is the quarterly deliverable the year plan promises:
scans, boards, the league, the evidence base, open exposure, slippage, and
the honest caveats — generated from the same tables the pages read, so the
report can't drift from the product.
"""
from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any

from ...db.schema import get_connection

log = logging.getLogger(__name__)


def _table(rows: list[dict[str, Any]], cols: list[tuple[str, str]]) -> str:
    if not rows:
        return "_none yet_\n"
    head = "| " + " | ".join(h for h, _ in cols) + " |"
    sep = "|" + "|".join("---" for _ in cols) + "|"
    body = []
    for r in rows:
        body.append("| " + " | ".join(str(r.get(k, "—") if r.get(k) is not None
                                          else "—") for _, k in cols) + " |")
    return "\n".join([head, sep] + body) + "\n"


def generate_season_report() -> dict[str, Any]:
    from .report_card import aggregate_report_card
    from .store import league_record, list_positions, stats as straddle_stats
    from .structures import (family_stats, greeks_rollup, list_structures,
                             slippage_report)
    from .wheel import list_wheels, wheel_league_row

    conn = get_connection()
    try:
        scan_days = conn.execute(
            "SELECT COUNT(DISTINCT scan_date) AS n, MIN(scan_date) AS a, "
            "MAX(scan_date) AS b FROM options_candidates").fetchone()
        cand_total = conn.execute(
            "SELECT COUNT(*) AS n FROM options_candidates").fetchone()["n"]
        qual_total = conn.execute(
            "SELECT COUNT(*) AS n FROM options_candidates "
            "WHERE qualified=1").fetchone()["n"]
        board_runs = conn.execute(
            "SELECT COUNT(*) AS n FROM options_board_runs").fetchone()["n"]
    finally:
        conn.close()

    league = family_stats()
    s = league_record()
    if s:
        league.setdefault("long_straddle", s)
    w = wheel_league_row()
    if w:
        league["wheel"] = w
    rc = aggregate_report_card()
    slip = slippage_report()
    greeks = greeks_rollup()
    open_straddles = list_positions("open")
    open_structs = list_structures("open")
    wheels = list_wheels(active_only=True)

    today = date.today().isoformat()
    lines = [
        f"# Options Program — Season Report ({today})",
        "",
        "_Generated from the live database. Every number is real; paper and "
        "real results are never mixed without labels._",
        "",
        "## The funnel",
        f"- Scan days: **{scan_days['n']}** ({scan_days['a']} → {scan_days['b']})",
        f"- Candidate evaluations: **{cand_total:,}** · qualified: "
        f"**{qual_total}** — the discipline is the product",
        f"- Strategy Board runs: **{board_runs}**",
        "",
        "## The league (realized, paper)",
        _table(
            [{"family": k.replace("_", " "), **v} for k, v in league.items()],
            [("Family", "family"), ("Closed", "trades"),
             ("Win %", "win_rate_pct"), ("Avg on risk %", "avg_return_on_risk_pct"),
             ("Total $", "total_pnl_usd"), ("Worst $", "worst_trade_usd")]),
        "## The evidence base (Layer 2)",
        f"- Stocks covered: **{rc['symbols_covered']}** · real historical "
        f"events priced: **{rc['events_priced']:,}**",
        f"- Qualifying events: **{rc['qualifying_events']}**"
        + (f" · win rate **{rc['qualifying_win_rate_pct']}%** · avg "
           f"**{rc['qualifying_avg_pnl_pct']:+.1f}%**"
           if rc.get("qualifying_win_rate_pct") is not None else ""),
        f"- Market-wide implied vs realized move: "
        f"**{rc.get('avg_implied_vs_actual') or '—'}×** — the structural "
        f"overpricing the two-sided book is built on",
        "",
        "## Open exposure (paper)",
        f"- Straddles: **{len(open_straddles)}** · multi-leg structures: "
        f"**{len(open_structs)}** · active wheels: **{len(wheels)}**",
        f"- Book Greeks (marked structures): net delta "
        f"**{greeks['totals']['delta']}** share-equivalents · theta "
        f"**{greeks['totals']['theta']}$/day** · vega "
        f"**{greeks['totals']['vega']}$/IV-pt**",
        "",
        "## Execution quality",
        f"- Real fills recorded: **{slip['fills_recorded']}** · median "
        f"slippage: **{slip['median_slippage_pct'] or '—'}%** (upgrade "
        f"trigger: {slip['upgrade_trigger_pct']}%)",
        f"- Live-data upgrade recommended: "
        f"**{'YES' if slip['upgrade_recommended'] else 'not yet'}**",
        "",
        "## Standing caveats",
        "- Quotes ~15-min delayed; every card says verify in broker.",
        "- Everything suggest-only; every real trade was placed by Akash.",
        "- Defined risk only; the gate refuses uncovered short exposure.",
        "",
        f"_Generated {datetime.utcnow().isoformat()}Z_",
    ]
    md = "\n".join(lines)
    return {"markdown": md, "generated_at": datetime.utcnow().isoformat(),
            "league_families": len(league),
            "events_priced": rc["events_priced"]}
