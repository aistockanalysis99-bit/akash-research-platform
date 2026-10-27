/**
 * TypeScript type definitions for the Point-in-Time Simulator.
 */

export interface PointInTimeSetup {
  ticker_a: string;
  ticker_b: string;
  pair_name: string;
  target_date: string;
  direction: "LONG_A_SHORT_B" | "SHORT_A_LONG_B" | string;
  hedge_ratio: number;
  alpha: number;
  r_squared: number;
  correlation: number;
  current_z_score: number;
  abs_z_score: number;
  current_spread: number;
  spread_mean: number;
  spread_std: number;
  target_spread_mean: number;
  target_spread_80pct: number;
  stop_loss_spread: number;
  price_a_entry: number;
  price_b_entry: number;
  adf_tstat: number;
  adf_pvalue: number;
  half_life_days: number;
  zero_crossings: number;
  relative_spread_vol_pct: number;
  spread_tier: "Ultra Tight" | "Tight" | "Medium" | "Wide" | string;
  composite_score: number;
  is_setup: boolean;
  window_bars: number;
  sector?: string;
  checks?: Record<string, boolean>;
  passed_checks_count?: number;
  is_perfect?: boolean;
  is_tradeable?: boolean;
  expected_reversion_return_pct?: number;
  risk_reward_ratio?: number;
  action_a?: string;
  action_b?: string;
}

export interface SimulatorInitResponse {
  status: string;
  anchor_date: string;
  current_date: string;
  min_date: string;
  max_date: string;
  total_trading_days: number;
  current_index: number;
  intact_pairs_count: number;
  parameters: {
    lookback_days: number;
    min_z_score: number;
    max_adf_pvalue: number;
    min_correlation: number;
    max_horizon_days: number;
  };
}

export interface SimulatorScanResponse {
  current_date: string;
  total_setups_found: number;
  setups: PointInTimeSetup[];
  scan_latency_ms: number;
  trading_date_used?: string;
  total_pairs_evaluated?: number;
  perfect_count?: number;
  tradeable_count?: number;
  tradeable_setups?: PointInTimeSetup[];
}

export interface SimulatorStepResponse {
  previous_date: string;
  current_date: string;
  direction: string;
  current_index: number;
  total_dates: number;
  is_min_date: boolean;
  is_max_date: boolean;
}

export interface HistoricalBar {
  date: string;
  price_a: number;
  price_b: number;
  spread: number;
  z_score: number;
}

export interface ForwardBar {
  date: string;
  days_elapsed: number;
  price_a: number;
  price_b: number;
  spread: number;
  z_score: number;
}

export interface ForwardEvaluationResult {
  pair_name: string;
  target_date: string;
  direction: string;
  outcome: "WIN" | "LOSS" | "NEUTRAL" | "OPEN" | string;
  status_reason: string;
  entry_price_a: number;
  entry_price_b: number;
  entry_spread: number;
  entry_z_score: number;
  exit_date?: string | null;
  exit_days_held: number;
  exit_price_a?: number | null;
  exit_price_b?: number | null;
  exit_spread?: number | null;
  exit_z_score?: number | null;
  realized_pnl_pct: number;
  max_favorable_z: number;
  max_adverse_z: number;
  path: Array<{
    date: string;
    days_elapsed: number;
    price_a: number;
    price_b: number;
    spread: number;
    z_score: number;
  }>;
}

export interface PairChartResponse {
  ticker_a: string;
  ticker_b: string;
  current_date: string;
  reveal: boolean;
  setup?: PointInTimeSetup | null;
  historical_bars: HistoricalBar[];
  forward_bars?: ForwardBar[] | null;
  forward_outcome?: ForwardEvaluationResult | null;
}

export interface DayBatchScorecard {
  target_date: string;
  total_setups: number;
  win_count: number;
  loss_count: number;
  neutral_count: number;
  win_rate_pct: number;
  avg_return_pct: number;
  median_return_pct: number;
  avg_days_held: number;
  profit_factor: number;
  total_gross_profit_pct: number;
  total_gross_loss_pct: number;
  evaluations: ForwardEvaluationResult[];
}

export interface Backtest1YTrade {
  id: string;
  pair_name: string;
  ticker_a: string;
  ticker_b: string;
  sector: string;
  entry_date: string;
  exit_date?: string | null;
  direction: string;
  direction_label: string;
  entry_z: number;
  abs_entry_z: number;
  exit_z?: number | null;
  hedge_ratio: number;
  entry_price_a: number;
  entry_price_b: number;
  exit_price_a?: number | null;
  exit_price_b?: number | null;
  outcome: "WIN" | "LOSS" | "NEUTRAL" | "OPEN" | string;
  status_reason: string;
  realized_return_pct: number;
  holding_days: number;
  max_favorable_z: number;
  max_adverse_z: number;
  is_perfect_10: boolean;
  passed_checks_count: number;
  checks?: Record<string, boolean>;
  adf_pvalue: number;
  correlation: number;
  half_life_days: number;
  spread_tier: string;
  relative_spread_vol_pct: number;
  composite_score: number;
}

export interface Backtest1YSummary {
  total_trades: number;
  win_count: number;
  loss_count: number;
  neutral_count: number;
  win_rate_pct: number;
  avg_return_pct: number;
  median_return_pct: number;
  avg_holding_days: number;
  profit_factor: number;
  gross_profit_pct: number;
  gross_loss_pct: number;
  max_drawdown_pct: number;
}

export interface Backtest1YResponse {
  period: {
    start_date: string;
    end_date: string;
    trading_days_evaluated: number;
    pairs_universe_count: number;
  };
  overall_summary: Backtest1YSummary;
  perfect_10_summary: Backtest1YSummary;
  checks_8plus_summary: Backtest1YSummary;
  trades: Backtest1YTrade[];
  meta: {
    entry_z: number;
    stop_z: number;
    max_horizon_days: number;
    computed_at: string;
    latency_seconds: number;
  };
}
