"""Agent 4b — Institutional Flow Analyst (Gemini Flash).

Consumes the 4 Unusual Whales data slots from prefetch:
    - uw_inst_ownership   (13F top holders + units_changed Q-o-Q)
    - uw_darkpool         (recent dark-pool prints)
    - uw_options_flow     (UOA flow alerts)
    - uw_options_volume   (daily call/put volume + premium)
    - uw_insider          (daily insider $ buy/sell totals)

Produces an InstitutionalFlowReport — a single structured object that
Bull, Bear, and the PM read so smart-money positioning explicitly shapes
the verdict instead of being a free-text afterthought.
"""
from __future__ import annotations

import json
from typing import Any

from ..renderers.institutional_flow import render as render_md
from ..schemas import InstitutionalFlowReport
from ..state import SignalState
from .base import Agent


class InstitutionalFlowAgent(Agent):
    NAME = "institutional_flow"
    LLM_TIER = "flash"
    REQUIRES_DATA = [
        "uw_inst_ownership", "uw_darkpool",
        "uw_options_flow", "uw_options_volume", "uw_insider",
    ]
    OUTPUT_SCHEMA = InstitutionalFlowReport
    STAGE = "institutional_flow"
    PROMPT_FILE = "institutional_flow.md"

    def build_prompt(self, state: SignalState) -> str:
        template = self.load_prompt_template()
        ctx = state.get("context", {})

        return template.format(
            symbol=state["symbol"],
            as_of_date=state["signal_date"],
            inst_ownership_json=_dump(_project_holders(ctx.get("uw_inst_ownership") or [])),
            darkpool_json=_dump(_project_darkpool(ctx.get("uw_darkpool") or [])),
            options_flow_json=_dump(_project_flow(ctx.get("uw_options_flow") or [])),
            options_volume_json=_dump(_project_volume(ctx.get("uw_options_volume") or [])),
            insider_json=_dump(_project_insider(ctx.get("uw_insider") or [])),
        )

    def render(self, output: InstitutionalFlowReport) -> str:
        return render_md(output)


# --------------------------------------------------------------------------- #
# Projections — keep the LLM prompt small. Each function picks the rows and
# fields most useful for the analyst and drops the rest.
# --------------------------------------------------------------------------- #


def _dump(obj: Any) -> str:
    return json.dumps(obj, indent=2, default=str, ensure_ascii=False)


def _project_holders(rows: list[dict]) -> list[dict]:
    """Top-30 institutional holders with Q-o-Q delta computed."""
    out = []
    for r in rows[:30]:
        units = _f(r.get("units"))
        units_changed = _f(r.get("units_changed"))
        prior = (units - units_changed) if (units is not None and units_changed is not None) else None
        pct_change = None
        if prior and prior > 0 and units_changed is not None:
            pct_change = round((units_changed / prior) * 100, 2)
        out.append({
            "name": r.get("name") or r.get("short_name"),
            "units": units,
            "units_changed": units_changed,
            "pct_change_qoq": pct_change,
            "value_usd": _f(r.get("value")),
            "avg_price": r.get("avg_price"),
            "first_buy": r.get("first_buy"),
            "filing_date": r.get("filing_date"),
            "report_date": r.get("report_date"),
            "is_hedge_fund": r.get("is_hedge_fund"),
            "historical_units_last_4q": (r.get("historical_units") or [])[:4],
        })
    return out


def _project_darkpool(rows: list[dict]) -> dict:
    """Aggregate dark pool into a small summary, not 200 row dump."""
    if not rows:
        return {"available": False}
    # 30 most recent prints projected verbatim — newest first
    recent = [
        {
            "executed_at": r.get("executed_at"),
            "size": _f(r.get("size")),
            "price": _f(r.get("price")),
            "premium": _f(r.get("premium")),
            "nbbo_bid": _f(r.get("nbbo_bid")),
            "nbbo_ask": _f(r.get("nbbo_ask")),
            "extended_hours": bool(r.get("ext_hour_sold_codes")),
        }
        for r in rows[:30]
    ]
    # Aggregate stats over the full window
    total_size = sum(_f(r.get("size")) or 0 for r in rows)
    total_premium = sum(_f(r.get("premium")) or 0 for r in rows)
    return {
        "available": True,
        "row_count": len(rows),
        "total_size_shares": total_size,
        "total_premium_usd": total_premium,
        "recent_prints": recent,
    }


def _project_flow(rows: list[dict]) -> list[dict]:
    """UOA alerts — top 30 by total_premium."""
    sorted_rows = sorted(
        rows,
        key=lambda r: float(r.get("total_premium") or 0),
        reverse=True,
    )
    out = []
    for r in sorted_rows[:30]:
        out.append({
            "created_at": r.get("created_at"),
            "type": r.get("type"),
            "strike": r.get("strike"),
            "expiry": r.get("expiry"),
            "underlying_price": r.get("underlying_price"),
            "volume": _f(r.get("volume")),
            "open_interest": _f(r.get("open_interest")),
            "total_premium": _f(r.get("total_premium")),
            "trade_count": _f(r.get("trade_count")),
            "iv_end": r.get("iv_end"),
        })
    return out


def _project_volume(rows: list[dict]) -> list[dict]:
    """Daily call/put volume — last 20 sessions."""
    out = []
    for r in (rows or [])[:20]:
        out.append({
            "date": r.get("date"),
            "call_volume": _f(r.get("call_volume")),
            "put_volume": _f(r.get("put_volume")),
            "net_call_premium": _f(r.get("net_call_premium")),
            "net_put_premium": _f(r.get("net_put_premium")),
        })
    return out


def _project_insider(rows: list[dict]) -> list[dict]:
    """Daily insider $ net flow — last 30 filings."""
    out = []
    for r in (rows or [])[:30]:
        out.append({
            "filing_date": r.get("filing_date"),
            "purchases": _f(r.get("purchases")),
            "purchases_notional": _f(r.get("purchases_notional")),
            "sells": _f(r.get("sells")),
            "sells_notional": _f(r.get("sells_notional")),
        })
    return out


def _f(v) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None
