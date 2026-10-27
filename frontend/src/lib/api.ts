// Typed API client. All calls go through /api which Vite proxies to FastAPI
// (and which FastAPI serves directly in production).
import type {
  AIJob,
  DecisionRow,
  Health,
  Lesson,
  OptionPosition,
  Position,
  PortfolioSnapshot,
  ProfileRow,
  RunRow,
  Scorecard,
  SchedulerStatus,
  StructurePosition,
  TelegramLogRow,
  WatchlistItem,
} from "./types";

// In dev + single-service prod, Vite/FastAPI handle "/api".
// On Vercel (frontend split from backend), set VITE_API_BASE to the Render
// backend URL, e.g. https://akash-backend.onrender.com
const BASE = (import.meta.env.VITE_API_BASE as string | undefined)?.replace(/\/$/, "") || "/api";

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`${res.status} ${res.statusText}: ${text.slice(0, 200)}`);
  }
  // Some endpoints return text/markdown
  const ct = res.headers.get("content-type") || "";
  if (ct.includes("application/json")) return res.json() as Promise<T>;
  return (await res.text()) as unknown as T;
}

const get = <T>(p: string) => req<T>(p);
const post = <T>(p: string, body?: unknown) =>
  req<T>(p, { method: "POST", body: body ? JSON.stringify(body) : undefined });
const put = <T>(p: string, body?: unknown) =>
  req<T>(p, { method: "PUT", body: body ? JSON.stringify(body) : undefined });
const del = <T>(p: string) => req<T>(p, { method: "DELETE" });

