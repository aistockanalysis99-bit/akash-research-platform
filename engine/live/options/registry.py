"""The Strategy Registry — every strategy the platform will ever suggest,
defined by the same four ingredients: entry conditions, structure, return/risk
math, exit rules. The Rulebook page renders this directly, so what the client
reads IS what the code does — parameters are pulled live from settings, never
hard-typed into prose.

Adding a future strategy = adding one entry here + its builder (Phase 1+).
Statuses: live | paper | planned. Nothing skips paper.
"""
from __future__ import annotations

from typing import Any

from .. import settings as s


def rulebook() -> list[dict[str, Any]]:
    """The full rulebook with CURRENT parameter values resolved."""
    return [
        {
            "key": "long_straddle",
            "name": "R1 · Earnings Straddle",
            "status": "live",
            "phase": "shipped",
            "direction": "long volatility (direction-neutral)",
            "risk_type": "debit — max loss = premium paid",
            "pools": ["A (S&P 500 earnings universe)"],
            "plain": ("Buy a call and a put at the money when the market "
                      "prices a smaller earnings move than the stock's own "
                      "history. Ride the anticipation; ALWAYS exit before "
                      "the announcement."),
            "entry_conditions": [
                f"earnings in {s.get_options_entry_min_days()}–"
                f"{s.get_options_entry_max_days()} days",
                f"cheapness ≤ {s.get_options_cheapness_max():.2f} "
                f"(implied ÷ historical move)",
                f"ATM open interest ≥ {s.get_options_min_oi()}",
                f"leg spread ≤ {s.get_options_max_spread_pct()}% when quotable",
            ],
            "structure": "buy ATM call + buy ATM put, first expiry after earnings",
            "exit_rules": [
                "HARD deadline: 15:45 ET the trading day before earnings",
                f"profit-target suggestion at +{s.get_options_profit_target_pct():.0f}%",
                "drift alert when the straddle leans >20 deltas",
            ],
            "return_metrics": ["P&L % on premium (capital at risk = debit)"],
        },
        {
            "key": "iron_condor",
            "name": "R2 · Earnings Iron Condor",
            "status": "paper",
            "phase": "Phase 1 (building)",
            "direction": "short volatility (direction-neutral)",
            "risk_type": "credit — max loss = wing width − credit, fixed at entry",
            "pools": ["B (liquidity list)"],
            "plain": ("When the market OVERPRICES an earnings move on a very "
                      "liquid name, sell the expected move and buy protective "
                      "wings. Profit if the stock stays inside the range "
                      "through the print; worst case is known to the dollar. "
                      "The defined-risk version of what income sites call a "
                      "strangle — we never sell naked."),
            "entry_conditions": [
                f"cheapness ≥ {s.get_options_condor_min_cheapness():.2f} "
                f"(move overpriced vs history)",
                f"IV percentile ≥ {s.get_options_condor_min_iv_rank():.0f} "
                f"of the stock's own IV history (needs 15+ snapshots)",
                "Pool B member (liquidity earned, not assumed)",
            ],
            "structure": (f"sell put & call near |Δ| "
                          f"{s.get_options_condor_short_delta():.2f}, buy wings "
                          f"{s.get_options_condor_wing_pct():.1f}% of spot further out"),
            "exit_rules": [
                "hold through the earnings print (the crush IS the edge)",
                "exit suggestion the morning after earnings",
                "never rolled into undefined risk",
            ],
            "return_metrics": [
                "return on risk = credit ÷ max loss",
                "annualized yield on capital at risk",
                "POP estimate from short-strike deltas",
            ],
        },
        {
            "key": "cash_secured_put",
            "name": "R3 · Cash-Secured Put",
            "status": "paper",
            "phase": "Phase 3 (income layer — paper)",
            "direction": "bullish income",
            "risk_type": "cash-secured — capital = strike − credit",
            "pools": ["C (ownership list: AI BUY ≥7 only)"],
            "plain": ("Get paid to place a buy order. Sell a put at or below "
                      "the AI's preferred entry on a stock the AI already "
                      "rates BUY. Assigned → own a wanted stock at a discount. "
                      "Not assigned → keep the premium. Never sold on a stock "
                      "the 11 analysts wouldn't own."),
            "entry_conditions": [
                "AI conviction ≥ 7 (BUY)",
                "strike at or below the AI's entry level",
                f"{s.get_options_income_min_dte()}–{s.get_options_income_max_dte()} "
                f"days to expiry · never through an earnings date",
                f"target |Δ| ≈ {s.get_options_csp_target_delta():.2f}",
            ],
            "structure": "sell 1 OTM put, fully cash-secured",
            "exit_rules": ["let expire / roll suggestion at 21 DTE",
                           "assignment → becomes a wheel position (Phase 4)"],
            "return_metrics": ["annualized yield on secured cash",
                               "effective cost basis if assigned"],
        },
        {
            "key": "covered_call",
            "name": "R4 · Covered Call",
            "status": "paper",
            "phase": "Phase 3 (income layer — paper)",
            "direction": "income on held stock",
            "risk_type": "covered — short call backed by 100 held shares",
            "pools": ["C (the fund's actual holdings)"],
            "plain": ("Rent out stock the fund already owns. Sell a call at or "
                      "above the AI's price target — if called away, that's a "
                      "sale at the AI's own target. Skips earnings weeks."),
            "entry_conditions": [
                "position held in the portfolio (100-share lots) — share "
                "coverage re-verified at creation, in code",
                f"strike ≥ AI target, or |Δ| ≈ {s.get_options_cc_target_delta():.2f}",
                f"{s.get_options_income_min_dte()}–{s.get_options_income_max_dte()} "
                f"days out · no earnings inside the expiry",
            ],
            "structure": "sell 1 OTM call per 100 shares held",
            "exit_rules": ["expire & repeat · called away = sold at AI target"],
            "return_metrics": ["monthly + annualized rent on stock value",
                               "if-called total return"],
        },
        {
            "key": "wheel",
            "name": "R4½ · The Wheel",
            "status": "paper",
            "phase": "Phase 4 (lifecycle machine — paper)",
            "direction": "income cycle (bullish carry)",
            "risk_type": "cash-secured cycle — capital fixed at the first "
                         "secured strike",
            "pools": ["C (ownership list)"],
            "plain": ("The full income cycle as one machine: get paid to wait "
                      "(sell a put) → if assigned, own a wanted stock at a "
                      "discounted basis → rent it out (sell calls) → if called "
                      "away, the cycle completes and books its TRUE return. "
                      "Every premium lands in a ledger; the cost basis you see "
                      "is the real one, net of everything banked."),
            "entry_conditions": [
                "Pool C stock (the AI would own it)",
                "each leg follows the income rules (R3/R4 strikes & DTE)",
                "state machine enforces the grammar: puts only from CASH, "
                "calls only while HOLDING",
            ],
            "structure": "CSP → (assigned) stock → covered calls → called away",
            "exit_rules": [
                "outcomes confirmed by YOU from the broker — never assumed",
                "expiry-day Telegram suggestion compares close vs strike",
                "cycle ROI books only at completion (or honest abandonment)",
            ],
            "return_metrics": ["full-cycle ROI on committed capital",
                               "effective basis (assigned − premiums banked)"],
        },
        {
            "key": "bull_put_spread",
            "name": "R5 · Bull Put Spread",
            "status": "planned",
            "phase": "Phase 5 (spreads + allocator)",
            "direction": "bullish, defined risk",
            "risk_type": "credit — max loss = width − credit",
            "pools": ["C (AI BUY ≥7)"],
            "plain": ("Collect premium betting a strong stock simply won't "
                      "fall through the AI's stop level. The AI's stop "
                      "literally becomes the short strike."),
            "entry_conditions": ["AI conviction ≥ 7", "short strike ≤ AI stop level"],
            "structure": "sell put at AI stop, buy put below (fixed width)",
            "exit_rules": ["profit target ~50–60% of credit", "close if AI verdict flips"],
            "return_metrics": ["return on risk", "annualized on capital at risk"],
        },
        {
            "key": "bear_call_spread",
            "name": "R6 · Bear Call Spread",
            "status": "planned",
            "phase": "Phase 5 (spreads + allocator)",
            "direction": "bearish, defined risk",
            "risk_type": "credit — max loss = width − credit",
            "pools": ["C (AI AVOID verdicts)"],
            "plain": ("The AI's bearish research finally earns: collect premium "
                      "betting an AVOID-rated stock won't rally past the AI's "
                      "ceiling."),
            "entry_conditions": ["AI verdict AVOID/SELL", "short strike ≥ AI ceiling"],
            "structure": "sell call at AI ceiling, buy call above (fixed width)",
            "exit_rules": ["profit target ~50–60% of credit", "close if AI verdict flips"],
            "return_metrics": ["return on risk", "annualized on capital at risk"],
        },
    ]


GOVERNANCE = [
    "DEFINED RISK ONLY — the platform refuses any structure with unlimited "
    "loss at the database layer, not just in the UI.",
    "Paper first, always — every strategy family trades on paper before a "
    "single real dollar, and keeps a public league-table record.",
    "Suggest-only forever — the platform finds, prices, times, and alerts; "
    "Akash decides and executes.",
    "Delayed data honesty — quotes are ~15-min delayed; every card says "
    "'verify in broker before entering'. Live-data upgrade happens when "
    "measured slippage exceeds 10% of credit, not before.",
    "Returns three ways — quoted yield, historical expectation, realized "
    "result. No number is shown without its label.",
]
