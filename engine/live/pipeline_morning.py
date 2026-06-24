"""Morning pipeline — daily position-management cycle.

Topology:
                              START
                                |
                  snapshot portfolio + market data
                                |
                            Regime (10)
                                |
                         (any open positions?)
                          /                \
                       no                   yes
                        |                    |
                        |              Position Monitor (11)
                        |                    |
                        |          (per EXIT flag in parallel)
                        |                    |
                        |              Exit Confirmer (12)
                        |                    |
                        |          (confirmed exits → close in portfolio)
                        |                    |
                        +-----.--------------+
                              |
                       Morning Briefing (13)
                              |
                            END

Artifacts persist to ai_research/_morning/{YYYY-MM-DD}/*.md.
Position closes apply to virtual_positions immediately.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import date
from typing import Any, Callable, Optional

from .agents.exit_confirmer import ExitConfirmerAgent
from .agents.morning_briefing import MorningBriefingAgent
from .agents.position_monitor import PositionMonitorAgent
from .agents.regime import RegimeAgent
from .data.market_data import fetch_market_data
from .file_store import FileStore
from .llm.claude import claude_sonnet
from .llm.gemini import gemini_flash, gemini_pro
from .morning_state import MorningState, new_morning_state
from .portfolio import VirtualPortfolio

log = logging.getLogger(__name__)


async def run_morning_cycle(
    progress: Optional[Callable[..., None]] = None,
) -> MorningState:
    """Run the full 4-agent morning cycle. Returns the final MorningState."""
    today = date.today().isoformat()
    fs = FileStore()

    def _step(stage: str, msg: str, **extra: Any) -> None:
        log.info("[morning:%s] %s", stage, msg)
        if progress:
            try:
                progress(stage, msg, **extra)
            except Exception:  # noqa: BLE001
                pass

    # 0. Init + portfolio snapshot
    state = new_morning_state(today)
    _step("init", f"snapshotting portfolio for {today}")
    portfolio = VirtualPortfolio()
    try:
        # Refresh live prices FIRST so stop/exit evaluation uses today's prices,
        # not a stale snapshot. (This also fires notify-only stop alerts.)
        try:
            _step("refresh", "refreshing live position prices...")
            res = await portfolio.refresh_all()
            _step("refresh",
                  f"refreshed {res.get('refreshed', 0)} position(s), "
                  f"{len(res.get('stop_alerts', []))} stop alert(s)")
        except Exception as e:  # noqa: BLE001
            _step("refresh", f"price refresh failed (using last-known): {e}")
        state["open_positions"] = portfolio.list_open()
        state["portfolio_snapshot"] = portfolio.equity_snapshot()
    finally:
        portfolio.close_conn()
    n_open = len(state["open_positions"])
    _step("init", f"portfolio has {n_open} open positions")

    # 1. Fetch market data
    _step("market_data", "fetching SPY + VIXY + sector ETFs...")
    state["market_data"] = await fetch_market_data()
    fetched = []
    if state["market_data"].get("spy"):
        fetched.append("SPY")
    if state["market_data"].get("volatility_proxy"):
        fetched.append("VIXY")
    fetched += list((state["market_data"].get("sectors") or {}).keys())
    _step("market_data", f"fetched: {', '.join(fetched)}")

    # 2. Agent 10: Regime
    _step("regime", "starting Market Regime Detector",
          agent="regime", model="gemini-2.5-pro")
    regime_agent = RegimeAgent(gemini_pro(), fs)
    regime_state_like = await _run_agent_with_morning_writes(
        regime_agent, state, "regime", fs, today,
    )
    state["regime"] = regime_state_like.get("regime")
    if state["regime"]:
        _step("regime", f"regime = {state['regime'].regime} "
                         f"(confidence {state['regime'].regime_confidence}/10)",
              agent="regime", action="complete",
              metrics={"regime": state["regime"].regime,
                       "confidence": state["regime"].regime_confidence})

    # 3. Agent 11: Position Monitor (skip if no positions)
    if n_open == 0:
        _step("position_monitor", "skipped — no open positions to review")
    else:
        _step("position_monitor",
              f"starting batch review of {n_open} positions",
              agent="position_review", model="gemini-2.5-pro")
        monitor_agent = PositionMonitorAgent(gemini_pro(), fs)
        monitor_state_like = await _run_agent_with_morning_writes(
            monitor_agent, state, "position_review", fs, today,
        )
        review = monitor_state_like.get("position_review")
        state["position_review"] = review
        if review:
            actions = [r.action for r in review.reviews]
            counts = {a: actions.count(a) for a in set(actions)}
            _step("position_monitor",
                  f"review complete — {counts}",
                  agent="position_review", action="complete",
                  metrics={"counts": counts, "total": len(review.reviews)})
            # Lifecycle: apply AI-set stops to positions + notify risk suggestions.
            try:
                await _apply_lifecycle(review.reviews, _step)
            except Exception as e:  # noqa: BLE001
                _step("lifecycle", f"risk re-rating failed (non-fatal): {e}")

    # 4. Agent 12: Exit Confirmer (one per EXIT flag, parallel)
    review = state.get("position_review")
    confirmations: dict[str, Any] = {}
    if review and review.reviews:
        exit_flags = [r for r in review.reviews if r.action == "EXIT"]
        if exit_flags:
            _step("exit_confirmer",
                  f"second-opinion needed on {len(exit_flags)} exit flag(s)",
                  agent="exit_confirmer", model="claude-sonnet-4-6")
            confirmations = await _run_exit_confirmers(
                state, exit_flags, fs, today, _step,
            )
        else:
            _step("exit_confirmer", "no exits flagged — skipping")
    state["exit_confirmations"] = confirmations

    # 5. Surface confirmed-exit suggestions — NEVER auto-close.
    #    The client manages every exit manually; the system only notifies.
    suggested_exits: list[dict[str, Any]] = []
    if confirmations:
        for symbol, conf in confirmations.items():
            if conf.verdict != "CONFIRM_EXIT":
                continue
            pos = next((p for p in state["open_positions"]
                        if p["symbol"] == symbol), None)
            if pos is None:
                continue
            suggested_exits.append({
                "symbol": symbol,
                "position_id": pos["id"],
                "urgency": getattr(conf, "urgency", None),
                "reason": getattr(conf, "exit_reasoning", "") or "",
            })
    # Auto-close is permanently disabled — nothing is ever executed automatically.
    state["executed_exits"] = []
    state["suggested_exits"] = suggested_exits
    if suggested_exits:
        _step("exit_suggestions",
              f"{len(suggested_exits)} exit suggestion(s) — NOT executed, "
              "client decides: " + ", ".join(e["symbol"] for e in suggested_exits))
        await _notify_exit_suggestions(suggested_exits)

    # 6. Agent 13: Morning Briefing
    _step("morning_briefing", "writing daily client briefing",
          agent="briefing", model="gemini-2.5-flash")
    briefing_agent = MorningBriefingAgent(gemini_flash(), fs)
    brief_state_like = await _run_agent_with_morning_writes(
        briefing_agent, state, "briefing", fs, today,
    )
    state["briefing"] = brief_state_like.get("briefing")
    if state["briefing"]:
        _step("morning_briefing", state["briefing"].headline,
              agent="briefing", action="complete")

    # 7. Persist raw state
    fs.write_morning_raw(today, state)

    # 8. Telegram notification — send the briefing to the client
    if state.get("briefing"):
        try:
            from .telegram import telegram as _telegram
            client = _telegram()
            ok = await client.send_morning_briefing(state["briefing"])
            _step("notify", f"telegram {'sent' if ok else 'skipped'} (briefing)")
        except Exception as e:  # noqa: BLE001
            _step("notify", f"telegram error: {e}")

    _step("done", f"morning cycle complete — artifacts in _morning/{today}/")

    return state


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


async def _run_agent_with_morning_writes(
    agent, state: MorningState, slot: str, fs: FileStore, today: str,
) -> MorningState:
    """Run an Agent (subclass) but redirect its file write to the morning folder.

    Reuses the base Agent.run() logic by handing it a temporary file_store
    proxy that routes writes to write_morning() instead of write_markdown().
    """
    # Build prompt + call LLM (re-implement the base Agent.run pieces we need)
    from .llm.structured import invoke_structured_or_freetext
    prompt = agent.build_prompt(state)
    result = await invoke_structured_or_freetext(
        agent.llm, prompt, agent.OUTPUT_SCHEMA,
    )
    markdown = agent.render(result.instance)

    suffix = ""
    if agent.STAGE == "exit_confirmer":
        suffix = getattr(agent, "target_symbol", "") or ""
    fs.write_morning(today, agent.STAGE, markdown, suffix=suffix)

    # Update the morning state (mirror Agent.run's slot-set logic)
    new_state: MorningState = dict(state)  # type: ignore[assignment]
    new_state[slot] = result.instance  # type: ignore[literal-required]
    return new_state


async def _apply_lifecycle(reviews: list, step_fn) -> None:
    """Daily AI-managed risk: store each position's updated stop and Telegram
    any trim/add/tighten/widen suggestions. Notify-only — never executed."""
    from .portfolio import VirtualPortfolio
    from .telegram import telegram as _telegram

    notes: list[dict[str, Any]] = []
    portfolio = VirtualPortfolio()
    try:
        open_by_sym = {p["symbol"].upper(): p for p in portfolio.list_open()}
        for r in reviews:
            sym = (getattr(r, "symbol", "") or "").upper()
            pos = open_by_sym.get(sym)
            if not pos:
                continue
            new_stop = getattr(r, "new_stop_price", None)
            risk_action = getattr(r, "risk_action", "hold") or "hold"
            risk_note = getattr(r, "risk_note", None)
            # Persist the AI stop (used by refresh_all breach alerts) when given.
            if new_stop and new_stop > 0:
                portfolio.set_ai_stop(pos["id"], float(new_stop), risk_note)
            if risk_action != "hold":
                notes.append({"symbol": sym, "action": risk_action,
                              "new_stop": new_stop, "note": risk_note})
    finally:
        portfolio.close_conn()

    if notes:
        step_fn("lifecycle",
                f"{len(notes)} risk suggestion(s): "
                + ", ".join(f"{n['symbol']}:{n['action']}" for n in notes))
        client = _telegram()
        for n in notes:
            verb = {"trim": "Consider trimming", "add": "Consider adding to",
                    "tighten_stop": "Tighten the stop on", "widen_stop": "Widen the stop on"}.get(
                        n["action"], "Review")
            msg = f"🛠 Risk update: {n['symbol']}\n\n{verb} {n['symbol']}."
            if n.get("new_stop"):
                msg += f"\nSuggested new stop: ${float(n['new_stop']):,.2f}."
            if n.get("note"):
                msg += f"\n\nWhy: {n['note']}"
            msg += ("\n\nThe system has NOT changed anything — this is a suggestion. "
                    f"You decide whether to act on {n['symbol']} in your real account.")
            try:
                await client.send_message(msg, kind="risk_update", symbol=n["symbol"])
            except Exception as e:  # noqa: BLE001
                log.warning("risk update send failed for %s: %s", n["symbol"], e)


async def _notify_exit_suggestions(suggestions: list[dict[str, Any]]) -> None:
    """Telegram a plain-language exit SUGGESTION per flagged position.
    The system never sells — the client decides whether to act."""
    try:
        from .telegram import telegram as _telegram
        client = _telegram()
        for s in suggestions:
            urg = (s.get("urgency") or "").replace("_", " ")
            reason = (s.get("reason") or "").strip()
            msg = (
                f"⚠️ Exit suggestion: {s['symbol']}\n\n"
                f"The system suggests you consider exiting {s['symbol']}"
                + (f" ({urg})" if urg else "") + ".\n"
                + (f"\nWhy: {reason}\n" if reason else "")
                + "\nThe system has NOT sold anything — this is only a suggestion. "
                f"You decide whether to exit {s['symbol']} in your real account."
            )
            try:
                await client.send_message(msg, kind="exit_suggestion", symbol=s["symbol"])
            except Exception as e:  # noqa: BLE001
                log.warning("exit suggestion send failed for %s: %s", s["symbol"], e)
    except Exception as e:  # noqa: BLE001
        log.warning("exit suggestion dispatch failed: %s", e)


async def _run_exit_confirmers(
    state: MorningState,
    exit_flags: list,
    fs: FileStore,
    today: str,
    step_fn,
) -> dict[str, Any]:
    """Run one Exit Confirmer per flagged position in parallel."""
    positions_by_sym = {p["symbol"]: p for p in state["open_positions"]}

    async def one(flag) -> tuple[str, Any]:
        agent = ExitConfirmerAgent(claude_sonnet(), fs)
        pos = positions_by_sym.get(flag.symbol, {})
        agent.for_position(flag.symbol, flag.reason, pos)
        confirmer_state = await _run_agent_with_morning_writes(
            agent, state, "exit_confirmation_singleton", fs, today,
        )
        conf = confirmer_state.get("exit_confirmation_singleton")
        # If returned as the raw ExitConfirmation
        if conf is not None:
            step_fn(
                "exit_confirmer",
                f"{flag.symbol}: {conf.verdict} ({conf.urgency})",
                agent="exit_confirmer",
                action="complete",
                metrics={"symbol": flag.symbol, "verdict": conf.verdict},
            )
        return flag.symbol, conf

    pairs = await asyncio.gather(*[one(f) for f in exit_flags])
    return {sym: conf for sym, conf in pairs if conf is not None}