export const api = {
  health: () => get<Health>("/health"),

  // Pairs Trading
  pairs: (params?: { sector?: string; min_corr?: number; search?: string; elite?: boolean }) => {
    const q = new URLSearchParams();
    if (params?.sector) q.set("sector", params.sector);
    if (params?.min_corr) q.set("min_corr", String(params.min_corr));
    if (params?.search) q.set("search", params.search);
    if (params?.elite) q.set("elite", "true");
    const qs = q.toString();
    return get<{
      metadata: {
        description: string;
        min_correlation: number;
        trading_days: number;
        filtered_count: number;
        total_count: number;
      };
      pairs: {
        ticker_a: string;
        ticker_b: string;
        sector: string;
        correlation: number;
        cointegration_pvalue: number;
        half_life?: number;
        hurst_exponent?: number;
        adf_t_stat?: number;
        zero_crossings?: number;
      }[];
    }>(`/pairs${qs ? `?${qs}` : ""}`);
  },

  activeSetups: (params?: {
    threshold?: number;
    sector?: string;
    search?: string;
    perfect_only?: boolean;
    low_spread_only?: boolean;
    medium_to_low_spread_only?: boolean;
    tradeable_now_only?: boolean;
    max_spread_vol?: number;
    limit?: number;
    refresh?: boolean;
  }) => {
    const q = new URLSearchParams();
    if (params?.threshold) q.set("threshold", String(params.threshold));
    if (params?.sector) q.set("sector", params.sector);
    if (params?.search) q.set("search", params.search);
    if (params?.perfect_only) q.set("perfect_only", "true");
    if (params?.low_spread_only) q.set("low_spread_only", "true");
    if (params?.medium_to_low_spread_only) q.set("medium_to_low_spread_only", "true");
    if (params?.tradeable_now_only) q.set("tradeable_now_only", "true");
    if (params?.max_spread_vol !== undefined) q.set("max_spread_vol", String(params.max_spread_vol));
    if (params?.limit) q.set("limit", String(params.limit));
    if (params?.refresh) q.set("refresh", "true");
    const qs = q.toString();
    return get<{
      metadata: {
        description: string;
        threshold: number;
        lookback_days: number;
        total_pairs_evaluated: number;
        active_setups_count: number;
        perfect_only?: boolean;
        low_spread_only?: boolean;
        medium_to_low_spread_only?: boolean;
        tradeable_now_only?: boolean;
        max_spread_vol?: number;
        generated_at?: string;
      };
      setups: {
        ticker_a: string;
        ticker_b: string;
        sector: string;
        current_z_score: number;
        hedge_ratio: number;
        trade_direction: string;
        action_a?: string;
        action_b?: string;
        exit_action_a?: string;
        exit_action_b?: string;
        target_price_a?: number;
        target_price_b?: number;
        stop_loss_price_a?: number;
        stop_loss_price_b?: number;
        expected_profit_dollar_a?: number;
        expected_profit_dollar_b?: number;
        expected_profit_pct_a?: number;
        expected_profit_pct_b?: number;
        pair_unit_cost?: number;
        current_spread: number;
        spread_mean: number;
        spread_std: number;
        relative_spread_vol_pct?: number;
        spread_tier?: string;
        spread_tightness_score?: number;
        is_low_spread?: boolean;
        is_medium_to_low_spread?: boolean;
        return_5y_a?: number;
        return_5y_b?: number;
        return_1y_a?: number;
        return_1y_b?: number;
        return_90d_a?: number;
        return_90d_b?: number;
        change_daily_a?: number;
        change_daily_b?: number;
        trend_a?: string;
        trend_b?: string;
        trend_co_movement_score?: number;
        spread_dislocation?: number;
        expected_reversion_return_pct?: number;
        target_exit_spread?: number;
        stop_loss_spread?: number;
        risk_reward_ratio?: number;
        expected_holding_days?: number;
        is_tradeable_now?: boolean;
        trade_readiness?: string;
        co_movement_score?: number;
        overlap_score?: number;
        overlap_pct?: number;
        overlap_tier?: string;
        divergence_score?: number;
        composite_score?: number;
        last_price_a: number;
        last_price_b: number;
        is_active: boolean;
        window_bars: number;
        historical_correlation?: number;
        cointegration_pvalue?: number;
        half_life?: number;
        hurst_exponent?: number;
        adf_t_stat?: number;
        zero_crossings?: number;
        r_squared?: number;
        checks?: Record<string, boolean>;
        passed_checks_count?: number;
        total_checks?: number;
        quality_score?: number;
        is_perfect_setup?: boolean;
        setup_grade?: string;
      }[];
      pairs: any[];
    }>(`/pairs/active-setups${qs ? `?${qs}` : ""}`);
  },

  pairHistory: (tickerA: string, tickerB: string, period = "5y", refresh = false) => {
    const qs = refresh ? `?period=${period}&refresh=true` : `?period=${period}`;
    return get<{
      ticker_a: string;
      ticker_b: string;
      sector: string;
      hedge_ratio: number;
      alpha: number;
      current_z_score: number;
      trade_direction: string;
      action_a?: string;
      action_b?: string;
      exit_action_a?: string;
      exit_action_b?: string;
      target_price_a?: number;
      target_price_b?: number;
      stop_loss_price_a?: number;
      stop_loss_price_b?: number;
      expected_profit_dollar_a?: number;
      expected_profit_dollar_b?: number;
      expected_profit_pct_a?: number;
      expected_profit_pct_b?: number;
      pair_unit_cost?: number;
      current_spread: number;
      spread_mean: number;
      spread_std: number;
      relative_spread_vol_pct?: number;
      spread_tier?: string;
      is_low_spread?: boolean;
      is_medium_to_low_spread?: boolean;
      spread_dislocation?: number;
      expected_reversion_return_pct?: number;
      target_exit_spread?: number;
      stop_loss_spread?: number;
      risk_reward_ratio?: number;
      expected_holding_days?: number;
      is_tradeable_now?: boolean;
      trade_readiness?: string;
      last_price_a: number;
      last_price_b: number;
      return_5y_a?: number;
      return_5y_b?: number;
      return_1y_a?: number;
      return_1y_b?: number;
      return_90d_a?: number;
      return_90d_b?: number;
      change_daily_a?: number;
      change_daily_b?: number;
      trend_a?: string;
      trend_b?: string;
      trend_co_movement_score?: number;
      total_bars: number;
      default_view_days: number;
      start_date_60d: string;
      bars: {
        date: string;
        price_a: number;
        price_b: number;
        price_b_overlay?: number;
        norm_a: number;
        norm_b: number;
        return_pct_a?: number;
        return_pct_b?: number;
        spread: number;
        spread_mean: number;
        spread_std: number;
        z_score: number;
        upper_threshold: number;
        lower_threshold: number;
        mean_line: number;
      }[];
      metadata: {
        historical_correlation?: number;
        cointegration_pvalue?: number;
        half_life?: number;
        hurst_exponent?: number;
        adf_t_stat?: number;
        zero_crossings?: number;
        overlap_score?: number;
        overlap_pct?: number;
        overlap_tier?: string;
        adv_a?: number;
        adv_b?: number;
        relative_spread_vol_pct?: number;
        spread_tier?: string;
        is_low_spread?: boolean;
        is_medium_to_low_spread?: boolean;
        return_5y_a?: number;
        return_5y_b?: number;
        return_1y_a?: number;
        return_1y_b?: number;
        return_90d_a?: number;
        return_90d_b?: number;
        change_daily_a?: number;
        change_daily_b?: number;
        trend_a?: string;
        trend_b?: string;
        trend_co_movement_score?: number;
        spread_dislocation?: number;
        expected_reversion_return_pct?: number;
        target_exit_spread?: number;
        stop_loss_spread?: number;
        risk_reward_ratio?: number;
        is_tradeable_now?: boolean;
        trade_readiness?: string;
        is_perfect_setup?: boolean;
      };
    }>(`/pairs/${tickerA}/${tickerB}/history${qs}`);
  },

  preloadTopSetups: (limit = 10, pairs?: { ticker_a: string; ticker_b: string }[]) =>
    post<{
      status: string;
      requested_count: number;
      preloaded_count: number;
      preloaded_pairs: string[];
      errors: string[];
    }>("/pairs/preload-top", { limit, pairs }),

  pairsConfig: () => get<Record<string, any>>("/pairs/config"),
  pairsConfigSave: (payload: Record<string, any>) =>
    post<{ status: string; message: string; config: Record<string, any> }>("/pairs/config", payload),

  // Portfolio
  portfolioSnapshot: () => get<PortfolioSnapshot>("/portfolio/snapshot"),
  portfolioOpen: () => get<Position[]>("/portfolio/open"),
  portfolioClosed: (limit = 200) => get<Position[]>(`/portfolio/closed?limit=${limit}`),
  portfolioToday: () => get<Position[]>("/portfolio/today"),
  portfolioRefresh: () => post<unknown>("/portfolio/refresh"),
  portfolioClose: (id: number, reason = "manual") =>
    post<unknown>(`/portfolio/close/${id}`, { reason }),
  portfolioCloseAll: () => post<unknown>("/portfolio/close-all"),
  portfolioHistory: () =>
    get<
      {
        snapshot_date: string;
        equity: number;
        cash: number;
        market_value: number;
        realized_pnl: number;
        unrealized_pnl: number;
        open_positions: number;
      }[]
    >("/portfolio/history"),
  portfolioBuy: (symbol: string, amount_usd: number) =>
    post<{ position_id: number; symbol: string; price: number; units: number }>(
      "/portfolio/buy",
      { symbol, amount_usd }
    ),
  positionDetail: (id: number) =>
    get<{
      position: import("./types").Position;
      bars: { date: string; close: number }[];
      ai: {
        decision_date?: string;
        verdict?: string;
        conviction?: number;
        target_6m_usd?: number;
        upside_pct?: number;
        why_now?: string;
        exit_thesis?: string;
      } | null;
    }>(`/portfolio/position/${id}`),
  portfolioQuote: (symbol: string) =>
    get<{ symbol: string; name?: string; sector?: string; price: number }>(
      `/portfolio/quote/${symbol}`
    ),
  quoteBars: (symbol: string, days = 130) =>
    get<{ date: string; close: number }[]>(`/quote/${symbol}/bars?days=${days}`),

  // Model Lab — Compare Mode
  compareModels: () =>
    get<{ key: string; id: string; name: string; tagline: string }[]>("/compare/models"),
  compareRun: (symbol: string, models: string[]) =>
    post<{
      symbol: string;
      company?: string;
      bundle: Record<string, any>;
      total_cost_usd: number;
      results: {
        key: string; model: string; tagline: string; ok: boolean;
        cost_usd?: number; latency_s?: number; error?: string | null; valid_json?: boolean;
        verdict?: string; conviction?: number; target_price?: number; stop_price?: number;
        bull_points?: string[]; bear_points?: string[]; key_risk?: string; summary?: string;
        raw_text?: string;
      }[];
    }>("/compare/run", { symbol, models }),

  // Full-pipeline bake-off (long-running job)
  compareStacks: () =>
    get<{ key: string; name: string; default: boolean }[]>("/compare/stacks"),
  compareFullStart: (symbol: string, models: string[]) =>
    post<{ job_id: string; symbol: string }>("/compare/full", { symbol, models }),
  compareFullStatus: (jobId: string) =>
    get<{
      job_id: string; symbol: string; status: string; error?: string;
      models?: string[]; total_cost_usd?: number;
      stacks: {
        name: string; model: string; ok: boolean; error?: string | null;
        cost_usd?: number; secs?: number;
        decision?: string; conviction?: number; position_pct_of_fund?: number;
        stop_price?: number; stop_pct?: number; sizing_rationale?: string;
        stop_rationale?: string; telegram_message?: string;
        telegram_portfolio_message?: string; exit_thesis?: string;
        agents?: Record<string, { score?: number | string | null; summary?: string }>;
      }[];
    }>(`/compare/full/${jobId}`),
  compareHistory: () =>
    get<{
      job_id: string; symbol: string; created_at: string; status: string;
      total_cost_usd?: number;
      verdicts: { name: string; decision?: string; conviction?: number }[];
    }[]>("/compare/history"),
  compareScorecard: () =>
    get<{
      runs_total: number;
      rows: {
        model: string; runs: number; agreement_pct?: number | null;
        avg_conviction?: number | null; valid_pct?: number | null;
        avg_cost?: number | null; avg_secs?: number | null;
      }[];
    }>("/compare/scorecard"),

  // Options module (earnings straddles)
  optionsScan: (notify = false) =>
    post<{ scanned: number; qualified: number; universe: number }>(
      "/options/scan", { notify }),
  optionsCandidates: () =>
    get<{
      id: number; scan_date: string; symbol: string; earnings_date: string;
      days_to_earnings: number; spot?: number; strike?: number; expiry?: string;
      straddle_cost?: number; implied_move_pct?: number;
      hist_median_move_pct?: number; hist_events?: number; cheapness?: number;
      atm_iv?: number; iv_percentile?: number | null;
      min_oi?: number; max_leg_spread_pct?: number | null;
      qualified: number; reject_reason?: string | null; dual_signal: number;
    }[]>("/options/candidates"),
  optionsTrack: (candidateId: number, contracts: number) =>
    post<{ position_id: number }>("/options/track",
      { candidate_id: candidateId, contracts }),
  optionsPositions: () =>
    get<{
      open: OptionPosition[]; closed: OptionPosition[];
      stats: { trades: number; win_rate_pct?: number | null;
               total_pnl_usd: number; avg_win_pct?: number | null;
               avg_loss_pct?: number | null };
      sleeve?: { count: number; capital: number };
    }>("/options/positions"),
  optionsRefresh: () =>
    post<{ marked: number }>("/options/positions/refresh"),
  optionsClose: (id: number, reason = "manual") =>
    post<OptionPosition>(`/options/position/${id}/close`, { reason }),
  optionsBacktest: (symbol: string, opts?: { refresh?: boolean; entryDays?: number }) =>
    get<{
      symbol: string; entry_days: number; computed_at?: string; error?: string;
      note?: string;
      summary: {
        events_simulated: number; events_priced: number; qualifying_events: number;
        qualifying_win_rate_pct?: number | null; qualifying_avg_pnl_pct?: number | null;
        all_events_avg_pnl_pct?: number | null; avg_implied_vs_actual?: number | null;
      };
      events: {
        earnings_date: string; entry_date?: string; exit_date?: string;
        spot_entry?: number; strike?: number; expiry?: string;
        entry_cost?: number; exit_cost?: number;
        implied_move_pct?: number; hist_median_move_pct?: number;
        actual_move_pct?: number; cheapness?: number; would_qualify?: boolean;
        trade_pnl_pct?: number; error?: string | null;
      }[];
    }>(`/options/backtest/${symbol}` +
      `?refresh=${opts?.refresh ? "true" : "false"}` +
      (opts?.entryDays ? `&entry_days=${opts.entryDays}` : "")),

  // Options: Strategy Board foundations (Phase 0)
  optionsRulebook: () =>
    get<{
      strategies: {
        key: string; name: string; status: "live" | "paper" | "planned";
        phase: string; direction: string; risk_type: string; pools: string[];
        plain: string; entry_conditions: string[]; structure: string;
        exit_rules: string[]; return_metrics: string[];
      }[];
      governance: string[];
      pool_b: {
        symbol: string; asof?: string; spot?: number | null;
        expiry?: string | null; atm_oi?: number | null;
        spread_pct?: number | null; qualified: number; note?: string;
      }[];
      league: Record<string, {
        trades: number; win_rate_pct?: number | null; total_pnl_usd: number;
        avg_return_on_risk_pct?: number | null; worst_trade_usd?: number | null;
      }>;
    }>("/options/rulebook"),
  optionsPoolBRefresh: () =>
    post<{ measured: number; qualified: number }>("/options/pool-b/refresh"),

  // Options: multi-leg paper structures (condors, spreads, …)
  optionsStructures: () =>
    get<{
      open: StructurePosition[]; closed: StructurePosition[];
      league: Record<string, { trades: number; win_rate_pct?: number | null;
        total_pnl_usd: number; avg_return_on_risk_pct?: number | null;
        worst_trade_usd?: number | null }>;
    }>("/options/structures"),
  optionsStructuresRefresh: () =>
    post<{ marked: number }>("/options/structures/refresh"),
  optionsStructureClose: (id: number, reason = "manual") =>
    post<StructurePosition>(`/options/structure/${id}/close`, { reason }),

  // Options: Strategy Board (Phase 1)
  optionsBoard: () =>
    get<{
      board_date: string | null;
      cards: {
        id: number; strategy_key: string; symbol: string;
        rules_fired?: string[]; exit_rule?: string;
        earnings_date?: string; days_to_earnings?: number; expiry?: string;
        // straddle mirror fields
        candidate_id?: number; strike?: number; straddle_cost?: number;
        cheapness?: number; dual_signal?: number;
        implied_move_pct?: number; hist_median_move_pct?: number;
        // condor fields
        spot?: number; credit?: number; max_profit?: number | null;
        max_loss?: number; breakevens?: number[]; pop_est?: number | null;
        return_on_risk_pct?: number | null; annualized_pct?: number | null;
        dte?: number; min_oi?: number; max_leg_spread_pct?: number | null;
        // income fields (R3 CSP / R4 covered call)
        premium?: number; premium_usd_per_contract?: number;
        shares_held?: number; qty_max?: number;
        monthly_yield_pct?: number | null; if_called_return_pct?: number | null;
        cash_secured_usd?: number; effective_basis?: number;
        discount_to_spot_pct?: number; ai_target?: number | null;
        ai_entry?: number; conviction?: number | null; oi?: number;
        delta?: number | null;
        // spread fields (R5 bull put / R6 bear call)
        level?: number; short_strike?: number; long_strike?: number;
        // allocator annotation (multi-strategy symbols)
        allocator?: { rank: number; of: number; why: string; basis: string };
        legs?: { side: number; contract_type: string; strike: number;
                 expiry: string; qty: number; price: number;
                 delta?: number | null; oi?: number;
                 spread_pct?: number | null }[];
      }[];
    }>("/options/board"),
  optionsBoardRefresh: (notify = false) =>
    post<{ board_date: string | null; straddle_cards?: number;
           condor_cards?: number; note?: string }>(
      "/options/board/refresh", { notify }),
  optionsBoardTrack: (boardId: number, contracts: number) =>
    post<{ position_id: number; kind: string }>(
      "/options/board/track", { board_id: boardId, contracts }),

  // Options: The Wheel (Phase 4)
  optionsWheels: () =>
    get<{
      wheels: {
        id: number; symbol: string; state: string; qty: number;
        capital_per_share?: number | null; assigned_price?: number | null;
        premiums_net?: number | null; exit_price?: number | null;
        cycle_roi_pct?: number | null; effective_basis?: number | null;
        started_at?: string; completed_at?: string | null; notes?: string;
        legs: {
          id: number; wheel_id: number; seq: number; kind: string;
          strike: number; expiry: string; premium: number; qty: number;
          outcome?: string | null; close_price?: number | null;
          opened_at?: string; closed_at?: string | null;
        }[];
      }[];
    }>("/options/wheels"),
  optionsWheelStart: (symbol: string, qty = 1) =>
    post<unknown>("/options/wheels", { symbol, qty }),
  optionsWheelLeg: (wheelId: number, kind: string, strike: number,
                    expiry: string, premium: number) =>
    post<unknown>(`/options/wheels/${wheelId}/leg`,
      { kind, strike, expiry, premium }),
  optionsWheelResolve: (wheelId: number, legId: number, outcome: string,
                        closePrice?: number) =>
    post<unknown>(`/options/wheels/${wheelId}/leg/${legId}/resolve`,
      { outcome, close_price: closePrice }),
  optionsWheelSuggest: (wheelId: number) =>
    get<{
      state: string; kind?: "csp" | "cc"; note?: string;
      suggestion?: {
        ok: boolean; reason?: string; strike?: number; expiry?: string;
        premium?: number; premium_usd_per_contract?: number;
        annualized_pct?: number | null;
      } | null;
      ai_levels?: { entry?: number | null; target?: number | null;
                    conviction?: number | null } | null;
    }>(`/options/wheels/${wheelId}/suggest`),

  // Options: Pro Desk (Phase 6)
  optionsGreeks: () =>
    get<{
      totals: { delta: number; theta: number; vega: number };
      per_symbol: Record<string, { delta: number; theta: number; vega: number }>;
      positions_counted: number; unmarked: string[]; note: string;
    }>("/options/greeks"),
  optionsSlippage: () =>
    get<{
      families: Record<string, { fills: number; median_slippage_pct: number }>;
      fills_recorded: number; median_slippage_pct?: number | null;
      upgrade_trigger_pct: number; upgrade_recommended: boolean; note: string;
    }>("/options/slippage"),
  optionsSeasonReport: () =>
    get<{ markdown: string; generated_at: string }>("/options/season-report"),

  // Options: Returns Engine (Phase 2)
  optionsLeague: () =>
    get<{
      rows: {
        key: string; name: string; status: string;
        trades: number; win_rate_pct?: number | null;
        avg_return_on_risk_pct?: number | null; total_pnl_usd: number;
        worst_trade_usd?: number | null;
        open_count: number; open_capital: number;
      }[];
    }>("/options/league"),
  optionsReportCard: () =>
    get<{
      symbols_covered: number; symbols_errored: number;
      events_priced: number; qualifying_events: number;
      qualifying_win_rate_pct?: number | null;
      qualifying_avg_pnl_pct?: number | null;
      avg_implied_vs_actual?: number | null;
      leaders: { symbol: string; qualifying_events?: number | null;
                 win_rate_pct?: number | null;
                 avg_pnl_pct?: number | null }[];
      generated_at: string;
    }>("/options/report-card"),
  optionsReportCardRun: (limit = 5) =>
    post<{ batch_done: number; batch_failed: number;
           coverage: number; universe: number }>(
      "/options/report-card/run", { limit }),
  optionsCondorBacktest: (symbol: string, refresh = false) =>
    get<{
      symbol: string; entry_days: number; computed_at?: string;
      error?: string; note?: string;
      summary?: {
        events_simulated: number; events_priced: number;
        rule_fired_events: number;
        fired_win_rate_pct?: number | null;
        fired_avg_return_on_risk_pct?: number | null;
        all_avg_return_on_risk_pct?: number | null;
      };
      events?: {
        earnings_date: string; error?: string | null;
        credit?: number; max_loss?: number; cheapness?: number | null;
        implied_move_pct?: number; actual_move_pct?: number | null;
        inside_range?: boolean | null; trade_pnl_usd?: number;
        return_on_risk_pct?: number; would_fire?: boolean;
      }[];
    }>(`/options/condor-backtest/${symbol}?refresh=${refresh ? "true" : "false"}`),

  // Settings (portfolio + scheduler)
  getSettings: () =>
    get<{
      portfolio: Record<string, { value: number | string | boolean; env_default: unknown }>;
      scheduler: Record<string, { value: number | string | boolean; env_default: unknown }>;
    }>("/settings"),
  updateSettings: (updates: Record<string, unknown>) =>
    post<{ applied: string[]; rejected: string[]; snapshot: unknown }>("/settings", updates),
  portfolioReset: (cash?: number) =>
    post<{ reset: boolean; positions_cleared: number; cash: number }>(
      "/portfolio/reset",
      cash != null ? { cash } : {}
    ),
  portfolioSetCash: (cash: number) =>
    post<{ cash: number }>("/portfolio/cash", { cash }),
  portfolioImport: (
    positions: {
      symbol: string;
      shares: number;
      entry_price: number;
      entry_date?: string;
      instrument_type?: string;
      option_type?: string;
      strike?: number;
      expiry?: string;
    }[]
  ) =>
    post<{
      added: number;
      total: number;
      results: { symbol: string; status: string; detail?: string; price?: number }[];
    }>("/portfolio/import", { positions }),
  positionAdd: (id: number, amount_usd: number) =>
    post<{ ok: boolean; price: number }>(`/portfolio/position/${id}/add`, { amount_usd }),
  positionTrim: (id: number, fraction: number) =>
    post<{ ok: boolean; price: number }>(`/portfolio/position/${id}/trim`, { fraction }),

  // AI pipeline
  aiAnalyze: (symbol: string, notes?: string) =>
    post<{ job_id: string }>("/ai/analyze", { symbol, source: "manual", notes }),
  aiJob: (jobId: string) => get<AIJob>(`/ai/analyze/${jobId}`),
  aiJobs: () => get<AIJob[]>("/ai/jobs"),
  aiDecisions: () => get<DecisionRow[]>("/ai/decisions"),
  aiDecisionFiles: (symbol: string, date: string) =>
    get<Record<string, string>>(`/ai/decisions/${symbol}/${date}`),
  aiScorecards: (symbol: string, date: string) =>
    get<Scorecard[]>(`/ai/decisions/${symbol}/${date}/scorecards`),

  // Morning / Weekly
  morningDates: () => get<string[]>("/ai/morning/dates"),
  morningFiles: (date: string) => get<Record<string, string>>(`/ai/morning/${date}`),
  morningRun: () => post<{ job_id: string }>("/ai/morning/run"),
  weeklyList: () => get<string[]>("/ai/weekly"),
  weeklyGet: (date: string) => get<Record<string, string>>(`/ai/weekly/${date}`),

  // Profiles / Watchlist
  profiles: () => get<ProfileRow[]>("/profiles"),
  profile: (symbol: string) => get<Record<string, unknown>>(`/profiles/${symbol}`),
  profileRaw: (symbol: string) => get<{ content: string }>(`/profiles/${symbol}/raw`),
  profileSaveRaw: (symbol: string, content: string) =>
    put<Record<string, unknown>>(`/profiles/${symbol}/raw`, { content }),
  profileDelete: (symbol: string) => del<unknown>(`/profiles/${symbol}`),
  watchlist: () => get<WatchlistItem[]>("/watchlist"),
  watchlistAdd: (symbol: string, notes?: string) =>
    post<unknown>("/watchlist", { symbol, notes }),
  watchlistRemove: (symbol: string) => del<unknown>(`/watchlist/${symbol}`),
  watchlistToggle: (symbol: string, enabled: boolean) =>
    post<unknown>(`/watchlist/${symbol}/toggle`, { enabled }),

  // Scheduler / Automation
  schedulerStatus: () => get<SchedulerStatus>("/scheduler/status"),
  schedulerStart: () => post<unknown>("/scheduler/start"),
  schedulerStop: () => post<unknown>("/scheduler/stop"),
  schedulerQuantScan: () =>
    post<
      {
        symbol: string;
        score: number;
        rank: number;
        trend_ok: boolean;
        breakout_ok: boolean;
        current_price: number;
        atr: number;
        as_of_date: string;
      }[]
    >("/scheduler/quant-scan"),
  schedulerRunMorning: () => post<unknown>("/scheduler/run/morning"),
  schedulerRunEvening: () => post<unknown>("/scheduler/run/evening"),
  schedulerRunWeekly: () => post<unknown>("/scheduler/run/weekly"),
  telegramLog: (limit = 50) => get<TelegramLogRow[]>(`/telegram/log?limit=${limit}`),
  telegramTest: (text?: string) => post<unknown>("/telegram/test", text ? { text } : {}),

  // Memory
  lessons: (limit = 100) => get<Lesson[]>(`/memory/lessons?limit=${limit}`),
  memoryPending: () => get<Lesson[]>("/memory/pending"),
  memoryReflect: () => post<unknown>("/memory/reflect"),

  // Backtesting
  universes: () => get<string[]>("/universes"),
  runs: (limit = 200) => get<RunRow[]>(`/runs?limit=${limit}`),
  run: (id: string) => get<Record<string, unknown>>(`/backtest/${id}`),
  runEquity: (id: string) =>
    get<{ timestamp: string; equity: number }[]>(`/backtest/${id}/equity`),
  runTrades: (id: string) => get<Record<string, unknown>[]>(`/backtest/${id}/trades`),
  runPerSymbol: (id: string) => get<Record<string, unknown>[]>(`/backtest/${id}/per-symbol`),
  runDelete: (id: string) => del<unknown>(`/runs/${id}`),
  runProgress: (id: string) => get<Record<string, unknown>>(`/backtest/${id}/progress`),
  backtestRun: (payload: unknown) => post<{ run_id: string }>("/backtest/run", payload),
  compare: (runIds: string[]) => post<Record<string, unknown>>("/compare", { run_ids: runIds }),
  dataStatus: () => get<Record<string, unknown>[]>("/data/status"),
  dataRefresh: (payload: {
    universe?: string;
    symbols?: string[];
    timeframe?: string;
    years?: number;
    full?: boolean;
  }) => post<{ job_id: string; symbols: number; label: string }>("/data/refresh", payload),
  dataRefreshStatus: (jobId: string) =>
    get<{
      status: string;
      done: number;
      total: number;
      current_symbol: string;
      label: string;
      timeframe: string;
      error?: string;
    }>(`/data/refresh/${jobId}`),
  params: () => get<{ name: string; params: Record<string, unknown> }[]>("/params"),
  paramGet: (name: string) =>
    get<{ name: string; params: Record<string, unknown> }>(`/params/${name}`),
  paramSave: (name: string, params: Record<string, unknown>) =>
    post<{ name: string; params: Record<string, unknown> }>("/params/save", { name, params }),
  paramDelete: (name: string) => del<unknown>(`/params/${name}`),
};
