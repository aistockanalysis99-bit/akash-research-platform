# Strategy 4 Alpaca Paper-Trading Automation — Four-Phase Implementation Plan

## 1. Objective and fixed scope

Build an automated **paper-trading** system for the existing **Strategy 4: Cointegrated Stat-Arb v4 (Risk-Engineered Pure Alpha)** only. The system will:

- use Alpaca's paper account for US-equity order execution;
- run the Strategy 4 candidate scan automatically before each US market session;
- open and manage both legs of each qualifying pair;
- monitor Alpaca orders and positions throughout the session;
- notify only authorized Telegram chats;
- send a daily Alpaca account and holdings report at **10:00 AM Asia/Kolkata**;
- expose a new application section for status, signals, orders, positions, alerts, and controls;
- survive process restarts without duplicating trades or losing broker state.

This plan does not change Strategy 4's signal rules. Live-paper results must remain attributable to the same v4 configuration used by the verified backtest.

## 2. Important operating decisions

### 2.1 Paper trading only

The first implementation will hard-block any Alpaca base URL other than:

```text
https://paper-api.alpaca.markets
```

There will be no live-trading switch in this phase of the project. A future live deployment requires a separate review and explicit implementation.

### 2.2 Correct interpretation of pre-market data

Strategy 4 is based on daily historical bars. A scan performed one or two hours before the US market opens cannot use a completed bar for that same US trading day. Therefore:

- signal calculations will use the **latest completed US trading session**;
- current pre-market quotes may be used only for execution validation, price guards, sizing refresh, and gap/slippage rejection;
- incomplete intraday or pre-market data will not be mixed into the 90-day daily-bar signal unless a separately backtested intraday variant is created later.

This prevents live signal logic from silently diverging from the backtest.

### 2.3 Market calendars and daylight saving time

- US-market jobs will use Alpaca's market clock/calendar and the `America/New_York` timezone, not fixed IST conversions.
- The daily account report will use `Asia/Kolkata` and run at 10:00 AM IST.
- Pre-market analysis will be scheduled relative to Alpaca's reported next market open, targeting 90 minutes before the regular session by default.
- Weekends, exchange holidays, early closes, and US daylight-saving changes must be handled automatically.

### 2.4 Short selling in US equities

US equity short positions can be held beyond the same day; they are not inherently intraday-only. For Alpaca:

- the account must have at least $2,000 equity for margin/short selling;
- every proposed short leg must be `tradable` and `shortable`;
- borrow status must be checked through the asset endpoint;
- Phase 1 will accept **easy-to-borrow** symbols only;
- hard-to-borrow locate purchasing will not be automated in the initial release;
- if a short leg is unavailable, the complete pair trade is rejected—never converted into a one-legged trade.

### 2.5 Pair execution is not atomic

Alpaca orders operate per symbol; the two stocks in a pair cannot be guaranteed to fill atomically. Each pair will therefore use a persisted `pair_trade_id`, deterministic client order IDs, and a compensating state machine:

1. validate both legs and reserve risk capacity;
2. submit both legs within the same execution operation;
3. monitor both order states;
4. mark the pair `OPEN` only after both legs reach the required filled quantity;
5. send the Telegram entry alert only after both legs are filled;
6. if one leg is rejected/cancelled or exceeds the fill timeout, cancel the other open order and flatten any filled exposure;
7. generate a high-priority failure alert and audit record.

### 2.6 Pair-level exits

Strategy 4 exits are driven by the pair spread and Z-score, not by two unrelated single-stock percentage moves. The monitor will therefore evaluate:

- target reversion at Strategy 4's configured absolute Z-score target (currently 0.40);
- dynamic spread stop (currently 2.85 or entry Z plus the configured cushion, as defined by the engine);
- half-life time stop (configured floor/cap);
- VIX panic handling and any existing Strategy 4 risk overlays;
- broker/account risk events and emergency flattening rules.

Telegram messages will show both legs' actual fills, sides, quantities, and indicative price levels, while clearly identifying the authoritative pair-level target and stop in Z-score terms.

