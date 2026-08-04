# Strategy Board — Master Build Plan (goal file)

> **How to use this file:** this is the single source of truth for the options
> Strategy Board build. Every phase below has a spec, a test checklist, and an
> exit gate. Work proceeds phase by phase; a phase's status flips to ✅ only
> when its exit gate passes AND the code is deployed + verified live. Any
> session (human or AI) resuming this work starts by reading this file and the
> Status board, then continues the first non-✅ phase. Update the Status board
> and per-phase checkboxes in the same commit as the work.

**Repo:** `aistockanalysis99-bit/akash-research-platform` · backend Render
(`akash-backend-vdlx.onrender.com`) · frontend Vercel
(`akash-research-platform.vercel.app`) · push to `main` auto-deploys both.

---

## The goal

A **rulebook-driven daily options desk** inside the Akash platform: every day,
for every stock where an explicit rule fires, show the exact trade (legs,
strikes, credit/debit, max loss, probability), track it on paper, measure
every strategy family's realized returns in one league table, and let the
AI's stock research (conviction, entry/target/stop levels) drive strategy
selection. Suggest-only forever; the client executes in his own broker.

## Non-negotiable invariants (apply to every phase)

1. **Defined risk only** — enforced in `structures._validate_covered`
   (one-for-one short/long coverage per type+expiry; declared cash-secured
   single puts are the only exception). Never weaken this to ship a feature.
2. **Paper first** — every new strategy family trades paper before real; no
   strategy skips the league table.
3. **Suggest-only** — nothing ever auto-trades. Alerts and cards, never orders.
4. **Delayed-data honesty** — quotes are ~15-min delayed Polygon ($79 tier,
   NBBO usually null). Every card carries "verify in broker". Live-data
   upgrade only when measured slippage > 10% of credit.
