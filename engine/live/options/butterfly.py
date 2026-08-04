"""Phase 6 — butterfly pilot, GATED on evidence about the AI's own aim.

A 1-2-1 butterfly is a cheap precision bet that the stock finishes near a
specific price — worth deploying ONLY if the AI's price targets have a
measured accuracy record. Until `target_accuracy()` can compute a real
figure from enough aged decisions, `build_butterfly` refuses to build.
The gate is the feature: shipping the builder without the gate would be
selling precision the platform hasn't earned.
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Any, Optional

from . import returns_math as rm
from .polygon_client import PolygonOptionsClient

log = logging.getLogger(__name__)

MIN_AGED_DECISIONS = 20     # decisions ≥90 days old with parsed targets
MAX_MEDIAN_TARGET_ERROR_PCT = 12.0   # target within ~12% of realized, median


async def target_accuracy(sample_limit: int = 40) -> dict[str, Any]:
    """Median |target − realized(+~120d)| / target across decisions old
    enough to judge. Expensive-ish (one FMP daily fetch per sampled symbol) —
    call on demand, cache the result upstream."""
    from datetime import timedelta
    from ...data.fmp_client import FMPClient
    from .income import ai_levels
    try:
        from api.ai_jobs import list_decisions_on_disk
    except Exception as e:  # noqa: BLE001
        return {"eligible": False, "reason": f"decisions unavailable: {e}"}

    cutoff = (date.today() - timedelta(days=90)).isoformat()
    aged: list[tuple[str, str, float]] = []
    seen: set[str] = set()
    for r in sorted(list_decisions_on_disk(),
                    key=lambda x: x.get("date") or "", reverse=True):
        sym = (r.get("symbol") or "").upper()
        d = r.get("date") or ""
        if not sym or sym in seen or d >= cutoff:
            continue
        lv = ai_levels(sym)
        if lv and lv.get("target") and lv.get("date") == d:
            aged.append((sym, d, float(lv["target"])))
            seen.add(sym)
        if len(aged) >= sample_limit:
            break
    if len(aged) < MIN_AGED_DECISIONS:
        return {"eligible": False,
                "reason": f"only {len(aged)} aged decisions with parsed "
                          f"targets — need {MIN_AGED_DECISIONS} (≥90 days "
                          f"old) before precision bets are earned",
                "sampled": len(aged)}

    errors: list[float] = []
    async with FMPClient() as fmp:
        for sym, d, target in aged:
            try:
                bars = await fmp.fetch_daily(sym)
                if bars is None or bars.empty:
                    continue
                dates = [str(ts)[:10] for ts in bars["timestamp"]]
                closes = bars["close"].astype(float).tolist()
                horizon = (date.fromisoformat(d)
                           + timedelta(days=120)).isoformat()
                idx = next((i for i, dd in enumerate(dates) if dd >= horizon),
                           None)
                if idx is None:
                    continue
                realized = closes[idx]
                errors.append(abs(target - realized) / target * 100)
            except Exception as e:  # noqa: BLE001
                log.info("target accuracy %s skipped: %s", sym, e)
    if len(errors) < MIN_AGED_DECISIONS:
        return {"eligible": False,
                "reason": f"only {len(errors)} decisions could be graded",
                "sampled": len(errors)}
    import statistics as _st
    median_err = round(_st.median(errors), 1)
    return {
        "eligible": median_err <= MAX_MEDIAN_TARGET_ERROR_PCT,
        "median_target_error_pct": median_err,
        "bar_pct": MAX_MEDIAN_TARGET_ERROR_PCT,
        "graded": len(errors),
        "reason": None if median_err <= MAX_MEDIAN_TARGET_ERROR_PCT else
        f"median target error {median_err}% is above the "
        f"{MAX_MEDIAN_TARGET_ERROR_PCT}% bar — targets aren't sharp enough "
        f"for pin bets yet",
    }


async def build_butterfly(poly: PolygonOptionsClient, symbol: str,
                          expiry: str, spot: float, ai_target: float,
                          accuracy: Optional[dict[str, Any]] = None
                          ) -> dict[str, Any]:
    """1-2-1 call butterfly centered on the AI's target. REFUSES unless the
    accuracy gate (pass `accuracy` from target_accuracy()) says eligible."""
    if not accuracy or not accuracy.get("eligible"):
        return {"ok": False,
                "reason": (accuracy or {}).get("reason")
                or "target-accuracy gate not evaluated — pilot locked"}
    band = spot * 0.30
    chain = await poly.chain_for_expiry(symbol, expiry, spot - band, spot + band)
    calls = {float((c.get("details") or {}).get("strike_price") or 0): c
             for c in chain
             if (c.get("details") or {}).get("contract_type") == "call"
             and poly.leg_price(c) is not None}
    if len(calls) < 3:
        return {"ok": False, "reason": "not enough priced call strikes"}
    center = min(calls, key=lambda k: abs(k - ai_target))
    wing = max(spot * 0.04, 1.0)
    lows = [k for k in calls if k < center]
    highs = [k for k in calls if k > center]
    if not lows or not highs:
        return {"ok": False, "reason": "no wing strikes around the target"}
    lo = min(lows, key=lambda k: abs((center - wing) - k))
    hi = min(highs, key=lambda k: abs((center + wing) - k))

    legs = []
    for side, k, qty in ((1, lo, 1), (-1, center, 2), (1, hi, 1)):
        c = calls[k]
        legs.append({"side": side, "contract_type": "call", "strike": k,
                     "expiry": expiry, "qty": qty,
                     "price": poly.leg_price(c),
                     "delta": (c.get("greeks") or {}).get("delta")})
    entry_value = rm.package_value(legs)
    if entry_value is None or entry_value <= 0:
        return {"ok": False, "reason": "butterfly did not net a debit — "
                                       "quotes stale/crossed"}
    stats = rm.payoff_stats(legs, entry_value, spot=spot)
    dte = (date.fromisoformat(expiry) - date.today()).days
    return {
        "ok": True, "symbol": symbol.upper(), "expiry": expiry, "dte": dte,
        "spot": round(spot, 2), "ai_target": ai_target,
        "strikes": [lo, center, hi], "legs": legs,
        "debit": round(entry_value, 4),
        "max_profit": stats["max_profit"],
        "max_loss": stats["max_loss"],
        "breakevens": stats["breakevens"],
        "accuracy_basis": {k: accuracy.get(k) for k in
                           ("median_target_error_pct", "graded", "bar_pct")},
    }
