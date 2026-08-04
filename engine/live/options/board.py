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

    if notify and (r1 or r2 or r3 or r4):
        await _send_digest(board_date, r1, r2, r3, r4)
    log.info("board %s: %d straddle, %d condor, %d CSP, %d CC card(s) "
             "(pool %d, candidates %d)",
             board_date, len(r1), len(r2), len(r3), len(r4),
             len(pool), len(cands or []))
    return {"board_date": board_date, "straddle_cards": len(r1),
            "condor_cards": len(r2), "csp_cards": len(r3),
            "cc_cards": len(r4)}


async def _send_digest(board_date: str, r1: list[dict], r2: list[dict],
                       r3: Optional[list[dict]] = None,
                       r4: Optional[list[dict]] = None) -> None:
    r3, r4 = r3 or [], r4 or []
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
        lines.append("")
        lines.append("Defined-risk, paper-first, nothing trades automatically — "
                     "open Options → Board to review and track.")
        await client.send_message("\n".join(lines), kind="strategy_board")
    except Exception as e:  # noqa: BLE001
        log.warning("board digest send failed: %s", e)
