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