### 2.7 Safety defaults

- Automation defaults to disabled and must be explicitly armed from the new application section.
- A global kill switch stops new entries while preserving monitoring and safe exit management.
- Daily pair count, gross exposure, per-pair allocation, buying-power reserve, maximum open pairs, maximum tolerated quote gap/slippage, and stale-data limits are mandatory configurable controls.
- Duplicate signals, duplicate orders, and duplicate Telegram notifications must be prevented using idempotency keys.
- Secrets must never appear in logs, API responses, UI payloads, database rows, or test fixtures.

## 3. Planned environment variables

The following placeholders will be added to the **LOCAL** `.env` during Phase 1. Values remain user-supplied:

```dotenv
TELEGRAM_BOT_TOKEN=
TELEGRAM_ENABLED=True
TELEGRAM_AUTH_PASSCODE=1234

ALPACA_API_KEY=
ALPACA_SECRET_KEY=
ALPACA_BASE_URL=https://paper-api.alpaca.markets
```

Additional safe operational defaults will be introduced in Phase 1, with credentials remaining env-only:

```dotenv
AUTO_TRADE_ENABLED=False
AUTO_TRADE_PAPER_ONLY=True
AUTO_TRADE_PREMARKET_MINUTES=90
AUTO_TRADE_MONITOR_MINUTES=10
AUTO_TRADE_MAX_OPEN_PAIRS=3
AUTO_TRADE_MAX_NEW_PAIRS_PER_DAY=2
AUTO_TRADE_MAX_GROSS_EXPOSURE_PCT=0.30
AUTO_TRADE_PAIR_CAPITAL_PCT=0.10
AUTO_TRADE_MIN_BUYING_POWER_RESERVE_PCT=0.20
```

`TELEGRAM_AUTH_PASSCODE` is the onboarding secret: after a user sends `/start`, the bot requests the passcode. A correct passcode authorizes that Telegram chat to receive messages. The passcode itself stays in `.env`; only authorized chat/user IDs and authorization timestamps are stored. Passcode comparisons will be constant-time, failed attempts will be rate-limited, and passcodes will not be logged.

---

# Phase 1 — Broker foundation, persistence, and Telegram authorization

## Goal

Create the secure infrastructure needed to talk to Alpaca paper trading and to authorize Telegram recipients, without placing trades.

## Implementation steps

1. Extend `engine/config.py` with validated Alpaca, Telegram, and auto-trading configuration.
   - Require HTTPS for Alpaca.
   - Fail closed if auto-trading is armed with missing credentials.
   - Reject non-paper Alpaca URLs when `AUTO_TRADE_PAPER_ONLY=True`.
   - Keep all secrets env-only and expose only redacted readiness flags.

2. Add an Alpaca paper client module with typed methods for:
   - account and buying-power retrieval;
   - market clock and calendar;
   - asset/tradability/shortability/borrow checks;
   - historical bars and current quotes;
   - orders, positions, activities, and portfolio history;
   - timeouts, bounded retries, structured errors, and redacted logging.

3. Add database migrations/tables for:
   - `telegram_authorized_chats`;
   - Telegram authentication attempts and update offset;
   - auto-trade runs;
   - Strategy 4 signal snapshots;
   - pair-trade intents and pair legs;
   - broker orders/events;
   - notification outbox/delivery status;
   - automation locks/heartbeats and daily account snapshots.

4. Upgrade the existing outbound-only Telegram client into inbound + outbound operation.
   - Use Telegram long polling for the local deployment; keep the inbound transport isolated so a webhook can replace it later.
   - `/start` prompts for the passcode.
   - Correct passcode authorizes the private chat.
   - Incorrect attempts receive a generic failure response and are rate-limited.
   - `/status` reports bot authorization and paper-bot health without exposing financial details to unauthorized chats.
   - `/stop` revokes that chat's authorization.
   - Outbound broadcasts target all active authorized chats.
   - Persist Telegram `update_id` so restarts do not reprocess messages.

