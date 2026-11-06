export interface AutoTradeLeg {
  symbol: string;
  side: "BUY" | "SHORT";
  qty: number;
  reference_price: number;
  proposed_notional: number;
}

export interface AutoTradeSignal {
  signal_id: string;
  session_date: string;
  ticker_a: string;
  ticker_b: string;
  decision: "QUALIFIED" | "REJECTED";
  rejection_reason?: string | null;
  payload: {
    pair_name: string;
    strategy: "strategy_v4";
    z_score?: number;
    hedge_ratio?: number;
    spread?: number;
    spread_vol_pct?: number;
    half_life_days?: number;
    composite_score?: number;
    correlation?: number;
    adf_pvalue?: number;
    adf_tstat?: number;
    momentum_slope?: number;
    rank?: number;
    current_drawdown_pct?: number;
    drawdown_dampened?: boolean;
    earnings_blackout?: boolean;
    earnings_blackout_reason?: string | null;
    market_vol_state?: "NORMAL" | "PANIC";
    proposed_capital?: number;
    target_z?: number;
    stop_z?: number;
    max_holding_date?: string;
    proposed_legs?: AutoTradeLeg[];
    failed_checks?: string[];
    chart_snapshot?: import("./simulatorTypes").PairChartResponse & { source?: string };
  };
}

export interface AutoTradeRun {
  run_id: string;
  status: string;
  started_at: string;
  finished_at?: string | null;
  idempotent_replay?: boolean;
  summary?: {
    strategy: "strategy_v4";
    strategy_version: string;
    config_hash: string;
    session_date: string;
    data_cutoff_date: string;
    observed_at: string;
    next_market_open: string;
    next_scheduled_scan_at: string;
    market_vol_pct: number;
    evaluated_pairs: number;
    qualified_pairs: number;
    rejected_pairs: number;
    trade_submission_available: false;
  } | null;
  signals: AutoTradeSignal[];
}

export interface AutoTradeStatus {
  phase: 4;
  mode: "paper_execution";
  trade_submission_available: boolean;
  armed: boolean;
  kill_switch: boolean;
  control_updated_at?: string | null;
  premarket_offset_minutes: number;
  latest_run?: AutoTradeRun | null;
  telegram_preview?: string | null;
  pairs: AutoTradePair[];
  operations: {
    jobs: Array<{ name: string; slot: string; status: string; started_at: string; finished_at?: string | null; error_type?: string | null }>;
    notification_outbox: Record<string, number>;
    performance: { closed_pairs: number; open_pairs: number; win_rate_pct?: number | null; realized_pnl: number; unrealized_pnl: number };
  };
  readiness: {
    configuration: {
      ready: boolean;
      errors: string[];
      alpaca: {
        api_key_configured: boolean;
        secret_key_configured: boolean;
      };
      telegram: {
        enabled: boolean;
        token_configured: boolean;
        passcode_configured: boolean;
      };
    };
  };
}

export interface AutoTradeBrokerSnapshot {
  account: { status: string; equity: number; cash: number; buying_power: number; portfolio_value: number; trading_blocked: boolean };
  market: { is_open: boolean; timestamp: string; next_open: string; next_close: string };
  positions: Array<Record<string, unknown>>;
  orders: Array<Record<string, unknown>>;
}

export interface AutoTradePairLeg {
  leg_id: string;
  symbol: string;
  side: "BUY" | "SHORT";
  target_qty: number;
  filled_qty: number;
  avg_fill_price?: number | null;
  state: string;
}

export interface AutoTradePair {
  pair_trade_id: string;
  ticker_a: string;
  ticker_b: string;
  state: string;
  target_z?: number | null;
  stop_z?: number | null;
  max_holding_date?: string | null;
  error_code?: string | null;
  error_message?: string | null;
  exit_reason?: string | null;
  current_z?: number | null;
  unrealized_pnl?: number | null;
  realized_pnl?: number | null;
  reconciled_at?: string | null;
  legs: AutoTradePairLeg[];
  orders: Array<{ status: string; symbol: string; filled_qty?: number | null }>;
}
