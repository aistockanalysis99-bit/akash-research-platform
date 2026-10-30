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
  is_tradeable?: boolean;
  is_ready_to_take?: boolean;
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
  equity_curve?: Array<{
    date: string;
    trade_id?: string;
    return_pct?: number;
    cumulative_equity_pct?: number;
    cumulative_return_pct?: number;
    drawdown_pct?: number;
  }>;
  monthly_returns?: Array<{
    month: string;
    trades_count: number;
    win_rate_pct: number;
    return_pct: number;
    cumulative_return_pct?: number;
  }>;
  meta: {
    entry_z: number;
    stop_z: number;
    max_horizon_days: number;
    computed_at: string;
    latency_seconds: number;
  };
}

export interface SavedTradeHighlight {
  pair_name: string;
  realized_return_pct: number;
  entry_date: string;
  exit_date?: string;
  holding_days: number;
}

export interface SavedBacktestRun {
  run_id: string;
  test_name?: string;
  start_date: string;
  end_date: string;
  entry_z: number;
  stop_z: number;
  max_horizon_days: number;
  trading_days: number;
  total_trades: number;
  win_count: number;
  loss_count: number;
  win_rate_pct: number;
  profit_factor: number;
  avg_return_pct: number;
  net_return_pct?: number;
  max_drawdown_pct: number;
  avg_holding_days: number;
  best_trade?: SavedTradeHighlight | null;
  worst_trade?: SavedTradeHighlight | null;
  perfect_10_win_rate?: number;
  perfect_10_trades?: number;
  computed_at: string;
  latency_seconds: number;
}

// ---------------------------------------------------------------------------
// Strategy v2 Type Definitions
// ---------------------------------------------------------------------------

export interface StrategyV2Trade {
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
  hurdle_breached_z: number;
  hook_entry_z: number;
  exit_z?: number | null;
  hedge_ratio: number;
  entry_price_a: number;
  entry_price_b: number;
  exit_price_a?: number | null;
  exit_price_b?: number | null;
  outcome: "WIN" | "LOSS" | "NEUTRAL" | "OPEN" | string;
  exit_reason: "TP1_AND_TP2" | "TP1_AND_BREAKEVEN" | "STOP_LOSS" | "TIME_STOP" | "EXPIRED" | string;
  status_reason: string;
  realized_return_pct: number;
  holding_days: number;
  time_stop_days: number;
  max_favorable_z: number;
  max_adverse_z: number;
  tp1_hit: boolean;
  tp1_date?: string | null;
  tp1_days_held: number;
  tp1_z_score?: number | null;
  tranche1_pnl_pct: number;
  tp2_hit: boolean;
  tp2_date?: string | null;
  tp2_days_held: number;
  tp2_z_score?: number | null;
  tranche2_pnl_pct: number;
  breakeven_stop_hit: boolean;
  time_stop_hit: boolean;
  stop_loss_hit: boolean;
  is_perfect: boolean;
  passed_checks_count: number;
  is_tradeable: boolean;
  checks?: Record<string, boolean>;
  adf_pvalue: number;
  correlation: number;
  r_squared: number;
  half_life_days: number;
  spread_tier: string;
  relative_spread_vol_pct: number;
  composite_score: number;
  trajectory?: Array<{
    date: string;
    days_elapsed: number;
    price_a: number;
    price_b: number;
    spread: number;
    z_score: number;
  }>;
}

export interface StrategyV2Summary {
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
  tp1_and_tp2_count: number;
  tp1_and_breakeven_count: number;
  stop_loss_count: number;
  time_stop_count: number;
}

export interface StrategyV2MonthlyReturn {
  month: string;
  trades_count: number;
  win_rate_pct: number;
  return_pct: number;
  cumulative_return_pct: number;
}

export interface StrategyV2EquityPoint {
  date: string;
  trade_id: string;
  return_pct: number;
  cumulative_equity_pct: number;
  drawdown_pct: number;
}

export interface StrategyV2Response {
  version: string;
  strategy_name: string;
  period: {
    start_date: string;
    end_date: string;
    trading_days_evaluated: number;
    pairs_universe_count: number;
  };
  overall_summary: StrategyV2Summary;
  perfect_summary: StrategyV2Summary;
  tradeable_summary: StrategyV2Summary;
  monthly_returns: StrategyV2MonthlyReturn[];
  equity_curve: StrategyV2EquityPoint[];
  trades: StrategyV2Trade[];
  meta: {
    strategy_version: string;
    z_score_hurdle: number;
    z_score_hook_entry: number;
    tp1_target: number;
    tp2_target: number;
    stop_loss_barrier: number;
    half_life_multiplier: number;
    computed_at: string;
    latency_seconds: number;
  };
}

export interface StrategyV2TrajectoryPin {
  date?: string | null;
  label: string;
  z_score?: number | null;
  price_a?: number | null;
  price_b?: number | null;
  days_held?: number;
  outcome?: string;
}