5. Add readiness APIs for the future UI:
   - configuration readiness with secrets redacted;
   - Alpaca connectivity/account type validation;
   - Telegram bot identity and authorized-chat count;
   - database/schema and scheduler health.

6. Ensure no trade-submission method is reachable while Phase 1 is active.

## Verification criteria

- The app starts safely with blank Alpaca and Telegram credentials.
- Arming automation without complete credentials fails with a clear, non-secret error.
- A non-paper Alpaca URL is rejected.
- Alpaca paper account, clock, calendar, and asset checks work with valid credentials.
- `/start` followed by the correct passcode authorizes one private chat.
- Wrong passcodes do not authorize a chat and trigger rate limiting after repeated failures.
- `/stop` removes authorization.
- Restarting the API/bot preserves authorized chats and does not replay processed Telegram updates.
- Logs, APIs, database records, and UI-readiness payloads contain no token, API secret, or passcode.

## Required tests before Phase 1 is complete

- Unit tests for configuration parsing, blank credentials, redaction, and paper-only URL enforcement.
- Mocked Alpaca client tests for success, authentication failure, timeout, 429, 5xx retry, and malformed responses.
- Database migration and round-trip tests for all new tables.
- Telegram state-machine tests for `/start`, correct passcode, wrong passcode, rate limiting, `/status`, `/stop`, duplicate update IDs, and multiple authorized chats.
- Secret-leak regression test scanning captured logs and serialized API responses.
- Existing full backend test suite must still pass.

---

# Phase 2 — Strategy 4 live signal pipeline and trade-intent generation

## Goal

Produce deterministic, auditable Strategy 4 trade intents from fresh data without sending orders.

## Implementation steps

1. Extract or adapt the existing `StrategyV4Engine` so backtest and live-paper evaluation share the same calculations and configuration source.
   - No duplicated Strategy 4 formula set.
   - Persist the configuration version/hash with every signal.
   - Preserve entry Z-score, velocity confirmation, volatility cap, VIX overlay, earnings blackout, half-life, sizing, and gauntlet gates.

2. Build the pre-market data workflow.
   - Query Alpaca clock/calendar first.
   - Skip non-trading days.
   - Download and validate daily bars through the latest completed session.
   - Refresh the eligible curated pair universe.
   - Obtain current pre-market quotes for gap, spread, staleness, and execution guards only.
   - Reject missing, stale, non-monotonic, duplicate, split-corrupted, or insufficient data.

3. Run Strategy 4 only and persist a complete scan record:
   - evaluated pairs and rejection reasons;
   - qualifying pairs and rank;
   - hedge ratio, spread, Z-score, velocity, half-life, spread volatility, VIX state, and earnings state;
   - proposed long/short symbols, dollar allocations, quantities, entry reference, target, stop, and maximum holding date;
   - source-data cutoff timestamp and market session date.

4. Apply broker and portfolio eligibility checks before creating an intent:
   - both assets active and tradable;
   - short leg shortable and easy-to-borrow;
   - account trading not blocked;
   - adequate buying power plus reserve;
   - max open pairs/new pairs/gross exposure/per-pair capital limits;
   - no overlapping or conflicting position/order in either symbol;
   - no duplicate pair/session signal;
   - pre-market gap/slippage and quote-freshness guard.

5. Add dry-run APIs and the first part of the new **Auto Trade** UI section:
   - bot readiness and armed/disarmed state;
   - next scheduled scan and relevant market session;
   - latest scan summary;
   - qualified/rejected pairs with exact reasons;
   - proposed quantities and risk numbers;
   - manual “Run dry scan” action that cannot place orders.

6. Create Telegram scan-summary formatting, but keep it dry-run only in this phase.

## Verification criteria

