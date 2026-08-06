"""The Strategy Board — the daily desk.

After the 16:45 ET scanner run, evaluate every rulebook strategy against
today's data and persist one card per (strategy, symbol) that fires. Cards
carry the COMPLETE trade (legs, prices, risk numbers) plus the exact rules
that fired — a card is an accountable suggestion, not a screener label.

Phase 1 evaluates R1 (mirror of qualified straddle candidates) and R2
(earnings iron condor on overpriced, Pool-B-liquid names). Later phases add
their families here — one evaluator per strategy key, all writing the same
card shape.

Suggest-only: the board never opens anything. Tracking a card is a separate,
human action (POST /options/board/track).
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime
from typing import Any, Optional

from ...db.schema import get_connection
from .. import settings as live_settings
from . import store
from .condor import build_condor
from .polygon_client import PolygonOptionsClient
from .pools import list_pool_b

log = logging.getLogger(__name__)

# Rate-limit discipline: a condor build = 1 chain call. Cap builds per run so
# the evening job never burns the per-minute budget the scanner also needs.
MAX_CONDOR_BUILDS = 8
CONDOR_MIN_DAYS = 1     # earnings at least tomorrow (room to exit after)
CONDOR_MAX_DAYS = 10    # close enough that event premium dominates

_ensured = False


def ensure_tables() -> None:
    global _ensured
    if _ensured:
        return
    conn = get_connection()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS options_board (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                board_date TEXT, strategy_key TEXT, symbol TEXT,
                payload TEXT, created_at TEXT,
                UNIQUE(board_date, strategy_key, symbol)
            )""")
        # Every generate_board run is recorded here even when ZERO cards fire,
        # so get_board can serve an honest empty board instead of silently
        # showing the previous day's cards (stale-board review finding).
        conn.execute("""
            CREATE TABLE IF NOT EXISTS options_board_runs (
                run_date TEXT PRIMARY KEY,
                straddle_cards INTEGER, condor_cards INTEGER,
                created_at TEXT
            )""")
        conn.commit()
        _ensured = True
    finally:
        conn.close()


def _save_card(board_date: str, strategy_key: str, symbol: str,
               payload: dict[str, Any]) -> None:
    ensure_tables()
    conn = get_connection()
    try:
        conn.execute("""
            INSERT INTO options_board
                (board_date, strategy_key, symbol, payload, created_at)
            VALUES (?,?,?,?,?)
            ON CONFLICT(board_date, strategy_key, symbol)
            DO UPDATE SET payload=excluded.payload
            """, (board_date, strategy_key, symbol.upper(),
                  json.dumps(payload), datetime.utcnow().isoformat()))
        conn.commit()
    finally:
        conn.close()


def get_board() -> dict[str, Any]:
    """Latest board RUN (not latest non-empty date — an empty board is a real,
    honest result), cards grouped by strategy."""
    ensure_tables()
    conn = get_connection()
    try:
        run = conn.execute(
            "SELECT MAX(run_date) AS d FROM options_board_runs").fetchone()
        board_date = run["d"] if run else None
        if not board_date:
            # legacy fallback: boards written before runs were recorded
            d = conn.execute(
                "SELECT MAX(board_date) AS d FROM options_board").fetchone()
            board_date = d["d"] if d else None
        if not board_date:
            return {"board_date": None, "cards": []}
        rows = conn.execute(
            "SELECT * FROM options_board WHERE board_date=? "
            "ORDER BY strategy_key, symbol", (board_date,)).fetchall()
    finally:
        conn.close()
    cards = []
    for r in rows:
        try:
            payload = json.loads(r["payload"])
        except (TypeError, ValueError):
            continue
        cards.append({"id": r["id"], "strategy_key": r["strategy_key"],
                      "symbol": r["symbol"], **payload})
    return {"board_date": board_date, "cards": cards}


def get_card(card_id: int) -> Optional[dict[str, Any]]:
    ensure_tables()
    conn = get_connection()
    try:
        r = conn.execute("SELECT * FROM options_board WHERE id=?",
                         (card_id,)).fetchone()
    finally:
        conn.close()
    if not r:
        return None
    payload = json.loads(r["payload"])
    return {"id": r["id"], "strategy_key": r["strategy_key"],
            "symbol": r["symbol"], "board_date": r["board_date"], **payload}


