"""Pool B — the liquidity list for short-premium strategies (condors, spreads).

Execution quality decides whether credit strategies make or lose money, so
membership here is EARNED by measurable liquidity, not opinion. The seed list
(client's optionincometools.com names + standard mega-liquid underlyings) only
decides who gets measured; the refresh job decides who qualifies.

Metrics per name, from the nearest expiry's ATM straddle snapshot:
  atm_oi        — min(call OI, put OI) at the ATM strike
  spread_pct    — worst leg bid/ask spread (None on the delayed tier when NBBO
                  is missing; qualification then rests on OI alone)
Qualified = atm_oi >= options_pool_b_min_oi (setting, default 1000).
"""
from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, timedelta
from typing import Any, Optional

from ...db.schema import get_connection
from .. import settings as live_settings
from .polygon_client import PolygonOptionsClient

log = logging.getLogger(__name__)

# Seed: who gets measured. Client's site names + standard liquid underlyings.
POOL_B_SEED = [
    "SPY", "QQQ", "IWM",
    "AAPL", "MSFT", "NVDA", "TSLA", "AMZN", "META", "GOOGL", "GOOG", "AMD",
    "AVGO", "NFLX", "CRM", "ORCL", "INTC", "MU",
    "PLTR", "SHOP", "COIN", "SNOW", "SOFI", "HOOD", "PYPL", "UBER",
    "DIS", "NKE", "F", "GM", "BA", "WMT", "HD", "COST",
    "XOM", "CVX", "JPM", "BAC", "GS", "C",
]

_ensured = False


def ensure_tables() -> None:
    global _ensured
    if _ensured:
        return
    conn = get_connection()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS options_pool_b (
                symbol TEXT PRIMARY KEY,
                asof TEXT, spot REAL, expiry TEXT,
                atm_oi INTEGER, spread_pct REAL,
                qualified INTEGER, note TEXT
            )""")
        conn.commit()
        _ensured = True
    finally:
        conn.close()


def list_pool_b(qualified_only: bool = False) -> list[dict[str, Any]]:
    ensure_tables()
    conn = get_connection()
    try:
        q = "SELECT * FROM options_pool_b"
        if qualified_only:
            q += " WHERE qualified=1"
        q += " ORDER BY atm_oi DESC"
        return [dict(r) for r in conn.execute(q).fetchall()]
    finally:
        conn.close()


def pool_b_symbols() -> list[str]:
    """Qualified members; falls back to the seed before the first refresh."""
    rows = list_pool_b(qualified_only=True)
    return [r["symbol"] for r in rows] if rows else list(POOL_B_SEED)


async def _measure_one(sym: str, poly: PolygonOptionsClient,
                       fmp) -> dict[str, Any]:
    min_oi = live_settings.get_options_pool_b_min_oi()
    row: dict[str, Any] = {"symbol": sym, "asof": date.today().isoformat(),
                           "spot": None, "expiry": None, "atm_oi": None,
                           "spread_pct": None, "qualified": 0, "note": ""}
    bars = await fmp.fetch_daily(sym)
    if bars is None or bars.empty:
        row["note"] = "no price data"
        return row
    spot = float(bars["close"].iloc[-1])
    row["spot"] = round(spot, 2)

    # Measure the expiry short-premium trades would actually use: the first
    # FRIDAY expiry ≥ ~a week out. Mega-liquid names list Mon/Wed weeklies
    # whose OI is near zero when freshly listed (AAPL's Monday weekly measured
    # 128 ATM OI while its Friday carried thousands) — judging liquidity on
    # those would disqualify the most liquid names in the market.
    after = (date.today() + timedelta(days=5)).isoformat()
    expiry = None
    for _ in range(5):
        nxt = await poly.first_expiry_after(sym, after)
        if not nxt:
            break
        if date.fromisoformat(nxt).weekday() == 4:  # Friday
            expiry = nxt
            break
        expiry = expiry or nxt  # remember the first as fallback
        after = nxt
    if not expiry:
        row["note"] = "no listed options"
        return row
    row["expiry"] = expiry
    # Best paired OI in the ATM neighborhood (±3% of spot): per strike take
    # min(call OI, put OI) — a straddle/condor needs BOTH sides — then take
    # the best strike. Judging one arbitrary strike understates real names
    # (the AES lesson); a trader would use the liquid strike next door.
    band = max(spot * 0.03, 2.5)
    chain = await poly.chain_for_expiry(sym, expiry, spot - band, spot + band)
    by_strike: dict[float, dict[str, int]] = {}
    spreads: list[float] = []
    for c in chain:
        det = c.get("details") or {}
        k, typ = det.get("strike_price"), det.get("contract_type")
        if k is None or typ not in ("call", "put"):
            continue
        by_strike.setdefault(float(k), {})[typ] = int(c.get("open_interest") or 0)
        sp = poly.leg_spread_pct(c)
        if sp is not None:
            spreads.append(sp)
    paired = [min(v.get("call", 0), v.get("put", 0)) for v in by_strike.values()
              if "call" in v and "put" in v]
    if not paired:
        row["note"] = "no paired ATM strikes"
        return row
    row["atm_oi"] = max(paired)
    row["spread_pct"] = round(max(spreads), 2) if spreads else None
    row["qualified"] = 1 if row["atm_oi"] >= min_oi else 0
    if not row["qualified"]:
        row["note"] = f"best ATM-neighborhood OI {row['atm_oi']} < {min_oi}"
    return row


async def refresh_pool_b(symbols: Optional[list[str]] = None) -> dict[str, Any]:
    """Re-measure the pool. Existing members are always re-measured (so decay
    gets caught), plus any new seed names."""
    ensure_tables()
    known = {r["symbol"] for r in list_pool_b()}
    todo = sorted(set(symbols or (list(known) + POOL_B_SEED)))

    from ...data.fmp_client import FMPClient
    results: list[dict[str, Any]] = []
    async with FMPClient() as fmp, PolygonOptionsClient() as poly:
        sem = asyncio.Semaphore(6)

        async def one(sym: str):
            async with sem:
                try:
                    return await _measure_one(sym, poly, fmp)
                except Exception as e:  # noqa: BLE001
                    log.warning("pool B measure %s failed: %s", sym, e)
                    return None

        rows = await asyncio.gather(*[one(s) for s in todo])
        results = [r for r in rows if r]

    conn = get_connection()
    try:
        for r in results:
            conn.execute("""
                INSERT INTO options_pool_b
                    (symbol, asof, spot, expiry, atm_oi, spread_pct,
                     qualified, note)
                VALUES (:symbol,:asof,:spot,:expiry,:atm_oi,:spread_pct,
                        :qualified,:note)
                ON CONFLICT(symbol) DO UPDATE SET
                    asof=excluded.asof, spot=excluded.spot,
                    expiry=excluded.expiry, atm_oi=excluded.atm_oi,
                    spread_pct=excluded.spread_pct,
                    qualified=excluded.qualified, note=excluded.note
                """, r)
        conn.commit()
    finally:
        conn.close()

    qualified = sum(1 for r in results if r["qualified"])
    log.info("pool B refresh: %d measured, %d qualified", len(results), qualified)
    return {"measured": len(results), "qualified": qualified,
            "updated": datetime.utcnow().isoformat()}
