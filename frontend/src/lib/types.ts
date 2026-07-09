// Shared API types — mirror the FastAPI response shapes we consume.

export interface Health {
  status: string;
}

export interface PortfolioSnapshot {
  equity: number; // account value = cash + holdings
  cash: number; // editable balance
  open_market_value: number; // holdings at market
  cost_basis: number; // holdings at cost
  realized_pnl: number;
  unrealized_pnl: number;
  total_return_pct: number;
  gross_exposure_pct: number; // % invested
  open_positions: number;
  initial_capital?: number; // legacy
}

export interface Position {
  id: number;
  symbol: string;
  sector?: string;
  entry_date?: string;
  entry_price?: number;
  current_price?: number;
  units?: number;
  market_value?: number;
  current_pnl_pct?: number;
  current_pnl_usd?: number;
  days_held?: number;
  trailing_stop?: number;
  initial_stop?: number;
  high_water_mark?: number;
  prev_close?: number;
  day_change_pct?: number;
  instrument_type?: string;   // 'stock' | 'option'
  option_type?: string;       // 'call' | 'put'
  strike?: number;
  expiry?: string;
  multiplier?: number;
  decision_verdict?: string;
  decision_conviction?: number;
  decision_size_pct?: number;
  status?: string;
  exit_date?: string;
  exit_price?: number;
  exit_reason?: string;
  final_pnl_usd?: number;
  final_pnl_pct?: number;
}

export interface AIJob {
  job_id: string;
  symbol: string;
  status: "queued" | "running" | "complete" | "failed";
  current_stage?: string;
  current_msg?: string;
  started_at?: string;
  completed_at?: string;
  signal_date?: string;
  stages?: StageEvent[];
  verdict?: { decision?: string; conviction?: number; size_pct?: number };
  error?: string;
}

export interface StageEvent {
  stage: string;
  msg?: string;
  at?: string;
  agent?: string;
  model?: string;
  action?: string;
  metrics?: Record<string, unknown>;
}

export interface Scorecard {
  name: string;
  emoji: string;
  label: string;
  score_label: string;
  score_value: number | string | null;
  summary: string;
  stage: string;
  // PM-only extras
  telegram_message?: string;
  telegram_portfolio_message?: string;
}

export interface DecisionRow {
  symbol: string;
  date: string;
  decision?: string;
  conviction?: number;
  size_pct?: number;
  source?: string;
  status: string;
  stages_present?: string[];
  has_summary?: boolean;
}

export interface ProfileRow {
  symbol: string;
  name?: string;
  sector?: string;
  priority?: string;
  position_intent?: string;
  held?: boolean;
  bull_pillar_count?: number;
  bear_pillar_count?: number;
  red_line_count?: number;
  last_reviewed?: string;
}

export interface WatchlistItem {
  symbol: string;
  enabled?: boolean;
  notes?: string;
  added_at?: string;
}

export interface RunMetrics {
  cagr?: number;
  total_return?: number;
  max_drawdown?: number;
  sharpe?: number;
  sortino?: number;
  annualized_vol?: number;
  final_equity?: number;
  "trades.total_trades"?: number;
  "trades.winners"?: number;
  "trades.losers"?: number;
  "trades.win_rate"?: number;
  [k: string]: number | undefined;
}

export interface RunRow {
  id: string;
  name?: string;
  status?: string;
  progress?: number;
  started_at?: string;
  finished_at?: string;
  timeframe?: string;
  universe_name?: string;
  initial_capital?: number;
  metrics?: RunMetrics;
}

export interface ParamPreset {
  name: string;
  params: Record<string, unknown>;
}

export interface SchedulerStatus {
  running?: boolean;
  jobs?: { id: string; next_run?: string; trigger?: string }[];
  [k: string]: unknown;
}

export interface Lesson {
  id?: number;
  symbol?: string;
  lesson?: string;
  created_at?: string;
  category?: string;
  [k: string]: unknown;
}

export interface TelegramLogRow {
  id?: number;
  sent_at?: string;
  symbol?: string;
  kind?: string;
  text?: string;
  status?: string;
  error?: string;
}

export interface OptionPosition {
  id: number;
  symbol: string;
  status: string;
  contracts: number;
  strike?: number;
  expiry?: string;
  earnings_date?: string;
  exit_deadline?: string;
  entry_date?: string;
  entry_spot?: number;
  entry_cost?: number;
  entry_iv?: number;
  current_value?: number;
  current_iv?: number;
  current_spot?: number;
  pnl_usd?: number;
  pnl_pct?: number;
  vega_pnl?: number | null;
  theta_pnl?: number | null;
  move_pnl?: number | null;
  last_marked?: string;
  exit_date?: string;
  exit_value?: number;
  exit_reason?: string;
  final_pnl_usd?: number;
  final_pnl_pct?: number;
  notes?: string;
}