export interface StrategyV2TrajectoryResponse {
  trade_id: string;
  pair_name: string;
  direction: string;
  direction_label: string;
  outcome: string;
  exit_reason: string;
  realized_return_pct: number;
  holding_days: number;
  pins: {
    entry: StrategyV2TrajectoryPin;
    tp1?: StrategyV2TrajectoryPin | null;
    exit: StrategyV2TrajectoryPin;
  };
  trajectory: Array<{
    date: string;
    days_elapsed: number;
    price_a: number;
    price_b: number;
    spread: number;
    z_score: number;
  }>;
}

export interface StrategyComparisonTradeDelta {
  id: string;
  pair_name: string;
  sector: string;
  direction?: string | null;
  category: "SAVED_LOSS" | "FLIPPED_TRADE" | "PRESERVED_WINNER" | "MISSED_OPPORTUNITY" | "PERSISTENT_LOSS" | "DEGRADED_WIN" | "V2_NEW_ALPHA" | string;
  category_label: string;
  v1_entry_date?: string | null;
  v1_exit_date?: string | null;
  v1_outcome?: string | null;
  v1_return_pct?: number | null;
  v1_exit_reason?: string | null;
  v2_entry_date?: string | null;
  v2_exit_date?: string | null;
  v2_outcome?: string | null;
  v2_return_pct?: number | null;
  v2_exit_reason?: string | null;
  return_delta_pct: number;
  failure_cause?: "RUNAWAY_MOMENTUM" | "EARNINGS_SHOCK" | "PROFIT_GIVEBACK" | "STALE_DECAY" | string | null;
  explanation: string;
}

export interface StrategyComparisonSummaryDelta {
  period: string;
  win_rate_v1: number;
  win_rate_v2: number;
  win_rate_v3?: number;
  win_rate_v4?: number;
  delta_win_rate_pct: number;
  profit_factor_v1: number;
  profit_factor_v2: number;
  profit_factor_v3?: number;
  profit_factor_v4?: number;
  delta_profit_factor: number;
  max_drawdown_v1: number;
  max_drawdown_v2: number;
  max_drawdown_v3?: number;
  max_drawdown_v4?: number;
  delta_max_drawdown_saved_pct: number;
  avg_return_v1: number;
  avg_return_v2: number;
  avg_return_v3?: number;
  avg_return_v4?: number;
  delta_avg_return_pct: number;
  avg_holding_days_v1: number;
  avg_holding_days_v2: number;
  avg_holding_days_v4?: number;
  delta_avg_holding_days: number;
  total_net_return_v1?: number;
  total_net_return_v2?: number;
  total_net_return_v3?: number;
  total_net_return_v4?: number;
  total_trades_v1: number;
  total_trades_v2: number;
  total_trades_v3?: number;
  total_trades_v4?: number;
  capital_preserved_loss_pct: number;
}

export interface StrategyComparisonCategoryMetrics {
  saved_losses_count: number;
  flipped_trades_count: number;
  preserved_winners_count: number;
  missed_opportunities_count: number;
  persistent_losses_count: number;
  degraded_wins_count: number;
  v2_new_alpha_count: number;
  total_matched_pairs: number;
  capital_preserved_loss_pct: number;
}

export interface StrategyComparisonFailureAttribution {
  total_losses: number;
  counts: Record<string, number>;
  percentages: Record<string, number>;
  descriptions: Record<string, string>;
}

export interface AlignedEquityPoint {
  date: string;
  v1_equity: number;
  v2_equity: number;
  v3_equity?: number;
  v4_equity?: number;
  spread_alpha: number;
  v3_spread_alpha?: number;
  v4_spread_alpha?: number;
}

export interface StrategyComparisonResponse {
  period: string;
  summary_delta: StrategyComparisonSummaryDelta;
  category_metrics: StrategyComparisonCategoryMetrics;
  failure_attribution: StrategyComparisonFailureAttribution;
  v1_summary: Record<string, any>;
  v2_summary: Record<string, any>;
  v3_summary?: StrategyV3Summary;
  v4_summary?: StrategyV4Summary;
  trade_deltas: StrategyComparisonTradeDelta[];
  aligned_equity: AlignedEquityPoint[];
}

// ---------------------------------------------------------------------------
// Strategy v3 Types ("Asymmetric Alpha Maximizer")
// ---------------------------------------------------------------------------

export interface StrategyV3Summary {
  total_trades: number;
  win_count: number;
  loss_count: number;
  neutral_count: number;
  win_rate_pct: number;
  net_return_pct: number;
  gross_profit_pct: number;
  gross_loss_pct: number;
  profit_factor: number;
  max_drawdown_pct: number;
  avg_return_pct: number;
  avg_holding_days: number;
  disaster_floor_saved_trades: number;
  tier1_trades_count: number;
}

