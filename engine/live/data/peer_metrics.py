"""Peer comparison data — finds 4-5 sector peers and fetches their key metrics.

Used by the Fundamental and PM agents to ground relative-value claims.
Without this, "INTC P/E is high" is a free-floating assertion; with this,
"INTC P/E is high vs. AMD 28x, NVDA 32x, AVGO 35x" is a real comparison.

Peer discovery cascade:
    1. FMP /stable/stock-peers (if available on this plan)
    2. Fall back to S&P 100 universe filtered by same sector + closest mkt cap
    3. Empty list if neither source has data

Metrics fetched per peer (best-effort, fail-soft):
    - TTM P/E, gross margin, operating margin, net margin
    - Last reported quarter: revenue, revenue YoY growth, FCF
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

from ...data.fmp_client import FMPClient
from ...data.universe import get_universe
from .fmp_research import FMPResearchClient

log = logging.getLogger(__name__)


async def fetch_peer_comparison(
    research: FMPResearchClient,
    fmp: FMPClient,
    symbol: str,
    profile: dict,
    n_peers: int = 5,
) -> dict[str, Any]:
    """Fetch peer comparison block for `symbol`. Returns a structured dict.

    On any failure, returns {"available": False, "reason": "..."} — never raises.
    """
    sector = (profile or {}).get("sector") or ""
    industry = (profile or {}).get("industry") or ""
    target_mcap = (profile or {}).get("mktCap") or (profile or {}).get("marketCap")

    # Stage 1: try FMP /stable/stock-peers
    peer_symbols = await _try_fmp_peers(fmp, symbol)

    # Stage 2: fall back to same-sector subset of S&P 100
    if not peer_symbols and sector:
        peer_symbols = await _fallback_sector_peers(
            fmp, symbol, sector, target_mcap, n_peers,
        )

    if not peer_symbols:
        return {
            "available": False,
            "reason": "Could not identify peers from either /stock-peers "
                       "or S&P 100 sector fallback.",
            "sector": sector,
            "industry": industry,
        }

    peer_symbols = peer_symbols[:n_peers]

    # Fetch metrics for each peer in parallel (cap to 6 concurrent)
    sem = asyncio.Semaphore(6)

    async def _one(sym: str) -> Optional[dict]:
        async with sem:
            return await _peer_metrics(research, sym)

    rows = await asyncio.gather(*[_one(s) for s in peer_symbols])
    peers = [r for r in rows if r is not None]

    return {
        "available": bool(peers),
        "sector": sector,
        "industry": industry,
        "peers": peers,
        "n_peers": len(peers),
    }


# --------------------------------------------------------------------------- #
# Peer discovery
# --------------------------------------------------------------------------- #


async def _try_fmp_peers(fmp: FMPClient, symbol: str) -> list[str]:
    """Try FMP's stock-peers endpoint. Returns empty list on any failure."""
    for path in ("/stock-peers", "/peers", "/peers-list"):
        try:
            data = await fmp._get(path, {"symbol": symbol})
        except Exception:  # noqa: BLE001 — try the next variant
            continue
        if isinstance(data, list) and data:
            first = data[0]
            if isinstance(first, dict):
                # Some endpoints return [{"symbol":"X","peersList":["A","B"]}]
                peers = first.get("peersList") or first.get("peers") or []
                if peers:
                    return [str(p).upper() for p in peers if p and p != symbol.upper()][:10]
            elif isinstance(first, str):
                # Or just a flat list of symbols
                return [str(p).upper() for p in data if p and p != symbol.upper()][:10]
    return []


