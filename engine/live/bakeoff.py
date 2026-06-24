"""Full-pipeline bake-off.

Runs the COMPLETE 11-agent pipeline end-to-end on each model stack
(Production = Gemini+Claude, plus DeepSeek-R1 / GLM-5.2 / Qwen via OpenRouter)
for the same stock, then returns an agent-by-agent comparison — so we can judge
whether the open models can run our WHOLE system before buying a DGX.

Runs in a background thread (jobs are long: ~5–15 min). Test-mode pipelines
don't fire Telegram, don't build profiles, and write to an isolated namespace.
"""
from __future__ import annotations

import json
import logging
import threading
import time
import uuid
from datetime import datetime
from typing import Any, Optional

from ..db.schema import get_connection

log = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Persistence — bake-off runs survive restarts and feed the scorecard.
# --------------------------------------------------------------------------- #

def _ensure_table() -> None:
    conn = get_connection()
    try:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS bakeoff_runs (
                job_id TEXT PRIMARY KEY,
                symbol TEXT,
                created_at TEXT,
                status TEXT,
                total_cost_usd REAL,
                results_json TEXT
            )"""
        )
        conn.commit()
    finally:
        conn.close()


def _save_run(job: dict[str, Any]) -> None:
    try:
        _ensure_table()
        conn = get_connection()
        try:
            conn.execute(
                """INSERT OR REPLACE INTO bakeoff_runs
                   (job_id, symbol, created_at, status, total_cost_usd, results_json)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (job["job_id"], job["symbol"],
                 job.get("created_at") or datetime.utcnow().isoformat(),
                 job.get("status"), job.get("total_cost_usd"),
                 json.dumps(job.get("stacks") or [])),
            )
            conn.commit()
        finally:
            conn.close()
    except Exception as e:  # noqa: BLE001 — persistence must never break a run
        log.warning("bakeoff save failed: %s", e)


def _load_run(job_id: str) -> Optional[dict[str, Any]]:
    _ensure_table()
    conn = get_connection()
    try:
        r = conn.execute(
            "SELECT * FROM bakeoff_runs WHERE job_id=?", (job_id,)
        ).fetchone()
    finally:
        conn.close()
    if not r:
        return None
    return {
        "job_id": r["job_id"], "symbol": r["symbol"], "status": r["status"],
        "created_at": r["created_at"], "total_cost_usd": r["total_cost_usd"],
        "stacks": json.loads(r["results_json"] or "[]"),
    }


def list_bakeoffs(limit: int = 60) -> list[dict[str, Any]]:
    """Compact history: one row per past run with each stack's verdict."""
    _ensure_table()
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT job_id, symbol, created_at, status, total_cost_usd, results_json "
            "FROM bakeoff_runs ORDER BY created_at DESC LIMIT ?", (limit,),
        ).fetchall()
    finally:
        conn.close()
    out = []
    for r in rows:
        stacks = json.loads(r["results_json"] or "[]")
        out.append({
            "job_id": r["job_id"], "symbol": r["symbol"],
            "created_at": r["created_at"], "status": r["status"],
            "total_cost_usd": r["total_cost_usd"],
            "verdicts": [{"name": s.get("name"), "decision": s.get("decision"),
                          "conviction": s.get("conviction")} for s in stacks],
        })
    return out


def compute_scorecard() -> dict[str, Any]:
    """Aggregate across all stored runs: per-model agreement vs Production,
    avg conviction, valid-output %, avg cost, avg speed."""
    _ensure_table()
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT results_json FROM bakeoff_runs WHERE status='complete'"
        ).fetchall()
    finally:
        conn.close()

    agg: dict[str, dict[str, float]] = {}

    def bucket(name: str) -> dict[str, float]:
        return agg.setdefault(name, {
            "runs": 0, "agree": 0, "compared": 0, "conv_sum": 0, "conv_n": 0,
            "valid": 0, "valid_n": 0, "cost_sum": 0.0, "cost_n": 0,
            "secs_sum": 0.0, "secs_n": 0,
        })

    n_runs = 0
    for r in rows:
        stacks = json.loads(r["results_json"] or "[]")
        if not stacks:
            continue
        n_runs += 1
        prod = next((s for s in stacks if s.get("model") == "production"), None)
        prod_dec = (prod or {}).get("decision")
        for s in stacks:
            name = "Production" if s.get("model") == "production" else s.get("name")
            b = bucket(name)
            b["runs"] += 1
            b["valid_n"] += 1
            if s.get("ok"):
                b["valid"] += 1
                if s.get("conviction") is not None:
                    b["conv_sum"] += s["conviction"]; b["conv_n"] += 1
                if s.get("cost_usd"):
                    b["cost_sum"] += s["cost_usd"]; b["cost_n"] += 1
                if s.get("secs"):
                    b["secs_sum"] += s["secs"]; b["secs_n"] += 1
                if name != "Production" and prod_dec and s.get("decision"):
                    b["compared"] += 1
                    if s["decision"] == prod_dec:
                        b["agree"] += 1

    def pct(a, n): return round(a / n * 100) if n else None
    def avg(a, n, d=1): return round(a / n, d) if n else None

    out_rows = []
    for name, b in agg.items():
        out_rows.append({
            "model": name,
            "runs": b["runs"],
            "agreement_pct": pct(b["agree"], b["compared"]),
            "avg_conviction": avg(b["conv_sum"], b["conv_n"]),
            "valid_pct": pct(b["valid"], b["valid_n"]),
            "avg_cost": avg(b["cost_sum"], b["cost_n"], 3),
            "avg_secs": avg(b["secs_sum"], b["secs_n"], 0),
        })
    # production first, then by agreement desc
    out_rows.sort(key=lambda x: (x["model"] != "Production", -(x["agreement_pct"] or 0)))
    return {"runs_total": n_runs, "rows": out_rows}

