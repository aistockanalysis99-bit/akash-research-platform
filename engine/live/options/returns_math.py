"""Return & risk mathematics for multi-leg option structures.

Pure functions, no I/O — the single source of truth for every return number
shown anywhere in the options module (cards, league table, reports), so a
condor and a CSP are always comparable on the same axis:
RETURN ON CAPITAL AT RISK, ANNUALIZED.

Leg convention used across the module:
    {"side": +1|-1,            # +1 long (bought), -1 short (sold)
     "contract_type": "call"|"put",
     "strike": float,
     "expiry": "YYYY-MM-DD",
     "qty": int,               # contracts (always positive)
     "price": float|None,      # per-share premium
     "delta": float|None}      # signed, per Polygon greeks

Package value per share = Σ side·qty·price — positive means a net DEBIT was
paid (you own value), negative means a net CREDIT was received. P&L per share
is always value_now − value_entry, which works for both signs.
"""
from __future__ import annotations

from typing import Any, Optional

MULT = 100  # US equity option contract multiplier


# --------------------------------------------------------------------------- #
# Package value / P&L
# --------------------------------------------------------------------------- #

def package_value(legs: list[dict[str, Any]]) -> Optional[float]:
    """Net per-share value of the structure (+debit / −credit). None if any
    leg is unpriced — a partial mark is worse than no mark."""
    total = 0.0
    for leg in legs:
        if leg.get("price") is None:
            return None
        total += leg["side"] * leg["qty"] * float(leg["price"])
    return round(total, 4)


def pnl_usd(entry_value: float, current_value: float,
            contracts_scale: int = 1) -> float:
    """Dollar P&L. `contracts_scale` multiplies the whole package (legs carry
    their own qty, so this is usually 1)."""
    return round((current_value - entry_value) * MULT * contracts_scale, 2)


# --------------------------------------------------------------------------- #
# Generic payoff engine — works for ANY leg combination
# --------------------------------------------------------------------------- #

def _payoff_at(spot: float, legs: list[dict[str, Any]],
               entry_value: float) -> float:
    """Per-share P&L at expiry if the underlying finishes at `spot`."""
    value_at_expiry = 0.0
    for leg in legs:
        if leg["contract_type"] == "call":
            intrinsic = max(0.0, spot - leg["strike"])
        else:
            intrinsic = max(0.0, leg["strike"] - spot)
        value_at_expiry += leg["side"] * leg["qty"] * intrinsic
    return value_at_expiry - entry_value


def payoff_stats(legs: list[dict[str, Any]], entry_value: float,
                 spot: Optional[float] = None) -> dict[str, Any]:
    """Max profit / max loss / breakevens at expiry, per share, by scanning the
    payoff curve. Generic: any 1-4 leg structure, debit or credit.

    Piecewise-linear payoffs kink only at strikes, so evaluating at every
    strike plus far-out extremes is exact for the bounded region; the two
    extreme points also reveal unbounded tails (naked short exposure).
    """
    strikes = sorted({float(l["strike"]) for l in legs})
    hi_ref = max(strikes + ([spot] if spot else []))
    # Extreme probes: 0 and far above the highest strike.
    probes = [0.0] + strikes + [hi_ref * 3]
    pays = [(_s, _payoff_at(_s, legs, entry_value)) for _s in probes]

    # Unbounded tails: compare slope beyond the last strike / below the first.
    tail_up = _payoff_at(hi_ref * 3, legs, entry_value)
    tail_up_further = _payoff_at(hi_ref * 6, legs, entry_value)
    unbounded_up = tail_up_further < tail_up - 1e-9        # loss keeps growing
    unbounded_profit = tail_up_further > tail_up + 1e-9    # profit keeps growing
    # Downside is naturally bounded at spot=0 for equity options.

    vals = [p for _, p in pays]
    # A structure with unlimited upside has no finite max profit to display.
    max_profit = None if unbounded_profit else round(max(vals), 4)
    max_loss = round(min(vals), 4)  # negative number (a loss) or 0+

    # Breakevens: sign changes between adjacent probe points (linear between).
    breakevens: list[float] = []
    pts = sorted(pays)
    for (s1, p1), (s2, p2) in zip(pts, pts[1:]):
        if p1 == 0:
            breakevens.append(round(s1, 2))
        if (p1 < 0 < p2) or (p2 < 0 < p1):
            frac = abs(p1) / (abs(p1) + abs(p2))
            breakevens.append(round(s1 + frac * (s2 - s1), 2))
    breakevens = sorted(set(b for b in breakevens if b > 0))

    return {
        "max_profit": max_profit,          # None = unlimited upside
        "max_loss": max_loss,
        "unbounded_loss": bool(unbounded_up),
        "unbounded_profit": bool(unbounded_profit),
        "breakevens": breakevens,
    }


