import React, { useState, useMemo } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import {
  TrendingUp,
  TrendingDown,
  ShieldCheck,
  CheckCircle2,
  XCircle,
  RefreshCw,
  Search,
  SlidersHorizontal,
  Calendar,
  Clock,
  Zap,
  Layers,
  ArrowUpDown,
  Sparkles,
  ChevronDown,
  ChevronUp,
  Eye,
  X,
  Award,
  AlertTriangle,
  Percent,
  Check,
  ArrowRight,
  Target,
  ShieldAlert,
  GitCompare,
  Filter,
} from "lucide-react";
import { api } from "@/lib/api";
import type {
  StrategyV2Response,
  StrategyV2Trade,
  StrategyV2Summary,
} from "@/lib/simulatorTypes";
import { Card } from "@/components/ui";
import { cn } from "@/lib/utils";
import TradeInspectorModal from "@/components/simulator/TradeInspectorModal";

type HorizonPeriod = "1Y" | "2Y" | "3Y" | "5Y";
type ActiveChartTab = "equity" | "drawdown" | "monthly" | "staged_breakdown";
type ExitFilter = "all" | "tp1_tp2" | "tp1_be" | "stop_loss" | "time_stop" | "perfect";

export default function StrategyV2Page() {
  const [activeHorizon, setActiveHorizon] = useState<HorizonPeriod>("1Y");
  const [activeChartTab, setActiveChartTab] = useState<ActiveChartTab>("equity");
  const [exitFilter, setExitFilter] = useState<ExitFilter>("all");
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedTrade, setSelectedTrade] = useState<StrategyV2Trade | null>(null);
  const [showParamEditor, setShowParamEditor] = useState(false);
  const [isRecalculating, setIsRecalculating] = useState(false);
  const [v2Params, setV2Params] = useState({
    z_score_hurdle: 2.1,
    z_score_hook_entry: 1.85,
    z_score_exit_tp1: 0.8,
    z_score_exit_tp2: 0.2,
    z_score_stop_loss_barrier: 3.2,
    half_life_multiplier: 1.75,
  });

  // TanStack Query for Strategy v2 Backtest dataset
  const { data, isLoading, isFetching, refetch } = useQuery({
    queryKey: ["strategyV2", activeHorizon],
    queryFn: () => api.simulator.getV2Backtest(activeHorizon),
    staleTime: 60_000,
  });

  const trades = useMemo(() => data?.trades || [], [data]);
  const summary: StrategyV2Summary = useMemo(
    () =>
      data?.overall_summary || {
        total_trades: 0,
        win_count: 0,
        loss_count: 0,
        neutral_count: 0,
        win_rate_pct: 0,
        avg_return_pct: 0,
        median_return_pct: 0,
        avg_holding_days: 0,
        profit_factor: 0,
        gross_profit_pct: 0,
        gross_loss_pct: 0,
        max_drawdown_pct: 0,
        tp1_and_tp2_count: 0,
        tp1_and_breakeven_count: 0,
        stop_loss_count: 0,
        time_stop_count: 0,
      },
    [data]
  );

  // Directional Long vs Short breakdowns
  const directionalStats = useMemo(() => {
    const longs = trades.filter((t) => t.direction === "LONG_A_SHORT_B" || t.entry_z < 0);
    const shorts = trades.filter((t) => t.direction === "SHORT_A_LONG_B" || t.entry_z > 0);

    const longWins = longs.filter((t) => t.outcome === "WIN").length;
    const shortWins = shorts.filter((t) => t.outcome === "WIN").length;

    const longWinRate = longs.length > 0 ? (longWins / longs.length) * 100 : 0;
    const shortWinRate = shorts.length > 0 ? (shortWins / shorts.length) * 100 : 0;

    return {
      longCount: longs.length,
      longWinRate: Math.round(longWinRate * 10) / 10,
      shortCount: shorts.length,
      shortWinRate: Math.round(shortWinRate * 10) / 10,
    };
  }, [trades]);

  // Filtered trades for history table
  const filteredTrades = useMemo(() => {
    return trades.filter((t) => {
      // Exit filter
      if (exitFilter === "tp1_tp2" && t.exit_reason !== "TP1_AND_TP2") return false;
      if (exitFilter === "tp1_be" && t.exit_reason !== "TP1_AND_BREAKEVEN") return false;
      if (exitFilter === "stop_loss" && t.exit_reason !== "STOP_LOSS") return false;
      if (exitFilter === "time_stop" && t.exit_reason !== "TIME_STOP") return false;
      if (exitFilter === "perfect" && !t.is_perfect) return false;

      // Text search
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase().trim();
        const matchPair = t.pair_name.toLowerCase().includes(q);
        const matchSector = (t.sector || "").toLowerCase().includes(q);
        const matchTickA = t.ticker_a.toLowerCase().includes(q);
        const matchTickB = t.ticker_b.toLowerCase().includes(q);
        if (!matchPair && !matchSector && !matchTickA && !matchTickB) return false;
      }

      return true;
    });
  }, [trades, exitFilter, searchQuery]);

  // Staged TP1 frequency %
  const tp1ExecutionFrequency = useMemo(() => {
    if (summary.total_trades === 0) return 0;
    const tp1Executed = summary.tp1_and_tp2_count + summary.tp1_and_breakeven_count;
    return Math.round((tp1Executed / summary.total_trades) * 1000) / 10;
  }, [summary]);

  const netRealizedReturn = useMemo(() => {
    return Math.round((summary.gross_profit_pct - summary.gross_loss_pct) * 100) / 100;
  }, [summary]);

  const handleRecalculate = async () => {
    setIsRecalculating(true);
    try {
      await api.simulator.recalculateV2({
        period: activeHorizon,
        ...v2Params,
      });
      refetch();
    } catch (e) {
      console.error(e);
    } finally {
      setIsRecalculating(false);
    }
  };

  return (
    <div className="space-y-6 pb-12 max-w-7xl mx-auto px-4 sm:px-6">
      {/* ------------------------------------------------------------------- */}
      {/* 1. Header & Horizon Switcher Bar                                    */}
      {/* ------------------------------------------------------------------- */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 pb-4 border-b border-line">
        <div>
          <div className="flex items-center gap-2.5">
            <div className="p-2 rounded-lg bg-amber-500/10 border border-amber-500/20 text-amber-400">
              <ShieldAlert className="w-5 h-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h1 className="text-2xl font-extrabold tracking-tight text-white font-mono">
                  Strategy v2 (Staged Experiment)
                </h1>
                <span className="px-2 py-0.5 rounded text-[11px] font-mono font-bold bg-amber-500/20 text-amber-300 border border-amber-500/30">
                  THE WIN-RATE TRAP
                </span>
              </div>
              <p className="text-xs text-gray-400 font-mono mt-0.5">
                Hook Confirmation (1.85σ) &middot; Staged TP1 (0.80σ) &middot; Breakeven Stop &middot; Earnings Blackout (±5d)
              </p>
            </div>
          </div>
        </div>

        {/* Horizon Pill Selector & Actions */}
        <div className="flex flex-wrap items-center gap-2">
          <button
            onClick={() => setShowParamEditor(!showParamEditor)}
            className={cn(
              "px-3 py-2 rounded-xl text-xs font-mono font-bold transition-all border flex items-center gap-1.5",
              showParamEditor
                ? "bg-amber-600 text-white border-amber-500 shadow-md shadow-amber-600/30"
                : "bg-surface-2 text-gray-300 border-line hover:text-white hover:bg-surface-3"
            )}
          >
            <SlidersHorizontal className="w-3.5 h-3.5" />
            <span>{showParamEditor ? "Hide Parameters" : "Edit Base Parameters"}</span>
          </button>

          <div className="flex items-center gap-1 bg-surface-2 p-1 rounded-xl border border-line">
            {(["1Y", "2Y", "3Y", "5Y"] as HorizonPeriod[]).map((h) => (
              <button
                key={h}
                onClick={() => setActiveHorizon(h)}
                className={cn(
                  "px-3 py-1.5 text-xs font-mono font-semibold rounded-lg transition-all",
                  activeHorizon === h
                    ? "bg-amber-600 text-white shadow-sm font-bold"
                    : "text-gray-400 hover:text-white hover:bg-surface-1"
                )}
              >
                {h}
              </button>
            ))}

            <button
              onClick={() => refetch()}
              disabled={isFetching}
              className="p-2 ml-1 rounded-lg text-gray-400 hover:text-white hover:bg-surface-1 transition-colors"
              title="Recalculate Backtest"
            >
              <RefreshCw className={cn("w-4 h-4", isFetching && "animate-spin text-amber-400")} />
            </button>
          </div>
        </div>
      </div>

      {/* ------------------------------------------------------------------- */}
      {/* 1.5 Collapsible Base Parameters & Recalculate Panel                 */}
      {/* ------------------------------------------------------------------- */}
      {showParamEditor && (
        <Card className="p-4 bg-surface-1 border-amber-500/40 space-y-4">
          <div className="flex items-center justify-between pb-2 border-b border-line text-xs font-mono">
            <span className="font-bold text-white flex items-center gap-2">
              <SlidersHorizontal className="w-4 h-4 text-amber-400" />
              Strategy 2 Base Parameters &amp; Calibration ({activeHorizon})
            </span>
            <span className="text-gray-400">Instant walkforward recalculation</span>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 text-xs font-mono">
            <div className="space-y-1">
              <label className="text-gray-400">Hurdle Barrier (σ)</label>
              <input
                type="number"
                step="0.05"
                value={v2Params.z_score_hurdle}
                onChange={(e) => setV2Params({ ...v2Params, z_score_hurdle: parseFloat(e.target.value) || 2.1 })}
                className="w-full bg-surface-2 border border-line rounded px-2.5 py-1.5 text-white focus:outline-none focus:border-amber-500"
              />
            </div>
            <div className="space-y-1">
              <label className="text-gray-400">Hook Entry (σ)</label>
              <input
                type="number"
                step="0.05"
                value={v2Params.z_score_hook_entry}
                onChange={(e) => setV2Params({ ...v2Params, z_score_hook_entry: parseFloat(e.target.value) || 1.85 })}
                className="w-full bg-surface-2 border border-line rounded px-2.5 py-1.5 text-white focus:outline-none focus:border-amber-500"
              />
            </div>
            <div className="space-y-1">
              <label className="text-gray-400">Staged TP1 (σ)</label>
              <input
                type="number"
                step="0.05"
                value={v2Params.z_score_exit_tp1}
                onChange={(e) => setV2Params({ ...v2Params, z_score_exit_tp1: parseFloat(e.target.value) || 0.8 })}
                className="w-full bg-surface-2 border border-line rounded px-2.5 py-1.5 text-white focus:outline-none focus:border-amber-500"
              />
            </div>
            <div className="space-y-1">
              <label className="text-gray-400">Stop Barrier (σ)</label>
              <input
                type="number"
                step="0.1"
                value={v2Params.z_score_stop_loss_barrier}
                onChange={(e) => setV2Params({ ...v2Params, z_score_stop_loss_barrier: parseFloat(e.target.value) || 3.2 })}
                className="w-full bg-surface-2 border border-line rounded px-2.5 py-1.5 text-white focus:outline-none focus:border-amber-500"
              />
            </div>
          </div>

          <div className="flex items-center justify-end gap-2 pt-2 border-t border-line text-xs font-mono">
            <button
              onClick={() => {
                setV2Params({
                  z_score_hurdle: 2.1,
                  z_score_hook_entry: 1.85,
                  z_score_exit_tp1: 0.8,
                  z_score_exit_tp2: 0.2,
                  z_score_stop_loss_barrier: 3.2,
                  half_life_multiplier: 1.75,
                });
              }}
              className="px-3 py-1.5 rounded bg-surface-2 hover:bg-surface-3 text-gray-400 hover:text-white border border-line"
            >
              Reset to Base Config
            </button>
            <button
              onClick={handleRecalculate}
              disabled={isRecalculating}
              className="px-4 py-1.5 rounded bg-amber-600 hover:bg-amber-500 text-white font-bold transition-all shadow-md flex items-center gap-1.5"
            >
              <RefreshCw className={cn("w-3.5 h-3.5", isRecalculating && "animate-spin")} />
              <span>{isRecalculating ? "Recalculating..." : "Apply & Recalculate"}</span>
            </button>
          </div>
        </Card>
      )}

      {/* ------------------------------------------------------------------- */}
      {/* 2. Active Upgrades HUD Card                                         */}
      {/* ------------------------------------------------------------------- */}
      <Card className="bg-gradient-to-r from-purple-950/20 via-surface-1 to-surface-1 border-purple-500/20 p-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <Zap className="w-4 h-4 text-purple-400" />
            <span className="text-xs font-bold uppercase tracking-wider text-purple-300">
              Active Strategy v2 Upgrades
            </span>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-[11px] font-mono bg-purple-500/10 text-purple-300 border border-purple-500/30">
              <Zap className="w-3 h-3 text-purple-400" />
              Hook Confirmation (2.10σ &rarr; 1.85σ)
            </span>
            <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-[11px] font-mono bg-emerald-500/10 text-emerald-300 border border-emerald-500/30">
              <Target className="w-3 h-3 text-emerald-400" />
              Staged TP1 (0.80σ) + Breakeven Stop
            </span>
            <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-[11px] font-mono bg-amber-500/10 text-amber-300 border border-amber-500/30">
              <Clock className="w-3 h-3 text-amber-400" />
              OU Time Stop (1.75x)
            </span>
            <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-[11px] font-mono bg-sky-500/10 text-sky-300 border border-sky-500/30">
              <ShieldCheck className="w-3 h-3 text-sky-400" />
              Earnings Blackout (&plusmn;5 Days)
            </span>
            <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-[11px] font-mono bg-rose-500/10 text-rose-300 border border-rose-500/30">
              <ShieldAlert className="w-3 h-3 text-rose-400" />
              Tight Stop Barrier (3.20σ)
            </span>
          </div>
        </div>
      </Card>

      {/* ------------------------------------------------------------------- */}
      {/* 3. Hero KPI Banners (5 Institutional Metric Cards)                 */}
      {/* ------------------------------------------------------------------- */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3.5">
        {/* KPI 1: Win Rate */}
        <Card className="p-4 bg-surface-1 border-line/80 relative overflow-hidden">
          <div className="flex items-center justify-between text-gray-400 text-xs mb-1">
            <span className="font-medium uppercase tracking-wider">Win Rate</span>
            <Award className="w-4 h-4 text-emerald-400" />
          </div>
          <div className="flex items-baseline gap-2">
            <span className="text-2xl font-bold font-mono text-emerald-400">
              {summary.win_rate_pct}%
            </span>
            <span className="text-[11px] text-gray-400 font-mono">
              ({summary.win_count}W / {summary.loss_count}L)
            </span>
          </div>
          <div className="mt-2 text-[11px] text-gray-500 font-mono flex items-center justify-between">
            <span>Long: {directionalStats.longWinRate}%</span>
            <span>Short: {directionalStats.shortWinRate}%</span>
          </div>
        </Card>

        {/* KPI 2: Profit Factor */}
        <Card className="p-4 bg-surface-1 border-line/80 relative overflow-hidden">
          <div className="flex items-center justify-between text-gray-400 text-xs mb-1">
            <span className="font-medium uppercase tracking-wider">Profit Factor</span>
            <Layers className="w-4 h-4 text-purple-400" />
          </div>
          <div className="flex items-baseline gap-2">
            <span className="text-2xl font-bold font-mono text-white">
              {summary.profit_factor}
            </span>
            <span className="text-[11px] text-emerald-400 font-mono">
              Avg: {summary.avg_return_pct > 0 ? "+" : ""}{summary.avg_return_pct}%
            </span>
          </div>
          <div className="mt-2 text-[11px] text-gray-500 font-mono flex items-center justify-between">
            <span>Gross: +{summary.gross_profit_pct}%</span>
            <span>Loss: -{summary.gross_loss_pct}%</span>
          </div>
        </Card>

        {/* KPI 3: Net Realized Return */}
        <Card className="p-4 bg-surface-1 border-line/80 relative overflow-hidden">
          <div className="flex items-center justify-between text-gray-400 text-xs mb-1">
            <span className="font-medium uppercase tracking-wider">Net Realized PnL</span>
            <TrendingUp className="w-4 h-4 text-emerald-400" />
          </div>
          <div className="flex items-baseline gap-2">
            <span
              className={cn(
                "text-2xl font-bold font-mono",
                netRealizedReturn >= 0 ? "text-emerald-400" : "text-rose-400"
              )}
            >
              {netRealizedReturn >= 0 ? "+" : ""}
              {netRealizedReturn}%
            </span>
            <span className="text-[11px] text-gray-400 font-mono">
              ({trades.length} trades)
            </span>
          </div>
          <div className="mt-2 text-[11px] text-gray-500 font-mono">
            <span>Median Payoff: {summary.median_return_pct > 0 ? "+" : ""}{summary.median_return_pct}%</span>
          </div>
        </Card>

        {/* KPI 4: Max Drawdown */}
        <Card className="p-4 bg-surface-1 border-line/80 relative overflow-hidden">
          <div className="flex items-center justify-between text-gray-400 text-xs mb-1">
            <span className="font-medium uppercase tracking-wider">Max Drawdown</span>
            <TrendingDown className="w-4 h-4 text-rose-400" />
          </div>
          <div className="flex items-baseline gap-2">
            <span className="text-2xl font-bold font-mono text-rose-400">
              -{summary.max_drawdown_pct}%
            </span>
            <span className="text-[11px] text-gray-400 font-mono">Peak-to-Trough</span>
          </div>
          <div className="mt-2 text-[11px] text-gray-500 font-mono">
            <span>v1 Baseline: -45.1%</span>
          </div>
        </Card>

        {/* KPI 5: Avg Holding Time & TP1 Frequency */}
        <Card className="p-4 bg-surface-1 border-line/80 relative overflow-hidden">
          <div className="flex items-center justify-between text-gray-400 text-xs mb-1">
            <span className="font-medium uppercase tracking-wider">Avg Holding Duration</span>
            <Clock className="w-4 h-4 text-sky-400" />
          </div>
          <div className="flex items-baseline gap-2">
            <span className="text-2xl font-bold font-mono text-white">
              {summary.avg_holding_days}d
            </span>
            <span className="text-[11px] text-emerald-400 font-mono">
              TP1 Exec: {tp1ExecutionFrequency}%
            </span>
          </div>
          <div className="mt-2 text-[11px] text-gray-500 font-mono">
            <span>Faster turnover than v1 (7.1d)</span>
          </div>
        </Card>
      </div>

      {/* ------------------------------------------------------------------- */}
      {/* 4. Interactive Chart Viewport                                       */}
      {/* ------------------------------------------------------------------- */}
      <Card className="p-4 bg-surface-1 border-line">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-3 mb-4 border-b border-line/60">
          <div className="flex items-center gap-2">
            <span className="text-xs font-bold uppercase tracking-wider text-gray-300">
              Strategy v2 Performance Analytics
            </span>
            <span className="text-[11px] font-mono text-gray-500">
              ({data?.period?.start_date} to {data?.period?.end_date})
            </span>
          </div>

          {/* Chart View Tabs */}
          <div className="flex items-center bg-surface-2 p-1 rounded-lg border border-line text-xs">
            <button
              onClick={() => setActiveChartTab("equity")}
              className={cn(
                "px-3 py-1 rounded transition-colors flex items-center gap-1.5",
                activeChartTab === "equity"
                  ? "bg-purple-600 text-white font-semibold"
                  : "text-gray-400 hover:text-white"
              )}
            >
              <TrendingUp className="w-3.5 h-3.5" />
              <span>Equity Curve</span>
            </button>
            <button
              onClick={() => setActiveChartTab("drawdown")}
              className={cn(
                "px-3 py-1 rounded transition-colors flex items-center gap-1.5",
                activeChartTab === "drawdown"
                  ? "bg-rose-500/80 text-white font-semibold"
                  : "text-gray-400 hover:text-white"
              )}
            >
              <TrendingDown className="w-3.5 h-3.5" />
              <span>Underwater Drawdown</span>
            </button>
            <button
              onClick={() => setActiveChartTab("monthly")}
              className={cn(
                "px-3 py-1 rounded transition-colors flex items-center gap-1.5",
                activeChartTab === "monthly"
                  ? "bg-sky-500/80 text-white font-semibold"
                  : "text-gray-400 hover:text-white"
              )}
            >
              <Calendar className="w-3.5 h-3.5" />
              <span>Monthly Heatmap</span>
            </button>
            <button
              onClick={() => setActiveChartTab("staged_breakdown")}
              className={cn(
                "px-3 py-1 rounded transition-colors flex items-center gap-1.5",
                activeChartTab === "staged_breakdown"
                  ? "bg-emerald-600 text-white font-semibold"
                  : "text-gray-400 hover:text-white"
              )}
            >
              <Target className="w-3.5 h-3.5" />
              <span>Staged Exits</span>
            </button>
          </div>
        </div>

        {/* Tab 1: Equity Curve */}
        {activeChartTab === "equity" && (
          <div className="space-y-2">
            <div className="flex items-center justify-between text-xs font-mono">
              <span className="text-gray-400">
                Strategy v2 Net Realized PnL (Chronological Exits)
              </span>
              <strong
                className={cn(
                  "text-sm font-mono",
                  netRealizedReturn >= 0 ? "text-emerald-400" : "text-rose-400"
                )}
              >
                {netRealizedReturn >= 0 ? "+" : ""}
                {netRealizedReturn}%
              </strong>
            </div>

            {/* SVG Non-scaling Area Curve */}
            <div className="h-44 w-full bg-surface-2/40 rounded-lg border border-line/60 p-2 relative overflow-hidden flex items-end">
              {data?.equity_curve && data.equity_curve.length > 1 ? (
                <svg
                  className="w-full h-full overflow-visible"
                  viewBox={`0 0 ${data.equity_curve.length} 100`}
                  preserveAspectRatio="none"
                >
                  <defs>
                    <linearGradient id="v2EquityGrad" x1="0%" y1="0%" x2="0%" y2="100%">
                      <stop offset="0%" stopColor="#8b5cf6" stopOpacity="0.45" />
                      <stop offset="100%" stopColor="#8b5cf6" stopOpacity="0.0" />
                    </linearGradient>
                  </defs>
                  {(() => {
                    const values = data.equity_curve.map((d) => d.cumulative_equity_pct);
                    const minVal = Math.min(0, ...values);
                    const maxVal = Math.max(10, ...values);
                    const range = maxVal - minVal || 1;

                    const points = data.equity_curve
                      .map((d, i) => {
                        const x = i;
                        const y = 92 - ((d.cumulative_equity_pct - minVal) / range) * 84;
                        return `${x},${y}`;
                      })
                      .join(" ");

                    const areaPoints = `0,92 ${points} ${data.equity_curve.length - 1},92`;

                    return (
                      <>
                        <polygon
                          points={areaPoints}
                          fill="url(#v2EquityGrad)"
                          vectorEffect="non-scaling-stroke"
                        />
                        <polyline
                          fill="none"
                          stroke="#8b5cf6"
                          strokeWidth="2.5"
                          points={points}
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          vectorEffect="non-scaling-stroke"
                        />
                      </>
                    );
                  })()}
                </svg>
              ) : (
                <div className="w-full h-full flex items-center justify-center text-xs text-gray-500 font-mono">
                  Loading equity data points...
                </div>
              )}
            </div>

            <div className="flex items-center justify-between text-[10px] text-gray-500 font-mono">
              <span>Start: {data?.period?.start_date}</span>
              <span>{trades.length} realized exits &middot; Staged Tranche Accounting</span>
              <span>End: {data?.period?.end_date}</span>
            </div>
          </div>
        )}

        {/* Tab 2: Underwater Drawdown Curve */}
        {activeChartTab === "drawdown" && (
          <div className="space-y-2">
            <div className="flex items-center justify-between text-xs font-mono">
              <span className="text-gray-400">Peak-to-Trough Drawdown Depth</span>
              <span className="text-rose-400 font-bold text-sm">
                Max DD: -{summary.max_drawdown_pct}%
              </span>
            </div>

            <div className="h-44 w-full bg-surface-2/40 rounded-lg border border-line/60 p-2 relative overflow-hidden flex items-start">
              {data?.equity_curve && data.equity_curve.length > 1 ? (
                <svg
                  className="w-full h-full overflow-visible"
                  viewBox={`0 0 ${data.equity_curve.length} 100`}
                  preserveAspectRatio="none"
                >
                  <defs>
                    <linearGradient id="v2DdGrad" x1="0%" y1="0%" x2="0%" y2="100%">
                      <stop offset="0%" stopColor="#ef4444" stopOpacity="0.45" />
                      <stop offset="100%" stopColor="#ef4444" stopOpacity="0.0" />
                    </linearGradient>
                  </defs>
                  {(() => {
                    const values = data.equity_curve.map((d) => d.drawdown_pct);
                    const maxVal = Math.max(5, ...values);

                    const points = data.equity_curve
                      .map((d, i) => {
                        const x = i;
                        const y = (d.drawdown_pct / maxVal) * 88 + 5;
                        return `${x},${y}`;
                      })
                      .join(" ");

                    const areaPoints = `0,5 ${points} ${data.equity_curve.length - 1},5`;

                    return (
                      <>
                        <polygon
                          points={areaPoints}
                          fill="url(#v2DdGrad)"
                          vectorEffect="non-scaling-stroke"
                        />
                        <polyline
                          fill="none"
                          stroke="#ef4444"
                          strokeWidth="2"
                          points={points}
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          vectorEffect="non-scaling-stroke"
                        />
                      </>
                    );
                  })()}
                </svg>
              ) : (
                <div className="w-full h-full flex items-center justify-center text-xs text-gray-500 font-mono">
                  Loading drawdown data...
                </div>
              )}
            </div>

            <div className="flex items-center justify-between text-[10px] text-gray-500 font-mono">
              <span>0% High-Water Mark</span>
              <span>Controlled Risk Barrier (3.20σ)</span>
              <span>Trough: -{summary.max_drawdown_pct}%</span>
            </div>
          </div>
        )}

        {/* Tab 3: Monthly Returns Heatmap */}
        {activeChartTab === "monthly" && (
          <div className="space-y-3">
            <div className="text-xs text-gray-400 font-mono">
              Monthly Net Performance Matrix ({data?.monthly_returns?.length || 0} Months)
            </div>

            <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6 gap-2.5">
              {data?.monthly_returns?.map((m) => (
                <div
                  key={m.month}
                  className={cn(
                    "p-3 rounded-lg border text-center transition-all",
                    m.return_pct >= 0
                      ? "bg-emerald-950/20 border-emerald-500/30 text-emerald-300"
                      : "bg-rose-950/20 border-rose-500/30 text-rose-300"
                  )}
                >
                  <div className="text-[11px] font-mono text-gray-400 mb-1">{m.month}</div>
                  <div className="text-base font-bold font-mono">
                    {m.return_pct >= 0 ? "+" : ""}
                    {m.return_pct}%
                  </div>
                  <div className="text-[10px] font-mono text-gray-500 mt-1">
                    {m.trades_count} trades &middot; {m.win_rate_pct}% WR
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Tab 4: Staged Profit Breakdown */}
        {activeChartTab === "staged_breakdown" && (
          <div className="space-y-4">
            <div className="text-xs text-gray-400 font-mono">
              Distribution of Exits Across Staged Architecture
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
              {/* Box 1: TP1 + TP2 Full Target */}
              <div className="p-3.5 rounded-lg bg-emerald-950/20 border border-emerald-500/30">
                <div className="flex items-center justify-between text-xs text-emerald-400 mb-1">
                  <span className="font-semibold">TP1 & TP2 (Full Target)</span>
                  <Target className="w-4 h-4" />
                </div>
                <div className="text-2xl font-bold font-mono text-white">
                  {summary.tp1_and_tp2_count}
                </div>
                <div className="text-[11px] text-gray-400 font-mono mt-1">
                  {summary.total_trades > 0
                    ? Math.round((summary.tp1_and_tp2_count / summary.total_trades) * 100)
                    : 0}
                  % of total trades &middot; Both tranches banked
                </div>
              </div>

              {/* Box 2: TP1 + Breakeven (Flipped Win) */}
              <div className="p-3.5 rounded-lg bg-cyan-950/20 border border-cyan-500/30">
                <div className="flex items-center justify-between text-xs text-cyan-400 mb-1">
                  <span className="font-semibold">TP1 + Breakeven (Saved Win)</span>
                  <ShieldCheck className="w-4 h-4" />
                </div>
                <div className="text-2xl font-bold font-mono text-white">
                  {summary.tp1_and_breakeven_count}
                </div>
                <div className="text-[11px] text-gray-400 font-mono mt-1">
                  {summary.total_trades > 0
                    ? Math.round((summary.tp1_and_breakeven_count / summary.total_trades) * 100)
                    : 0}
                  % of trades &middot; Strategy v1 would have lost
                </div>
              </div>

              {/* Box 3: Stop Loss Barrier */}
              <div className="p-3.5 rounded-lg bg-rose-950/20 border border-rose-500/30">
                <div className="flex items-center justify-between text-xs text-rose-400 mb-1">
                  <span className="font-semibold">Stop Loss Barrier (3.20σ)</span>
                  <ShieldAlert className="w-4 h-4" />
                </div>
                <div className="text-2xl font-bold font-mono text-white">
                  {summary.stop_loss_count}
                </div>
                <div className="text-[11px] text-gray-400 font-mono mt-1">
                  {summary.total_trades > 0
                    ? Math.round((summary.stop_loss_count / summary.total_trades) * 100)
                    : 0}
                  % stopped out &middot; Controlled loss size
                </div>
              </div>

              {/* Box 4: Ornstein-Uhlenbeck Time Stop */}
              <div className="p-3.5 rounded-lg bg-amber-950/20 border border-amber-500/30">
                <div className="flex items-center justify-between text-xs text-amber-400 mb-1">
                  <span className="font-semibold">OU Time Stop Exits</span>
                  <Clock className="w-4 h-4" />
                </div>
                <div className="text-2xl font-bold font-mono text-white">
                  {summary.time_stop_count}
                </div>
                <div className="text-[11px] text-gray-400 font-mono mt-1">
                  {summary.total_trades > 0
                    ? Math.round((summary.time_stop_count / summary.total_trades) * 100)
                    : 0}
                  % time stop exits &middot; Prevents capital lockup
                </div>
              </div>
            </div>
          </div>
        )}
      </Card>

      {/* ------------------------------------------------------------------- */}
      {/* 5. Trade History Table & Inspector Modal                            */}
      {/* ------------------------------------------------------------------- */}
      <Card className="p-4 bg-surface-1 border-line">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-3 pb-3 border-b border-line/60">
          <div>
            <h3 className="text-sm font-bold text-white uppercase tracking-wider flex items-center gap-2">
              <span>Strategy v2 Executed Trade Log</span>
              <span className="text-xs font-mono font-normal text-gray-400">
                ({filteredTrades.length} of {trades.length} trades)
              </span>
            </h3>
          </div>

          {/* Table Filters & Search */}
          <div className="flex flex-wrap items-center gap-2">
            <div className="relative">
              <Search className="w-3.5 h-3.5 text-gray-500 absolute left-2.5 top-1/2 -translate-y-1/2" />
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search pair or sector..."
                className="pl-8 pr-3 py-1 bg-surface-2 border border-line rounded-lg text-xs text-white placeholder-gray-500 focus:outline-none focus:border-purple-500"
              />
            </div>

            {/* Exit Filter Pills */}
            <div className="flex items-center bg-surface-2 p-0.5 rounded-lg border border-line text-[11px]">
              <button
                onClick={() => setExitFilter("all")}
                className={cn(
                  "px-2.5 py-1 rounded transition-colors",
                  exitFilter === "all" ? "bg-purple-600 text-white font-medium" : "text-gray-400 hover:text-white"
                )}
              >
                All
              </button>
              <button
                onClick={() => setExitFilter("tp1_tp2")}
                className={cn(
                  "px-2.5 py-1 rounded transition-colors",
                  exitFilter === "tp1_tp2" ? "bg-emerald-600 text-white font-medium" : "text-gray-400 hover:text-white"
                )}
              >
                TP1 & TP2
              </button>
              <button
                onClick={() => setExitFilter("tp1_be")}
                className={cn(
                  "px-2.5 py-1 rounded transition-colors",
                  exitFilter === "tp1_be" ? "bg-cyan-600 text-white font-medium" : "text-gray-400 hover:text-white"
                )}
              >
                Flipped (BE)
              </button>
              <button
                onClick={() => setExitFilter("stop_loss")}
                className={cn(
                  "px-2.5 py-1 rounded transition-colors",
                  exitFilter === "stop_loss" ? "bg-rose-600 text-white font-medium" : "text-gray-400 hover:text-white"
                )}
              >
                Stops
              </button>
              <button
                onClick={() => setExitFilter("time_stop")}
                className={cn(
                  "px-2.5 py-1 rounded transition-colors",
                  exitFilter === "time_stop" ? "bg-amber-600 text-white font-medium" : "text-gray-400 hover:text-white"
                )}
              >
                Time Stops
              </button>
            </div>
          </div>
        </div>

        {/* Trade Table */}
        <div className="overflow-x-auto mt-3">
          <table className="w-full text-xs text-left">
            <thead>
              <tr className="border-b border-line text-[11px] text-gray-400 font-mono uppercase tracking-wider">
                <th className="py-2.5 px-3">Pair & Direction</th>
                <th className="py-2.5 px-3">Entry Date</th>
                <th className="py-2.5 px-3">Hook Entry Z</th>
                <th className="py-2.5 px-3">Exit Date</th>
                <th className="py-2.5 px-3">Holding</th>
                <th className="py-2.5 px-3">Exit Reason</th>
                <th className="py-2.5 px-3">Tranche PnL</th>
                <th className="py-2.5 px-3 text-right">Net Return</th>
                <th className="py-2.5 px-3 text-center">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line/40">
              {filteredTrades.length > 0 ? (
                filteredTrades.map((t) => (
                  <tr
                    key={t.id}
                    className="hover:bg-surface-2/60 transition-colors group cursor-pointer"
                    onClick={() => setSelectedTrade(t)}
                  >
                    {/* Pair & Direction */}
                    <td className="py-2.5 px-3">
                      <div className="font-bold text-white font-mono flex items-center gap-1.5">
                        <span>{t.pair_name}</span>
                        {t.is_perfect && (
                          <span className="px-1.5 py-0.2 rounded text-[9px] bg-purple-500/20 text-purple-300 font-mono">
                            11/11
                          </span>
                        )}
                      </div>
                      <div className="text-[10px] text-gray-500 font-mono">
                        {t.direction_label}
                      </div>
                    </td>

                    {/* Entry Date */}
                    <td className="py-2.5 px-3 font-mono text-gray-300">
                      {t.entry_date}
                    </td>

                    {/* Hook Entry Z */}
                    <td className="py-2.5 px-3 font-mono">
                      <span className="text-purple-300">
                        {t.entry_z >= 0 ? "+" : ""}{t.entry_z}σ
                      </span>
                      <div className="text-[10px] text-gray-500">
                        Hurdle: {t.hurdle_breached_z >= 0 ? "+" : ""}{t.hurdle_breached_z}σ
                      </div>
                    </td>

                    {/* Exit Date */}
                    <td className="py-2.5 px-3 font-mono text-gray-300">
                      {t.exit_date || "—"}
                    </td>

                    {/* Holding */}
                    <td className="py-2.5 px-3 font-mono text-gray-300">
                      {t.holding_days}d
                    </td>

                    {/* Exit Reason Badge */}
                    <td className="py-2.5 px-3">
                      {t.exit_reason === "TP1_AND_TP2" && (
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-mono bg-emerald-500/10 text-emerald-300 border border-emerald-500/30">
                          <Target className="w-3 h-3 text-emerald-400" />
                          TP1 &amp; TP2 Full
                        </span>
                      )}
                      {t.exit_reason === "TP1_AND_BREAKEVEN" && (
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-mono bg-cyan-500/10 text-cyan-300 border border-cyan-500/30">
                          <ShieldCheck className="w-3 h-3 text-cyan-400" />
                          TP1 + Breakeven
                        </span>
                      )}
                      {t.exit_reason === "STOP_LOSS" && (
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-mono bg-rose-500/10 text-rose-300 border border-rose-500/30">
                          <ShieldAlert className="w-3 h-3 text-rose-400" />
                          Stop Loss (3.2σ)
                        </span>
                      )}
                      {t.exit_reason === "TIME_STOP" && (
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-mono bg-amber-500/10 text-amber-300 border border-amber-500/30">
                          <Clock className="w-3 h-3 text-amber-400" />
                          Time Stop ({t.time_stop_days}d)
                        </span>
                      )}
                    </td>

                    {/* Tranche Breakdown */}
                    <td className="py-2.5 px-3 font-mono text-[11px] text-gray-400">
                      <div>T1: <span className={t.tranche1_pnl_pct >= 0 ? "text-emerald-400" : "text-rose-400"}>{t.tranche1_pnl_pct > 0 ? "+" : ""}{t.tranche1_pnl_pct}%</span></div>
                      <div>T2: <span className={t.tranche2_pnl_pct > 0 ? "text-emerald-400" : t.tranche2_pnl_pct < 0 ? "text-rose-400" : "text-gray-400"}>{t.tranche2_pnl_pct > 0 ? "+" : ""}{t.tranche2_pnl_pct}%</span></div>
                    </td>

                    {/* Net Return */}
                    <td className="py-2.5 px-3 text-right font-mono font-bold">
                      <span
                        className={cn(
                          t.realized_return_pct >= 0 ? "text-emerald-400" : "text-rose-400"
                        )}
                      >
                        {t.realized_return_pct >= 0 ? "+" : ""}
                        {t.realized_return_pct}%
                      </span>
                    </td>

                    {/* Action Button */}
                    <td className="py-2.5 px-3 text-center">
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          setSelectedTrade(t);
                        }}
                        className="p-1 rounded hover:bg-surface-3 text-gray-400 hover:text-purple-300 transition-colors"
                        title="Inspect Trade Trajectory"
                      >
                        <Eye className="w-4 h-4" />
                      </button>
                    </td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td colSpan={9} className="py-8 text-center text-gray-500 font-mono">
                    No trades match the selected filter.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </Card>

      {/* ------------------------------------------------------------------- */}
      {/* 6. Institutional Full-Window Trade Inspector Modal                  */}
      {/* ------------------------------------------------------------------- */}
      {selectedTrade && (
        <TradeInspectorModal
          trade={selectedTrade}
          onClose={() => setSelectedTrade(null)}
          strategyLabel="STRATEGY 2: STAGED PARTIAL EXITS (FAILED EXP.)"
          strategyThemeColor="amber"
          tradeIndex={filteredTrades.findIndex((t) => t.id === selectedTrade.id)}
          totalTrades={filteredTrades.length}
          onPrevTrade={() => {
            const idx = filteredTrades.findIndex((t) => t.id === selectedTrade.id);
            if (idx > 0) setSelectedTrade(filteredTrades[idx - 1]);
          }}
          onNextTrade={() => {
            const idx = filteredTrades.findIndex((t) => t.id === selectedTrade.id);
            if (idx < filteredTrades.length - 1) setSelectedTrade(filteredTrades[idx + 1]);
          }}
        />
      )}
    </div>
  );
}
