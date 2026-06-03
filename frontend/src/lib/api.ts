// Typed API client. All calls go through /api which Vite proxies to FastAPI
// (and which FastAPI serves directly in production).
import type {
  AIJob,
  DecisionRow,
  Health,
  Lesson,
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
  portfolioReset: (initial_capital?: number) =>
    post<{ reset: boolean; positions_cleared: number; initial_capital: number }>(
      "/portfolio/reset",
      initial_capital != null ? { initial_capital } : {}
    ),
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
};
