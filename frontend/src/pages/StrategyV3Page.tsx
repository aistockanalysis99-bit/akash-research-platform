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
} from "lucide-react";
import { api } from "@/lib/api";
import type {
  StrategyV3Response,
  StrategyV3Trade,
  StrategyV3Summary,
} from "@/lib/simulatorTypes";
import { Card } from "@/components/ui";
import { cn } from "@/lib/utils";

type HorizonPeriod = "1Y" | "2Y" | "3Y" | "5Y";
type ActiveChartTab = "equity" | "drawdown" | "monthly";
type TierFilter = "all" | "tier1" | "tier2" | "tier3" | "disaster_saved" | "wins" | "losses";

const HORIZONS: { key: HorizonPeriod; label: string; periodLabel: string }[] = [
  { key: "1Y", label: "1 Year", periodLabel: "2025 – 2026" },
  { key: "2Y", label: "2 Years", periodLabel: "2024 – 2026" },
  { key: "3Y", label: "3 Years", periodLabel: "2023 – 2026" },
  { key: "5Y", label: "5 Years", periodLabel: "2021 – 2026" },
];

export default function StrategyV3Page() {
  const [activeHorizon, setActiveHorizon] = useState<HorizonPeriod>("1Y");
  const [activeChartTab, setActiveChartTab] = useState<ActiveChartTab>("equity");
  const [tierFilter, setTierFilter] = useState<TierFilter>("all");
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedTrade, setSelectedTrade] = useState<StrategyV3Trade | null>(null);
  const [showParamEditor, setShowParamEditor] = useState(false);
  const [isRecalculating, setIsRecalculating] = useState(false);
  const [params, setParams] = useState({
    z_score_entry: 2.0,
    z_score_stop_loss: 3.5,
    tier1_multiplier: 1.45,
    tier3_multiplier: 0.65,
    protected_stop_z: 1.5,
    activation_recovery_z: 0.6,
    max_holding_days: 35,
  });

  // TanStack Query for Strategy v3 Backtest dataset
  const { data, isLoading, isFetching, refetch } = useQuery({
    queryKey: ["strategyV3", activeHorizon],
    queryFn: () => api.simulator.getV3Backtest(activeHorizon),
    staleTime: 60_000,
  });

  const trades = useMemo(() => data?.trades || [], [data]);
  const summary: StrategyV3Summary = useMemo(
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
        disaster_floor_saved_trades: 0,
        tier1_trades_count: 0,
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

  // Tier 1 Conviction Trade Stats
  const tier1Stats = useMemo(() => {
    const t1Trades = trades.filter(
      (t) => t.conviction_tier?.startsWith("Tier 1") || t.conviction_multiplier > 1.2
    );
    const t1Wins = t1Trades.filter((t) => t.outcome === "WIN").length;
    const t1WinRate = t1Trades.length > 0 ? (t1Wins / t1Trades.length) * 100 : 0;
    const t1TotalPnl = t1Trades.reduce((acc, t) => acc + (t.realized_return_pct || 0), 0);

    return {
      count: t1Trades.length,
      wins: t1Wins,
      winRate: Math.round(t1WinRate * 10) / 10,
      totalPnl: Math.round(t1TotalPnl * 10) / 10,
    };
  }, [trades]);

  // Disaster Floor Saved Stats
  const disasterFloorCount = useMemo(() => {
    return trades.filter((t) => t.protected_stop_hit || t.recovered_to_floor).length;
  }, [trades]);

  // Filtered trades for history table
  const filteredTrades = useMemo(() => {
    return trades.filter((t) => {
      // Tier filter
      if (tierFilter === "tier1" && !t.conviction_tier?.startsWith("Tier 1")) return false;
      if (tierFilter === "tier2" && !t.conviction_tier?.startsWith("Tier 2")) return false;
      if (tierFilter === "tier3" && !t.conviction_tier?.startsWith("Tier 3")) return false;
      if (tierFilter === "disaster_saved" && !t.protected_stop_hit && !t.recovered_to_floor) return false;
      if (tierFilter === "wins" && t.outcome !== "WIN") return false;
      if (tierFilter === "losses" && t.outcome !== "LOSS") return false;

      // Text search
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase().trim();
        const matchPair = t.pair_name.toLowerCase().includes(q);
        const matchSector = (t.sector || "").toLowerCase().includes(q);
        const matchTickA = t.ticker_a.toLowerCase().includes(q);
        const matchTickB = t.ticker_b.toLowerCase().includes(q);
        const matchReason = (t.status_reason || "").toLowerCase().includes(q);
        if (!matchPair && !matchSector && !matchTickA && !matchTickB && !matchReason) return false;
      }

      return true;
    });
  }, [trades, tierFilter, searchQuery]);

  const netRealizedReturn = summary.net_return_pct;

  const handleRecalculate = async () => {
    setIsRecalculating(true);
    try {
      await api.simulator.recalculateV3({
        period: activeHorizon,
        ...params,
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
            <div className="p-2 rounded-lg bg-emerald-500/10 border border-emerald-500/20 text-emerald-400">
              <Flame className="w-5 h-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h1 className="text-2xl font-extrabold tracking-tight text-white font-mono">
                  Strategy v3 (Asymmetric Alpha Maximizer)
                </h1>
                <span className="px-2 py-0.5 rounded text-[11px] font-mono font-bold bg-emerald-500/20 text-emerald-300 border border-emerald-500/30">
                  PRODUCTION FLAGSHIP
                </span>
              </div>
              <p className="text-xs text-gray-400 font-mono mt-0.5">
                Full-Ride Mean Reversion &middot; 1.45x Tier-1 Conviction Sizing &middot; Trailing Disaster Floor (1.50σ) &middot; 35d Horizon
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
                ? "bg-emerald-600 text-white border-emerald-500 shadow-md shadow-emerald-600/30"
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
                      ? "bg-emerald-600 text-white font-bold shadow-md shadow-emerald-600/30"
                      : "text-gray-400 hover:text-gray-200 hover:bg-surface-1"
                  )}
                >
                  <span>{h.label}</span>
                  <span className={cn("text-[10px]", active ? "text-emerald-100" : "text-gray-500")}>
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
              <RefreshCw className={cn("w-4 h-4", isFetching && "animate-spin text-emerald-400")} />
            </button>
          </div>
        </div>
      </div>

      {/* ------------------------------------------------------------------- */}
      {/* 1.5 Collapsible Base Parameters & Recalculate Panel                 */}
      {/* ------------------------------------------------------------------- */}
      {showParamEditor && (
        <Card className="p-4 bg-surface-1 border-emerald-500/40 space-y-4">
          <div className="flex items-center justify-between pb-2 border-b border-line text-xs font-mono">
            <span className="font-bold text-white flex items-center gap-2">
              <SlidersHorizontal className="w-4 h-4 text-emerald-400" />
              Strategy 3 Base Parameters &amp; Calibration ({activeHorizon})
            </span>
            <span className="text-gray-400">Instant walkforward recalculation</span>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 text-xs font-mono">
            <div className="space-y-1">
              <label className="text-gray-400">Tier 1 Multiplier</label>
              <input
                type="number"
                step="0.05"
                value={params.tier1_multiplier}
                onChange={(e) => setParams({ ...params, tier1_multiplier: parseFloat(e.target.value) || 1.45 })}
                className="w-full bg-surface-2 border border-line rounded px-2.5 py-1.5 text-white focus:outline-none focus:border-emerald-500"
              />
            </div>
            <div className="space-y-1">
              <label className="text-gray-400">Trailing Floor (σ)</label>
              <input
                type="number"
                step="0.1"
                value={params.protected_stop_z}
                onChange={(e) => setParams({ ...params, protected_stop_z: parseFloat(e.target.value) || 1.5 })}
                className="w-full bg-surface-2 border border-line rounded px-2.5 py-1.5 text-white focus:outline-none focus:border-emerald-500"
              />
            </div>
            <div className="space-y-1">
              <label className="text-gray-400">Disaster Stop (σ)</label>
              <input
                type="number"
                step="0.1"
                value={params.z_score_stop_loss}
                onChange={(e) => setParams({ ...params, z_score_stop_loss: parseFloat(e.target.value) || 3.5 })}
                className="w-full bg-surface-2 border border-line rounded px-2.5 py-1.5 text-white focus:outline-none focus:border-emerald-500"
              />
            </div>
            <div className="space-y-1">
              <label className="text-gray-400">Adaptive Horizon Days</label>
              <input
                type="number"
                step="1"
                value={params.max_holding_days}
                onChange={(e) => setParams({ ...params, max_holding_days: parseInt(e.target.value) || 35 })}
                className="w-full bg-surface-2 border border-line rounded px-2.5 py-1.5 text-white focus:outline-none focus:border-emerald-500"
              />
            </div>
          </div>

          <div className="flex items-center justify-end gap-2 pt-2 border-t border-line text-xs font-mono">
            <button
              onClick={() => {
                setParams({
                  z_score_entry: 2.0,
                  z_score_stop_loss: 3.5,
                  tier1_multiplier: 1.45,
                  tier3_multiplier: 0.65,
                  protected_stop_z: 1.5,
                  activation_recovery_z: 0.6,
                  max_holding_days: 35,
                });
              }}
              className="px-3 py-1.5 rounded bg-surface-2 hover:bg-surface-3 text-gray-400 hover:text-white border border-line"
            >
              Reset to Base Config
            </button>
            <button
              onClick={handleRecalculate}
              disabled={isRecalculating}
              className="px-4 py-1.5 rounded bg-emerald-600 hover:bg-emerald-500 text-white font-bold transition-all shadow-md flex items-center gap-1.5"
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
          <div className="space-y-1">
            <div className="flex items-center gap-2 text-xs font-mono font-semibold text-emerald-400">
              <Zap className="w-4 h-4" />
              <span>ACTIVE QUANTITATIVE ARCHITECTURE</span>
            </div>
            <p className="text-xs text-gray-400">
              Four institutional upgrades engineered to maximize raw asymmetric payoff while protecting capital.
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            {/* Pill 1 */}
            <span className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-mono font-medium bg-emerald-500/10 text-emerald-300 border border-emerald-500/20">
              <span>🚀</span>
              <strong>Full-Ride Reversion</strong>
              <span className="text-[10px] text-emerald-400/80">(Exit at Z = 0.0)</span>
            </span>

            {/* Pill 2 */}
            <span className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-mono font-medium bg-emerald-500/10 text-emerald-300 border border-emerald-500/20">
              <span>💎</span>
              <strong>Conviction Sizing</strong>
              <span className="text-[10px] text-emerald-400/80">(1.45x on Score ≥ 82)</span>
            </span>

            {/* Pill 3 */}
            <span className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-mono font-medium bg-emerald-500/10 text-emerald-300 border border-emerald-500/20">
              <span>🛡️</span>
              <strong>Trailing Disaster Floor</strong>
              <span className="text-[10px] text-emerald-400/80">(Moves to 1.5σ on 60% rec)</span>
            </span>

            {/* Pill 4 */}
            <span className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-mono font-medium bg-emerald-500/10 text-emerald-300 border border-emerald-500/20">
              <span>⏱️</span>
              <strong>35-Day Adaptive Horizon</strong>
              <span className="text-[10px] text-emerald-400/80">(Gives pairs space to revert)</span>
            </span>
          </div>
        </div>
      </Card>

      {/* ------------------------------------------------------------------- */}
      {/* 3. Hero KPI Banners                                                 */}
      {/* ------------------------------------------------------------------- */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3">
        {/* KPI 1: Realized Net Profit % */}
        <div className="bg-surface-1 border border-emerald-500/30 rounded-xl p-4 flex flex-col justify-between relative overflow-hidden bg-gradient-to-br from-emerald-500/[0.05] to-transparent">
          <div className="flex items-center justify-between text-xs text-gray-400">
            <span className="flex items-center gap-1.5 font-medium text-emerald-400">
              <TrendingUp className="w-3.5 h-3.5" />
              Net Realized Profit
            </span>
            <span className="px-1.5 py-0.5 rounded text-[10px] font-mono font-bold bg-emerald-500/20 text-emerald-300 border border-emerald-500/30">
              ★ BEATS S1 &amp; S2
            </span>
          </div>
          <div className="mt-3">
            <div className="text-2xl font-extrabold text-emerald-400 font-mono">
              +{netRealizedReturn.toFixed(1)}%
            </div>
            <div className="text-[11px] text-gray-400 font-mono mt-1">
              Gross: +{summary.gross_profit_pct.toFixed(1)}% | Loss: -{summary.gross_loss_pct.toFixed(1)}%
            </div>
          </div>
        </div>

        {/* KPI 2: Profit Factor */}
        <div className="bg-surface-1 border border-line rounded-xl p-4 flex flex-col justify-between">
          <div className="flex items-center justify-between text-xs text-gray-400">
            <span className="flex items-center gap-1.5 font-medium">
              <Zap className="w-3.5 h-3.5 text-amber-400" />
              Profit Factor
            </span>
            <span className="px-1.5 py-0.5 rounded text-[10px] font-mono font-bold bg-surface-2 text-gray-300 border border-line">
              Win/Loss Ratio
            </span>
          </div>
          <div className="mt-3">
            <div className="text-2xl font-extrabold text-white font-mono">
              {summary.profit_factor.toFixed(2)}
            </div>
            <div className="text-[11px] text-gray-400 font-mono mt-1">
              Avg Trade: +{summary.avg_return_pct.toFixed(2)}%
            </div>
          </div>
        </div>

        {/* KPI 3: Win Rate % */}
        <div className="bg-surface-1 border border-line rounded-xl p-4 flex flex-col justify-between">
          <div className="flex items-center justify-between text-xs text-gray-400">
            <span className="flex items-center gap-1.5 font-medium">
              <CheckCircle2 className="w-3.5 h-3.5 text-sky-400" />
              Win Rate %
            </span>
            <span className="px-1.5 py-0.5 rounded text-[10px] font-mono font-bold bg-surface-2 text-gray-300 border border-line">
              {summary.win_count}W / {summary.loss_count}L
            </span>
          </div>
          <div className="mt-3">
            <div className="text-2xl font-extrabold text-white font-mono">
              {summary.win_rate_pct.toFixed(1)}%
            </div>
            <div className="text-[11px] text-gray-400 font-mono mt-1">
              Long: {directionalStats.longWinRate}% | Short: {directionalStats.shortWinRate}%
            </div>
          </div>
        </div>

        {/* KPI 4: Max Drawdown % */}
        <div className="bg-surface-1 border border-line rounded-xl p-4 flex flex-col justify-between">
          <div className="flex items-center justify-between text-xs text-gray-400">
            <span className="flex items-center gap-1.5 font-medium">
              <ShieldCheck className="w-3.5 h-3.5 text-rose-400" />
              Max Drawdown
            </span>
            <span className="px-1.5 py-0.5 rounded text-[10px] font-mono font-bold bg-surface-2 text-gray-300 border border-line">
              Peak-to-Trough
            </span>
          </div>
          <div className="mt-3">
            <div className="text-2xl font-extrabold text-rose-400 font-mono">
              -{summary.max_drawdown_pct.toFixed(1)}%
            </div>
            <div className="text-[11px] text-gray-400 font-mono mt-1">
              Protected by 1.50σ Disaster Floor
            </div>
          </div>
        </div>

        {/* KPI 5: Tier-1 Prime Win Rate & Compounding */}
        <div className="bg-surface-1 border border-emerald-500/20 rounded-xl p-4 flex flex-col justify-between bg-emerald-500/[0.02]">
          <div className="flex items-center justify-between text-xs text-emerald-300">
            <span className="flex items-center gap-1.5 font-medium">
              <Sparkles className="w-3.5 h-3.5 text-emerald-400" />
              Tier-1 Conviction WR
            </span>
            <span className="px-1.5 py-0.5 rounded text-[10px] font-mono font-bold bg-emerald-500/20 text-emerald-300 border border-emerald-500/30">
              1.45x Sized
            </span>
          </div>
          <div className="mt-3">
            <div className="text-2xl font-extrabold text-emerald-300 font-mono">
              {tier1Stats.winRate}%
            </div>
            <div className="text-[11px] text-gray-400 font-mono mt-1">
              {tier1Stats.count} Prime Trades &middot; PnL: +{tier1Stats.totalPnl}%
            </div>
          </div>
        </div>
      </div>

      {/* ------------------------------------------------------------------- */}
      {/* 4. Chart Viewport Switcher (Equity, Drawdown, Monthly)              */}
      {/* ------------------------------------------------------------------- */}
      <Card className="p-4 bg-surface-1 border-line">
        <div className="flex items-center justify-between pb-3 border-b border-line mb-4">
          <div className="flex items-center gap-2">
            <TrendingUp className="w-4 h-4 text-emerald-400" />
            <h2 className="text-sm font-bold text-white font-mono">
              Performance Trajectory &amp; Return Distribution
            </h2>
          </div>

          <div className="flex items-center bg-surface-2 p-1 rounded-lg border border-line text-xs font-mono">
            <button
              onClick={() => setActiveChartTab("equity")}
              className={cn(
                "px-3 py-1 rounded transition-colors flex items-center gap-1.5",
                activeChartTab === "equity"
                  ? "bg-emerald-600 text-white font-semibold"
                  : "text-gray-400 hover:text-white"
              )}
            >
              <span>Cumulative Equity</span>
            </button>
            <button
              onClick={() => setActiveChartTab("drawdown")}
              className={cn(
                "px-3 py-1 rounded transition-colors flex items-center gap-1.5",
                activeChartTab === "drawdown"
                  ? "bg-rose-600 text-white font-semibold"
                  : "text-gray-400 hover:text-white"
              )}
            >
              <span>Underwater Drawdown</span>
            </button>
            <button
              onClick={() => setActiveChartTab("monthly")}
              className={cn(
                "px-3 py-1 rounded transition-colors flex items-center gap-1.5",
                activeChartTab === "monthly"
                  ? "bg-sky-600 text-white font-semibold"
                  : "text-gray-400 hover:text-white"
              )}
            >
              <span>Monthly Heatmap</span>
            </button>
          </div>
        </div>

        {/* Tab 1: Equity Curve */}
        {activeChartTab === "equity" && (
          <div className="space-y-2">
            <div className="flex items-center justify-between text-xs font-mono">
              <span className="text-gray-400">
                Strategy v3 Net Realized PnL (Full-Ride Mean Reversion &middot; Tiered Size)
              </span>
              <strong className="text-sm font-mono text-emerald-400">
                +{netRealizedReturn.toFixed(1)}%
              </strong>
            </div>

            {/* SVG Area Curve */}
            <div className="h-48 w-full bg-surface-2/40 rounded-lg border border-line/60 p-2 relative overflow-hidden flex items-end">
              {data?.equity_curve && data.equity_curve.length > 1 ? (
                <svg
                  className="w-full h-full overflow-visible"
                  viewBox={`0 0 ${data.equity_curve.length} 100`}
                  preserveAspectRatio="none"
                >
                  <defs>
                    <linearGradient id="v3EquityGrad" x1="0%" y1="0%" x2="0%" y2="100%">
                      <stop offset="0%" stopColor="#10b981" stopOpacity="0.45" />
                      <stop offset="100%" stopColor="#10b981" stopOpacity="0.0" />
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
                          fill="url(#v3EquityGrad)"
                          vectorEffect="non-scaling-stroke"
                        />
                        <polyline
                          fill="none"
                          stroke="#10b981"
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
              <span>{trades.length} realized exits &middot; Full Reversion Walkforward</span>
              <span>End: {data?.period?.end_date}</span>
            </div>
          </div>
        )}

        {/* Tab 2: Underwater Drawdown */}
        {activeChartTab === "drawdown" && (
          <div className="space-y-2">
            <div className="flex items-center justify-between text-xs font-mono">
              <span className="text-gray-400">Peak-to-Trough Drawdown Depth</span>
              <span className="text-rose-400 font-bold text-sm">
                Max DD: -{summary.max_drawdown_pct.toFixed(1)}%
              </span>
            </div>

            <div className="h-48 w-full bg-surface-2/40 rounded-lg border border-line/60 p-2 relative overflow-hidden flex items-start">
              {data?.equity_curve && data.equity_curve.length > 1 ? (
                <svg
                  className="w-full h-full overflow-visible"
                  viewBox={`0 0 ${data.equity_curve.length} 100`}
                  preserveAspectRatio="none"
                >
                  <defs>
                    <linearGradient id="v3DdGrad" x1="0%" y1="0%" x2="0%" y2="100%">
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
                          fill="url(#v3DdGrad)"
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
              <span>Trailing Disaster Floor engaged on recovery</span>
              <span>Trough: -{summary.max_drawdown_pct.toFixed(1)}%</span>
            </div>
          </div>
        )}

        {/* Tab 3: Monthly Heatmap */}
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
      </Card>

      {/* ------------------------------------------------------------------- */}
      {/* 5. Trade History Table & Inspector Filter Bar                       */}
      {/* ------------------------------------------------------------------- */}
      <Card className="p-4 bg-surface-1 border-line space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <Layers className="w-4 h-4 text-emerald-400" />
            <h2 className="text-sm font-bold text-white font-mono">
              Strategy v3 Trade Ledger ({filteredTrades.length} of {trades.length})
            </h2>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            {/* Filter Pills */}
            <div className="flex items-center bg-surface-2 p-1 rounded-lg border border-line text-xs font-mono">
              <button
                onClick={() => setTierFilter("all")}
                className={cn(
                  "px-2.5 py-1 rounded transition-colors",
                  tierFilter === "all" ? "bg-surface-3 text-white font-semibold" : "text-gray-400 hover:text-white"
                )}
              >
                All
              </button>
              <button
                onClick={() => setTierFilter("tier1")}
                className={cn(
                  "px-2.5 py-1 rounded transition-colors",
                  tierFilter === "tier1" ? "bg-emerald-600 text-white font-semibold" : "text-gray-400 hover:text-white"
                )}
              >
                Tier 1 (1.45x)
              </button>
              <button
                onClick={() => setTierFilter("tier2")}
                className={cn(
                  "px-2.5 py-1 rounded transition-colors",
                  tierFilter === "tier2" ? "bg-sky-600 text-white font-semibold" : "text-gray-400 hover:text-white"
                )}
              >
                Tier 2 (1.0x)
              </button>
              <button
                onClick={() => setTierFilter("disaster_saved")}
                className={cn(
                  "px-2.5 py-1 rounded transition-colors",
                  tierFilter === "disaster_saved" ? "bg-purple-600 text-white font-semibold" : "text-gray-400 hover:text-white"
                )}
              >
                Floor Saved ({disasterFloorCount})
              </button>
              <button
                onClick={() => setTierFilter("wins")}
                className={cn(
                  "px-2.5 py-1 rounded transition-colors",
                  tierFilter === "wins" ? "bg-emerald-800 text-white font-semibold" : "text-gray-400 hover:text-white"
                )}
              >
                Wins Only
              </button>
              <button
                onClick={() => setTierFilter("losses")}
                className={cn(
                  "px-2.5 py-1 rounded transition-colors",
                  tierFilter === "losses" ? "bg-rose-800 text-white font-semibold" : "text-gray-400 hover:text-white"
                )}
              >
                Losses Only
              </button>
            </div>

            {/* Search Input */}
            <div className="relative">
              <Search className="w-3.5 h-3.5 text-gray-400 absolute left-2.5 top-1/2 -translate-y-1/2" />
              <input
                type="text"
                placeholder="Search pair, ticker, or sector..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="bg-surface-2 border border-line rounded-lg pl-8 pr-3 py-1 text-xs text-white placeholder-gray-500 focus:outline-none focus:border-emerald-500 w-48 sm:w-56 font-mono"
              />
            </div>
          </div>
        </div>

        {/* Ledger Table */}
        <div className="overflow-x-auto rounded-lg border border-line">
          <table className="w-full text-left text-xs border-collapse">
            <thead>
              <tr className="bg-surface-2 border-b border-line font-mono text-[11px] text-gray-400">
                <th className="py-2.5 px-3">Pair &amp; Sector</th>
                <th className="py-2.5 px-3">Direction</th>
                <th className="py-2.5 px-3">Entry Date &amp; Z</th>
                <th className="py-2.5 px-3">Exit Date &amp; Z</th>
                <th className="py-2.5 px-3">Holding</th>
                <th className="py-2.5 px-3">Conviction Tier</th>
                <th className="py-2.5 px-3 text-right">Net Return</th>
                <th className="py-2.5 px-3">Status &amp; Exit Reason</th>
                <th className="py-2.5 px-3 text-center">Inspect</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line/60 font-mono">
              {filteredTrades.slice(0, 60).map((t) => {
                const isT1 = t.conviction_tier?.startsWith("Tier 1");
                const isT3 = t.conviction_tier?.startsWith("Tier 3");

                return (
                  <tr
                    key={t.id}
                    onClick={() => setSelectedTrade(t)}
                    className="hover:bg-surface-2/60 transition-colors cursor-pointer group"
                  >
                    {/* Pair & Sector */}
                    <td className="py-2.5 px-3">
                      <div className="font-bold text-white group-hover:text-emerald-400 transition-colors">
                        {t.pair_name}
                      </div>
                      <div className="text-[10px] text-gray-400 font-sans">{t.sector}</div>
                    </td>

                    {/* Direction */}
                    <td className="py-2.5 px-3 text-[11px]">
                      <span className="text-gray-300">{t.direction_label}</span>
                    </td>

                    {/* Entry Date & Z */}
                    <td className="py-2.5 px-3 text-gray-300">
                      <div>{t.entry_date}</div>
                      <div className="text-[10px] text-emerald-400 font-semibold">{t.entry_z.toFixed(2)}σ</div>
                    </td>

                    {/* Exit Date & Z */}
                    <td className="py-2.5 px-3 text-gray-300">
                      <div>{t.exit_date}</div>
                      <div className="text-[10px] text-gray-400">
                        {t.exit_z !== null && t.exit_z !== undefined ? `${t.exit_z.toFixed(2)}σ` : "—"}
                      </div>
                    </td>

                    {/* Holding Days */}
                    <td className="py-2.5 px-3 text-gray-400">
                      {t.holding_days}d
                    </td>

                    {/* Conviction Tier Badge */}
                    <td className="py-2.5 px-3">
                      {isT1 ? (
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-bold bg-emerald-500/15 text-emerald-300 border border-emerald-500/30 whitespace-nowrap">
                          💎 Tier 1 ({t.conviction_multiplier}x)
                        </span>
                      ) : isT3 ? (
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-medium bg-amber-500/15 text-amber-300 border border-amber-500/30 whitespace-nowrap">
                          ⚡ Tier 3 ({t.conviction_multiplier}x)
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-medium bg-sky-500/15 text-sky-300 border border-sky-500/30 whitespace-nowrap">
                          🎯 Tier 2 ({t.conviction_multiplier}x)
                        </span>
                      )}
                    </td>

                    {/* Net Realized Return */}
                    <td className="py-2.5 px-3 text-right">
                      <div
                        className={cn(
                          "font-bold text-sm",
                          t.outcome === "WIN" ? "text-emerald-400" : "text-rose-400"
                        )}
                      >
                        {t.realized_return_pct >= 0 ? "+" : ""}
                        {t.realized_return_pct.toFixed(2)}%
                      </div>
                      <div className="text-[10px] text-gray-500">
                        raw: {t.raw_return_pct >= 0 ? "+" : ""}{t.raw_return_pct.toFixed(2)}%
                      </div>
                    </td>

                    {/* Reason */}
                    <td className="py-2.5 px-3 text-[11px] max-w-xs truncate text-gray-300" title={t.status_reason}>
                      {t.protected_stop_hit ? (
                        <span className="text-purple-300 font-semibold">🛡️ Trailing Floor Hit</span>
                      ) : (
                        t.exit_reason
                      )}
                    </td>

                    {/* Inspect Button */}
                    <td className="py-2.5 px-3 text-center">
                      <button className="p-1 rounded hover:bg-surface-3 text-gray-400 group-hover:text-emerald-400 transition-colors">
                        <Eye className="w-3.5 h-3.5" />
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>

        {filteredTrades.length > 60 && (
          <div className="text-center text-xs text-gray-500 font-mono pt-2">
            Showing top 60 trades of {filteredTrades.length} matching criteria.
          </div>
        )}

        {filteredTrades.length === 0 && (
          <div className="p-8 text-center text-xs text-gray-500 font-mono">
            No trades match the current filter or search query.
          </div>
        )}
      </Card>

      {/* ------------------------------------------------------------------- */}
      {/* 6. Trade Inspector Modal                                            */}
      {/* ------------------------------------------------------------------- */}
      {selectedTrade && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/75 backdrop-blur-sm">
          <div
            className="w-full max-w-3xl bg-surface-1 border border-line rounded-xl p-5 shadow-2xl relative max-h-[90vh] overflow-y-auto"
            onClick={(e) => e.stopPropagation()}
          >
            {/* Header */}
            <div className="flex items-start justify-between pb-4 border-b border-line">
              <div>
                <div className="flex items-center gap-2">
                  <h3 className="text-lg font-bold text-white font-mono">
                    {selectedTrade.pair_name} Trade Inspector
                  </h3>
                  <span
                    className={cn(
                      "px-2 py-0.5 rounded text-xs font-mono font-semibold",
                      selectedTrade.outcome === "WIN"
                        ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/30"
                        : "bg-rose-500/20 text-rose-300 border border-rose-500/30"
                    )}
                  >
                    {selectedTrade.outcome} ({selectedTrade.realized_return_pct >= 0 ? "+" : ""}{selectedTrade.realized_return_pct.toFixed(2)}%)
                  </span>
                </div>
                <p className="text-xs text-gray-400 font-mono mt-1">
                  {selectedTrade.direction_label} &middot; Sector: {selectedTrade.sector} &middot; Held for {selectedTrade.holding_days} trading days
                </p>
              </div>

              <button
                onClick={() => setSelectedTrade(null)}
                className="p-1.5 rounded-lg hover:bg-surface-3 text-gray-400 hover:text-white transition-colors"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Quant Attributes Grid */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 my-4">
              <div className="p-3 rounded-lg bg-surface-2 border border-line">
                <div className="text-[10px] text-gray-400 font-mono uppercase">Conviction Tier</div>
                <div className="text-sm font-bold font-mono text-emerald-400 mt-0.5">
                  {selectedTrade.conviction_tier}
                </div>
                <div className="text-[10px] text-gray-500 font-mono">
                  Multiplier: {selectedTrade.conviction_multiplier}x
                </div>
              </div>

              <div className="p-3 rounded-lg bg-surface-2 border border-line">
                <div className="text-[10px] text-gray-400 font-mono uppercase">Entry Z-Score</div>
                <div className="text-sm font-bold font-mono text-white mt-0.5">
                  {selectedTrade.entry_z.toFixed(2)}σ
                </div>
                <div className="text-[10px] text-gray-500 font-mono">
                  Date: {selectedTrade.entry_date}
                </div>
              </div>

              <div className="p-3 rounded-lg bg-surface-2 border border-line">
                <div className="text-[10px] text-gray-400 font-mono uppercase">Exit Z-Score</div>
                <div className="text-sm font-bold font-mono text-white mt-0.5">
                  {selectedTrade.exit_z !== null && selectedTrade.exit_z !== undefined ? `${selectedTrade.exit_z.toFixed(2)}σ` : "0.00σ"}
                </div>
                <div className="text-[10px] text-gray-500 font-mono">
                  Date: {selectedTrade.exit_date}
                </div>
              </div>

              <div className="p-3 rounded-lg bg-surface-2 border border-line">
                <div className="text-[10px] text-gray-400 font-mono uppercase">Trailing Floor Status</div>
                <div className="text-sm font-bold font-mono text-purple-300 mt-0.5">
                  {selectedTrade.protected_stop_hit
                    ? "Floor Exit Hit"
                    : selectedTrade.recovered_to_floor
                    ? "Floor Active (1.5σ)"
                    : "Not Triggered"}
                </div>
                <div className="text-[10px] text-gray-500 font-mono">
                  Favorable Z: {selectedTrade.max_favorable_z?.toFixed(2) || "—"}σ
                </div>
              </div>
            </div>

            {/* Trajectory Chart */}
            <div className="space-y-2 mt-4">
              <div className="flex items-center justify-between text-xs font-mono text-gray-400">
                <span>Spread Z-Score Trajectory Over Holding Episode</span>
                <span>Max Adverse Z: {selectedTrade.max_adverse_z?.toFixed(2) || "—"}σ</span>
              </div>

              <div className="h-44 w-full bg-surface-2 rounded-lg border border-line p-3 relative flex items-center">
                {selectedTrade.trajectory && selectedTrade.trajectory.length > 1 ? (
                  <svg
                    className="w-full h-full overflow-visible"
                    viewBox={`0 0 ${selectedTrade.trajectory.length} 100`}
                    preserveAspectRatio="none"
                  >
                    {(() => {
                      const zVals = selectedTrade.trajectory.map((p) => p.z_score);
                      const minZ = Math.min(-3.5, ...zVals);
                      const maxZ = Math.max(3.5, ...zVals);
                      const zRange = maxZ - minZ || 1;

                      const toY = (z: number) => 95 - ((z - minZ) / zRange) * 90;

                      const points = selectedTrade.trajectory
                        .map((p, i) => `${i},${toY(p.z_score)}`)
                        .join(" ");

                      return (
                        <>
                          {/* Zero Mean Line */}
                          <line
                            x1="0"
                            y1={toY(0)}
                            x2={selectedTrade.trajectory.length - 1}
                            y2={toY(0)}
                            stroke="#475569"
                            strokeDasharray="3 3"
                            strokeWidth="1"
                            vectorEffect="non-scaling-stroke"
                          />
                          {/* Trailing Floor Line (1.50σ) */}
                          <line
                            x1="0"
                            y1={toY(selectedTrade.direction === "LONG_A_SHORT_B" ? -1.5 : 1.5)}
                            x2={selectedTrade.trajectory.length - 1}
                            y2={toY(selectedTrade.direction === "LONG_A_SHORT_B" ? -1.5 : 1.5)}
                            stroke="#8b5cf6"
                            strokeDasharray="2 2"
                            strokeWidth="1"
                            vectorEffect="non-scaling-stroke"
                          />
                          {/* Disaster Stop Line (3.50σ) */}
                          <line
                            x1="0"
                            y1={toY(selectedTrade.direction === "LONG_A_SHORT_B" ? -3.5 : 3.5)}
                            x2={selectedTrade.trajectory.length - 1}
                            y2={toY(selectedTrade.direction === "LONG_A_SHORT_B" ? -3.5 : 3.5)}
                            stroke="#ef4444"
                            strokeDasharray="2 2"
                            strokeWidth="1"
                            vectorEffect="non-scaling-stroke"
                          />

                          {/* Trajectory Polyline */}
                          <polyline
                            fill="none"
                            stroke="#10b981"
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
                    Point-in-time trajectory points available via daily log.
                  </div>
                )}
              </div>

              <div className="flex items-center justify-between text-[10px] text-gray-500 font-mono">
                <span>Entry: {selectedTrade.entry_date}</span>
                <span className="text-emerald-400">Green = Spread Path | Purple = Floor (1.5σ) | Red = Disaster Stop (3.5σ)</span>
                <span>Exit: {selectedTrade.exit_date}</span>
              </div>
            </div>

            {/* Status Reason */}
            <div className="mt-4 p-3 rounded-lg bg-surface-2 border border-line">
              <div className="text-[10px] text-gray-400 font-mono uppercase mb-1">Execution Narrative</div>
              <p className="text-xs text-gray-300 font-mono">
                {selectedTrade.status_reason || selectedTrade.exit_reason}
              </p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
