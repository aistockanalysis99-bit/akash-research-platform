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
            "symbol": r["symbol"], **payload}


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


async def generate_board(notify: bool = True) -> dict[str, Any]:
    """Evaluate all active strategy families against today's data."""
    cands = store.latest_candidates()
    if not cands:
        return {"board_date": None, "cards": 0,
                "note": "no scanner data — run the scanner first"}
    board_date = cands[0].get("scan_date") or date.today().isoformat()
    pool = {p["symbol"] for p in list_pool_b(qualified_only=True)}

    r1 = _r1_cards(cands)
    r2 = await _r2_cards(cands, pool)

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

    if notify and (r1 or r2):
        await _send_digest(board_date, r1, r2)
    log.info("board %s: %d straddle card(s), %d condor card(s) "
             "(pool %d, candidates %d)",
             board_date, len(r1), len(r2), len(pool), len(cands))
    return {"board_date": board_date, "straddle_cards": len(r1),
            "condor_cards": len(r2)}


async def _send_digest(board_date: str, r1: list[dict], r2: list[dict]) -> None:
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
        lines.append("")
        lines.append("Defined-risk, paper-first, nothing trades automatically — "
                     "open Options → Board to review and track.")
        await client.send_message("\n".join(lines), kind="strategy_board")
    except Exception as e:  # noqa: BLE001
        log.warning("board digest send failed: %s", e)