async def _fallback_sector_peers(
    fmp: FMPClient, symbol: str, sector: str,
    target_mcap: Optional[float], n: int,
) -> list[str]:
    """Build a peer list from the S&P 100 universe in the same sector,
    sorted by closeness in market cap.
    """
    try:
        sp100 = get_universe("SP100")
    except Exception:  # noqa: BLE001
        return []

    sp100 = [s for s in sp100 if s != symbol.upper()]
    if not sp100:
        return []

    # Fetch profiles in parallel to filter by sector + sort by mkt cap
    sem = asyncio.Semaphore(8)

    async def _profile(sym: str) -> Optional[dict]:
        async with sem:
            try:
                data = await fmp._get("/profile", {"symbol": sym})
                if isinstance(data, list) and data:
                    return data[0]
            except Exception:  # noqa: BLE001
                return None
            return None

    profiles = await asyncio.gather(*[_profile(s) for s in sp100])
    same_sector = [
        p for p in profiles
        if p and p.get("sector") == sector
    ]
    if not same_sector:
        return []

    # If we have target market cap, sort by distance; else just by descending mcap
    if target_mcap and target_mcap > 0:
        same_sector.sort(
            key=lambda p: abs((p.get("mktCap") or p.get("marketCap") or 0) - target_mcap),
        )
    else:
        same_sector.sort(
            key=lambda p: -(p.get("mktCap") or p.get("marketCap") or 0),
        )

    return [str(p.get("symbol", "")).upper()
            for p in same_sector[:n] if p.get("symbol")]


# --------------------------------------------------------------------------- #
# Per-peer metric fetcher
# --------------------------------------------------------------------------- #


async def _peer_metrics(
    research: FMPResearchClient, symbol: str,
) -> Optional[dict]:
    """Fetch a compact metric snapshot for one peer."""
    try:
        profile_r, ttm_r, income_r = await asyncio.gather(
            research.fetch_profile(symbol),
            research.fetch_ratios_ttm(symbol),
            research.fetch_income_quarterly(symbol, limit=5),
        )
    except Exception as e:  # noqa: BLE001
        log.warning("peer_metrics: %s failed: %s", symbol, e)
        return None

    profile = profile_r.data or {}
    ttm = ttm_r.data or {}
    income_rows = income_r.data or []

    if not profile and not ttm and not income_rows:
        return None

    last = income_rows[0] if income_rows else {}
    yoy = income_rows[4] if len(income_rows) > 4 else None  # 4 quarters back

    revenue_now = _f(last.get("revenue"))
    revenue_yoy = _f(yoy.get("revenue")) if yoy else None
    revenue_growth_yoy = (
        (revenue_now / revenue_yoy - 1) * 100.0
        if (revenue_now and revenue_yoy and revenue_yoy > 0) else None
    )

    op_income = _f(last.get("operatingIncome"))
    gross_profit = _f(last.get("grossProfit"))
    net_income = _f(last.get("netIncome"))

    return {
        "symbol": symbol.upper(),
        "company": profile.get("companyName"),
        "sector": profile.get("sector"),
        "industry": profile.get("industry"),
        "market_cap_usd": _f(profile.get("mktCap") or profile.get("marketCap")),
        "current_price": _f(profile.get("price")),
        "pe_ttm": _f(ttm.get("peRatioTTM")),
        "ev_to_ebitda_ttm": _f(ttm.get("enterpriseValueMultipleTTM")),
        "gross_margin_ttm": _f(ttm.get("grossProfitMarginTTM")),
        "operating_margin_ttm": _f(ttm.get("operatingProfitMarginTTM")),
        "net_margin_ttm": _f(ttm.get("netProfitMarginTTM")),
        "roe_ttm": _f(ttm.get("returnOnEquityTTM")),
        "fcf_margin_ttm": _f(ttm.get("freeCashFlowMarginTTM")),
        "last_quarter_revenue_usd": revenue_now,
        "last_quarter_revenue_yoy_pct": (
            round(revenue_growth_yoy, 2) if revenue_growth_yoy is not None else None
        ),
        "last_quarter_gross_margin": (
            round(gross_profit / revenue_now, 4)
            if (gross_profit and revenue_now and revenue_now > 0) else None
        ),
        "last_quarter_operating_margin": (
            round(op_income / revenue_now, 4)
            if (op_income and revenue_now and revenue_now > 0) else None
        ),
        "last_quarter_net_margin": (
            round(net_income / revenue_now, 4)
            if (net_income and revenue_now and revenue_now > 0) else None
        ),
    }


def _f(v: Any) -> Optional[float]:
    if v is None:
        return None
    try:
        f = float(v)
        return f if f == f else None  # filter NaN
    except (TypeError, ValueError):
        return None
