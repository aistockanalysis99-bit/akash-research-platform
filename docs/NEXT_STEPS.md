# NEXT_STEPS.md — Phase 2 Developer Handoff

This document describes what comes after Phase 1 (the completed backtester).
It is written for a developer picking up Phase 2 cold, with or without an LLM assistant.

---

## What is already done (Phase 1)

- Full event-driven backtest engine with look-ahead protection
- Vol-normalized multi-horizon momentum strategy
- Hybrid portfolio layer (slot cap + vol target + gross cap)
- FastAPI backend with background job execution
- NiceGUI interactive web UI (6 pages, all charts)
- SQLite run history + trade log
- Parquet OHLCV cache with incremental FMP refresh
- 57/57 tests passing

The Phase 1 codebase is **production-ready as a local research tool**.
Phase 2 adds live signal delivery without touching any of the existing engine code.

---

## Phase 2 goal

Every trading day at 16:30 ET:

1. Pull latest EOD data for the S&P 100 from FMP (incremental cache update)
2. Run the momentum strategy signal computation (no full backtest — signals only)
3. For each new entry signal, ask Claude to generate a brief plain-English analysis
4. Send signals + analysis to a Telegram channel/bot

---

## New files to create

### `engine/live/live_runner.py`

The main live signal runner. Skeleton:

```python
"""Live signal runner — Phase 2 entry point."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from engine.config import FMP_API_KEY
from engine.data.cache import refresh_universe
from engine.data.loader import load_universe_panel
from engine.data.universe import SP100
from engine.strategy.signal import compute_signal_columns
from engine.live.claude_client import analyze_signal
from engine.live.telegram_client import send_signal_message


async def run_live_signals() -> None:
    """Called daily at 16:30 ET by the scheduler."""
    today = datetime.now(timezone.utc).date()

    # 1. Refresh data (incremental — only fetches new bars)
    await refresh_universe(SP100, "1D", years=1)

    # 2. Load panel
    panel = load_universe_panel(SP100, "1D", lookback_bars=300)

    # 3. Compute signals
    new_signals = []
    for symbol, df in panel.items():
        df = compute_signal_columns(df)
        last = df.iloc[-1]
        if last["breakout_long"] and last["bull_state"] and last["mom_score"] > 0.25:
            new_signals.append({
                "symbol": symbol,
                "score": round(float(last["mom_score"]), 3),
                "close": round(float(last["close"]), 2),
                "atr": round(float(last["atr"]), 3),
                "date": str(today),
            })

    if not new_signals:
        return

    # 4. Enrich with Claude analysis
    for sig in new_signals:
        sig["analysis"] = await analyze_signal(sig)

    # 5. Deliver via Telegram
    for sig in new_signals:
        await send_signal_message(sig)
```

---

### `engine/live/claude_client.py`

Calls the Claude API (Anthropic SDK) to generate a 2–3 sentence signal analysis.

```python
"""Claude API client for signal analysis."""
from __future__ import annotations

import anthropic

from engine.config import CLAUDE_API_KEY  # add to .env + config.py


_client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)


async def analyze_signal(signal: dict) -> str:
    """Return a brief plain-English analysis of the entry signal."""
    prompt = (
        f"A momentum breakout entry signal just triggered for {signal['symbol']}.\n"
        f"Score: {signal['score']} (vol-normalized multi-horizon momentum)\n"
        f"Close: ${signal['close']}, ATR: {signal['atr']}\n\n"
        "In 2-3 sentences, explain what this signal means for a trend-following trader. "
        "Be concise and practical. Do not give investment advice."
    )
    message = _client.messages.create(
        model="claude-opus-4-5",
        max_tokens=200,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text
```

**Required `.env` additions:**
```
CLAUDE_API_KEY=sk-ant-...
```

**Required `engine/config.py` additions:**
```python
CLAUDE_API_KEY: str = os.getenv("CLAUDE_API_KEY", "")
```

---

### `engine/live/telegram_client.py`

Sends formatted messages to a Telegram bot.

```python
"""Telegram delivery client."""
from __future__ import annotations

import httpx

from engine.config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID  # add to .env + config.py


TELEGRAM_API = "https://api.telegram.org"


async def send_signal_message(signal: dict) -> None:
    text = (
        f"📈 *{signal['symbol']}* — Momentum Breakout\n"
        f"Score: `{signal['score']}` | Close: `${signal['close']}` | ATR: `{signal['atr']}`\n\n"
        f"{signal['analysis']}"
    )
    async with httpx.AsyncClient() as client:
        await client.post(
            f"{TELEGRAM_API}/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": text,
                "parse_mode": "Markdown",
            },
        )
```