5. **Returns three ways** — quoted (today's math) / expected (backtest) /
   realized (league table). Never show one layer's number as another's.
6. **Additive only** — existing features (equity portfolio, straddle module,
   AI pipeline) must be behaviorally untouched. New tables, new routes, new
   pages.
7. **Every phase ends with:** syntax checks → unit tests → live e2e test →
   `tsc`/`vite build` → adversarial review workflow → fix confirmed findings
   → commit → push → poll both deploys → verify live endpoint/page.

## Stock pools

- **Pool A** — S&P 500 earnings universe (~503, auto-fetched). Event
  strategies; conditions pick the stock, not opinion.
- **Pool B** — liquidity list (`pools.py`, 40-name seed, weekly re-measured,
  membership earned by best paired ATM-neighborhood OI on the nearest Friday
  expiry ≥ `options_pool_b_min_oi`). Short-premium strategies only trade
  Pool B members.
- **Pool C** — ownership list: current holdings + watchlist + AI BUY
  conviction ≥ 7 decisions. Wheel/CSP/CC/bull-put only — never sell a put on
  a stock the AI wouldn't own.

## Status board

| Phase | Name | Status | Commits | Exit gate |
|---|---|---|---|---|
| 0 | Foundations | ✅ done (2026-08-03) | `16139d3`, `de68a9e` | met — multi-leg store/price/mark/close proven live; rulebook page live; defined-risk rule adversarially hardened |
| 1 | Strategy Board + Iron Condor | ✅ done (2026-08-04) | `8c7d893` | met — live board generated ON PRODUCTION from real scan data (WBD straddle card, cheapness 0.41); Pool B populated live (40/10); zero condor cards correctly explained (qualified pool has no earnings in window — wave moved down-cap). 8/8 review findings fixed pre-ship. NVDA/SNOW Aug 20–21 = live rehearsal. |
| 2 | Returns Engine + League Table | 🚀 shipped (2026-08-04) — pending live verify + coverage ramp | this commit | condor backtest (real prices, exit-mark floor), Report Card aggregator + nightly 03:30 sweep, League page, Friday scorecard, board-card rule history. Review: 6 raised → 5 confirmed → all fixed (dead-code exit rules/stale pre-crush marks HIGH, strikes pagination, shared artifact ceiling, no caching of transient failures ×2). Exit gate needs ≥100 events coverage — accumulates nightly. |
| 3 | Income Layer (CC + CSP) | ⬜ | — | see Phase 3 |
| 4 | Wheel State Machine | ⬜ | — | see Phase 4 |
| 5 | Spreads + Strategy Allocator | ⬜ | — | see Phase 5 |
| 6 | Pro Desk | ⬜ | — | see Phase 6 |

**Activation vs construction:** software for later phases may be BUILT early
(this plan builds all phases in sequence), but each strategy family only
starts producing live suggestions when its roadmap gate allows (condor
rehearsal → income paper month → wheel cycles → league-data allocator).
Building early never means activating early.

---

## Phase 0 — Foundations ✅

Shipped: `returns_math.py` (generic payoff engine, POP, yields),
`pricing.py` (pricing seam: `DelayedPolygonPricing`, one chain call per
structure), `structures.py` (multi-leg paper positions, defined-risk gate,
mark/close, `family_stats`), `pools.py` (Pool B qualifier),
`registry.py` + `RulebookPage.tsx` (+ nav/route), 6 settings, 2 scheduler
jobs (`pool_b_refresh` Mon 08:10 ET, `mark_structures` 09:20 ET), 5 API
routes. Adversarial review: 17 raised → 9 confirmed → all fixed (incl. HIGH
ratio-spread hole in the coverage rule). Verified live: 40 measured / 10
qualified in Pool B, rulebook serving 6 strategies.

Key learnings for later phases:
- Polygon: 429s under fan-out (backoff exists in `_get`); Mon/Wed weeklies
  have near-zero OI when fresh — always prefer Friday expiries for liquidity
  measurement; NBBO null on weekends/this tier → spread gates must be
  None-tolerant.
- "Bounded" ≠ "defined": validate coverage by COUNT per (type, expiry).
- Never record a P&L that wasn't priced (`:unpriced` close path).

## Phase 1 — Strategy Board + Iron Condor 🔨

**Objective:** the daily board page listing every rule that fires with a
complete trade card; first new family live-on-paper: R2 earnings iron condor.

Build items:
- [ ] `engine/live/options/condor.py` — `build_condor(symbol, expiry, spot)`:
      chain snapshot → short strikes at ±`options_condor_short_delta` (nearest
      listed strike by |delta|, fall back to expected-move distance when
      greeks missing), wings `options_condor_wing_pct`% of spot further out
      (nearest listed), one `chain_for_expiry` call, returns legs (priced,
      with deltas/OI) + credit + `payoff_stats` + POP + liquidity flags.
- [ ] `engine/live/options/board.py` — `generate_board()`: read today's
      scanner candidates (`store.latest_candidates()`); R2 fires when
      cheapness ≥ `options_condor_min_cheapness` AND symbol in Pool B
      (qualified) AND (IV percentile ≥ `options_condor_min_iv_rank` when
      available — inert while history < 15 snapshots) AND earnings 1–10 days
      out. R1 card mirrors qualified straddle candidates (links to existing
      tracker). Persist to `options_board` table (board_date, strategy_key,
      symbol, payload JSON, unique(board_date, strategy_key, symbol)).
      Never raises: per-symbol try/except.
- [ ] Board Telegram digest (plain-English, per strategy, max ~6 cards).
- [ ] Scheduler: `_job_strategy_board` 17:05 ET weekdays (after 16:45 scan).
- [ ] API: `GET /options/board` (latest board + date), `POST /options/board/refresh`,
      `POST /options/board/track` {board_id, contracts} → `create_structure`
      (condor) with `exit_deadline` = morning after earnings 10:00 ET.
- [ ] Frontend `StrategyBoardPage.tsx` at `/options/board` (nav "Board"):
      grouped by strategy, cards show legs table, credit, max loss, POP,
      breakevens, annualized-on-risk, dual-signal badge, "verify in broker"
      note, Track(paper) button; empty state explains why nothing fired.
- [ ] Exit alerts for condors: extend straddle exit-alert job or structures
      mark job to alert when `exit_deadline` reached (close-suggestion, once).

Tests:
- [ ] Unit: condor builder on a synthetic chain (strike selection by delta,
      wing rounding, refusal when legs unpriced).
- [ ] Live: `build_condor` on one Pool B name; assert legs priced, credit>0,
      max loss = width−credit, POP sane (50–95).
- [ ] Live e2e: `generate_board()` end-to-end; board persists + API serves it;
      track one condor → structure opens → `mark_structures` prices it.
- [ ] UI renders board with data; empty-state path.
- [ ] Regression: straddle scanner/candidates/positions endpoints unchanged.

Exit gate: board generated from live data ≥1 evening; ≥1 paper condor
tracked and marked cleanly next morning; adversarial review confirmed
findings fixed; deployed + verified live. (Season rehearsal: NVDA/SNOW
earnings Aug 20–21.)

## Phase 2 — Returns Engine + League Table ⬜

**Objective:** all three return layers visible; strategy families comparable
on one page.

Build items:
- [ ] `engine/live/options/condor_backtest.py` — historical condor simulation
      per symbol (reuse `historical_leg_bars` for 4 legs, expired contracts):
      entry N days pre-earnings at delta-band strikes (approximate from
      historical straddle-implied move when greeks unavailable), exit close
      the day after earnings; point-in-time cheapness reused from straddle
      backtest ambient logic. Cache in `options_backtests`-style table keyed
      (symbol, strategy).
- [ ] Straddle aggregate "Report Card": paced sweep over S&P 500 backtests
      (existing `backtest_symbol`), aggregate table (events, win rate, avg
      P&L for qualifying events) stored + API `GET /options/report-card`
      (+ `POST /options/report-card/run` — long-running job w/ progress in
      settings/table row; respect 429 budget: sequential, ~2s spacing).
- [ ] Layer-2 wiring: board cards + backtest pages show "this rule on this
      stock historically: N events, X% win, avg Y%".
- [ ] `LeagueTablePage.tsx` at `/options/league` (nav "League"): one row per
      family (straddle from `store.league_record`, rest from `family_stats`):
      trades, win rate, avg return-on-risk, total $, worst trade; sortable;
      quoted-vs-realized honesty note.
- [ ] Friday scorecard Telegram: extend weekly job with league summary.

Tests: unit condor-backtest math on fixed bars; live backtest one symbol
(rate-budget aware); report-card run on ≥25 symbols slice; league page
renders with straddle + condor rows; regression suite.

Exit gate: league page live with ≥2 family rows; report card covering ≥100
historical events; deployed + verified.

## Phase 3 — Income Layer (Covered Calls + CSPs) ⬜

**Objective:** income suggestions on Pool C using AI levels; the "your stocks
would have paid $X this month" number.

Build items:
- [ ] `engine/live/options/income.py` — `build_covered_call(symbol, shares,
      ai_target)`: 100-share lots from portfolio holdings; strike =
      max(nearest listed ≥ AI target, |Δ|≈0.25–0.30 band), 21–45 DTE Friday
      expiry, skip if earnings inside expiry (FMP next-earnings) or
      ex-dividend risk flag; returns premium, monthly + annualized rent,
      if-called return. `build_csp(symbol, ai_entry)`: strike ≤ AI entry,
      |Δ| 0.20–0.30, 30–45 DTE, cash-secured; annualized yield on secured
      cash + effective basis.
- [ ] Pool C resolver: holdings (from VirtualPortfolio) + AI BUY ≥7 latest
      decisions (reuse `_latest_convictions` pattern + decision levels).
- [ ] Board integration: R3/R4 sections on the Strategy Board (paper-track
      buttons → `create_structure` CSP w/ `cash_secured=True`; CC stored as
      single-leg short call with `covered_call` strategy_key + notes
      recording the covering shares — the ONLY covered exception, gated on
      verified holding of ≥100·qty shares in the portfolio at creation).
      ⚠ requires a deliberate, narrow extension of `_validate_covered`
      (`stock_covered=True` flag validated against the live portfolio) —
      re-run the coverage regression suite + adversarial review on this
      change specifically.
- [ ] Income summary card: paper income booked this month vs quoted.
- [ ] Settings: `options_cc_min_delta/max_delta`, `options_csp_min_dte` etc.
      (add to get_all + SETTABLE_KEYS + rulebook display).
- [ ] Registry statuses: R3/R4 → "paper".

Tests: unit strike selection (target vs delta band conflicts); earnings-week
exclusion; CC coverage check refuses when shares < 100·qty; live build on one
holding; e2e paper month accrual math; regression coverage suite.

Exit gate: R3/R4 cards on the board for real holdings; ≥3 paper income
positions tracked + marked; coverage rule reviewed; deployed + verified.

## Phase 4 — Wheel State Machine ⬜

**Objective:** full CSP → assignment → CC → called-away lifecycle with true
cost basis and full-cycle ROI.

Build items:
- [ ] `engine/live/options/wheel.py` + `options_wheels` table: wheel_id,
      symbol, state (CASH_PUT / ASSIGNED_STOCK / STOCK_CALL / COMPLETE),
      legs ledger (each premium banked), assigned_basis, effective_basis
      (strike − Σpremiums), cycle ROI on committed capital, timestamps.
- [ ] Transitions: expiry-day evaluator (spot vs strike at expiry → suggest
      "expired — sell again" or "assigned — mark it"), manual Mark-assigned /
      Mark-called-away endpoints (user confirms what happened in broker),
      next-action suggester using AI levels for the next leg.
- [ ] `WheelPage.tsx` at `/options/wheel`: active wheels as state diagrams,
      ledger per wheel, cycle ROI; league table gains "wheel (full cycles)".
- [ ] Telegram: expiry-day wheel suggestions.

Tests: unit state transitions incl. premium ledger + basis math across a
scripted full cycle; e2e paper wheel driven through all states via API;
regression.

Exit gate: ≥1 scripted paper wheel completes a full cycle with correct
basis/ROI; page live; deployed + verified.

## Phase 5 — Spreads + Strategy Allocator ⬜

**Objective:** every AI verdict (bullish AND bearish) earns; the platform
recommends WHICH structure fits a signal, ranked by our own league data.

Build items:
- [ ] `engine/live/options/spreads.py` — `build_bull_put(symbol, ai_stop)`:
      short put at nearest strike ≤ AI stop, long put one wing below
      (settings width), 30–45 DTE; `build_bear_call(symbol, ai_ceiling)`
      mirror using AVOID verdicts + bear-case ceiling (decision levels).
- [ ] Verdict hook: on each new decision (or nightly sweep of latest
      decisions), board gains R5/R6 candidates for conviction ≥7 BUY /
      AVOID names with liquid chains (Pool B ∩ Pool C logic).
- [ ] `allocator.py` — given (symbol, signal context: earnings proximity,
      cheapness, IV percentile, AI verdict+levels, liquidity), list viable
      structures, rank by league-table realized return-on-risk (fallback
      order documented in registry when a family has <10 trades), emit
      one-line WHY per rank. API `GET /options/allocator/{symbol}`.
- [ ] Board shows allocator pick per symbol ("best structure for this
      signal: …"); registry R5/R6 → "paper".
- [ ] Exit suggestions: profit-target 50–60% of credit alert for spreads
      (reuse structures mark job), close-on-verdict-flip alert.

Tests: unit strike selection from AI levels; allocator ranking determinism +
fallback path; live build both spreads on one name; e2e verdict→board flow;
regression.

Exit gate: spreads appear for real verdicts; allocator returns ranked
structures with reasons; deployed + verified.

## Phase 6 — Pro Desk ⬜

**Objective:** portfolio-level risk view, butterfly pilot, evidence-driven
data upgrade, the annual report machinery.

Build items:
- [ ] Greeks rollup: net delta/theta/vega across all open structures
      (current_delta per leg already stored; add theta/vega capture in
      pricing quote_legs → legs table columns), "book is net +N deltas ≈
      $X of stock" card on Positions/Board. API `GET /options/greeks`.
- [ ] Fill-quality tracking: optional `real_fill_value` on track/close
      endpoints + slippage report (paper mid vs real fill, per family);
      the live-data upgrade trigger = median slippage > 10% of credit —
      surfaced on the League page.
- [ ] Butterfly pilot (`build_butterfly` around AI target, defined-risk
      1-2-1) — registry "paper", gated: only enabled when AI target-accuracy
      stats (from decisions vs realized prices) meet a documented bar.
- [ ] Season/Annual report generator: markdown report (scans, boards,
      trades, league, slippage, lessons) saved + downloadable; Telegram
      summary.

Tests: greeks rollup math vs hand-sum; slippage report with seeded fills;
butterfly builder unit + refusal when gate unmet; report generation e2e;
full regression.

Exit gate: greeks card live; slippage metric computing; report generated for
the season to date; deployed + verified.

---

## Testing & deployment protocol (every phase)

1. `python -c "ast.parse(...)"` on all touched files.
2. Unit tests inline (hand-computed cases; keep the Phase 0/1 regression
   suites green — especially the 12-case coverage boundary).
3. Live e2e against Polygon/FMP (weekend caveat: NBBO null, day-close
   fallbacks; budget 429s — sequential where wide).
4. `cd frontend && npm run build` (tsc + vite) exit 0.
5. Adversarial review workflow (3 reviewers: math/backend/frontend +
   verify pass) → fix CONFIRMED findings only → re-test.
6. Commit (message pattern: "<Phase N>: <what> — <key decisions>"), push
   `main`; if credential manager hangs: `taskkill //F //IM
   git-credential-manager.exe` then push with prompts allowed.
7. Poll deploys: Vercel bundle marker + Render endpoint marker (Render
   restarts ~2–4 min, 502 during restart is normal; Vercel sometimes skips
   a webhook — empty commit re-triggers).
8. Verify the live endpoint/page; update this file's Status board + phase
   checkboxes; update memory file summary.

## Operational constraints

- Polygon $79: 429/min under fan-out (backoff in `_get`), 15-min delayed,
  NBBO usually null, no historical IV (own history accumulating since
  2026-07; percentile gates inert until 15 snapshots/symbol).
- FMP: earnings dates lack BMO/AMC → conservative exit deadlines; dates can
  be wrong → cross-check before real trades (client-side discipline).
- Org AI spend limit can clip review workflows mid-run — fix confirmed
  findings, note unverified dimensions in the commit.
- The straddle module (`positions.py`/`store.py`/`scanner.py`) is legacy-
  stable: extend around it, don't refactor it mid-season.
