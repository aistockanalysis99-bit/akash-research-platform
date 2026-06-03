"""Rewrite the two Telegram messages for existing analyses in plain language.

Cheap path: instead of re-running the full 11-agent pipeline, we take the
PM decision + key facts already on disk and make ONE LLM call to rewrite
the stock-view + portfolio-fit messages in the new client-friendly style.

For each ticker:
  1. Read ai_research/{SYM}/{latest_date}/_raw.json
  2. Pull decision, conviction, size, entry/target/stop + the OLD messages
  3. One Claude call → two new plain-language messages
  4. Write them back into _raw.json (telegram_message + telegram_portfolio_message)
  5. Re-send both to Telegram

Usage:
    python scripts/reformat_telegram_messages.py [--tickers SYM1,SYM2]
                                                  [--no-send]   (rewrite only)
                                                  [--dry-run]   (print, no write/send)
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

# UTF-8 stdout on Windows
try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:  # noqa: BLE001
    pass

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine.config import AI_RESEARCH_DIR                       # noqa: E402
from engine.live.llm.claude import claude_sonnet                # noqa: E402
from engine.live.llm.structured import invoke_structured_or_freetext  # noqa: E402
from engine.live.schemas import PMDecision                      # noqa: E402

DEFAULT_TICKERS = [
    "INTC", "MU", "AMD", "NVDA", "SOXX", "AAPL", "ORCL", "AVGO",
    "NOW", "WMT", "CRWV", "MSFT", "CCJ", "PLTR", "CEG", "GLD", "KLAR",
]


class TwoMessages(BaseModel):
    stock_view: str = Field(..., max_length=3500,
                            description="The 📈 stock-view Telegram message, plain language")
    portfolio_fit: str = Field(..., max_length=3500,
                               description="The 📂 portfolio-fit Telegram message, plain language")


REWRITE_PROMPT = """You rewrite trading research messages into PLAIN ENGLISH
for a smart business owner who is NOT a finance professional. They are
intelligent but do not know finance jargon.

You are given two existing messages (a stock view and a portfolio-fit note)
plus the key facts. Rewrite BOTH into clean, simple, mobile-friendly
messages. Keep every fact accurate — do not invent numbers, only simplify
the language.

### MANDATORY PLAIN-LANGUAGE RULES
1. No jargon. Remove or explain in plain words: FCF/NI conversion, blended
   margins, basis points/bps, put wall, gamma, re-rating, ARPU, multiple,
   P/E premium, TTM, YoY (say "vs a year ago"), gross exposure, notional.
2. Every number gets context. Not "-$185.9M over 30d" → "executives sold
   $186 million of stock in the last month". Not "37x P/E" → "expensive —
   priced at about 37 years of current profit".
3. Short lines. Scannable on a phone.
4. Keep all the real facts: prices, target, stop, the catalyst, the risk,
   the rotation candidate.

### FACTS
Ticker: {symbol}
Decision: {decision} | Confidence: {conviction}/10 | Suggested size: {size}%
Entry: {entry} | 6-month target: {target} | Stop: {stop}

### OLD STOCK VIEW (rewrite this — keep facts, fix language)
{old_stock}

### OLD PORTFOLIO FIT (rewrite this — keep facts, fix language)
{old_portfolio}

### OUTPUT — produce exactly two fields:

**stock_view** — use this exact format:
🟢 {symbol} — BUY   (or ⚠ WATCH / 🔴 AVOID — match the old verdict)
Confidence: X out of 10

Why it's a buy:
<2-3 plain sentences>

What could go wrong:
<1-2 plain sentences — the biggest risk>

What to watch:
<the key upcoming event, plain>

The trade:
• Buy around $X
• 6-month target: $Y (about +Z%)
• Sell to cut losses at: $S (about -W%)

Exit early if: <plain version of exit conditions>

**portfolio_fit** — use this exact format:
📂 {symbol} — Portfolio fit
<one-line plain verdict>