# The stacks to compare. (display name, OpenRouter model id or None=production)
STACKS: list[tuple[str, Optional[str]]] = [
    ("Production (Gemini + Claude)", None),
    ("DeepSeek-R1", "deepseek/deepseek-r1"),
    ("GLM-5.2", "z-ai/glm-5.2"),
    ("Qwen 3.7 Plus", "qwen/qwen3.7-plus"),
    ("Fugu Ultra", "sakana/fugu-ultra"),
]

# In-memory job store (fine for a manual tool on a single instance).
_jobs: dict[str, dict[str, Any]] = {}


def _g(obj: Any, attr: str, default=None):
    return getattr(obj, attr, default) if obj is not None else default


def _summarize_stack(name: str, model: Optional[str], state: dict,
                     cost: float, secs: float) -> dict[str, Any]:
    """Compact, comparable view of one full-pipeline run."""
    pm = state.get("pm")
    return {
        "name": name,
        "model": model or "production",
        "ok": pm is not None,
        "cost_usd": round(cost, 4),
        "secs": round(secs, 0),
        "error": None,
        # final verdict
        "decision": _g(pm, "decision"),
        "conviction": _g(pm, "conviction_score"),
        "position_pct_of_fund": _g(pm, "position_pct_of_fund"),
        "stop_price": _g(pm, "stop_price"),
        "stop_pct": _g(pm, "stop_pct"),
        "sizing_rationale": _g(pm, "sizing_rationale"),
        "stop_rationale": _g(pm, "stop_rationale"),
        "telegram_message": _g(pm, "telegram_message"),
        "telegram_portfolio_message": _g(pm, "telegram_portfolio_message"),
        "exit_thesis": _g(pm, "exit_thesis"),
        # agent-by-agent
        "agents": {
            "fundamental": {"score": _g(state.get("fundamental"), "fundamental_score"),
                            "summary": _g(state.get("fundamental"), "summary")},
            "news": {"score": _g(state.get("news"), "news_risk_score"),
                     "summary": _g(state.get("news"), "summary")},
            "technical": {"score": _g(state.get("technical"), "technical_strength"),
                          "summary": _g(state.get("technical"), "summary")},
            "institutional_flow": {"score": _g(state.get("institutional_flow"), "smart_money_score"),
                                   "summary": _g(state.get("institutional_flow"), "summary")},
            "options_structure": {"score": _g(state.get("options_structure"), "dealer_positioning"),
                                  "summary": _g(state.get("options_structure"), "summary")},
            "macro_regime": {"score": _g(state.get("macro_regime"), "regime_risk_score"),
                             "summary": _g(state.get("macro_regime"), "summary")},
            "bull": {"score": _g(state.get("bull"), "conviction_self_rated"),
                     "summary": _g(state.get("bull"), "strongest_point")},
            "bear": {"score": _g(state.get("bear"), "conviction_self_rated"),
                     "summary": _g(state.get("bear"), "strongest_point")},
            "judge": {"score": _g(state.get("judge"), "conviction_score"),
                      "summary": (f"Winner: {_g(state.get('judge'), 'winner')}. "
                                  f"{_g(state.get('judge'), 'synthesis') or ''}")},
            "risk": {"score": _g(state.get("risk"), "verdict"),
                     "summary": _g(state.get("risk"), "summary")},
            "pm": {"score": _g(pm, "conviction_score"),
                   "summary": _g(pm, "audit_note")},
        },
    }


async def _run_async(job_id: str, symbol: str) -> None:
    import asyncio
    from .pipeline import run_full_pipeline

    async def one(name: str, model: Optional[str]) -> dict[str, Any]:
        sink: list[float] = []
        t0 = time.monotonic()
        try:
            state = await run_full_pipeline(
                symbol, source="manual", model_override=model,
                test_mode=True, cost_sink=sink,
            )
            return _summarize_stack(name, model, state, sum(sink), time.monotonic() - t0)
        except Exception as e:  # noqa: BLE001
            log.warning("bakeoff stack %s failed: %s", name, e)
            return {"name": name, "model": model or "production", "ok": False,
                    "error": str(e)[:300], "cost_usd": round(sum(sink), 4),
                    "secs": round(time.monotonic() - t0, 0), "agents": {}}

    results = await asyncio.gather(*[one(n, m) for n, m in STACKS])
    _jobs[job_id].update(
        status="complete",
        stacks=list(results),
        total_cost_usd=round(sum((r.get("cost_usd") or 0) for r in results), 4),
    )
    _save_run(_jobs[job_id])   # persist so it survives restarts + feeds scorecard


def _run_thread(job_id: str, symbol: str) -> None:
    import asyncio
    try:
        asyncio.run(_run_async(job_id, symbol))
    except Exception as e:  # noqa: BLE001
        log.exception("bakeoff job failed")
        _jobs[job_id].update(status="failed", error=str(e)[:300])
        _save_run(_jobs[job_id])


def start_bakeoff(symbol: str) -> str:
    symbol = symbol.upper().strip()
    job_id = uuid.uuid4().hex[:12]
    _jobs[job_id] = {
        "job_id": job_id, "symbol": symbol, "status": "running",
        "stacks": [], "models": [n for n, _ in STACKS],
        "created_at": datetime.utcnow().isoformat(),
    }
    threading.Thread(target=_run_thread, args=(job_id, symbol), daemon=True).start()
    return job_id


def get_job(job_id: str) -> Optional[dict[str, Any]]:
    # In-memory (running or recent) first; else load the persisted run.
    return _jobs.get(job_id) or _load_run(job_id)