- Running the live scanner twice with the same frozen dataset produces identical signals and intent IDs.
- Live evaluation on a historical cutoff matches the Strategy 4 engine's decision for the same pair/date/configuration.
- Only Strategy 4 code/configuration is used; no Strategy 1–3 fallback exists.
- Incomplete current-day bars never influence the daily signal.
- Non-trading days and early-close sessions are handled through the broker calendar.
- Unshortable/HTB assets, stale data, earnings blackout, VIX freeze, risk-cap breach, or insufficient buying power reject the whole pair with a persisted reason.
- Dry-run mode creates no Alpaca orders.

## Required tests before Phase 2 is complete

- Golden-data parity tests comparing historical live-scan output with known Strategy 4 evaluation output.
- Unit tests for every Strategy 4 gate and every broker/risk rejection rule.
- Calendar/timezone tests covering normal EST, normal EDT, DST transition weeks, weekends, US holidays, and early closes.
- Data-quality tests for stale/missing/duplicate bars, incomplete sessions, split-like discontinuities, and stale pre-market quotes.
- Idempotency tests for repeated scan, concurrent scan attempts, and restart after a persisted scan.
- API and React component tests for the dry-scan/status views.
- Existing Strategy 4 regression suite and frontend production build must pass.

---

# Phase 3 — Pair order execution, reconciliation, and Strategy 4 exit management

## Goal

Safely turn approved Strategy 4 intents into Alpaca paper positions and manage their full lifecycle.

## Implementation steps

1. Implement a persisted pair-trade state machine, for example:

```text
DRAFT -> VALIDATED -> SUBMITTING -> ORDERS_OPEN -> OPEN
      -> ENTRY_FAILED -> COMPENSATING -> FLAT
OPEN  -> EXIT_PENDING -> EXITING -> CLOSED
      -> ERROR_REQUIRES_ATTENTION
```

2. Create deterministic IDs:
   - one `pair_trade_id` per pair/session/signal/configuration;
   - one Alpaca `client_order_id` per leg and action;
   - dedupe constraints so retries cannot create a second position.

3. Implement entry execution during the intended regular-market window.
   - Revalidate account, market state, quote freshness, shortability, buying power, signal validity, and risk immediately before submission.
   - Use whole-share hedge-ratio-aware quantities unless fractional-short support is explicitly verified.
   - Submit both legs and persist raw broker IDs/responses.
   - Handle partial fills, rejected legs, timeouts, cancellations, and process crashes.
   - Apply a bounded fill timeout and a safe cancel/unwind compensation policy.
   - Never label or notify a pair as open until both legs satisfy the fill rule.

4. Implement broker order-state ingestion.
   - Prefer Alpaca trade-update streaming for prompt state changes.
   - Retain scheduled REST reconciliation every 10 minutes as the recovery/source-of-truth path.
   - Normalize all Alpaca lifecycle states, including partial fill, filled, cancelled, expired, replaced, rejected, and rare pending states.

5. Implement Strategy 4 position monitoring every 10 minutes during relevant market hours.
   - Refresh both leg prices and recompute the live pair spread/Z-score.
   - Evaluate target, dynamic stop, half-life time stop, macro-risk action, and emergency broker/account conditions.
   - Close both legs through an idempotent paired-exit flow.
   - If one exit leg fails, retry/reconcile and raise a high-priority exposure alert.

6. Send Telegram messages only on confirmed state transitions.
   - **Entry filled:** pair, both symbols, BUY/SHORT, quantities, actual average fills, pair Z at signal/fill, target Z, stop Z, indicative leg target/stop prices, capital used, and maximum holding date.
   - **Entry failure/compensation:** failure reason and confirmation that exposure is flat or still requires attention.
   - **Exit filled:** reason, both exit fills, realized P&L per leg and pair, holding period, and account impact.
   - **Risk/error alert:** stale data, disconnected stream, blocked account, unbalanced pair, rejected order, or reconciliation mismatch.
   - Notification outbox keys prevent duplicates after restart/retry.

