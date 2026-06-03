"""CLI: run an AI research analysis on a single ticker.

Usage:
    python -m engine.live.analyze NVDA
    python -m engine.live.analyze NVDA --agent fundamental
    python -m engine.live.analyze NVDA --source manual

In Phase 2 the only wired agent is `fundamental`. As more agents land they
become available via --agent (or omit --agent to run the full pipeline once
the LangGraph wiring is in place).

The CLI handles three things:
    1. Pre-fetch the FMP data bundle the agent needs (in parallel)
    2. Write the input signal markdown (00_signal.md)
    3. Run the agent and dump the resulting state to _raw.json
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from datetime import date
from typing import Optional

from ..data.fmp_client import FMPClient
from .agents.fundamental import FundamentalAgent
from .data.fmp_research import FMPResearchClient
from .file_store import FileStore
from .llm.gemini import GeminiClient, gemini_flash, gemini_pro
from .pipeline import run_full_pipeline
from .schemas import SignalInput
from .state import SignalState, new_signal_state


# --------------------------------------------------------------------------- #
# Per-agent context pre-fetch
# --------------------------------------------------------------------------- #


async def _prefetch_fundamental(
    research: FMPResearchClient, symbol: str
) -> dict[str, object]:
    """Fetch all FMP endpoints the Fundamental Agent needs, in parallel."""
    (
        profile, income, balance, cashflow,
        ratios_annual, ratios_ttm, km_ttm, earnings,
    ) = await asyncio.gather(
        research.fetch_profile(symbol),
        research.fetch_income_quarterly(symbol, limit=8),
        research.fetch_balance_quarterly(symbol, limit=4),
        research.fetch_cashflow_quarterly(symbol, limit=4),
        research.fetch_ratios_annual(symbol, limit=5),
        research.fetch_ratios_ttm(symbol),
        research.fetch_key_metrics_ttm(symbol),
        research.fetch_earnings(symbol, limit=8),
    )
    next_earnings = await research.fetch_next_earnings_date(symbol)

    return {
        "profile": profile.data,
        "income_q": income.data,
        "balance_q": balance.data,
        "cashflow_q": cashflow.data,
        "ratios_annual": ratios_annual.data,
        "ratios_ttm": ratios_ttm.data,
        "key_metrics_ttm": km_ttm.data,
        "earnings": earnings.data,
        "next_earnings_date": next_earnings.isoformat() if next_earnings else None,
        "_availability": {
            "profile": profile.available,
            "income_q": income.available,
            "balance_q": balance.available,
            "cashflow_q": cashflow.available,
            "ratios_annual": ratios_annual.available,
            "ratios_ttm": ratios_ttm.available,
            "key_metrics_ttm": km_ttm.available,
            "earnings": earnings.available,
        },
    }


# --------------------------------------------------------------------------- #
# Markdown for the input signal
# --------------------------------------------------------------------------- #


def _render_signal_md(state: SignalState) -> str:
    sym = state["symbol"]
    src = state["source"]
    d = state["signal_date"]
    sig: SignalInput | None = state.get("signal_input")  # type: ignore[assignment]
    lines = [
        f"# Signal — {sym}",
        "",
        f"_Date: {d}_  ",
        f"_Source: **{src}**_",
        "",
    ]
    if sig:
        if sig.notes:
            lines += ["## Notes", "", sig.notes, ""]
        if sig.quant_score is not None:
            lines += [
                "## Quant snapshot",
                "",
                f"- Score: `{sig.quant_score}`",
                f"- Trend OK: `{sig.trend_ok}`",
                f"- Breakout OK: `{sig.breakout_ok}`",
                f"- Current price: `{sig.current_price}`",
                f"- ATR: `{sig.atr}`",
                "",
            ]
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Main analyze flow
# --------------------------------------------------------------------------- #


async def analyze(
    symbol: str,
    agent_name: str = "fundamental",
    source: str = "manual",
    notes: Optional[str] = None,
    model: str = "flash",
) -> SignalState:
    symbol = symbol.upper()
    today = date.today().isoformat()
    fs = FileStore()

    # 1. Build initial state + write the input signal markdown
    state = new_signal_state(symbol, today, source)
    state["signal_input"] = SignalInput(
        symbol=symbol,
        source=source,  # type: ignore[arg-type]
        signal_date=today,
        notes=notes,
    )
    fs.write_markdown(symbol, today, "signal", _render_signal_md(state))

    # 2. Pre-fetch data (per-agent for now; full pipeline pre-fetches once)
    print(f"[1/4] Fetching FMP data for {symbol}...", flush=True)
    async with FMPClient() as raw:
        research = FMPResearchClient(raw)
        if agent_name == "fundamental":
            state["context"] = await _prefetch_fundamental(research, symbol)
        else:
            raise SystemExit(
                f"Unknown agent '{agent_name}'. Phase 2 only ships 'fundamental'."
            )

    avail = state["context"].get("_availability", {})
    fetched_ok = [k for k, v in avail.items() if v]
    print(f"      OK fetched: {', '.join(fetched_ok)}")

    # 3. Run the requested agent
    print(f"[2/4] Building agent prompt...", flush=True)
    llm = gemini_flash(temperature=0.2) if model == "flash" else gemini_pro(temperature=0.2)
    agent = FundamentalAgent(llm, fs)

    model_label = "Gemini 2.5 Flash" if model == "flash" else "Gemini 2.5 Pro"
    print(f"[3/4] Calling {model_label}...", flush=True)
    state = await agent.run(state)

    # 4. Dump full state to _raw.json
    print(f"[4/4] Writing report...", flush=True)
    fs.write_raw_state(symbol, today, state)

    folder = fs.folder(symbol, today)
    print()
    print(f"      OK ai_research/{symbol}/{today}/02_fundamental.md")
    print(f"      OK ai_research/{symbol}/{today}/_raw.json")
    print()

    # Pretty summary
    report = state.get("fundamental")
    if report is not None:
        print(f"Fundamental score: {report.fundamental_score}/10")
        if report.earnings_risk_days is not None:
            print(f"Earnings risk:     {report.earnings_risk_days} days")
        print(f"Key upside:        {report.key_upside_driver}")
        print(f"Key risk:          {report.key_downside_risk}")
        if report.red_flags:
            print(f"Red flags:         {len(report.red_flags)} flagged")

    return state


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Run an AI research agent on a single ticker."
    )
    ap.add_argument("symbol", help="Ticker symbol (e.g. NVDA)")
    ap.add_argument("--agent", default="full",
                    choices=["fundamental", "full"],
                    help="'fundamental' = run only that agent; 'full' = run the entire pipeline")
    ap.add_argument("--source", default="manual",
                    choices=["manual", "quant", "external"])
    ap.add_argument("--notes", default=None,
                    help="Optional note to attach to the signal markdown")
    ap.add_argument("--model", default="flash", choices=["flash", "pro"],
                    help="Which Gemini tier to use (default: flash for free tier)")
    ap.add_argument("--verbose", "-v", action="store_true")
    args = ap.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    try:
        if args.agent == "full":
            asyncio.run(_run_full(args.symbol, args.source, args.notes))
        else:
            asyncio.run(analyze(
                args.symbol, agent_name=args.agent,
                source=args.source, notes=args.notes, model=args.model,
            ))
    except KeyboardInterrupt:
        sys.exit(130)


async def _run_full(symbol: str, source: str, notes: Optional[str]) -> None:
    """Driver for --agent full. Prints stage transitions then a verdict summary."""
    def progress(stage: str, msg: str) -> None:
        print(f"  [{stage}] {msg}", flush=True)

    print(f"=== Full Pipeline — {symbol.upper()} ===\n", flush=True)
    state = await run_full_pipeline(symbol, source=source, notes=notes, progress=progress)

    print()
    pm = state.get("pm")
    if pm is not None:
        print(f"VERDICT:    {pm.decision}  (conviction {pm.conviction_score}/10)")
        print(f"SIZE:       {pm.recommended_size_pct}%")
        print(f"EXIT:       {pm.exit_thesis}")
        print()
        print("Telegram draft:")
        print("-" * 60)
        # Console may be cp1252 on Windows; squash chars it can't render.
        msg = pm.telegram_message.encode(sys.stdout.encoding or "utf-8",
                                          errors="replace").decode(
            sys.stdout.encoding or "utf-8", errors="replace")
        print(msg)
        print("-" * 60)
    today_dir = state.get("symbol", symbol.upper())
    print()
    print(f"Artifacts written under: ai_research/{today_dir}/{state['signal_date']}/")


if __name__ == "__main__":
    main()