# --------------------------------------------------------------------------- #
# Evaluators
# --------------------------------------------------------------------------- #

def _r1_cards(cands: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """R1 mirror: qualified straddle candidates, linked to the existing
    tracker (candidate_id) rather than duplicating its lifecycle."""
    out = []
    for c in cands:
        if not c.get("qualified"):
            continue
        out.append({
            "symbol": c["symbol"],
            "rules_fired": [
                f"cheapness {c.get('cheapness')} ≤ "
                f"{live_settings.get_options_cheapness_max():.2f}",
                f"earnings {c.get('earnings_date')} "
                f"({c.get('days_to_earnings')}d out)",
                f"ATM OI {c.get('min_oi')}",
            ],
            "candidate_id": c.get("id"),
            "earnings_date": c.get("earnings_date"),
            "days_to_earnings": c.get("days_to_earnings"),
            "expiry": c.get("expiry"),
            "strike": c.get("strike"),
            "straddle_cost": c.get("straddle_cost"),
            "implied_move_pct": c.get("implied_move_pct"),
            "hist_median_move_pct": c.get("hist_median_move_pct"),
            "cheapness": c.get("cheapness"),
            "dual_signal": c.get("dual_signal"),
            "exit_rule": "sell before the print — hard deadline 15:45 ET the "
                         "day before earnings",
        })
    return out


def _r2_shortlist(cands: list[dict[str, Any]],
                  pool: set[str]) -> list[dict[str, Any]]:
    min_cheap = live_settings.get_options_condor_min_cheapness()
    min_ivr = live_settings.get_options_condor_min_iv_rank()
    picked = []
    for c in cands:
        cheap = c.get("cheapness")
        days = c.get("days_to_earnings") or 0
        if cheap is None or cheap < min_cheap:
            continue
        if c["symbol"].upper() not in pool:
            continue
        if not (CONDOR_MIN_DAYS <= days <= CONDOR_MAX_DAYS):
            continue
        ivp = c.get("iv_percentile")
        if ivp is not None and ivp < min_ivr:
            continue  # gate inert while history is thin (ivp None)
        if not c.get("expiry") or not c.get("spot"):
            continue
        picked.append(c)
    picked.sort(key=lambda c: -(c.get("cheapness") or 0))
    return picked[:MAX_CONDOR_BUILDS]


async def _r2_cards(cands: list[dict[str, Any]],
                    pool: set[str]) -> list[dict[str, Any]]:
    shortlist = _r2_shortlist(cands, pool)
    if not shortlist:
        return []
    out: list[dict[str, Any]] = []
    min_oi = live_settings.get_options_min_oi()
    async with PolygonOptionsClient() as poly:
        for c in shortlist:  # sequential on purpose — rate-limit discipline
            try:
                condor = await build_condor(
                    poly, c["symbol"], c["expiry"], float(c["spot"]),
                    expected_move_pct=c.get("implied_move_pct"))
            except Exception as e:  # noqa: BLE001
                log.warning("board: condor build %s failed: %s", c["symbol"], e)
                continue
            if not condor.get("ok"):
                log.info("board: condor %s skipped — %s",
                         c["symbol"], condor.get("reason"))
                continue
            if (condor.get("min_oi") or 0) < min_oi:
                log.info("board: condor %s skipped — leg OI %s below %s",
                         c["symbol"], condor.get("min_oi"), min_oi)
                continue
            out.append({
                **condor,
                "rules_fired": [
                    f"cheapness {c.get('cheapness')} ≥ "
                    f"{live_settings.get_options_condor_min_cheapness():.2f} "
                    f"(move overpriced)",
                    "Pool B liquidity member",
                    f"earnings {c.get('earnings_date')} "
                    f"({c.get('days_to_earnings')}d out)",
                ] + ([f"IV percentile {c.get('iv_percentile')}"]
                     if c.get("iv_percentile") is not None else []),
                "earnings_date": c.get("earnings_date"),
                "days_to_earnings": c.get("days_to_earnings"),
                "cheapness": c.get("cheapness"),
                "implied_move_pct": c.get("implied_move_pct"),
                "hist_median_move_pct": c.get("hist_median_move_pct"),
                "exit_rule": "hold through the print; exit suggestion the "
                             "morning after earnings (10:00 ET deadline)",
            })
    return out


async def _income_cards() -> tuple[list[dict], list[dict]]:
    """R3 (CSP) + R4 (covered call) cards from Pool C. Independent of the
    earnings scanner — income runs off ownership + AI levels."""
    from ...data.fmp_client import FMPClient
    from ..data.fmp_research import FMPResearchClient
    from .income import (MAX_INCOME_BUILDS, ai_levels, build_covered_call,
                         build_csp, pool_c)

    pc = pool_c()
    cc_cards: list[dict] = []
    csp_cards: list[dict] = []
    async with FMPClient() as fmp, PolygonOptionsClient() as poly:
        research = FMPResearchClient(fmp)
        for h in pc["holdings"][:MAX_INCOME_BUILDS]:
            try:
                bars = await fmp.fetch_daily(h["symbol"])
                if bars is None or bars.empty:
                    continue
                spot = float(bars["close"].iloc[-1])
                lv = ai_levels(h["symbol"]) or {}
                cc = await build_covered_call(poly, research, h["symbol"],
                                              h["shares"], spot,
                                              lv.get("target"))
            except Exception as e:  # noqa: BLE001
                log.warning("board: CC build %s failed: %s", h["symbol"], e)
                continue
            if not cc.get("ok"):
                log.info("board: CC %s skipped — %s", h["symbol"], cc.get("reason"))
                continue
            cc_cards.append({
                **cc, "shares_held": h["shares"],
                "rules_fired": [f"{h['shares']} shares held (portfolio)",
                                f"strike ${cc['strike']} "
                                + (f"≥ AI target ${lv.get('target')}" if lv.get("target")
                                   else f"at Δ {live_settings.get_options_cc_target_delta():.2f}"),
                                "no earnings inside expiry"],
                "exit_rule": "let it expire and repeat; called away = sold at "
                             "the AI's own target",
            })
        for b in pc["buy_candidates"][:MAX_INCOME_BUILDS]:
            try:
                bars = await fmp.fetch_daily(b["symbol"])
                if bars is None or bars.empty:
                    continue
                spot = float(bars["close"].iloc[-1])
                csp = await build_csp(poly, research, b["symbol"], spot,
                                      float(b["entry"]), b.get("conviction"))
            except Exception as e:  # noqa: BLE001
                log.warning("board: CSP build %s failed: %s", b["symbol"], e)
                continue
            if not csp.get("ok"):
                log.info("board: CSP %s skipped — %s", b["symbol"], csp.get("reason"))
                continue
            csp_cards.append({
                **csp,
                "rules_fired": [f"AI BUY conviction {b.get('conviction')} "
                                f"({b.get('date')})",
                                f"strike ${csp['strike']} ≤ AI entry "
                                f"${b['entry']:,.0f}",
                                "no earnings inside expiry"],
                "exit_rule": "expire worthless = keep premium; assigned = own "
                             "a stock the AI wants, at a discount (wheel "
                             "begins in Phase 4)",
            })
    return csp_cards, cc_cards


MAX_SPREAD_BUILDS = 4


async def _spread_cards() -> tuple[list[dict], list[dict]]:
    """R5 bull puts (BUY ≥7 with a parsed stop) + R6 bear calls (AVOID/SELL
    with a parsed invalidation level). Fresh decisions only (45d, same rule
    as the income layer). No parseable level → no card, never a guess."""
    from ...data.fmp_client import FMPClient
    from ..data.fmp_research import FMPResearchClient
    from .income import ai_levels
    from .spreads import build_bear_call, build_bull_put

    bulls: list[dict] = []
    bears: list[dict] = []
    try:
        from datetime import timedelta
        from api.ai_jobs import list_decisions_on_disk
        stale_before = (date.today() - timedelta(days=45)).isoformat()
        newest: dict[str, dict] = {}
        for r in list_decisions_on_disk():
            sym = (r.get("symbol") or "").upper()
            if sym and (sym not in newest
                        or (r.get("date") or "") > newest[sym]["date"]):
                newest[sym] = r
        cand_bull, cand_bear = [], []
        for sym, r in newest.items():
            lv = ai_levels(sym)
            if not lv:
                continue
            # Freshness on the decision that supplies the LEVELS (ai_levels
            # skips failed runs — the newest folder's date can lie).
            if (lv.get("date") or "") < stale_before:
                continue
            # PM vocabulary is APPROVE / RESIZE / REJECT (review HIGH —
            # "AVOID"/"SELL" never occur; legacy strings kept defensively).
            # REJECT fires NEITHER side: it can mean risk-cap-blocked-bullish
            # (NVDA case) or thesis-rejected, and the decision field alone
            # can't tell them apart — ambiguity means no trade.
            decision = (lv.get("decision") or r.get("decision") or "").upper()
            if decision in ("AVOID", "SELL"):
                if lv.get("ceiling"):   # explicit upside invalidation ONLY
                    cand_bear.append((sym, lv))
            elif decision in ("APPROVE", "RESIZE") \
                    and (lv.get("conviction") or 0) >= 7 and lv.get("stop"):
                cand_bull.append((sym, lv))
    except Exception as e:  # noqa: BLE001
        log.warning("board: spread candidate sweep failed: %s", e)
        return [], []

    if not cand_bull and not cand_bear:
        return [], []
    async with FMPClient() as fmp, PolygonOptionsClient() as poly:
        research = FMPResearchClient(fmp)
        for sym, lv in cand_bull[:MAX_SPREAD_BUILDS]:
            try:
                bars = await fmp.fetch_daily(sym)
                if bars is None or bars.empty:
                    continue
                spot = float(bars["close"].iloc[-1])
                from .spreads import build_bull_put as _bp
                s = await _bp(poly, research, sym, spot, float(lv["stop"]))
            except Exception as e:  # noqa: BLE001
                log.warning("board: bull put %s failed: %s", sym, e)
                continue
            if not s.get("ok"):
                log.info("board: bull put %s skipped — %s", sym, s.get("reason"))
                continue
            bulls.append({**s,
                          "rules_fired": [
                              f"AI {lv.get('decision')} conviction "
                              f"{lv.get('conviction')} ({lv.get('date')})",
                              f"short strike ${s['short_strike']} ≤ AI stop "
                              f"${lv['stop']:,.2f}",
                              "no earnings inside expiry"],
                          "conviction": lv.get("conviction"),
                          "exit_rule": "suggestion: take profit at ~50-60% of "
                                       "the credit; close if the AI verdict "
                                       "flips"})
        for sym, lv in cand_bear[:MAX_SPREAD_BUILDS]:
            try:
                bars = await fmp.fetch_daily(sym)
                if bars is None or bars.empty:
                    continue
                spot = float(bars["close"].iloc[-1])
                s = await build_bear_call(poly, research, sym, spot,
                                          float(lv["ceiling"]))
            except Exception as e:  # noqa: BLE001
                log.warning("board: bear call %s failed: %s", sym, e)
                continue
            if not s.get("ok"):
                log.info("board: bear call %s skipped — %s", sym, s.get("reason"))
                continue
            bears.append({**s,
                          "rules_fired": [
                              f"AI verdict {lv.get('decision')} ({lv.get('date')})",
                              f"short strike ${s['short_strike']} ≥ the AI's "
                              f"re-entry ceiling ${lv['ceiling']:,.2f} "
                              f"('wrong if it climbs back above')",
                              "no earnings inside expiry"],
                          "exit_rule": "suggestion: take profit at ~50-60% of "
                                       "the credit; close if the AI verdict "
                                       "flips"})
    return bulls, bears


def _annotate_allocator(all_cards: dict[str, list[dict]]) -> None:
    """When one symbol fires MULTIPLE strategies, rank them and stamp each
    card with the allocator's verdict — the board explains which structure
    fits best and on what basis (our record vs prior)."""
    from .allocator import rank_structures
    from .income import ai_levels, pool_c
    try:
        holdings = {h["symbol"]: h["shares"] for h in pool_c()["holdings"]}
    except Exception:  # noqa: BLE001
        holdings = {}
    by_symbol: dict[str, list[tuple[str, dict]]] = {}
    for key, cards in all_cards.items():
        for c in cards:
            by_symbol.setdefault(c["symbol"], []).append((key, c))
    for sym, entries in by_symbol.items():
        if len(entries) < 2:
            continue
        # Earnings context is a SYMBOL fact but only event-family cards carry
        # it — scan all of the symbol's cards, not just whichever sorted first,
        # or a condor card behind a CC card loses its allocator badge.
        days = next((c.get("days_to_earnings") for _, c in entries
                     if c.get("days_to_earnings") is not None), None)
        cheap = next((c.get("cheapness") for _, c in entries
                      if c.get("cheapness") is not None), None)
        ctx = {"holding_shares": holdings.get(sym, 0),
               "ai": ai_levels(sym) or {},
               "earnings_days": days,
               "cheapness": cheap}
        try:
            ranking = rank_structures(sym, ctx)
        except Exception as e:  # noqa: BLE001
            log.warning("allocator ranking %s failed: %s", sym, e)
            continue
        pos = {r["key"]: r for r in ranking}
        for key, c in entries:
            if key in pos:
                c["allocator"] = {"rank": pos[key]["rank"],
                                  "of": len(ranking),
                                  "why": pos[key]["why"],
                                  "basis": pos[key]["basis"]}


async def generate_board(notify: bool = True) -> dict[str, Any]:
    """Evaluate all active strategy families against today's data."""
    # Event strategies (R1/R2) need scanner data; income (R3/R4) does NOT —
    # it runs off ownership + AI levels, so a missing scan must not blank
    # the whole board.
    cands = store.latest_candidates()
    board_date = (cands[0].get("scan_date") if cands else None) \
        or date.today().isoformat()
    pool = {p["symbol"] for p in list_pool_b(qualified_only=True)}

    r1 = _r1_cards(cands) if cands else []
    r2 = await _r2_cards(cands, pool) if cands else []
    try:
        r3, r4 = await _income_cards()
    except Exception as e:  # noqa: BLE001
        log.warning("board: income evaluators failed: %s", e)
        r3, r4 = [], []
    try:
        r5, r6 = await _spread_cards()
    except Exception as e:  # noqa: BLE001
        log.warning("board: spread evaluators failed: %s", e)
        r5, r6 = [], []

    _annotate_allocator({"long_straddle": r1, "iron_condor": r2,
                         "cash_secured_put": r3, "covered_call": r4,
                         "bull_put_spread": r5, "bear_call_spread": r6})

    # Rebuild semantics: this run REPLACES the date's board. Without the
    # delete, a same-day rerun leaves ghost cards for symbols that no longer
    # fire (settings changed, credit vanished, dropped from shortlist) —
    # still displayed and still trackable.
    ensure_tables()
    conn = get_connection()
    try:
        conn.execute("DELETE FROM options_board WHERE board_date=?",
                     (board_date,))
        conn.execute(
            "INSERT OR REPLACE INTO options_board_runs VALUES (?,?,?,?)",
            (board_date, len(r1), len(r2), datetime.utcnow().isoformat()))
        conn.commit()
    finally:
        conn.close()
    for card in r1:
        _save_card(board_date, "long_straddle", card["symbol"], card)
    for card in r2:
        _save_card(board_date, "iron_condor", card["symbol"], card)
    for card in r3:
        _save_card(board_date, "cash_secured_put", card["symbol"], card)
    for card in r4:
        _save_card(board_date, "covered_call", card["symbol"], card)
    for card in r5:
        _save_card(board_date, "bull_put_spread", card["symbol"], card)
    for card in r6:
        _save_card(board_date, "bear_call_spread", card["symbol"], card)

    if notify and (r1 or r2 or r3 or r4 or r5 or r6):
        await _send_digest(board_date, r1, r2, r3, r4, r5, r6)
    log.info("board %s: %d straddle, %d condor, %d CSP, %d CC, %d bull-put, "
             "%d bear-call card(s) (pool %d, candidates %d)",
             board_date, len(r1), len(r2), len(r3), len(r4), len(r5), len(r6),
             len(pool), len(cands or []))
    return {"board_date": board_date, "straddle_cards": len(r1),
            "condor_cards": len(r2), "csp_cards": len(r3),
            "cc_cards": len(r4), "bull_put_cards": len(r5),
            "bear_call_cards": len(r6)}


async def _send_digest(board_date: str, r1: list[dict], r2: list[dict],
                       r3: Optional[list[dict]] = None,
                       r4: Optional[list[dict]] = None,
                       r5: Optional[list[dict]] = None,
                       r6: Optional[list[dict]] = None) -> None:
    r3, r4, r5, r6 = r3 or [], r4 or [], r5 or [], r6 or []
    try:
        from ..telegram import telegram as _telegram
        client = _telegram()
        lines = [f"📋 Strategy Board — {board_date}", ""]
        for c in r1[:4]:
            lines.append(
                f"🎯 {c['symbol']} STRADDLE (buy vol) — earnings "
                f"{c['earnings_date']}. Market prices ±{c['implied_move_pct']}%, "
                f"it normally moves ±{c['hist_median_move_pct']}% "
                f"(cheapness {c['cheapness']}).")
        for c in r2[:4]:
            cost = (c.get("credit") or 0) * 100
            ml = abs(c.get("max_loss") or 0) * 100
            lines.append(
                f"🛡 {c['symbol']} IRON CONDOR (sell overpriced vol) — earnings "
                f"{c['earnings_date']}. Collect ≈${cost:,.0f}/set, worst case "
                f"${ml:,.0f}, ≈{c.get('pop_est') or '—'}% odds. "
                f"Implied ±{c['implied_move_pct']}% vs normal "
                f"±{c['hist_median_move_pct']}%.")
        for c in r4[:4]:
            lines.append(
                f"🏠 {c['symbol']} COVERED CALL — rent out your "
                f"{c['shares_held']} shares: sell the ${c['strike']} call "
                f"({c['expiry']}), collect ≈${c['premium_usd_per_contract']:,.0f}"
                f"/contract (~{c['monthly_yield_pct']}%/month). Called away = "
                f"sold at the AI's target.")
        for c in r3[:4]:
            lines.append(
                f"💵 {c['symbol']} CASH-SECURED PUT — get paid to place the "
                f"AI's buy order: sell the ${c['strike']} put ({c['expiry']}), "
                f"collect ≈${c['premium_usd_per_contract']:,.0f} "
                f"({c['annualized_pct']}% annualized on the cash). Assigned = "
                f"buy at {c['discount_to_spot_pct']}% below today's price.")
        for c in r5[:3]:
            lines.append(
                f"📈 {c['symbol']} BULL PUT SPREAD — collect "
                f"≈${(c['credit'] or 0) * 100:,.0f} betting it holds above the "
                f"AI's own stop (${c['short_strike']}). Worst case "
                f"${abs(c['max_loss'] or 0) * 100:,.0f}, ≈{c.get('pop_est') or '—'}% odds.")
        for c in r6[:3]:
            lines.append(
                f"📉 {c['symbol']} BEAR CALL SPREAD — the AVOID verdict earns: "
                f"≈${(c['credit'] or 0) * 100:,.0f} unless it rallies past "
                f"${c['short_strike']}. Worst case "
                f"${abs(c['max_loss'] or 0) * 100:,.0f}.")
        lines.append("")
        lines.append("Defined-risk, paper-first, nothing trades automatically — "
                     "open Options → Board to review and track.")
        await client.send_message("\n".join(lines), kind="strategy_board")
    except Exception as e:  # noqa: BLE001
        log.warning("board digest send failed: %s", e)