7. Expand the Auto Trade UI:
   - active pair trades and both legs;
   - pending/partial/rejected orders;
   - target/stop/time-stop status;
   - realized and unrealized pair P&L;
   - broker-vs-local reconciliation state;
   - arm/disarm and kill-switch controls with confirmation and audit trail.

## Verification criteria

- A qualifying dry intent can create exactly one two-leg Alpaca paper trade.
- Telegram entry alert is sent only after both legs fill and contains actual broker fill values.
- Re-running submission, restarting mid-submit, or receiving duplicate broker events never duplicates an order.
- If only one leg fills, compensation produces a flat account or an explicit `ERROR_REQUIRES_ATTENTION` alert—never a silently unhedged position.
- Strategy 4 target, stop, and time-stop each close both legs and record the correct exit reason.
- Local orders/positions/P&L reconcile with Alpaca after restart.
- Disarming stops new entries but continues monitoring and closing already-open Strategy 4 positions.
- Kill switch cancels pending entries and blocks new ones; any flatten-all action remains separately confirmed and audited.

## Required tests before Phase 3 is complete

- State-machine transition and invalid-transition tests.
- Mocked broker tests for both filled, partial fills, one-leg reject, one-leg timeout, cancel race, late fill, replace, network timeout after accepted order, and duplicate trade updates.
- Idempotency and crash-recovery tests at every submission/exit checkpoint.
- Pair math tests for long-spread and short-spread direction, beta quantities, per-leg P&L, net P&L, target, stop, and time-stop.
- Reconciliation tests where local state differs from Alpaca orders/positions.
- Telegram outbox tests proving entry/exit/error alerts are sent once and only to authorized chats.
- Alpaca paper-account smoke test with minimal quantities, followed by verified flattening.
- Full backend tests and frontend production build must pass.

---

# Phase 4 — Production-style scheduling, daily reporting, observability, and paper soak test

## Goal

Operate the paper bot every US trading day with clear controls, reporting, restart recovery, and evidence that it is reliable enough for ongoing paper evaluation.

## Implementation steps

1. Extend the existing APScheduler integration with separately locked jobs:
   - market-calendar refresh;
   - Strategy 4 pre-market scan at the configurable offset before market open;
   - entry execution at the configured regular-session window;
   - order/position reconciliation every 10 minutes while orders or positions exist;
   - Strategy 4 exit evaluation every 10 minutes during the monitored session;
   - daily account report at 10:00 AM Asia/Kolkata;
   - end-of-session reconciliation and daily performance snapshot.

2. Implement distributed/process-safe job locking and misfire policy.
   - Prevent two API workers from running the same job.
   - Record job start, heartbeat, completion, skip, failure, and duration.
   - On restart, reconcile Alpaca first, then resume scheduling.
   - Never “catch up” by blindly submitting a stale missed entry.

3. Implement the 10:00 AM IST Telegram account report using Alpaca as source of truth:
   - account equity/portfolio value;
   - cash and buying power;
   - market value currently invested, with long and short exposure separated;
   - total unrealized and realized P&L where available;
   - each open holding: symbol, side, quantity, average entry rate, current rate, market value, and current P&L;
   - active Strategy 4 pairs and any unmatched/manual Alpaca positions;
   - pending orders and bot health summary.

4. Complete the Auto Trade UI section:
   - account summary and exposure;
   - bot health, current mode, last heartbeat, next jobs, and last successful run;
   - Strategy 4 scan history and rejection audit;
   - open/closed pair trades and performance;
   - order/reconciliation event timeline;
   - Telegram authorization/delivery status without exposing chat-sensitive data;
   - manual dry scan, reconciliation, test-message, arm/disarm, and kill-switch controls;
   - paper-trading banner on every page in this section.

5. Add operational alerts:
   - missed pre-market scan;
   - scheduler or heartbeat stale;
   - Alpaca/Telegram/data-provider outage;
   - stale market data;
   - broker/local position mismatch;
   - buying-power or margin warning;
   - persistent unbalanced pair;
   - daily report failure.