def is_defined_risk(legs: list[dict[str, Any]],
                    entry_value: float = 0.0) -> bool:
    """The house rule, in code: every structure we suggest or track must have
    a finite worst case. Naked short calls fail here and are refused."""
    return not payoff_stats(legs, entry_value)["unbounded_loss"]


def capital_at_risk(legs: list[dict[str, Any]], entry_value: float,
                    cash_secured_strike: Optional[float] = None) -> Optional[float]:
    """Per-share capital genuinely at risk (per SHARE-SET, i.e. qty-scaled to
    match entry_value / package_value).

    Defined-risk structures: |max_loss|. Cash-secured puts: the secured cash
    (qty × strike − credit), which is the honest denominator his site also
    uses. Returns None for unbounded structures (which we refuse anyway)."""
    if cash_secured_strike is not None:
        # entry_value scales with qty, so the strike term must too — otherwise
        # a 2-lot CSP reports half its true secured cash and double its yield.
        qty = sum(int(l.get("qty", 1)) for l in legs
                  if l["side"] < 0 and l["contract_type"] == "put") or 1
        return round(qty * cash_secured_strike + min(entry_value, 0.0), 4)
    stats = payoff_stats(legs, entry_value)
    if stats["unbounded_loss"]:
        return None
    if stats["max_loss"] >= 0:
        # No losing scenario = arbitrage manufactured by stale quotes.
        # Returning None makes create_structure refuse the position instead
        # of booking it with fantasy capital-at-risk.
        return None
    return round(abs(stats["max_loss"]), 4)


# --------------------------------------------------------------------------- #
# Standardized return metrics (Layer 1 — "quoted")
# --------------------------------------------------------------------------- #

def annualized_yield_pct(income_per_share: float, capital_per_share: float,
                         dte: int) -> Optional[float]:
    """The comparison metric his site leads with, same formula, same honesty
    caveat: (income ÷ capital at risk) × (365 ÷ DTE). A screening yardstick,
    never a forecast."""
    if capital_per_share <= 0 or dte <= 0:
        return None
    return round(income_per_share / capital_per_share * 365.0 / dte * 100, 1)


def return_on_risk_pct(max_profit: float, max_loss: float) -> Optional[float]:
    """Credit structures: what you make if right vs what you lose if wrong."""
    if max_loss >= 0:  # no loss side — degenerate
        return None
    return round(max_profit / abs(max_loss) * 100, 1)


def pop_estimate_pct(legs: list[dict[str, Any]]) -> Optional[float]:
    """Probability-of-profit ESTIMATE for net-credit structures, from short-leg
    deltas (|Δ| of a short option ≈ probability it finishes in the money).
    Standard trader heuristic, clearly labeled an estimate.

    None for DEBIT structures — the heuristic is only valid when the credit
    itself is the profit. On a debit vertical it would report P(short strike
    not breached), which is roughly the probability the trade does NOT reach
    max profit: an inverted, dangerously optimistic number."""
    net = package_value(legs)
    if net is None or net >= 0:      # unpriced, or a net debit was paid
        return None
    shorts = [l for l in legs if l["side"] < 0]
    if not shorts or any(l.get("delta") is None for l in shorts):
        return None
    p_breach = sum(abs(float(l["delta"])) * int(l.get("qty", 1)) for l in shorts)
    return round(max(0.0, min(1.0, 1.0 - p_breach)) * 100)
