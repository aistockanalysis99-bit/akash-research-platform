"""Sequentially analyze every ticker in the watchlist.

Posts one /ai/analyze job to the running FastAPI server, polls until that
job reports complete (or failed), then moves to the next. Writes a
human-readable progress log so the user can `tail -f` to follow along.

Usage:
    python scripts/batch_analyze_watchlist.py [--tickers SYM1,SYM2,...]
                                                [--skip SYM1,SYM2,...]

Default ticker list is the full 17-name watchlist; flags let you override.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

import httpx

# Force UTF-8 stdout on Windows (cp1252 default would die on unicode)
try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:  # noqa: BLE001
    pass

API = "http://127.0.0.1:8001"
POLL_INTERVAL_S = 15
MAX_JOB_SECONDS = 900           # 15-min hard timeout per ticker
INTER_JOB_PAUSE_S = 5            # Cooldown between jobs

DEFAULT_TICKERS = [
    "INTC", "MU", "AMD", "NVDA", "SOXX", "AAPL", "ORCL", "AVGO",
    "NOW", "WMT", "CRWV", "MSFT", "CCJ", "PLTR", "CEG", "GLD", "KLAR",
]

LOG_PATH = Path(__file__).resolve().parent.parent / "logs" / "batch_analyze.log"
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def log(msg: str) -> None:
    line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line, flush=True)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def submit(symbol: str) -> str | None:
    try:
        r = httpx.post(
            f"{API}/ai/analyze",
            json={"symbol": symbol, "source": "manual",
                  "notes": "batch backfill (M19 — full watchlist)"},
            timeout=30,
        )
        r.raise_for_status()
        return r.json()["job_id"]
    except Exception as e:  # noqa: BLE001
        log(f"  !! submit failed for {symbol}: {e}")
        return None


def poll(job_id: str, symbol: str) -> dict:
    """Block until the job hits complete or failed; return final state."""
    start = time.time()
    last_stage = None
    while True:
        try:
            j = httpx.get(f"{API}/ai/analyze/{job_id}", timeout=30).json()
        except Exception as e:  # noqa: BLE001
            log(f"  !! poll error for {symbol}: {e}")
            time.sleep(POLL_INTERVAL_S)
            continue

        status = j.get("status")
        stage = j.get("current_stage")
        if stage and stage != last_stage:
            log(f"  {symbol} :: {stage}")
            last_stage = stage

        if status in ("complete", "failed"):
            return j
        if time.time() - start > MAX_JOB_SECONDS:
            log(f"  !! {symbol} exceeded {MAX_JOB_SECONDS}s — moving on")
            return j

        time.sleep(POLL_INTERVAL_S)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tickers", help="Comma-separated ticker list (overrides default)")
    parser.add_argument("--skip", help="Comma-separated tickers to skip")
    args = parser.parse_args()

    tickers = (
        [s.strip().upper() for s in args.tickers.split(",")]
        if args.tickers else list(DEFAULT_TICKERS)
    )
    if args.skip:
        skip = {s.strip().upper() for s in args.skip.split(",")}
        tickers = [t for t in tickers if t not in skip]

    log("=" * 64)
    log(f"BATCH START — {len(tickers)} tickers: {', '.join(tickers)}")
    log("=" * 64)

    # Health check first
    try:
        h = httpx.get(f"{API}/health", timeout=10).json()
        log(f"API health: {h}")
    except Exception as e:  # noqa: BLE001
        log(f"!! API not reachable at {API}: {e}")
        return 1

    summary = []
    overall_start = time.time()

    for i, sym in enumerate(tickers, 1):
        log(f"\n[{i}/{len(tickers)}] >>> {sym} <<<")
        t0 = time.time()
        job_id = submit(sym)
        if not job_id:
            summary.append({"symbol": sym, "status": "submit_failed"})
            continue

        log(f"  job_id={job_id}")
        final = poll(job_id, sym)
        dur = int(time.time() - t0)

        verdict = final.get("verdict") or {}
        decision = verdict.get("decision", "—")
        conviction = verdict.get("conviction", "—")
        size_pct = verdict.get("size_pct", "—")
        signal_date = final.get("signal_date", "?")
        status = final.get("status", "?")
        err = (final.get("error") or "")[:120]

        if status == "complete":
            log(f"  [OK] {sym} complete in {dur}s -- {decision} {conviction}/10 @ {size_pct}%")
        else:
            log(f"  [FAIL] {sym} {status} after {dur}s -- {err}")

        summary.append({
            "symbol": sym, "status": status, "decision": decision,
            "conviction": conviction, "size_pct": size_pct,
            "signal_date": signal_date, "duration_s": dur,
            "error": err if status == "failed" else "",
        })

        # Pause between jobs (rate-limit hygiene)
        if i < len(tickers):
            time.sleep(INTER_JOB_PAUSE_S)

    elapsed = int(time.time() - overall_start)
    log("\n" + "=" * 64)
    log(f"BATCH COMPLETE in {elapsed//60}m{elapsed%60:02d}s")
    log("=" * 64)
    log(f"\n{'Symbol':<8} {'Status':<10} {'Decision':<10} {'Conv':<6} {'Size':<6} {'Time':<6}")
    for row in summary:
        log(f"{row['symbol']:<8} {row['status']:<10} "
            f"{row.get('decision','—'):<10} {str(row.get('conviction','—')):<6} "
            f"{str(row.get('size_pct','—')):<6} {row.get('duration_s','?')}s")

    # JSON sidecar for the UI to pick up
    json_out = LOG_PATH.with_suffix(".json")
    json_out.write_text(json.dumps({
        "started_at": datetime.now().isoformat(),
        "total_seconds": elapsed,
        "ticker_count": len(tickers),
        "complete_count": sum(1 for r in summary if r["status"] == "complete"),
        "failed_count": sum(1 for r in summary if r["status"] != "complete"),
        "rows": summary,
    }, indent=2), encoding="utf-8")
    log(f"\nJSON summary written to {json_out}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