Your situation right now:
<1-2 plain sentences on how invested they are>

To add this, sell:
<specific stock + plain reason, OR "Nothing — you have room", OR "Skip for now">

Bottom line:
<single clear action in plain words>
"""


def _money(v) -> str:
    if v is None:
        return "n/a"
    try:
        return f"${float(v):,.2f}"
    except (TypeError, ValueError):
        return str(v)


def latest_date_dir(symbol: str) -> Optional[Path]:
    sym_dir = AI_RESEARCH_DIR / symbol.upper()
    if not sym_dir.exists():
        return None
    dates = sorted((p for p in sym_dir.iterdir() if p.is_dir()),
                   key=lambda p: p.name, reverse=True)
    return dates[0] if dates else None


async def reformat_one(symbol: str, send: bool, dry_run: bool) -> dict:
    folder = latest_date_dir(symbol)
    if folder is None:
        return {"symbol": symbol, "status": "no_folder"}
    raw_path = folder / "_raw.json"
    if not raw_path.exists():
        return {"symbol": symbol, "status": "no_raw"}

    raw = json.loads(raw_path.read_text(encoding="utf-8"))
    pm = raw.get("pm") or {}
    if not pm:
        return {"symbol": symbol, "status": "no_pm"}

    prompt = REWRITE_PROMPT.format(
        symbol=symbol,
        decision=pm.get("decision", "?"),
        conviction=pm.get("conviction_score", "?"),
        size=pm.get("recommended_size_pct", "?"),
        entry=_money(pm.get("entry_price")),
        target=_money(pm.get("target_price")),
        stop=_money(pm.get("stop_loss")),
        old_stock=(pm.get("telegram_message") or "")[:2000],
        old_portfolio=(pm.get("telegram_portfolio_message") or "")[:2000],
    )

    client = claude_sonnet(max_tokens=2000)
    result = await invoke_structured_or_freetext(client, prompt, TwoMessages)
    new = result.instance

    if dry_run:
        print(f"\n===== {symbol} (DRY RUN) =====")
        print(new.stock_view)
        print("\n" + new.portfolio_fit)
        return {"symbol": symbol, "status": "dry_run"}

    # Write back into _raw.json
    pm["telegram_message"] = new.stock_view
    pm["telegram_portfolio_message"] = new.portfolio_fit
    raw["pm"] = pm
    raw_path.write_text(json.dumps(raw, default=str, ensure_ascii=False, indent=2),
                        encoding="utf-8")

    sent = False
    if send:
        from engine.live.schemas import PMDecision as _PM
        from engine.live.telegram import telegram
        try:
            pm_obj = _PM.model_validate(pm)
            client_t = telegram()
            sent = await client_t.send_pm_verdict(symbol, pm_obj)
        except Exception as e:  # noqa: BLE001
            print(f"  !! {symbol} telegram send failed: {e}")

    return {"symbol": symbol, "status": "done", "sent": sent}


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tickers")
    parser.add_argument("--no-send", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    tickers = (
        [s.strip().upper() for s in args.tickers.split(",")]
        if args.tickers else list(DEFAULT_TICKERS)
    )
    send = not args.no_send and not args.dry_run

    print(f"Reformatting {len(tickers)} tickers "
          f"(send={send}, dry_run={args.dry_run})")

    for i, sym in enumerate(tickers, 1):
        try:
            res = await reformat_one(sym, send, args.dry_run)
            print(f"[{i}/{len(tickers)}] {sym}: {res['status']}"
                  + (f" sent={res.get('sent')}" if 'sent' in res else ""))
        except Exception as e:  # noqa: BLE001
            print(f"[{i}/{len(tickers)}] {sym}: ERROR {e}")
        # Small pause to space out Telegram + respect rate limits
        if send and i < len(tickers):
            await asyncio.sleep(2.0)

    print("\nDone.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
