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
  Flame,
  ShieldAlert,
  GitCompare,
  Filter,
  Activity,
  BarChart3,
} from "lucide-react";
import { api } from "@/lib/api";
import type {
  StrategyV4Response,
  StrategyV4Trade,
  StrategyV4Summary,
} from "@/lib/simulatorTypes";
import { Card } from "@/components/ui";
import { cn } from "@/lib/utils";
import TradeInspectorModal from "@/components/simulator/TradeInspectorModal";

type HorizonPeriod = "1Y" | "2Y" | "3Y" | "5Y";
type ActiveChartTab = "equity" | "drawdown" | "monthly";
type ExitFilter = "all" | "reversion_target" | "tight_stop" | "time_stop" | "wins" | "losses";

const HORIZONS: { key: HorizonPeriod; label: string; periodLabel: string }[] = [
  { key: "1Y", label: "1 Year", periodLabel: "2025 – 2026" },
  { key: "2Y", label: "2 Years", periodLabel: "2024 – 2026" },
  { key: "3Y", label: "3 Years", periodLabel: "2023 – 2026" },
  { key: "5Y", label: "5 Years", periodLabel: "2021 – 2026" },
];

export default function StrategyV4Page() {
  const [activeHorizon, setActiveHorizon] = useState<HorizonPeriod>("1Y");
  const [activeChartTab, setActiveChartTab] = useState<ActiveChartTab>("equity");
  const [exitFilter, setExitFilter] = useState<ExitFilter>("all");
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedSector, setSelectedSector] = useState("all");
  const [selectedTrade, setSelectedTrade] = useState<StrategyV4Trade | null>(null);
  const [showParamEditor, setShowParamEditor] = useState(false);
  const [isRecalculating, setIsRecalculating] = useState(false);
  const [params, setParams] = useState({
    z_score_entry_hurdle: 2.10,
    max_entry_momentum_slope: 0.05,
    z_score_exit_target: 0.40,
    z_score_stop_loss_barrier: 2.85,
    target_spread_vol_pct: 3.5,
    drawdown_threshold_pct: 20.0,
    drawdown_scaling_factor: 0.70,
    half_life_time_stop_multiplier: 2.5,
    min_holding_days_floor: 4,
    max_holding_days_cap: 22,
    vix_panic_threshold: 25.0,
    max_allowed_spread_vol_pct: 5.5,
  });

  // TanStack Query for Strategy v4 Backtest dataset
  const { data, isLoading, isFetching, refetch } = useQuery({
    queryKey: ["strategyV4", activeHorizon],
    queryFn: () => api.simulator.getV4Backtest(activeHorizon),
    staleTime: 60_000,
  });

  const trades = useMemo(() => data?.trades || [], [data]);
  const summary: StrategyV4Summary = useMemo(
    () =>
      data?.overall_summary || {
        total_trades: 0,
        win_count: 0,
        loss_count: 0,
        neutral_count: 0,
        win_rate_pct: 0,
        net_return_pct: 0,
        gross_profit_pct: 0,
        gross_loss_pct: 0,
        profit_factor: 0,
        max_drawdown_pct: 0,
        avg_return_pct: 0,
        avg_holding_days: 0,
        reversion_target_exits: 0,
        tight_stop_exits: 0,
        time_stop_exits: 0,
        sharpe_ratio: 0,
        calmar_ratio: 0,
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

  // Unique sectors for filtering
  const sectors = useMemo(() => {
    const set = new Set<string>();
    trades.forEach((t) => {
      if (t.sector) set.add(t.sector);
    });
    return Array.from(set).sort();
  }, [trades]);

  // Filtered trades
  const filteredTrades = useMemo(() => {
    return trades.filter((t) => {
      // Exit filter
      if (exitFilter === "reversion_target" && t.exit_reason !== "REVERSION_TARGET") return false;
      if (exitFilter === "tight_stop" && t.exit_reason !== "TIGHT_STOP") return false;
      if (exitFilter === "time_stop" && t.exit_reason !== "TIME_STOP") return false;
      if (exitFilter === "wins" && t.outcome !== "WIN") return false;
      if (exitFilter === "losses" && t.outcome !== "LOSS") return false;

      // Sector filter
      if (selectedSector !== "all" && t.sector !== selectedSector) return false;

      // Search query
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase().trim();
        const matchPair = t.pair_name.toLowerCase().includes(q);
        const matchTickerA = t.ticker_a.toLowerCase().includes(q);
        const matchTickerB = t.ticker_b.toLowerCase().includes(q);
        const matchSector = t.sector.toLowerCase().includes(q);
        if (!matchPair && !matchTickerA && !matchTickerB && !matchSector) return false;
      }

      return true;
    });
  }, [trades, exitFilter, selectedSector, searchQuery]);

  // Handle custom recalculate
  const handleRecalculate = async () => {
    setIsRecalculating(true);
    try {
      await api.simulator.recalculateV4({
        period: activeHorizon,
        ...params,
      });
      await refetch();
    } catch (err) {
      console.error("Recalculation error:", err);
    } finally {
      setIsRecalculating(false);
    }
  };

  // Equity Curve min/max points
  const equityPoints = useMemo(() => data?.equity_curve || [], [data]);

  return (
    <div className="space-y-6 pb-16">
      {/* ------------------------------------------------------------------- */}
      {/* 1. Header & Navigation Banner                                       */}
      {/* ------------------------------------------------------------------- */}
      <div className="flex flex-col xl:flex-row xl:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-3">
            <div className="p-2.5 rounded-xl bg-cyan-500/10 border border-cyan-500/30 text-cyan-400">
              <ShieldCheck className="w-6 h-6" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h1 className="text-xl font-bold font-mono text-white tracking-tight">
                  Strategy v4 &mdash; Risk-Engineered Pure Alpha
                </h1>
                <span className="px-2 py-0.5 rounded text-[11px] font-mono font-bold bg-cyan-500/20 text-cyan-300 border border-cyan-500/30">
                  FLAGSHIP QUANT UPGRADE
                </span>
              </div>
              <p className="text-xs text-gray-400 font-mono mt-0.5">
                Momentum Flattening &middot; Vol-Inverse Sizing &middot; Tight Stops (2.85σ) &middot; 2x Half-Life Time Stops &middot; VIX Overlay
              </p>
            </div>
          </div>
        </div>

        {/* Master Horizon Switcher & Parameter Toggle */}
        <div className="flex flex-wrap items-center gap-2">
          <button
            onClick={() => setShowParamEditor(!showParamEditor)}
            className={cn(
              "px-3 py-2 rounded-xl text-xs font-mono font-bold transition-all border flex items-center gap-1.5",
              showParamEditor
                ? "bg-cyan-600 text-white border-cyan-500 shadow-md shadow-cyan-600/30"
                : "bg-surface-2 text-gray-300 border-line hover:text-white hover:bg-surface-3"
            )}
          >
            <SlidersHorizontal className="w-3.5 h-3.5" />
            <span>{showParamEditor ? "Hide Parameters" : "Edit Base Parameters"}</span>
          </button>

          <div className="flex items-center gap-1 bg-surface-2 p-1 rounded-xl border border-line">
            {HORIZONS.map((h) => {
              const active = activeHorizon === h.key;
              return (
                <button
                  key={h.key}
                  onClick={() => setActiveHorizon(h.key)}
                  className={cn(
                    "px-3 py-1.5 rounded-lg text-xs font-mono transition-all flex flex-col items-center",
                    active
                      ? "bg-cyan-600 text-white font-bold shadow-md shadow-cyan-600/30"
                      : "text-gray-400 hover:text-gray-200 hover:bg-surface-1"
                  )}
                >
                  <span>{h.label}</span>
                  <span className={cn("text-[10px]", active ? "text-cyan-100" : "text-gray-500")}>
                    {h.periodLabel}
                  </span>
                </button>
              );
            })}

            <button
              onClick={() => refetch()}
              disabled={isFetching}
              className="p-2 ml-1 rounded-lg text-gray-400 hover:text-white hover:bg-surface-1 transition-colors"
              title="Recalculate Backtest"
            >
              <RefreshCw className={cn("w-4 h-4", isFetching && "animate-spin text-cyan-400")} />
            </button>
          </div>
        </div>
      </div>

      {/* ------------------------------------------------------------------- */}
      {/* 1.5 Collapsible Base Parameters & Recalculate Panel                 */}
      {/* ------------------------------------------------------------------- */}
      {showParamEditor && (
        <Card className="p-4 bg-surface-1 border-cyan-500/40 space-y-4">
          <div className="flex items-center justify-between pb-2 border-b border-line text-xs font-mono">
            <span className="font-bold text-white flex items-center gap-2">
              <SlidersHorizontal className="w-4 h-4 text-cyan-400" />
              Strategy 4 Base Parameters &amp; Risk Engine Calibration ({activeHorizon})
            </span>
            <span className="text-gray-400">Institutional Point-in-Time Simulation</span>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 text-xs font-mono">
            <div className="space-y-1">
              <label className="text-gray-400">Entry Hurdle (|Z| ≥ σ)</label>
              <input
                type="number"
                step="0.05"
                value={params.z_score_entry_hurdle}
                onChange={(e) => setParams({ ...params, z_score_entry_hurdle: parseFloat(e.target.value) || 2.10 })}
                className="w-full bg-surface-2 border border-line rounded px-2.5 py-1.5 text-white focus:outline-none focus:border-cyan-500"
              />
            </div>
            <div className="space-y-1">
              <label className="text-gray-400">Max Momentum Slope</label>
              <input
                type="number"
                step="0.01"
                value={params.max_entry_momentum_slope}
                onChange={(e) => setParams({ ...params, max_entry_momentum_slope: parseFloat(e.target.value) || 0.05 })}
                className="w-full bg-surface-2 border border-line rounded px-2.5 py-1.5 text-white focus:outline-none focus:border-cyan-500"
              />
            </div>
            <div className="space-y-1">
              <label className="text-gray-400">Exit Target (|Z| ≤ σ)</label>
              <input
                type="number"
                step="0.05"
                value={params.z_score_exit_target}
                onChange={(e) => setParams({ ...params, z_score_exit_target: parseFloat(e.target.value) || 0.40 })}
                className="w-full bg-surface-2 border border-line rounded px-2.5 py-1.5 text-white focus:outline-none focus:border-cyan-500"
              />
            </div>
            <div className="space-y-1">
              <label className="text-gray-400">Tight Stop Barrier (σ)</label>
              <input
                type="number"
                step="0.05"
                value={params.z_score_stop_loss_barrier}
                onChange={(e) => setParams({ ...params, z_score_stop_loss_barrier: parseFloat(e.target.value) || 2.85 })}
                className="w-full bg-surface-2 border border-line rounded px-2.5 py-1.5 text-white focus:outline-none focus:border-cyan-500"
              />
            </div>
          </div>

          <div className="flex items-center justify-end gap-2 pt-2 border-t border-line text-xs font-mono">
            <button
              onClick={() => {
                setParams({
                  z_score_entry_hurdle: 2.10,
                  max_entry_momentum_slope: 0.05,
                  z_score_exit_target: 0.40,
                  z_score_stop_loss_barrier: 2.85,
                  target_spread_vol_pct: 3.5,
                  drawdown_threshold_pct: 20.0,
                  drawdown_scaling_factor: 0.70,
                  half_life_time_stop_multiplier: 2.5,
                  min_holding_days_floor: 4,
                  max_holding_days_cap: 22,
                  vix_panic_threshold: 25.0,
                  max_allowed_spread_vol_pct: 5.5,
                });
              }}
              className="px-3 py-1.5 rounded bg-surface-2 hover:bg-surface-3 text-gray-400 hover:text-white border border-line"
            >
              Reset to Base Config
            </button>
            <button
              onClick={handleRecalculate}
              disabled={isRecalculating}
              className="px-4 py-1.5 rounded bg-cyan-600 hover:bg-cyan-500 text-white font-bold transition-all shadow-md flex items-center gap-1.5"
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
      <Card className="p-4 bg-surface-1 border-line">
        <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-xs font-mono font-bold text-gray-400 uppercase tracking-wider mr-2">
              Active Upgrades:
            </span>
            <div className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-mono bg-cyan-500/10 text-cyan-300 border border-cyan-500/30">
              <Activity className="w-3.5 h-3.5" />
              <span>Momentum Flattening Confirmation</span>
            </div>
            <div className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-mono bg-cyan-500/10 text-cyan-300 border border-cyan-500/30">
              <Target className="w-3.5 h-3.5" />
              <span>Realistic Exit (|Z| &le; 0.40&sigma;)</span>
            </div>
            <div className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-mono bg-cyan-500/10 text-cyan-300 border border-cyan-500/30">
              <ShieldAlert className="w-3.5 h-3.5" />
              <span>Tight Dynamic Stop (2.85&sigma;)</span>
            </div>
            <div className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-mono bg-cyan-500/10 text-cyan-300 border border-cyan-500/30">
              <Clock className="w-3.5 h-3.5" />
              <span>2x Half-Life Time Stop</span>
            </div>
            <div className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-mono bg-cyan-500/10 text-cyan-300 border border-cyan-500/30">
              <Percent className="w-3.5 h-3.5" />
              <span>Vol-Inverse Sizing (0.4x &ndash; 1.25x)</span>
            </div>
            <div className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-mono bg-cyan-500/10 text-cyan-300 border border-cyan-500/30">
              <ShieldCheck className="w-3.5 h-3.5" />
              <span>Earnings Blackout Shield</span>
            </div>
            <div className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-mono bg-cyan-500/10 text-cyan-300 border border-cyan-500/30">
              <Zap className="w-3.5 h-3.5" />
              <span>VIX Macro Freeze (&gt; 25.0)</span>
            </div>
          </div>

          <Link
            to="/backtest/compare"
            className="inline-flex items-center gap-1.5 text-xs font-mono text-cyan-400 hover:text-cyan-300 transition-colors whitespace-nowrap"
          >
            <GitCompare className="w-4 h-4" />
            <span>Benchmark vs Strategies 1, 2 &amp; 3</span>
            <ArrowRight className="w-3.5 h-3.5" />
          </Link>
        </div>
      </Card>

      {/* ------------------------------------------------------------------- */}
      {/* 3. Hero KPI Cards                                                  */}
      {/* ------------------------------------------------------------------- */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-3">
        {/* KPI 1: Realized Net Profit */}
        <Card className="p-4 bg-surface-1 border-line relative overflow-hidden group">
          <div className="flex items-center justify-between text-xs text-gray-400 font-mono">
            <span>Net Realized Profit</span>
            <TrendingUp className="w-4 h-4 text-cyan-400" />
          </div>
          <div className="mt-2 text-2xl font-bold font-mono text-cyan-400">
            +{summary.net_return_pct.toFixed(2)}%
          </div>
          <div className="mt-1 text-[11px] font-mono text-gray-500 flex items-center justify-between">
            <span>Gross Profit: +{summary.gross_profit_pct.toFixed(1)}%</span>
            <span>Loss: -{summary.gross_loss_pct.toFixed(1)}%</span>
          </div>
          <div className="absolute top-0 right-0 w-24 h-24 bg-cyan-500/5 rounded-full blur-xl pointer-events-none" />
        </Card>

        {/* KPI 2: Win Rate */}
        <Card className="p-4 bg-surface-1 border-line relative overflow-hidden group">
          <div className="flex items-center justify-between text-xs text-gray-400 font-mono">
            <span>Win Rate</span>
            <Percent className="w-4 h-4 text-emerald-400" />
          </div>
          <div className="mt-2 text-2xl font-bold font-mono text-emerald-400">
            {summary.win_rate_pct.toFixed(1)}%
          </div>
          <div className="mt-1 text-[11px] font-mono text-gray-500">
            {summary.win_count} Wins / {summary.loss_count} Losses ({summary.total_trades} total)
          </div>
        </Card>

        {/* KPI 3: Profit Factor */}
        <Card className="p-4 bg-surface-1 border-line relative overflow-hidden group">
          <div className="flex items-center justify-between text-xs text-gray-400 font-mono">
            <span>Profit Factor</span>
            <Award className="w-4 h-4 text-cyan-400" />
          </div>
          <div className="mt-2 text-2xl font-bold font-mono text-white">
            {summary.profit_factor.toFixed(2)}
          </div>
          <div className="mt-1 text-[11px] font-mono text-gray-500">
            Institutional Target: &ge; 1.65
          </div>
        </Card>

        {/* KPI 4: Max Drawdown */}
        <Card className="p-4 bg-surface-1 border-line relative overflow-hidden group">
          <div className="flex items-center justify-between text-xs text-gray-400 font-mono">
            <span>Max Drawdown</span>
            <TrendingDown className="w-4 h-4 text-rose-400" />
          </div>
          <div className="mt-2 text-2xl font-bold font-mono text-rose-400">
            -{Math.abs(summary.max_drawdown_pct).toFixed(2)}%
          </div>
          <div className="mt-1 text-[11px] font-mono text-gray-500">
            Slashing v3&apos;s 78% &amp; v1&apos;s 45% DD
          </div>
        </Card>

        {/* KPI 5: Average Holding Days */}
        <Card className="p-4 bg-surface-1 border-line relative overflow-hidden group">
          <div className="flex items-center justify-between text-xs text-gray-400 font-mono">
            <span>Avg Holding Duration</span>
            <Clock className="w-4 h-4 text-cyan-400" />
          </div>
          <div className="mt-2 text-2xl font-bold font-mono text-white">
            {summary.avg_holding_days.toFixed(1)}d
          </div>
          <div className="mt-1 text-[11px] font-mono text-gray-500">
            2x Half-Life Clamped (4d &ndash; 22d)
          </div>
        </Card>
      </div>

      {/* ------------------------------------------------------------------- */}
      {/* 4. Directional Stats & Exit Breakdown Matrix                        */}
      {/* ------------------------------------------------------------------- */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-3 text-xs font-mono">
        <Card className="p-3 bg-surface-1 border-line flex items-center justify-between">
          <div>
            <div className="text-gray-400">Reversion Exits (|Z| &le; 0.40)</div>
            <div className="text-lg font-bold text-emerald-400 mt-0.5">
              {summary.reversion_target_exits} trades
            </div>
          </div>
          <Target className="w-6 h-6 text-emerald-400/50" />
        </Card>

        <Card className="p-3 bg-surface-1 border-line flex items-center justify-between">
          <div>
            <div className="text-gray-400">Tight Stops (|Z| &ge; 2.85)</div>
            <div className="text-lg font-bold text-rose-400 mt-0.5">
              {summary.tight_stop_exits} trades
            </div>
          </div>
          <ShieldAlert className="w-6 h-6 text-rose-400/50" />
        </Card>

        <Card className="p-3 bg-surface-1 border-line flex items-center justify-between">
          <div>
            <div className="text-gray-400">Time Stops (2x Half-Life)</div>
            <div className="text-lg font-bold text-cyan-400 mt-0.5">
              {summary.time_stop_exits} trades
            </div>
          </div>
          <Clock className="w-6 h-6 text-cyan-400/50" />
        </Card>

        <Card className="p-3 bg-surface-1 border-line flex items-center justify-between">
          <div>
            <div className="text-gray-400">Long vs Short Win Rate</div>
            <div className="text-sm font-bold text-white mt-0.5">
              L: {directionalStats.longWinRate}% &middot; S: {directionalStats.shortWinRate}%
            </div>
          </div>
          <ArrowUpDown className="w-6 h-6 text-gray-400/50" />
        </Card>
      </div>

      {/* ------------------------------------------------------------------- */}
      {/* 5. Equity Curve / Underwater Drawdown Chart Card                   */}
      {/* ------------------------------------------------------------------- */}
      <Card className="p-5 bg-surface-1 border-line space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-3 border-b border-line">
          <div>
            <h2 className="text-sm font-bold font-mono text-white flex items-center gap-2">
              <TrendingUp className="w-4 h-4 text-cyan-400" />
              Strategy v4 Performance Trajectory ({activeHorizon})
            </h2>
            <p className="text-xs text-gray-400 font-mono mt-0.5">
              Daily walkforward compounding equity with volatility-inverse sizing
            </p>
          </div>

          <div className="flex items-center gap-1 bg-surface-2 p-1 rounded-lg border border-line text-xs font-mono">
            <button
              onClick={() => setActiveChartTab("equity")}
              className={cn(
                "px-3 py-1 rounded transition-colors",
                activeChartTab === "equity"
                  ? "bg-cyan-600 text-white font-bold"
                  : "text-gray-400 hover:text-white"
              )}
            >
              Equity Curve
            </button>
            <button
              onClick={() => setActiveChartTab("drawdown")}
              className={cn(
                "px-3 py-1 rounded transition-colors",
                activeChartTab === "drawdown"
                  ? "bg-cyan-600 text-white font-bold"
                  : "text-gray-400 hover:text-white"
              )}
            >
              Underwater Drawdown
            </button>
          </div>
        </div>

        {/* SVG Equity Chart Container */}
        <div className="relative h-72 w-full bg-surface-2/40 rounded-lg border border-line p-3 flex flex-col justify-between font-mono text-xs">
          {equityPoints.length > 0 ? (
            <svg className="w-full h-full overflow-visible" preserveAspectRatio="none" viewBox="0 0 1000 200">
              <defs>
                <linearGradient id="v4Gradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#06B6D4" stopOpacity="0.4" />
                  <stop offset="100%" stopColor="#06B6D4" stopOpacity="0.0" />
                </linearGradient>
                <linearGradient id="v4DrawdownGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#EF4444" stopOpacity="0.0" />
                  <stop offset="100%" stopColor="#EF4444" stopOpacity="0.3" />
                </linearGradient>
              </defs>

              {activeChartTab === "equity" ? (
                <>
                  {/* Grid Lines */}
                  <line x1="0" y1="50" x2="1000" y2="50" stroke="#334155" strokeDasharray="3 3" opacity="0.3" />
                  <line x1="0" y1="100" x2="1000" y2="100" stroke="#334155" strokeDasharray="3 3" opacity="0.3" />
                  <line x1="0" y1="150" x2="1000" y2="150" stroke="#334155" strokeDasharray="3 3" opacity="0.3" />

                  {/* Equity Line & Area */}
                  {(() => {
                    const maxVal = Math.max(...equityPoints.map((p) => p.cumulative_equity_pct), 10);
                    const minVal = Math.min(...equityPoints.map((p) => p.cumulative_equity_pct), 0);
                    const range = maxVal - minVal || 1;
                    const pts = equityPoints
                      .map((p, i) => {
                        const x = (i / Math.max(1, equityPoints.length - 1)) * 1000;
                        const y = 190 - ((p.cumulative_equity_pct - minVal) / range) * 170;
                        return `${x},${y}`;
                      })
                      .join(" ");

                    const zeroY = 190 - ((0 - minVal) / range) * 170;
                    const areaPts = `0,${zeroY} ${pts} 1000,${zeroY}`;

                    return (
                      <>
                        <polygon points={areaPts} fill="url(#v4Gradient)" />
                        <polyline points={pts} fill="none" stroke="#06B6D4" strokeWidth="2.5" />
                      </>
                    );
                  })()}
                </>
              ) : (
                <>
                  {/* Drawdown Area */}
                  {(() => {
                    const maxDD = Math.max(...equityPoints.map((p) => p.drawdown_pct), 10);
                    const pts = equityPoints
                      .map((p, i) => {
                        const x = (i / Math.max(1, equityPoints.length - 1)) * 1000;
                        const y = (p.drawdown_pct / maxDD) * 180 + 10;
                        return `${x},${y}`;
                      })
                      .join(" ");

                    const areaPts = `0,10 ${pts} 1000,10`;

                    return (
                      <>
                        <polygon points={areaPts} fill="url(#v4DrawdownGradient)" />
                        <polyline points={pts} fill="none" stroke="#EF4444" strokeWidth="2" />
                      </>
                    );
                  })()}
                </>
              )}
            </svg>
          ) : (
            <div className="flex items-center justify-center h-full text-gray-500">
              No equity curve data available.
            </div>
          )}

          <div className="flex items-center justify-between text-[11px] text-gray-500 pt-2 border-t border-line">
            <span>{data?.period?.start_date}</span>
            <span>{activeChartTab === "equity" ? "Cumulative Realized Growth (%)" : "Underwater Drawdown (%)"}</span>
            <span>{data?.period?.end_date}</span>
          </div>
        </div>
      </Card>

      {/* ------------------------------------------------------------------- */}
      {/* 6. Filterable Trade Ledger                                          */}
      {/* ------------------------------------------------------------------- */}
      <Card className="p-5 bg-surface-1 border-line space-y-4">
        <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-3">
          <div>
            <h2 className="text-sm font-bold font-mono text-white flex items-center gap-2">
              <Layers className="w-4 h-4 text-cyan-400" />
              Strategy v4 Trade Ledger ({filteredTrades.length} / {trades.length} trades)
            </h2>
            <p className="text-xs text-gray-400 font-mono mt-0.5">
              Click any trade row to view full forward trajectory excursion
            </p>
          </div>

          {/* Search & Sector Filters */}
          <div className="flex flex-wrap items-center gap-2">
            <div className="relative">
              <Search className="w-3.5 h-3.5 absolute left-2.5 top-2.5 text-gray-400" />
              <input
                type="text"
                placeholder="Search pair or ticker..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="pl-8 pr-3 py-1.5 rounded-lg bg-surface-2 border border-line text-xs font-mono text-white placeholder-gray-500 focus:outline-none focus:border-cyan-500"
              />
            </div>

            <select
              value={selectedSector}
              onChange={(e) => setSelectedSector(e.target.value)}
              className="px-2.5 py-1.5 rounded-lg bg-surface-2 border border-line text-xs font-mono text-gray-300 focus:outline-none focus:border-cyan-500"
            >
              <option value="all">All Sectors</option>
              {sectors.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          </div>
        </div>

        {/* Exit Filter Pills */}
        <div className="flex flex-wrap items-center gap-1.5 pt-1 border-t border-line text-xs font-mono">
          <button
            onClick={() => setExitFilter("all")}
            className={cn(
              "px-3 py-1 rounded-lg transition-colors border",
              exitFilter === "all"
                ? "bg-cyan-600 text-white border-cyan-500 font-bold"
                : "bg-surface-2 text-gray-400 border-line hover:text-white"
            )}
          >
            All Trades ({trades.length})
          </button>
          <button
            onClick={() => setExitFilter("reversion_target")}
            className={cn(
              "px-3 py-1 rounded-lg transition-colors border",
              exitFilter === "reversion_target"
                ? "bg-emerald-600 text-white border-emerald-500 font-bold"
                : "bg-surface-2 text-gray-400 border-line hover:text-white"
            )}
          >
            Reversion Targets ({summary.reversion_target_exits})
          </button>
          <button
            onClick={() => setExitFilter("tight_stop")}
            className={cn(
              "px-3 py-1 rounded-lg transition-colors border",
              exitFilter === "tight_stop"
                ? "bg-rose-600 text-white border-rose-500 font-bold"
                : "bg-surface-2 text-gray-400 border-line hover:text-white"
            )}
          >
            Tight Stops ({summary.tight_stop_exits})
          </button>
          <button
            onClick={() => setExitFilter("time_stop")}
            className={cn(
              "px-3 py-1 rounded-lg transition-colors border",
              exitFilter === "time_stop"
                ? "bg-amber-600 text-white border-amber-500 font-bold"
                : "bg-surface-2 text-gray-400 border-line hover:text-white"
            )}
          >
            Time Stops ({summary.time_stop_exits})
          </button>
          <button
            onClick={() => setExitFilter("wins")}
            className={cn(
              "px-3 py-1 rounded-lg transition-colors border",
              exitFilter === "wins"
                ? "bg-emerald-600/80 text-white border-emerald-500 font-bold"
                : "bg-surface-2 text-gray-400 border-line hover:text-white"
            )}
          >
            Wins ({summary.win_count})
          </button>
          <button
            onClick={() => setExitFilter("losses")}
            className={cn(
              "px-3 py-1 rounded-lg transition-colors border",
              exitFilter === "losses"
                ? "bg-rose-600/80 text-white border-rose-500 font-bold"
                : "bg-surface-2 text-gray-400 border-line hover:text-white"
            )}
          >
            Losses ({summary.loss_count})
          </button>
        </div>

        {/* Ledger Table */}
        <div className="overflow-x-auto rounded-lg border border-line">
          <table className="w-full text-xs font-mono">
            <thead className="bg-surface-2 text-gray-400 border-b border-line text-left">
              <tr>
                <th className="py-2.5 px-3">Pair / Sector</th>
                <th className="py-2.5 px-3">Entry Date</th>
                <th className="py-2.5 px-3">Exit Date</th>
                <th className="py-2.5 px-3">Direction</th>
                <th className="py-2.5 px-3">Entry Z</th>
                <th className="py-2.5 px-3">Exit Z</th>
                <th className="py-2.5 px-3">Sizing</th>
                <th className="py-2.5 px-3">Holding</th>
                <th className="py-2.5 px-3">Exit Reason</th>
                <th className="py-2.5 px-3 text-right">Return %</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line/40">
              {filteredTrades.map((t) => {
                const isWin = t.outcome === "WIN";
                return (
                  <tr
                    key={t.id}
                    onClick={() => setSelectedTrade(t)}
                    className="hover:bg-surface-2/60 cursor-pointer transition-colors"
                  >
                    <td className="py-2.5 px-3">
                      <div className="font-bold text-white flex items-center gap-1.5">
                        <span>{t.pair_name}</span>
                      </div>
                      <div className="text-[10px] text-gray-400">{t.sector}</div>
                    </td>
                    <td className="py-2.5 px-3 text-gray-300">{t.entry_date}</td>
                    <td className="py-2.5 px-3 text-gray-300">{t.exit_date || "—"}</td>
                    <td className="py-2.5 px-3">
                      <span
                        className={cn(
                          "px-1.5 py-0.5 rounded text-[10px] font-bold",
                          t.entry_z < 0
                            ? "bg-emerald-500/10 text-emerald-300 border border-emerald-500/20"
                            : "bg-rose-500/10 text-rose-300 border border-rose-500/20"
                        )}
                      >
                        {t.entry_z < 0 ? "LONG SPREAD" : "SHORT SPREAD"}
                      </span>
                    </td>
                    <td className="py-2.5 px-3 text-gray-300">{t.entry_z.toFixed(2)}&sigma;</td>
                    <td className="py-2.5 px-3 text-gray-300">{t.exit_z.toFixed(2)}&sigma;</td>
                    <td className="py-2.5 px-3">
                      <span className="px-1.5 py-0.5 rounded text-[10px] bg-cyan-500/10 text-cyan-300 border border-cyan-500/20 font-bold">
                        {t.sizing_multiplier.toFixed(2)}x
                      </span>
                    </td>
                    <td className="py-2.5 px-3 text-gray-300">{t.holding_days}d</td>
                    <td className="py-2.5 px-3">
                      <span
                        className={cn(
                          "px-2 py-0.5 rounded text-[10px] font-bold",
                          t.exit_reason === "REVERSION_TARGET"
                            ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/30"
                            : t.exit_reason === "TIGHT_STOP"
                            ? "bg-rose-500/20 text-rose-300 border border-rose-500/30"
                            : "bg-amber-500/20 text-amber-300 border border-amber-500/30"
                        )}
                      >
                        {t.exit_reason}
                      </span>
                    </td>
                    <td
                      className={cn(
                        "py-2.5 px-3 text-right font-bold",
                        t.realized_return_pct >= 0 ? "text-emerald-400" : "text-rose-400"
                      )}
                    >
                      {t.realized_return_pct >= 0 ? "+" : ""}
                      {t.realized_return_pct.toFixed(2)}%
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </Card>

      {/* ------------------------------------------------------------------- */}
      {/* 7. Institutional Full-Window Trade Inspector Modal                  */}
      {/* ------------------------------------------------------------------- */}
      {selectedTrade && (
        <TradeInspectorModal
          trade={selectedTrade}
          onClose={() => setSelectedTrade(null)}
          strategyLabel="STRATEGY 4: RISK-ENGINEERED PURE ALPHA"
          strategyThemeColor="cyan"
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