**Required `.env` additions:**
```
TELEGRAM_BOT_TOKEN=<bot_token_from_BotFather>
TELEGRAM_CHAT_ID=<your_channel_or_group_id>
```

**Required `engine/config.py` additions:**
```python
TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID: str = os.getenv("TELEGRAM_CHAT_ID", "")
```

---

### `engine/live/scheduler.py`

APScheduler job wiring. Can be started standalone or imported into `run.py`.

```python
"""APScheduler: fire live_runner daily at 16:30 ET."""
from __future__ import annotations

import asyncio
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from engine.live.live_runner import run_live_signals

logger = logging.getLogger(__name__)


def create_scheduler() -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone="America/New_York")
    scheduler.add_job(
        run_live_signals,
        CronTrigger(hour=16, minute=30, day_of_week="mon-fri"),
        id="live_signals",
        replace_existing=True,
        misfire_grace_time=300,  # 5-minute window
    )
    return scheduler


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    scheduler = create_scheduler()
    scheduler.start()
    logger.info("Scheduler running — will fire at 16:30 ET on market days")
    asyncio.get_event_loop().run_forever()
```

**New dependency:** `apscheduler>=3.10`

---

## Changes to existing files

### `run.py`

Optionally start the scheduler alongside the API + UI:

```python
# Add near the bottom of run.py, before ui.run():
if os.getenv("ENABLE_LIVE_SIGNALS", "false").lower() == "true":
    from engine.live.scheduler import create_scheduler
    scheduler = create_scheduler()
    scheduler.start()
```

### `.env`

Add:
```
ENABLE_LIVE_SIGNALS=false   # flip to true when ready
CLAUDE_API_KEY=sk-ant-...
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...
```

### `pyproject.toml` / `pip install`

Add:
```
apscheduler>=3.10
anthropic>=0.25
```

---

## Telegram bot setup (one-time)

1. Open Telegram, search for `@BotFather`
2. `/newbot` → follow prompts → copy the **bot token** → `TELEGRAM_BOT_TOKEN`
3. Create a channel or group. Add your bot as an admin.
4. Get the chat ID:
   - For a channel: `@your_channel_name` (with @) works as the chat ID for public channels
   - For a group: send a message, then call `https://api.telegram.org/bot<TOKEN>/getUpdates` to find the numeric ID
5. Set `TELEGRAM_CHAT_ID` in `.env`

---

## Testing Phase 2 before going live

```bash
# Smoke-test the live runner manually (outside market hours is fine)
python -c "
import asyncio
from engine.live.live_runner import run_live_signals
asyncio.run(run_live_signals())
"
```

This will refresh data, compute signals, call Claude, and send Telegram messages if any signals fire.
If no signals fire (common outside trending conditions), add a forced test signal in `live_runner.py`
temporarily.

---

## Architecture diagram (Phase 1 + Phase 2)

```
                      ┌─────────────────────────────┐
                      │   Shared Engine Layer         │
                      │  engine/data/    (FMP, cache) │
                      │  engine/strategy/ (signals)   │
                      │  engine/core/    (portfolio)  │
                      │  engine/metrics/ (KPIs)       │
                      │  engine/db/      (SQLite)     │
                      └───────────┬─────────────┬─────┘
                                  │             │
              ┌───────────────────▼──┐     ┌────▼─────────────────────┐
              │  Phase 1: Backtester │     │  Phase 2: Live Runner     │
              │  api/  (FastAPI)      │     │  engine/live/             │
              │  ui/   (NiceGUI)      │     │  ├── live_runner.py       │
              │  scripts/             │     │  ├── claude_client.py     │
              └───────────────────────┘     │  ├── telegram_client.py  │
                                            │  └── scheduler.py        │
                                            └──────────────────────────┘
```

---

## Key design constraints (do not change)

- **No look-ahead bias**: signals at close of bar T, fills at open of bar T+1 — live runner must respect this
- **Same strategy code**: `compute_signal_columns()` is shared between backtest and live — do not fork it
- **FMP `/stable/` endpoints only**: `/api/v3/` returns 403 on this account
- **Whole shares by default**: `fractional_shares=False` in `StrategyParams`
- **Long-only in v1**: no short signals, no derivatives

---

## Estimated Phase 2 effort

| Task | Estimate |
|---|---|
| `live_runner.py` | 1–2 hours |
| `claude_client.py` | 30 min |
| `telegram_client.py` | 30 min |
| `scheduler.py` | 30 min |
| `.env` + `config.py` updates | 15 min |
| End-to-end smoke test + Telegram bot setup | 1 hour |
| **Total** | **~4–5 hours** |