export interface StrategyV3Trade {
  id: string;
  pair_name: string;
  ticker_a: string;
  ticker_b: string;
  sector: string;
  entry_date: string;
  exit_date: string;
  direction: string;
  direction_label: string;
  entry_z: number;
  exit_z: number;
  hedge_ratio: number;
  entry_price_a: number;
  entry_price_b: number;
  exit_price_a: number;
  exit_price_b: number;
  outcome: string;
  exit_reason: string;
  status_reason: string;
  holding_days: number;
  raw_return_pct: number;
  realized_return_pct: number;
  conviction_tier: string;
  conviction_multiplier: number;
  composite_score: number;
  recovered_to_floor: boolean;
  protected_stop_hit: boolean;
  max_favorable_z: number;
  max_adverse_z: number;
  trajectory?: Array<{
    date: string;
    days_elapsed: number;
    price_a: number;
    price_b: number;
    spread: number;
    z_score: number;
  }>;
}

export interface StrategyV3MonthlyReturn {
  month: string;
  trades_count: number;
  win_rate_pct: number;
  return_pct: number;
  cumulative_return_pct: number;
}

export interface StrategyV3EquityPoint {
  date: string;
  trade_id: string;
  return_pct: number;
  cumulative_equity_pct: number;
  drawdown_pct: number;
}

export interface StrategyV3Response {
  version: string;
  strategy_name: string;
  period: {
    start_date: string;
    end_date: string;
    trading_days_evaluated: number;
    pairs_universe_count: number;
  };
  overall_summary: StrategyV3Summary;
  monthly_returns: StrategyV3MonthlyReturn[];
  equity_curve: StrategyV3EquityPoint[];
  trades: StrategyV3Trade[];
  meta: Record<string, any>;
}

// ---------------------------------------------------------------------------
// Strategy v4 Types ("Risk-Engineered Pure Alpha")
// ---------------------------------------------------------------------------

export interface StrategyV4Summary {
  total_trades: number;
  win_count: number;
  loss_count: number;
  neutral_count: number;
  win_rate_pct: number;
  net_return_pct: number;
  gross_profit_pct: number;
  gross_loss_pct: number;
  profit_factor: number;
  max_drawdown_pct: number;
  avg_return_pct: number;
  avg_holding_days: number;
  reversion_target_exits: number;
  tight_stop_exits: number;
  time_stop_exits: number;
  sharpe_ratio: number;
  calmar_ratio: number;
}

export interface StrategyV4Trade {
  id: string;
  pair_name: string;
  ticker_a: string;
  ticker_b: string;
  sector: string;
  entry_date: string;
  exit_date: string;
  direction: string;
  direction_label: string;
  entry_z: number;
  exit_z: number;
  hedge_ratio: number;
  entry_price_a: number;
  entry_price_b: number;
  exit_price_a: number;
  exit_price_b: number;
  outcome: string;
  exit_reason: string;
  status_reason: string;
  holding_days: number;
  raw_return_pct: number;
  realized_return_pct: number;
  sizing_multiplier: number;
  spread_vol_pct: number;
  half_life_days: number;
  max_holding_limit: number;
  is_dampened: boolean;
  momentum_slope: number;
  composite_score: number;
  trajectory?: Array<{
    date: string;
    days_elapsed: number;
    price_a: number;
    price_b: number;
    spread: number;
    z_score: number;
  }>;
}

export interface StrategyV4MonthlyReturn {
  month: string;
  trades_count: number;
  win_rate_pct: number;
  return_pct: number;
  cumulative_return_pct: number;
}

export interface StrategyV4EquityPoint {
  date: string;
  daily_pnl_pct?: number;
  trade_id?: string;
  return_pct?: number;
  cumulative_equity_pct: number;
  drawdown_pct: number;
}

export interface StrategyV4Response {
  version: string;
  strategy_name: string;
  period: {
    start_date: string;
    end_date: string;
    trading_days: number;
  };
  overall_summary: StrategyV4Summary;
  monthly_returns: Record<string, number> | StrategyV4MonthlyReturn[];
  equity_curve: StrategyV4EquityPoint[];
  trades: StrategyV4Trade[];
  meta: Record<string, any>;
}

export interface TradeChartBar {
  date: string;
  price_a: number;
  price_b: number;
  norm_price_a: number;
  norm_price_b: number;
  spread: number;
  z_score: number;
  is_entry: boolean;
  is_exit: boolean;
  in_trade: boolean;
}

export interface TradeChartDataResponse {
  ticker_a: string;
  ticker_b: string;
  pair_name: string;
  entry_date: string;
  exit_date?: string | null;
  pre_days: number;
  post_days: number;
  entry_index: number;
  exit_index: number;
  hedge_ratio: number;
  spread_mean: number;
  spread_std: number;
  total_bars: number;
  bars: TradeChartBar[];
}