6. Add paper-performance reporting separate from backtest results.
   - realized/unrealized P&L;
   - fill slippage vs signal/reference price;
   - rejected/missed/partial trades;
   - exposure and drawdown curve;
   - win rate, profit factor, holding time, and exit-reason distribution;
   - comparison against the Strategy 4 backtest assumptions without rewriting historical results.

7. Run an end-to-end paper soak period before declaring the automation complete.
   - Minimum recommended duration: 10 US trading sessions.
   - Use real scheduled scans and monitoring.
   - No manual database edits to make results appear successful.
   - Record every incident and corrective change.

## Verification criteria

- Jobs execute once at the correct local/market times across EST/EDT and IST.
- Weekends, holidays, and early-close days do not create stale entries.
- The 10:00 AM IST report matches Alpaca account and position values within documented rounding tolerance.
- Restarting during pre-market, an open order, or an open pair recovers safely and without duplicate actions.
- A second application worker cannot duplicate a scheduled scan/order.
- UI, database, Alpaca, and Telegram reflect the same pair/order state.
- Alerts fire for intentionally simulated outages and mismatches.
- The soak test completes with no silent unhedged exposure, duplicate order, duplicate notification, missed exit evaluation, or secret leakage.

## Required tests before Phase 4 is complete

- Scheduler tests with a controllable clock for IST, EST, EDT, DST changes, holidays, early closes, misfires, and restart recovery.
- Multi-worker lock/concurrency tests.
- Daily account-report formatting and calculation tests using mocked Alpaca accounts with long, short, flat, pending, and mixed/manual positions.
- End-to-end mocked workflow: authorize Telegram -> scan -> qualify pair -> submit -> both fill -> monitor -> exit -> reconcile -> report.
- Fault-injection tests for Alpaca outage, Telegram outage, data outage, database lock, process crash, stale stream, and malformed broker response.
- Security tests for unauthorized UI/API actions, Telegram passcode brute-force controls, and secret redaction.
- Frontend tests and production build.
- Complete backend regression suite.
- Controlled Alpaca paper smoke test and documented 10-session soak-test report.

---

## 4. Phase completion rule

A phase is complete only when all of the following are true:

1. every implementation step for that phase is present;
2. every verification criterion has been checked and recorded;
3. all required new tests pass;
4. the existing backend regression suite still passes;
5. the frontend production build passes when the phase touches frontend code;
6. no credentials or passcodes appear in source control, logs, API responses, database content, screenshots, or test output;
7. the phase has a short verification report listing commands run, results, known limitations, and any deferred work.

An agent must not say a phase is complete merely because the code was written.

## 5. Initial definition of done for the complete project

- Strategy 4 alone generates live-paper candidates from completed daily data.
- Eligible pair orders execute in Alpaca paper trading with both-leg safety.
- Orders and positions reconcile every 10 minutes, with streaming updates used when available.
- Strategy 4 target, stop, and time-stop rules manage exits.
- Telegram passcode onboarding works and only authorized chats receive messages.
- Entry messages are sent only after both legs fill.
- Exit, failure, mismatch, and operational alerts are reliable and deduplicated.
- The 10:00 AM IST account report is accurate and automatic.
- The Auto Trade application section provides operational visibility and safe controls.
- Restarts and duplicate scheduler invocations do not duplicate trades.
- A documented paper soak test demonstrates stable daily operation.

## 6. External behavior references used by this plan

- Alpaca paper trading is a simulation with paper-specific limitations and uses a separate paper API endpoint: <https://docs.alpaca.markets/us/docs/paper-trading>
- Alpaca order lifecycle, buying-power checks, extended-hours restrictions, bracket behavior, and order-state streaming guidance: <https://docs.alpaca.markets/us/docs/orders-at-alpaca>
- Alpaca margin and short-selling rules, including account-equity threshold and ETB/HTB checks: <https://docs.alpaca.markets/us/docs/margin-and-short-selling>
- Telegram Bot API update delivery, `getUpdates`, webhooks, and `sendMessage`: <https://core.telegram.org/bots/api>

