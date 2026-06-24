"""Full-pipeline bake-off.

Runs the COMPLETE 11-agent pipeline end-to-end on each model stack
(Production = Gemini+Claude, plus DeepSeek-R1 / GLM-5.2 / Qwen via OpenRouter)
for the same stock, then returns an agent-by-agent comparison — so we can judge
whether the open models can run our WHOLE system before buying a DGX.

Runs in a background thread (jobs are long: ~5–15 min). Test-mode pipelines
don't fire Telegram, don't build profiles, and write to an isolated namespace.
"""
from __future__ import annotations

import logging
import threading
import time
import uuid
from typing import Any, Optional

log = logging.getLogger(__name__)

# The stacks to compare. (display name, OpenRouter model id or None=production)
STACKS: list[tuple[str, Optional[str]]] = [
    ("Production (Gemini + Claude)", None),
    ("DeepSeek-R1", "deepseek/deepseek-r1"),
    ("GLM-5.2", "z-ai/glm-5.2"),
    ("Qwen 3.7 Plus", "qwen/qwen3.7-plus"),
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


def _run_thread(job_id: str, symbol: str) -> None:
    import asyncio
    try:
        asyncio.run(_run_async(job_id, symbol))
    except Exception as e:  # noqa: BLE001
        log.exception("bakeoff job failed")
        _jobs[job_id].update(status="failed", error=str(e)[:300])


def start_bakeoff(symbol: str) -> str:
    symbol = symbol.upper().strip()
    job_id = uuid.uuid4().hex[:12]
    _jobs[job_id] = {
        "job_id": job_id, "symbol": symbol, "status": "running",
        "stacks": [], "models": [n for n, _ in STACKS],
    }
    threading.Thread(target=_run_thread, args=(job_id, symbol), daemon=True).start()
    return job_id


def get_job(job_id: str) -> Optional[dict[str, Any]]:
    return _jobs.get(job_id)
