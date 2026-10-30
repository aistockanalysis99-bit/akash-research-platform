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
import type { Backtest1YTrade } from "@/lib/simulatorTypes";
import { Card } from "@/components/ui";
import { cn } from "@/lib/utils";
import TradeInspectorModal from "@/components/simulator/TradeInspectorModal";

type HorizonPeriod = "1Y" | "2Y" | "3Y" | "5Y";
type ActiveChartTab = "equity" | "drawdown" | "monthly";
type FilterOption = "all" | "perfect10" | "checks8" | "wins" | "losses";

const HORIZONS: { key: HorizonPeriod; label: string; periodLabel: string }[] = [
  { key: "1Y", label: "1 Year", periodLabel: "2025 – 2026" },
  { key: "2Y", label: "2 Years", periodLabel: "2024 – 2026" },
  { key: "3Y", label: "3 Years", periodLabel: "2023 – 2026" },
  { key: "5Y", label: "5 Years", periodLabel: "2021 – 2026" },
];

export default function StrategyV1Page() {
  const [activeHorizon, setActiveHorizon] = useState<HorizonPeriod>("1Y");
  const [activeChartTab, setActiveChartTab] = useState<ActiveChartTab>("equity");
  const [filterOption, setFilterOption] = useState<FilterOption>("all");
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedTrade, setSelectedTrade] = useState<Backtest1YTrade | null>(null);
  const [showParamEditor, setShowParamEditor] = useState(false);
  const [isRecalculating, setIsRecalculating] = useState(false);
  const [params, setParams] = useState({
    entry_z: 2.0,
    stop_z: 3.5,
    max_horizon_days: 30,
  });

  // Query Strategy 1 backtest data for selected horizon
  const { data, isLoading, isFetching, refetch } = useQuery({
    queryKey: ["strategyV1", activeHorizon],
    queryFn: () => api.simulator.getV1Backtest(activeHorizon),
    staleTime: 60_000,
  });

  const trades = useMemo(() => data?.trades || [], [data]);
  const summary = useMemo(
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
      },
    [data]
  );

  // Directional Stats
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

  // Perfect 10/10 Checks Stats
  const perfectStats = useMemo(() => {
    const perfectTrades = trades.filter((t) => t.passed_checks_count === 10 || t.is_perfect_10);
    const wins = perfectTrades.filter((t) => t.outcome === "WIN").length;
    const wr = perfectTrades.length > 0 ? (wins / perfectTrades.length) * 100 : 0;
    return {
      count: perfectTrades.length,
      wins,
      winRate: Math.round(wr * 10) / 10,
    };
  }, [trades]);

  // Derived Equity Curve
  const equityCurve = useMemo(() => {
    if (data?.equity_curve && data.equity_curve.length > 0) return data.equity_curve;
    let cum = 0;
    let peak = 0;
    const sorted = [...trades].sort((a, b) => (a.exit_date || "").localeCompare(b.exit_date || ""));
    return sorted.map((t, idx) => {
      cum += (t.realized_return_pct || 0);
      if (cum > peak) peak = cum;
      const dd = peak > 0 ? ((peak - cum) / peak) * 100 : 0;
      return {
        date: t.exit_date || t.entry_date || "",
        trade_id: t.id || String(idx),
        return_pct: t.realized_return_pct || 0,
        cumulative_equity_pct: Math.round(cum * 100) / 100,
        drawdown_pct: Math.round(dd * 100) / 100,
      };
    });
  }, [data, trades]);

  // Derived Monthly Returns
  const monthlyReturns = useMemo(() => {
    if (data?.monthly_returns && data.monthly_returns.length > 0) return data.monthly_returns;
    const mGroups: Record<string, { wins: number; total: number; pnl: number }> = {};
    trades.forEach((t) => {
      const d = t.exit_date || t.entry_date;
      if (!d) return;
      const mKey = d.substring(0, 7);
      if (!mGroups[mKey]) mGroups[mKey] = { wins: 0, total: 0, pnl: 0 };
      mGroups[mKey].total += 1;
      if (t.outcome === "WIN") mGroups[mKey].wins += 1;
      mGroups[mKey].pnl += (t.realized_return_pct || 0);
    });
    return Object.keys(mGroups).sort().map((mKey) => ({
      month: mKey,
      trades_count: mGroups[mKey].total,
      win_rate_pct: Math.round((mGroups[mKey].wins / mGroups[mKey].total) * 1000) / 10,
      return_pct: Math.round(mGroups[mKey].pnl * 10) / 10,
    }));
  }, [data, trades]);

  // Filtered trades
  const filteredTrades = useMemo(() => {
    return trades.filter((t) => {
      if (filterOption === "perfect10" && (t.passed_checks_count || 0) < 10) return false;
      if (filterOption === "checks8" && (t.passed_checks_count || 0) < 8) return false;
      if (filterOption === "wins" && t.outcome !== "WIN") return false;
      if (filterOption === "losses" && t.outcome !== "LOSS") return false;

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
  }, [trades, filterOption, searchQuery]);

  const netRealizedReturn = useMemo(() => {
    return Math.round((summary.gross_profit_pct - summary.gross_loss_pct) * 100) / 100;
  }, [summary]);

  const handleRecalculate = async () => {
    setIsRecalculating(true);
    try {
      await api.simulator.recalculate1Y({
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
            <div className="p-2 rounded-lg bg-sky-500/10 border border-sky-500/20 text-sky-400">
              <TrendingUp className="w-5 h-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h1 className="text-2xl font-extrabold tracking-tight text-white font-mono">
                  Strategy 1 (Baseline Mean Reversion)
                </h1>
                <span className="px-2 py-0.5 rounded text-[11px] font-mono font-bold bg-sky-500/20 text-sky-300 border border-sky-500/30">
                  ESTABLISHED BASELINE
                </span>
              </div>
              <p className="text-xs text-gray-400 font-mono mt-0.5">
                Single-Tranche Mean Reversion &middot; Entry at Z = 2.0σ &middot; Exit at Mean Z = 0.0σ &middot; Stop Barrier 3.50σ
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
                ? "bg-sky-600 text-white border-sky-500 shadow-md shadow-sky-600/30"
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
                      ? "bg-sky-600 text-white font-bold shadow-md shadow-sky-600/30"
                      : "text-gray-400 hover:text-gray-200 hover:bg-surface-1"
                  )}
                >
                  <span>{h.label}</span>
                  <span className={cn("text-[10px]", active ? "text-sky-100" : "text-gray-500")}>
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
              <RefreshCw className={cn("w-4 h-4", isFetching && "animate-spin text-sky-400")} />
            </button>
          </div>
        </div>
      </div>

      {/* ------------------------------------------------------------------- */}
      {/* 1.5 Collapsible Base Parameters & Recalculate Panel                 */}
      {/* ------------------------------------------------------------------- */}
      {showParamEditor && (
        <Card className="p-4 bg-surface-1 border-sky-500/40 space-y-4">
          <div className="flex items-center justify-between pb-2 border-b border-line text-xs font-mono">
            <span className="font-bold text-white flex items-center gap-2">
              <SlidersHorizontal className="w-4 h-4 text-sky-400" />
              Strategy 1 Base Parameters &amp; Calibration ({activeHorizon})
            </span>
            <span className="text-gray-400">Instant walkforward recalculation</span>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 text-xs font-mono">
            <div className="space-y-1">
              <label className="text-gray-400">Entry Z-Score Hurdle</label>
              <input
                type="number"
                step="0.05"
                value={params.entry_z}
                onChange={(e) => setParams({ ...params, entry_z: parseFloat(e.target.value) || 2.0 })}
                className="w-full bg-surface-2 border border-line rounded px-2.5 py-1.5 text-white focus:outline-none focus:border-sky-500"
              />
            </div>
            <div className="space-y-1">
              <label className="text-gray-400">Stop-Loss Barrier (σ)</label>
              <input
                type="number"
                step="0.1"
                value={params.stop_z}
                onChange={(e) => setParams({ ...params, stop_z: parseFloat(e.target.value) || 3.5 })}
                className="w-full bg-surface-2 border border-line rounded px-2.5 py-1.5 text-white focus:outline-none focus:border-sky-500"
              />
            </div>
            <div className="space-y-1">
              <label className="text-gray-400">Max Holding Days</label>
              <input
                type="number"
                step="1"
                value={params.max_horizon_days}
                onChange={(e) => setParams({ ...params, max_horizon_days: parseInt(e.target.value) || 30 })}
                className="w-full bg-surface-2 border border-line rounded px-2.5 py-1.5 text-white focus:outline-none focus:border-sky-500"
              />
            </div>
          </div>

          <div className="flex items-center justify-end gap-2 pt-2 border-t border-line text-xs font-mono">
            <button
              onClick={() => {
                setParams({ entry_z: 2.0, stop_z: 3.5, max_horizon_days: 30 });
              }}
              className="px-3 py-1.5 rounded bg-surface-2 hover:bg-surface-3 text-gray-400 hover:text-white border border-line"
            >
              Reset to Base Config
            </button>
            <button
              onClick={handleRecalculate}
              disabled={isRecalculating}
              className="px-4 py-1.5 rounded bg-sky-600 hover:bg-sky-500 text-white font-bold transition-all shadow-md flex items-center gap-1.5"
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
            <div className="flex items-center gap-2 text-xs font-mono font-semibold text-sky-400">
              <Zap className="w-4 h-4" />
              <span>BASELINE QUANTITATIVE ARCHITECTURE</span>
            </div>
            <p className="text-xs text-gray-400">
              Rigorous single-tranche statistical arbitrage engine operating across S&amp;P 500 cointegrated pairs.
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <span className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-mono font-medium bg-sky-500/10 text-sky-300 border border-sky-500/20">
              <span>🎯</span>
              <strong>Mean Equilibrium Exit</strong>
              <span className="text-[10px] text-sky-400/80">(Z = 0.0σ)</span>
            </span>
            <span className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-mono font-medium bg-sky-500/10 text-sky-300 border border-sky-500/20">
              <span>⚡</span>
              <strong>Entry Hurdle</strong>
              <span className="text-[10px] text-sky-400/80">(2.00σ Barrier)</span>
            </span>
            <span className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-mono font-medium bg-sky-500/10 text-sky-300 border border-sky-500/20">
              <span>🛡️</span>
              <strong>Disaster Stop</strong>
              <span className="text-[10px] text-sky-400/80">(3.50σ Tail Exit)</span>
            </span>
            <span className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-mono font-medium bg-sky-500/10 text-sky-300 border border-sky-500/20">
              <span>⏱️</span>
              <strong>Max Duration</strong>
              <span className="text-[10px] text-sky-400/80">(30 Trading Days)</span>
            </span>
          </div>
        </div>
      </Card>

      {/* ------------------------------------------------------------------- */}
      {/* 3. Hero KPI Banners                                                 */}
      {/* ------------------------------------------------------------------- */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3">
        {/* KPI 1: Realized Net Profit */}
        <div className="bg-surface-1 border border-sky-500/30 rounded-xl p-4 flex flex-col justify-between relative overflow-hidden bg-gradient-to-br from-sky-500/[0.05] to-transparent">
          <div className="flex items-center justify-between text-xs text-gray-400">
            <span className="flex items-center gap-1.5 font-medium text-sky-400">
              <TrendingUp className="w-3.5 h-3.5" />
              Net Realized Profit
            </span>
            <span className="px-1.5 py-0.5 rounded text-[10px] font-mono font-bold bg-sky-500/20 text-sky-300 border border-sky-500/30">
              BASELINE
            </span>
          </div>
          <div className="mt-3">
            <div className="text-2xl font-extrabold text-sky-400 font-mono">
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
              Exit at 3.50σ stop barrier
            </div>
          </div>
        </div>

        {/* KPI 5: Perfect 10/10 Checks Win Rate */}
        <div className="bg-surface-1 border border-sky-500/20 rounded-xl p-4 flex flex-col justify-between bg-sky-500/[0.02]">
          <div className="flex items-center justify-between text-xs text-sky-300">
            <span className="flex items-center gap-1.5 font-medium">
              <Sparkles className="w-3.5 h-3.5 text-sky-400" />
              Perfect 10/10 WR
            </span>
            <span className="px-1.5 py-0.5 rounded text-[10px] font-mono font-bold bg-sky-500/20 text-sky-300 border border-sky-500/30">
              High Conviction
            </span>
          </div>
          <div className="mt-3">
            <div className="text-2xl font-extrabold text-sky-300 font-mono">
              {perfectStats.winRate}%
            </div>
            <div className="text-[11px] text-gray-400 font-mono mt-1">
              {perfectStats.count} Setups passed all 10 checks
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
            <TrendingUp className="w-4 h-4 text-sky-400" />
            <h2 className="text-sm font-bold text-white font-mono">
              Strategy 1 Performance Trajectory &amp; Distributions
            </h2>
          </div>

          <div className="flex items-center bg-surface-2 p-1 rounded-lg border border-line text-xs font-mono">
            <button
              onClick={() => setActiveChartTab("equity")}
              className={cn(
                "px-3 py-1 rounded transition-colors flex items-center gap-1.5",
                activeChartTab === "equity"
                  ? "bg-sky-600 text-white font-semibold"
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
                  ? "bg-purple-600 text-white font-semibold"
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
                Strategy 1 Net Realized PnL (Chronological Exits)
              </span>
              <strong className="text-sm font-mono text-sky-400">
                +{netRealizedReturn.toFixed(1)}%
              </strong>
            </div>

            {/* SVG Area Curve */}
            <div className="h-48 w-full bg-surface-2/40 rounded-lg border border-line/60 p-2 relative overflow-hidden flex items-end">
              {equityCurve && equityCurve.length > 1 ? (
                <svg
                  className="w-full h-full overflow-visible"
                  viewBox={`0 0 ${equityCurve.length} 100`}
                  preserveAspectRatio="none"
                >
                  <defs>
                    <linearGradient id="v1EquityGrad" x1="0%" y1="0%" x2="0%" y2="100%">
                      <stop offset="0%" stopColor="#0ea5e9" stopOpacity="0.45" />
                      <stop offset="100%" stopColor="#0ea5e9" stopOpacity="0.0" />
                    </linearGradient>
                  </defs>
                  {(() => {
                    const values = equityCurve.map((d: any) => d.cumulative_return_pct ?? d.cumulative_equity_pct ?? 0);
                    const minVal = Math.min(0, ...values);
                    const maxVal = Math.max(10, ...values);
                    const range = maxVal - minVal || 1;

                    const points = equityCurve
                      .map((d: any, i: number) => {
                        const val = d.cumulative_return_pct ?? d.cumulative_equity_pct ?? 0;
                        const x = i;
                        const y = 92 - ((val - minVal) / range) * 84;
                        return `${x},${y}`;
                      })
                      .join(" ");

                    const areaPoints = `0,92 ${points} ${equityCurve.length - 1},92`;

                    return (
                      <>
                        <polygon
                          points={areaPoints}
                          fill="url(#v1EquityGrad)"
                          vectorEffect="non-scaling-stroke"
                        />
                        <polyline
                          fill="none"
                          stroke="#0ea5e9"
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
                  Loading equity curve...
                </div>
              )}
            </div>

            <div className="flex items-center justify-between text-[10px] text-gray-500 font-mono">
              <span>Start: {data?.period?.start_date}</span>
              <span>{trades.length} realized exits &middot; S&amp;P 500 Walkforward</span>
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
              {equityCurve && equityCurve.length > 1 ? (
                <svg
                  className="w-full h-full overflow-visible"
                  viewBox={`0 0 ${equityCurve.length} 100`}
                  preserveAspectRatio="none"
                >
                  <defs>
                    <linearGradient id="v1DdGrad" x1="0%" y1="0%" x2="0%" y2="100%">
                      <stop offset="0%" stopColor="#ef4444" stopOpacity="0.45" />
                      <stop offset="100%" stopColor="#ef4444" stopOpacity="0.0" />
                    </linearGradient>
                  </defs>
                  {(() => {
                    const values = equityCurve.map((d: any) => d.drawdown_pct || 0);
                    const maxVal = Math.max(5, ...values);

                    const points = equityCurve
                      .map((d: any, i: number) => {
                        const dd = d.drawdown_pct || 0;
                        const x = i;
                        const y = (dd / maxVal) * 88 + 5;
                        return `${x},${y}`;
                      })
                      .join(" ");

                    const areaPoints = `0,5 ${points} ${equityCurve.length - 1},5`;

                    return (
                      <>
                        <polygon
                          points={areaPoints}
                          fill="url(#v1DdGrad)"
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
              <span>Disaster Stop Barrier (3.50σ)</span>
              <span>Trough: -{summary.max_drawdown_pct.toFixed(1)}%</span>
            </div>
          </div>
        )}

        {/* Tab 3: Monthly Heatmap */}
        {activeChartTab === "monthly" && (
          <div className="space-y-3">
            <div className="text-xs text-gray-400 font-mono">
              Monthly Net Performance Matrix ({monthlyReturns?.length || 0} Months)
            </div>

            <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6 gap-2.5">
              {monthlyReturns?.map((m: any) => (
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
      {/* 5. Trade History Ledger & Filters                                   */}
      {/* ------------------------------------------------------------------- */}
      <Card className="p-4 bg-surface-1 border-line space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <Layers className="w-4 h-4 text-sky-400" />
            <h2 className="text-sm font-bold text-white font-mono">
              Strategy 1 Trade Ledger ({filteredTrades.length} of {trades.length})
            </h2>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            {/* Filter Pills */}
            <div className="flex items-center bg-surface-2 p-1 rounded-lg border border-line text-xs font-mono">
              <button
                onClick={() => setFilterOption("all")}
                className={cn(
                  "px-2.5 py-1 rounded transition-colors",
                  filterOption === "all" ? "bg-surface-3 text-white font-semibold" : "text-gray-400 hover:text-white"
                )}
              >
                All
              </button>
              <button
                onClick={() => setFilterOption("perfect10")}
                className={cn(
                  "px-2.5 py-1 rounded transition-colors",
                  filterOption === "perfect10" ? "bg-sky-600 text-white font-semibold" : "text-gray-400 hover:text-white"
                )}
              >
                Perfect 10/10 ({perfectStats.count})
              </button>
              <button
                onClick={() => setFilterOption("checks8")}
                className={cn(
                  "px-2.5 py-1 rounded transition-colors",
                  filterOption === "checks8" ? "bg-purple-600 text-white font-semibold" : "text-gray-400 hover:text-white"
                )}
              >
                Passed ≥ 8
              </button>
              <button
                onClick={() => setFilterOption("wins")}
                className={cn(
                  "px-2.5 py-1 rounded transition-colors",
                  filterOption === "wins" ? "bg-emerald-800 text-white font-semibold" : "text-gray-400 hover:text-white"
                )}
              >
                Wins Only
              </button>
              <button
                onClick={() => setFilterOption("losses")}
                className={cn(
                  "px-2.5 py-1 rounded transition-colors",
                  filterOption === "losses" ? "bg-rose-800 text-white font-semibold" : "text-gray-400 hover:text-white"
                )}
              >
                Losses Only
              </button>
            </div>

            {/* Search */}
            <div className="relative">
              <Search className="w-3.5 h-3.5 text-gray-400 absolute left-2.5 top-1/2 -translate-y-1/2" />
              <input
                type="text"
                placeholder="Search pair, ticker, or sector..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="bg-surface-2 border border-line rounded-lg pl-8 pr-3 py-1 text-xs text-white placeholder-gray-500 focus:outline-none focus:border-sky-500 w-48 sm:w-56 font-mono"
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
                <th className="py-2.5 px-3">Quality Score</th>
                <th className="py-2.5 px-3 text-right">Net Return</th>
                <th className="py-2.5 px-3">Status &amp; Exit Reason</th>
                <th className="py-2.5 px-3 text-center">Inspect</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line/60 font-mono">
              {filteredTrades.slice(0, 60).map((t) => (
                <tr
                  key={t.id}
                  onClick={() => setSelectedTrade(t)}
                  className="hover:bg-surface-2/60 transition-colors cursor-pointer group"
                >
                  <td className="py-2.5 px-3">
                    <div className="font-bold text-white group-hover:text-sky-400 transition-colors">
                      {t.pair_name}
                    </div>
                    <div className="text-[10px] text-gray-400 font-sans">{t.sector || "Other"}</div>
                  </td>

                  <td className="py-2.5 px-3 text-[11px] text-gray-300">
                    {t.direction_label || t.direction}
                  </td>

                  <td className="py-2.5 px-3 text-gray-300">
                    <div>{t.entry_date}</div>
                    <div className="text-[10px] text-sky-400 font-semibold">{t.entry_z?.toFixed(2)}σ</div>
                  </td>

                  <td className="py-2.5 px-3 text-gray-300">
                    <div>{t.exit_date}</div>
                    <div className="text-[10px] text-gray-400">
                      {t.exit_z !== null && t.exit_z !== undefined ? `${t.exit_z.toFixed(2)}σ` : "0.00σ"}
                    </div>
                  </td>

                  <td className="py-2.5 px-3 text-gray-400">
                    {t.holding_days}d
                  </td>

                  <td className="py-2.5 px-3">
                    <span
                      className={cn(
                        "inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-bold",
                        (t.passed_checks_count || 0) === 10
                          ? "bg-emerald-500/15 text-emerald-300 border border-emerald-500/30"
                          : (t.passed_checks_count || 0) >= 8
                          ? "bg-sky-500/15 text-sky-300 border border-sky-500/30"
                          : "bg-surface-2 text-gray-400 border border-line"
                      )}
                    >
                      {t.passed_checks_count || 0}/10 Checks
                    </span>
                  </td>

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
                  </td>

                  <td className="py-2.5 px-3 text-[11px] max-w-xs truncate text-gray-300" title={t.status_reason}>
                    {t.status_reason || t.outcome}
                  </td>

                  <td className="py-2.5 px-3 text-center">
                    <button className="p-1 rounded hover:bg-surface-3 text-gray-400 group-hover:text-sky-400 transition-colors">
                      <Eye className="w-3.5 h-3.5" />
                    </button>
                  </td>
                </tr>
              ))}
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
      {/* 6. Institutional Full-Window Trade Inspector Modal                  */}
      {/* ------------------------------------------------------------------- */}
      {selectedTrade && (
        <TradeInspectorModal
          trade={selectedTrade}
          onClose={() => setSelectedTrade(null)}
          strategyLabel="STRATEGY 1: BASELINE DIVERGENCE ARBITRAGE"
          strategyThemeColor="sky"
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
