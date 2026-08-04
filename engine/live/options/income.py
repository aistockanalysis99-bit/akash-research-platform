"""Phase 3 — the income layer: covered calls (R4) and cash-secured puts (R3).

Pool C discipline: income is only ever generated on stocks the fund already
owns (covered calls) or stocks the AI would happily own at the strike price
(CSPs on BUY conviction ≥ 7, struck at or below the AI's own entry level).
Premium is never chased for its own sake — that's how income sellers get
hurt, and it's the line between this module and a yield screener.

AI levels come from the newest PM verdict's client message, which is
template-generated ("Buy around: $X … target: $Y … cut losses at: $Z") —
parsed defensively; a name with unparseable levels simply produces no card.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import date, timedelta
from typing import Any, Optional

from .. import settings as live_settings
from . import returns_math as rm
from .polygon_client import PolygonOptionsClient

log = logging.getLogger(__name__)

MAX_INCOME_BUILDS = 6      # per family per board run — rate-limit discipline

_RE_ENTRY = re.compile(r"Buy around:?\s*\$([\d,]+(?:\.\d+)?)", re.I)
_RE_TARGET = re.compile(r"target:?\s*\$([\d,]+(?:\.\d+)?)", re.I)
_RE_STOP = re.compile(r"cut losses at:?\s*\$([\d,]+(?:\.\d+)?)", re.I)
# Upside invalidation in BEARISH messages ("only think about buying again if
# the price climbs back above $121"). This — never the downside stop — is the
# only honest ceiling for a bear call (review HIGH: the stop is ~8% BELOW the
# entry and carries zero "won't rally past here" meaning).
_RE_CEILING = re.compile(
    r"(?:climbs?|rises?|gets?|moves?)\s+back\s+above:?\s*\$([\d,]+(?:\.\d+)?)",
    re.I)


def _num(m: Optional[re.Match]) -> Optional[float]:
    return float(m.group(1).replace(",", "")) if m else None


def ai_levels(symbol: str) -> Optional[dict[str, Any]]:
    """Newest decision's parsed levels for `symbol`:
    {date, decision, conviction, entry, target, stop} — None if no decision
    or the message format didn't parse (never guess a level)."""
    try:
        from api.ai_jobs import AI_RESEARCH_DIR
    except Exception:  # noqa: BLE001
        return None
    from pathlib import Path
    sym_dir = Path(AI_RESEARCH_DIR) / symbol.upper()
    if not sym_dir.exists():
        return None
    dates = sorted((d.name for d in sym_dir.iterdir() if d.is_dir()),
                   reverse=True)
    for d in dates:
        raw_f = sym_dir / d / "_raw.json"
        if not raw_f.exists():
            continue
        try:
            raw = json.loads(raw_f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        pm = raw.get("pm") or {}
        msg = pm.get("telegram_message") or ""
        levels = {
            "date": d,
            "decision": pm.get("decision"),
            "conviction": pm.get("conviction_score"),
            "entry": _num(_RE_ENTRY.search(msg)),
            "target": _num(_RE_TARGET.search(msg)),
            "stop": _num(_RE_STOP.search(msg)),
            "ceiling": _num(_RE_CEILING.search(msg)),
        }
        if levels["conviction"] is not None:
            return levels
    return None


def pool_c() -> dict[str, Any]:
    """The ownership pool. holdings: stock positions with ≥100 shares
    (covered-call raw material). buy_candidates: AI BUY conviction ≥ 7 with a
    parsed entry level (CSP raw material)."""
    holdings: list[dict[str, Any]] = []
    try:
        from ..portfolio import VirtualPortfolio
        p = VirtualPortfolio()
        try:
            for pos in p.list_open():
                if (pos.get("instrument_type") or "stock") != "stock":
                    continue
                units = float(pos.get("units") or 0)
                if units >= 100:
                    holdings.append({"symbol": pos["symbol"].upper(),
                                     "shares": int(units),
                                     "ai_stop": pos.get("ai_stop_price")})
        finally:
            p.close_conn()
    except Exception as e:  # noqa: BLE001
        log.warning("pool C: portfolio read failed: %s", e)

    buys: list[dict[str, Any]] = []
    try:
        from api.ai_jobs import list_decisions_on_disk
        newest: dict[str, dict] = {}
        for r in list_decisions_on_disk():
            sym = (r.get("symbol") or "").upper()
            if not sym:
                continue
            if sym not in newest or (r.get("date") or "") > newest[sym]["date"]:
                newest[sym] = r
        stale_before = (date.today() - timedelta(days=45)).isoformat()
        for sym, r in newest.items():
            if (r.get("conviction") or 0) < 7:
                continue
            if (r.get("date") or "") < stale_before:
                continue  # never sell puts on a months-old opinion
            lv = ai_levels(sym)
            # Freshness must hold on the decision that SUPPLIES the levels —
            # ai_levels skips failed runs, so its date can be older than the
            # newest folder's (review finding: a crashed August run must not
            # launder a May decision's levels through the date check).
            if not lv or not lv.get("entry") \
                    or (lv.get("date") or "") < stale_before:
                continue
            if (lv.get("decision") or "").upper() not in ("APPROVE", "RESIZE"):
                continue  # a REJECT's "Buy around" line is not a buy order
            buys.append({"symbol": sym, **lv})
    except Exception as e:  # noqa: BLE001
        log.warning("pool C: decisions read failed: %s", e)
    return {"holdings": holdings, "buy_candidates": buys}


async def _friday_expiry(poly: PolygonOptionsClient, symbol: str,
                         min_dte: int, max_dte: int) -> Optional[str]:
    """First FRIDAY expiry inside the DTE window (liquidity lives on
    Fridays — the Pool B lesson). Falls back to any expiry in-window."""
    after = (date.today() + timedelta(days=min_dte)).isoformat()
    limit_day = date.today() + timedelta(days=max_dte)
    fallback = None
    for _ in range(6):
        nxt = await poly.first_expiry_after(symbol, after)
        if not nxt or date.fromisoformat(nxt) > limit_day:
            break
        if date.fromisoformat(nxt).weekday() == 4:
            return nxt
        fallback = fallback or nxt
        after = nxt
    return fallback


async def _earnings_inside(research, symbol: str, expiry: str) -> bool:
    """True = skip (earnings inside expiry OR unverifiable). Fails CLOSED:
    the research client swallows plan/endpoint errors into an empty result
    with available=False, and the old Optional-date API turned that into
    'no earnings' — silently disabling the guard (review finding). Income
    trades never run unverified."""
    try:
        result = await research.fetch_earnings(symbol, limit=16)
    except Exception:  # noqa: BLE001
        return True
    if not getattr(result, "available", False) or not result.data:
        return True   # can't verify → risky → skip (income ≠ event bets)
    today = date.today()
    future = []
    for row in result.data:
        try:
            d = date.fromisoformat(row.get("date") or "")
        except ValueError:
            continue
        if d >= today and row.get("epsActual") is None:
            future.append(d)
    nxt = min(future) if future else None
    return bool(nxt and nxt <= date.fromisoformat(expiry))


def _pick_by_delta(book: dict[float, dict], target: float, is_call: bool,
                   spot: float, poly: PolygonOptionsClient) -> Optional[dict]:
    scored = []
    for k, c in book.items():
        if (is_call and k <= spot) or (not is_call and k >= spot):
            continue
        d = (c.get("greeks") or {}).get("delta")
        if d is None or poly.leg_price(c) is None:
            continue
        scored.append((abs(abs(float(d)) - target), k, c))
    if not scored:
        return None
    _, k, c = min(scored, key=lambda t: (t[0], t[1]))
    return c


async def build_covered_call(poly: PolygonOptionsClient, research, symbol: str,
                             shares: int, spot: float,
                             ai_target: Optional[float]) -> dict[str, Any]:
    """R4: rent out held stock. Strike = the FARTHER (safer) of the delta-band
    strike and the AI's target — never selling upside the AI expects."""
    min_dte = live_settings.get_options_income_min_dte()
    max_dte = live_settings.get_options_income_max_dte()
    expiry = await _friday_expiry(poly, symbol, min_dte, max_dte)
    if not expiry:
        return {"ok": False, "reason": "no expiry in the income window"}
    if await _earnings_inside(research, symbol, expiry):
        return {"ok": False, "reason": "earnings inside expiry — income "
                                       "trades skip event weeks"}
    chain = await poly.chain_for_expiry(symbol, expiry, spot,
                                        spot * 1.25)
    calls = {float((c.get("details") or {}).get("strike_price") or 0): c
             for c in chain
             if (c.get("details") or {}).get("contract_type") == "call"}
    pick = _pick_by_delta(calls, live_settings.get_options_cc_target_delta(),
                          True, spot, poly)
    if pick is None:
        return {"ok": False, "reason": "no priced call in the delta band"}
    strike = float(pick["details"]["strike_price"])
    if ai_target and ai_target > spot:
        # never cap the position below the AI's own expectation
        above_target = {k: c for k, c in calls.items() if k >= ai_target
                        and poly.leg_price(c) is not None}
        if strike < ai_target and above_target:
            strike = min(above_target)
            pick = above_target[strike]
    premium = poly.leg_price(pick)
    if not premium:
        return {"ok": False, "reason": "strike not priceable"}
    dte = (date.fromisoformat(expiry) - date.today()).days
    qty = shares // 100
    monthly = premium / spot * (30 / max(dte, 1)) * 100
    if_called = ((strike - spot) + premium) / spot * 100
    return {
        "ok": True, "symbol": symbol.upper(), "expiry": expiry, "dte": dte,
        "spot": round(spot, 2), "strike": strike, "qty_max": qty,
        "premium": premium,
        "premium_usd_per_contract": round(premium * 100, 2),
        "oi": pick.get("open_interest") or 0,
        "delta": (pick.get("greeks") or {}).get("delta"),
        "monthly_yield_pct": round(monthly, 2),
        "annualized_pct": rm.annualized_yield_pct(premium, spot, dte),
        "if_called_return_pct": round(if_called, 2),
        "ai_target": ai_target,
        "legs": [{"side": -1, "contract_type": "call", "strike": strike,
                  "expiry": expiry, "qty": 1, "price": premium,
                  "delta": (pick.get("greeks") or {}).get("delta")}],
    }


async def build_csp(poly: PolygonOptionsClient, research, symbol: str,
                    spot: float, ai_entry: float,
                    conviction: Optional[int]) -> dict[str, Any]:
    """R3: get paid to place the AI's buy order. Strike = the LOWER (safer) of
    the delta-band strike and the AI's entry level."""
    min_dte = live_settings.get_options_income_min_dte()
    max_dte = live_settings.get_options_income_max_dte()
    expiry = await _friday_expiry(poly, symbol, min_dte, max_dte)
    if not expiry:
        return {"ok": False, "reason": "no expiry in the income window"}
    if await _earnings_inside(research, symbol, expiry):
        return {"ok": False, "reason": "earnings inside expiry — income "
                                       "trades skip event weeks"}
    chain = await poly.chain_for_expiry(symbol, expiry, spot * 0.70, spot)
    puts = {float((c.get("details") or {}).get("strike_price") or 0): c
            for c in chain
            if (c.get("details") or {}).get("contract_type") == "put"}
    pick = _pick_by_delta(puts, live_settings.get_options_csp_target_delta(),
                          False, spot, poly)
    if pick is None:
        return {"ok": False, "reason": "no priced put in the delta band"}
    strike = float(pick["details"]["strike_price"])
    if strike > ai_entry:
        # only promise to buy at or below the AI's own entry
        at_or_below = {k: c for k, c in puts.items() if k <= ai_entry
                       and poly.leg_price(c) is not None}
        if not at_or_below:
            return {"ok": False,
                    "reason": f"no priced strike at/below the AI entry "
                              f"${ai_entry:,.0f}"}
        strike = max(at_or_below)
        pick = at_or_below[strike]
    premium = poly.leg_price(pick)
    if not premium:
        return {"ok": False, "reason": "strike not priceable"}
    dte = (date.fromisoformat(expiry) - date.today()).days
    secured = strike - premium
    return {
        "ok": True, "symbol": symbol.upper(), "expiry": expiry, "dte": dte,
        "spot": round(spot, 2), "strike": strike,
        "premium": premium,
        "premium_usd_per_contract": round(premium * 100, 2),
        "cash_secured_usd": round(secured * 100, 2),
        "oi": pick.get("open_interest") or 0,
        "delta": (pick.get("greeks") or {}).get("delta"),
        "annualized_pct": rm.annualized_yield_pct(premium, secured, dte),
        "effective_basis": round(secured, 2),
        "discount_to_spot_pct": round((1 - secured / spot) * 100, 1),
        "ai_entry": ai_entry, "conviction": conviction,
        "legs": [{"side": -1, "contract_type": "put", "strike": strike,
                  "expiry": expiry, "qty": 1, "price": premium,
                  "delta": (pick.get("greeks") or {}).get("delta")}],
    }
