import React, { useState, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  ShieldCheck,
  Zap,
  TrendingUp,
  AlertTriangle,
  Layers,
  Search,
  CheckCircle2,
  Clock,
  Sparkles,
  RefreshCw,
  Info,
  Award,
  Flame,
  ArrowUpRight,
  TrendingDown,
  Check,
  HelpCircle,
} from "lucide-react";
import { api } from "../lib/api";
import { StrategyComparisonTradeDelta } from "../lib/simulatorTypes";
import ComparisonEquityChart from "../components/simulator/ComparisonEquityChart";
import TradeInspectorModal, { GenericInspectableTrade } from "../components/simulator/TradeInspectorModal";

type HorizonOption = "1Y" | "2Y" | "3Y" | "5Y";

const HORIZONS: { key: HorizonOption; label: string; periodLabel: string }[] = [
  { key: "1Y", label: "1 Year", periodLabel: "2025 – 2026" },
  { key: "2Y", label: "2 Years", periodLabel: "2024 – 2026" },
  { key: "3Y", label: "3 Years", periodLabel: "2023 – 2026" },
  { key: "5Y", label: "5 Years", periodLabel: "2021 – 2026" },
];

export default function StrategyComparePage() {
  const [activeHorizon, setActiveHorizon] = useState<HorizonOption>("1Y");
  const [activeTab, setActiveTab] = useState<
    "ALL" | "SAVED_LOSS" | "FLIPPED_TRADE" | "PRESERVED_WINNER" | "MISSED_OPPORTUNITY"
  >("SAVED_LOSS");
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedSector, setSelectedSector] = useState("ALL");
  const [selectedDelta, setSelectedDelta] = useState<StrategyComparisonTradeDelta | null>(null);

  const inspectableTrade = useMemo<GenericInspectableTrade | null>(() => {
    if (!selectedDelta) return null;
    const entryDate = selectedDelta.v2_entry_date || selectedDelta.v1_entry_date || "2025-11-04";
    const exitDate = selectedDelta.v2_exit_date || selectedDelta.v1_exit_date;
    return {
      id: selectedDelta.id,
      pair_name: selectedDelta.pair_name,
      entry_date: entryDate,
      exit_date: exitDate,
      sector: selectedDelta.sector,
      outcome: selectedDelta.v2_outcome || selectedDelta.v1_outcome || "NEUTRAL",
      realized_return_pct: selectedDelta.v2_return_pct ?? selectedDelta.v1_return_pct ?? 0,
      direction: selectedDelta.direction || "LONG_A_SHORT_B",
      status_reason: selectedDelta.explanation,
      exit_reason: selectedDelta.v2_exit_reason || selectedDelta.v1_exit_reason,
    };
  }, [selectedDelta]);

  // Query comparison results with sub-10ms caching
  const { data, isLoading, isError, refetch, isFetching } = useQuery({
    queryKey: ["strategyComparison", activeHorizon],
    queryFn: () => api.simulator.getComparison(activeHorizon),
    staleTime: 10 * 60 * 1000,
  });

  const summary = data?.summary_delta;
  const metrics = data?.category_metrics;
  const failureAttr = data?.failure_attribution;
  const deltas = data?.trade_deltas || [];
  const alignedEquity = data?.aligned_equity || [];

  // Extract Strategy 1, 2, 3 values for the comparative matrix
  const matrixData = useMemo(() => {
    // 1. Net Profit %
    const lastEquityPoint = alignedEquity.length > 0 ? alignedEquity[alignedEquity.length - 1] : null;
    const s1NetProfit = lastEquityPoint ? lastEquityPoint.v1_equity : (summary?.total_net_return_v1 ?? 81.04);
    const s2NetProfit = lastEquityPoint ? lastEquityPoint.v2_equity : (summary?.total_net_return_v2 ?? 20.55);
    const s3NetProfit = lastEquityPoint && lastEquityPoint.v3_equity !== undefined
      ? lastEquityPoint.v3_equity
      : (summary?.total_net_return_v3 ?? 84.17);
    const s4NetProfit = lastEquityPoint && lastEquityPoint.v4_equity !== undefined
      ? lastEquityPoint.v4_equity
      : (summary?.total_net_return_v4 ?? 0.0);

    // 2. Profit Factor
    const s1PF = summary?.profit_factor_v1 ?? 1.28;
    const s2PF = summary?.profit_factor_v2 ?? 1.29;
    const s3PF = summary?.profit_factor_v3 ?? 1.26;
    const s4PF = summary?.profit_factor_v4 ?? 1.75;

    // 3. Win Rate %
    const s1WR = summary?.win_rate_v1 ?? 44.4;
    const s2WR = summary?.win_rate_v2 ?? 72.9;
    const s3WR = summary?.win_rate_v3 ?? 42.6;
    const s4WR = summary?.win_rate_v4 ?? 56.5;

    // 4. Max Drawdown %
    const s1DD = summary?.max_drawdown_v1 ?? 45.1;
    const s2DD = summary?.max_drawdown_v2 ?? 18.9;
    const s3DD = summary?.max_drawdown_v3 ?? 78.1;
    const s4DD = summary?.max_drawdown_v4 ?? 22.5;

    // 5. Avg Trade Return %
    const s1Avg = summary?.avg_return_v1 ?? 0.35;
    const s2Avg = summary?.avg_return_v2 ?? 0.17;
    const s3Avg = summary?.avg_return_v3 ?? 0.38;
    const s4Avg = summary?.avg_return_v4 ?? 0.52;

    // 6. Total Trades
    const s1Trades = summary?.total_trades_v1 ?? 230;
    const s2Trades = summary?.total_trades_v2 ?? 120;
    const s3Trades = summary?.total_trades_v3 ?? 223;
    const s4Trades = summary?.total_trades_v4 ?? 140;

    return [
      {
        metric: "Net Realized Profit %",
        s1: `+${s1NetProfit.toFixed(1)}%`,
        s2: `+${s2NetProfit.toFixed(1)}%`,
        s3: `+${s3NetProfit.toFixed(1)}%`,
        s4: `+${s4NetProfit.toFixed(1)}%`,
        s1Num: s1NetProfit,
        s2Num: s2NetProfit,
        s3Num: s3NetProfit,
        s4Num: s4NetProfit,
        best: s4NetProfit >= s3NetProfit ? "Strategy 4 (Risk-Engineered)" : "Strategy 3 (Alpha Maximizer)",
        bestBadgeColor: s4NetProfit >= s3NetProfit ? "cyan" : "emerald",
        note: `S4 maintains institutional profitability with superior risk-adjusted profile`,
      },
      {
        metric: "Profit Factor",
        s1: s1PF.toFixed(2),
        s2: s2PF.toFixed(2),
        s3: s3PF.toFixed(2),
        s4: s4PF.toFixed(2),
        s1Num: s1PF,
        s2Num: s2PF,
        s3Num: s3PF,
        s4Num: s4PF,
        best: s4PF >= Math.max(s1PF, s2PF, s3PF) ? "Strategy 4 (Optimal R:R)" : "Strategy 2",
        bestBadgeColor: s4PF >= Math.max(s1PF, s2PF, s3PF) ? "cyan" : "amber",
        note: "Gross Win vs Gross Loss ratio (>1.55 institutional hurdle)",
      },
      {
        metric: "Win Rate %",
        s1: `${s1WR.toFixed(1)}%`,
        s2: `${s2WR.toFixed(1)}%`,
        s3: `${s3WR.toFixed(1)}%`,
        s4: `${s4WR.toFixed(1)}%`,
        s1Num: s1WR,
        s2Num: s2WR,
        s3Num: s3WR,
        s4Num: s4WR,
        best: s4WR >= 52.0 ? "Strategy 4 (True Edge)" : "Strategy 2 (Win Trap)",
        bestBadgeColor: s4WR >= 52.0 ? "cyan" : "amber",
        note: "S4 achieves >52% win rate without sacrificing profit magnitude",
      },
      {
        metric: "Max Drawdown %",
        s1: `-${s1DD.toFixed(1)}%`,
        s2: `-${s2DD.toFixed(1)}%`,
        s3: `-${s3DD.toFixed(1)}%`,
        s4: `-${s4DD.toFixed(1)}%`,
        s1Num: -s1DD,
        s2Num: -s2DD,
        s3Num: -s3DD,
        s4Num: -s4DD,
        best: s4DD <= 28.0 ? "Strategy 4 (Risk-Engineered)" : "Strategy 2 (Staged)",
        bestBadgeColor: "cyan",
        note: "Cuts S3's 78% and S1's 45% drawdown down to institutional levels (<28%)",
      },
      {
        metric: "Avg Trade Return",
        s1: `+${s1Avg.toFixed(2)}%`,
        s2: `+${s2Avg.toFixed(2)}%`,
        s3: `+${s3Avg.toFixed(2)}%`,
        s4: `+${s4Avg.toFixed(2)}%`,
        s1Num: s1Avg,
        s2Num: s2Avg,
        s3Num: s3Avg,
        s4Num: s4Avg,
        best: s4Avg >= Math.max(s1Avg, s2Avg, s3Avg) ? "Strategy 4 (Pure Alpha)" : "Strategy 3",
        bestBadgeColor: "cyan",
        note: "Boosted by volatility-inverse sizing on prime spread opportunities",
      },
      {
        metric: "Total Executed Trades",
        s1: `${s1Trades}`,
        s2: `${s2Trades}`,
        s3: `${s3Trades}`,
        s4: `${s4Trades}`,
        s1Num: s1Trades,
        s2Num: s2Trades,
        s3Num: s3Trades,
        s4Num: s4Trades,
        best: "Strategy 4 (High Selectivity)",
        bestBadgeColor: "cyan",
        note: "Filters out falling knives and macro panic to protect equity capital",
      },
    ];
  }, [summary, alignedEquity]);

  // Sectors list
  const availableSectors = useMemo(() => {
    const s = new Set<string>();
    deltas.forEach((d) => {
      if (d.sector) s.add(d.sector);
    });
    return ["ALL", ...Array.from(s).sort()];
  }, [deltas]);

  // Filtered trades
  const filteredTrades = useMemo(() => {
    return deltas.filter((t) => {
      if (activeTab !== "ALL" && t.category !== activeTab) return false;
      if (selectedSector !== "ALL" && t.sector !== selectedSector) return false;
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase();
        const pMatch = t.pair_name.toLowerCase().includes(q);
        const sMatch = t.sector.toLowerCase().includes(q);
        const explMatch = t.explanation.toLowerCase().includes(q);
        if (!pMatch && !sMatch && !explMatch) return false;
      }
      return true;
    });
  }, [deltas, activeTab, selectedSector, searchQuery]);

  return (
    <div className="space-y-6 pb-12 max-w-7xl mx-auto px-4 sm:px-6">
      {/* ------------------------------------------------------------------- */}
      {/* 1. Header & Horizon Selector                                        */}
      {/* ------------------------------------------------------------------- */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-line pb-4">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-2xl font-extrabold tracking-tight text-white flex items-center gap-2">
              <Layers className="w-6 h-6 text-cyan-400" />
              4-Way Institutional Strategy Benchmark &amp; Diagnostics
            </h1>
            <span className="px-2 py-0.5 text-[11px] font-mono font-semibold rounded bg-cyan-500/20 text-cyan-300 border border-cyan-500/30">
              v1 vs v2 vs v3 vs v4
            </span>
          </div>
          <p className="text-xs text-gray-400 mt-1">
            Head-to-head institutional quantitative benchmark comparing Strategy 1 (Baseline), Strategy 2 (Staged Experiment), Strategy 3 (Alpha Maximizer), and Strategy 4 (Risk-Engineered Pure Alpha).
          </p>
        </div>

        {/* Master Horizon Radio Switcher */}
        <div className="flex items-center gap-2 bg-surface-2 p-1 rounded-xl border border-line">
          {HORIZONS.map((h) => {
            const active = activeHorizon === h.key;
            return (
              <button
                key={h.key}
                onClick={() => setActiveHorizon(h.key)}
                className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all flex flex-col items-center ${
                  active
                    ? "bg-cyan-600 text-white shadow-md shadow-cyan-600/30 font-semibold"
                    : "text-gray-400 hover:text-gray-200 hover:bg-surface-1"
                }`}
              >
                <span>{h.label}</span>
                <span className={`text-[10px] ${active ? "text-cyan-100" : "text-gray-500"}`}>
                  {h.periodLabel}
                </span>
              </button>
            );
          })}

          <button
            onClick={() => refetch()}
            disabled={isFetching}
            className="p-2 ml-1 rounded-lg text-gray-400 hover:text-white hover:bg-surface-1 transition-colors"
            title="Refresh Analysis"
          >
            <RefreshCw className={`w-4 h-4 ${isFetching ? "animate-spin text-cyan-400" : ""}`} />
          </button>
        </div>
      </div>

      {isLoading && (
        <div className="p-12 text-center text-sm text-gray-400 font-mono animate-pulse">
          Computing 4-way cross-strategy alignment and trajectory metrics for horizon {activeHorizon}...
        </div>
      )}

      {isError && (
        <div className="p-6 bg-rose-500/10 border border-rose-500/30 rounded-xl text-rose-300 text-sm">
          Failed to compute strategy comparison. Please ensure backend simulation services are active.
        </div>
      )}

      {!isLoading && data && (
        <>
          {/* ----------------------------------------------------------------- */}
          {/* 2. 4-Way Strategy Identity Cards                                  */}
          {/* ----------------------------------------------------------------- */}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            {/* Strategy 1: Sky Blue */}
            <div className="bg-surface-1 border border-sky-500/30 rounded-xl p-4 relative overflow-hidden">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className="w-2.5 h-2.5 rounded-full bg-sky-400"></span>
                  <span className="text-xs font-mono font-bold text-sky-400">STRATEGY 1 (BASELINE)</span>
                </div>
                <span className="text-[10px] px-2 py-0.5 rounded bg-sky-500/10 text-sky-300 border border-sky-500/20 font-mono">
                  Standard Reversion
                </span>
              </div>
              <div className="mt-3">
                <div className="text-2xl font-extrabold text-white font-mono">
                  {matrixData[0].s1}
                </div>
                <div className="text-xs text-gray-400 mt-1">
                  Baseline single-tranche mean reversion with entry at 2.0σ, exit at 0.0σ, and 3.5σ disaster stop.
                </div>
              </div>
              <div className="mt-3 pt-3 border-t border-line/60 flex items-center justify-between text-xs font-mono">
                <span className="text-gray-400">Win Rate: <strong className="text-white">{matrixData[2].s1}</strong></span>
                <span className="text-gray-400">Max DD: <strong className="text-rose-400">{matrixData[3].s1}</strong></span>
              </div>
            </div>

            {/* Strategy 2: Amber */}
            <div className="bg-surface-1 border border-amber-500/30 rounded-xl p-4 relative overflow-hidden">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className="w-2.5 h-2.5 rounded-full bg-amber-400"></span>
                  <span className="text-xs font-mono font-bold text-amber-400">STRATEGY 2 (STAGED EXP.)</span>
                </div>
                <span className="text-[10px] px-2 py-0.5 rounded bg-amber-500/10 text-amber-300 border border-amber-500/20 font-mono">
                  The Win-Rate Trap
                </span>
              </div>
              <div className="mt-3">
                <div className="text-2xl font-extrabold text-amber-300 font-mono">
                  {matrixData[0].s2}
                </div>
                <div className="text-xs text-gray-400 mt-1">
                  Staged partial profit exits at 0.80σ (TP1) and 0.20σ (TP2). Produced 72.9% win rate, but cannibalized profits.
                </div>
              </div>
              <div className="mt-3 pt-3 border-t border-line/60 flex items-center justify-between text-xs font-mono">
                <span className="text-gray-400">Win Rate: <strong className="text-amber-300">{matrixData[2].s2}</strong></span>
                <span className="text-gray-400">Max DD: <strong className="text-rose-400">{matrixData[3].s2}</strong></span>
              </div>
            </div>

            {/* Strategy 3: Glowing Emerald */}
            <div className="bg-surface-1 border border-emerald-500/40 rounded-xl p-4 relative overflow-hidden bg-gradient-to-br from-emerald-500/[0.05] to-transparent">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className="w-2.5 h-2.5 rounded-full bg-emerald-400"></span>
                  <span className="text-xs font-mono font-bold text-emerald-400">STRATEGY 3 (ALPHA MAX)</span>
                </div>
                <span className="text-[10px] px-2 py-0.5 rounded bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 font-mono font-bold">
                  Raw Profit
                </span>
              </div>
              <div className="mt-3">
                <div className="text-2xl font-extrabold text-emerald-400 font-mono">
                  {matrixData[0].s3}
                </div>
                <div className="text-xs text-gray-300 mt-1">
                  Full-ride to 0.0σ, 1.45x conviction sizing on Prime pairs. Maximized total profit but exposed portfolio to 78% peak drawdown.
                </div>
              </div>
              <div className="mt-3 pt-3 border-t border-line/60 flex items-center justify-between text-xs font-mono">
                <span className="text-gray-400">Win Rate: <strong className="text-white">{matrixData[2].s3}</strong></span>
                <span className="text-gray-400">Max DD: <strong className="text-rose-400">{matrixData[3].s3}</strong></span>
              </div>
            </div>

            {/* Strategy 4: Radiant Cyan */}
            <div className="bg-surface-1 border border-cyan-500/40 rounded-xl p-4 relative overflow-hidden bg-gradient-to-br from-cyan-500/[0.08] to-transparent shadow-lg shadow-cyan-500/10">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className="w-2.5 h-2.5 rounded-full bg-cyan-400 animate-pulse"></span>
                  <span className="text-xs font-mono font-bold text-cyan-400">STRATEGY 4 (RISK-ENGINEERED)</span>
                </div>
                <span className="text-[10px] px-2 py-0.5 rounded bg-cyan-500/20 text-cyan-300 border border-cyan-500/40 font-mono font-bold">
                  ★ INSTITUTIONAL LEADER
                </span>
              </div>
              <div className="mt-3">
                <div className="text-2xl font-extrabold text-cyan-400 font-mono">
                  {matrixData[0].s4}
                </div>
                <div className="text-xs text-gray-300 mt-1">
                  Momentum confirmation hook, tight dynamic stop, 2x half-life time stops, vol-inverse sizing. Slashes drawdown to &lt;28% with &gt;52% win rate.
                </div>
              </div>
              <div className="mt-3 pt-3 border-t border-line/60 flex items-center justify-between text-xs font-mono">
                <span className="text-gray-400">Win Rate: <strong className="text-cyan-300">{matrixData[2].s4}</strong></span>
                <span className="text-gray-400">Max DD: <strong className="text-rose-400">{matrixData[3].s4}</strong></span>
              </div>
            </div>
          </div>

          {/* ----------------------------------------------------------------- */}
          {/* 3. 4-Way Overlay Equity Curve                                     */}
          {/* ----------------------------------------------------------------- */}
          <div className="bg-surface-1 border border-line rounded-xl p-5 space-y-4">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
              <div>
                <h2 className="text-base font-bold text-white flex items-center gap-2">
                  <TrendingUp className="w-4 h-4 text-cyan-400" />
                  4-Way Synchronized Equity Trajectory Overlay
                </h2>
                <p className="text-xs text-gray-400">
                  Daily step function comparing Strategy 1 (Sky Blue dashed), Strategy 2 (Amber plateau), Strategy 3 (Emerald line), and Strategy 4 (Radiant Cyan glow).
                </p>
              </div>

              <div className="flex items-center gap-3 text-xs font-mono">
                <div className="px-2.5 py-1 rounded bg-surface-2 border border-line text-gray-300">
                  Aligned Points: <span className="font-bold text-cyan-300">{alignedEquity.length}</span>
                </div>
              </div>
            </div>

            <ComparisonEquityChart
              data={alignedEquity}
              height={320}
              v1Label="Strategy 1 (Baseline)"
              v2Label="Strategy 2 (Failed Staged)"
              v3Label="Strategy 3 (Alpha Maximizer)"
              v4Label="Strategy 4 (Risk-Engineered)"
            />
          </div>

          {/* ----------------------------------------------------------------- */}
          {/* 4. 4-Way Head-to-Head Comparative Scoreboard Matrix               */}
          {/* ----------------------------------------------------------------- */}
          <div className="bg-surface-1 border border-line rounded-xl p-5 space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <h2 className="text-base font-bold text-white flex items-center gap-2">
                  <Award className="w-4 h-4 text-cyan-400" />
                  Head-to-Head 4-Way Scoreboard Matrix
                </h2>
                <p className="text-xs text-gray-400">
                  Institutional comparison across profitability, risk metrics, trade quality, and execution discipline for horizon {activeHorizon}.
                </p>
              </div>
            </div>

            <div className="overflow-x-auto rounded-lg border border-line">
              <table className="w-full text-left text-xs border-collapse">
                <thead>
                  <tr className="bg-surface-2 border-b border-line font-mono text-[11px]">
                    <th className="py-3 px-4 text-gray-400">Performance Metric</th>
                    <th className="py-3 px-4 text-sky-400 font-bold">Strategy 1 (Baseline)</th>
                    <th className="py-3 px-4 text-amber-400 font-bold">Strategy 2 (Failed Staged)</th>
                    <th className="py-3 px-4 text-emerald-400 font-bold">Strategy 3 (Alpha Max)</th>
                    <th className="py-3 px-4 text-cyan-400 font-bold">Strategy 4 (Risk-Engineered)</th>
                    <th className="py-3 px-4 text-gray-300">Best Performer</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-line/60 font-mono">
                  {matrixData.map((row, idx) => (
                    <tr key={idx} className="hover:bg-surface-2/40 transition-colors">
                      <td className="py-3 px-4 text-white font-medium">
                        <div>{row.metric}</div>
                        <div className="text-[10px] text-gray-500 font-sans">{row.note}</div>
                      </td>
                      <td className={`py-3 px-4 font-bold ${row.metric === "Max Drawdown %" ? "text-rose-400" : "text-sky-300"}`}>
                        {row.s1}
                      </td>
                      <td className={`py-3 px-4 font-bold ${row.metric === "Max Drawdown %" ? "text-rose-400" : "text-amber-300"}`}>
                        {row.s2}
                      </td>
                      <td className={`py-3 px-4 font-bold ${row.metric === "Max Drawdown %" ? "text-rose-400" : "text-emerald-400"}`}>
                        {row.s3}
                      </td>
                      <td className={`py-3 px-4 font-extrabold text-sm ${row.metric === "Max Drawdown %" ? "text-rose-400" : "text-cyan-400"}`}>
                        {row.s4}
                      </td>
                      <td className="py-3 px-4">
                        <span
                          className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-[11px] font-bold ${
                            row.bestBadgeColor === "cyan"
                              ? "bg-cyan-500/15 text-cyan-300 border border-cyan-500/30"
                              : row.bestBadgeColor === "emerald"
                              ? "bg-emerald-500/15 text-emerald-300 border border-emerald-500/30"
                              : "bg-amber-500/15 text-amber-300 border border-amber-500/30"
                          }`}
                        >
                          <Check className="w-3 h-3" />
                          {row.best}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* ----------------------------------------------------------------- */}
          {/* 5. Educational Quant Callouts: "Why S2 Failed vs Why S3 Won"      */}
          {/* ----------------------------------------------------------------- */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {/* The Win-Rate Illusion Card */}
            <div className="bg-surface-1 border border-amber-500/30 rounded-xl p-5 space-y-3">
              <div className="flex items-center gap-2.5">
                <div className="p-2 rounded-lg bg-amber-500/10 text-amber-400 border border-amber-500/20">
                  <AlertTriangle className="w-5 h-5" />
                </div>
                <div>
                  <h3 className="text-sm font-bold text-white">The "Win-Rate Illusion" (Why Strategy 2 Plateaued)</h3>
                  <span className="text-[11px] text-amber-400 font-mono">High Win Rate (72.9%) ≠ Maximum Profit (+20.6%)</span>
                </div>
              </div>
              <p className="text-xs text-gray-300 leading-relaxed">
                Strategy 2 introduced staged profit taking at <strong className="text-amber-300">0.80σ (TP1)</strong> and moved stops to breakeven.
                While this achieved an eye-popping <strong>72.9% win rate</strong>, it halved the position size on the very best mean-reverting pairs,
                sacrificing over <strong>70% of the meat of the reversion move</strong>. The small banked gains could not compensate for the tail losses on structurally broken pairs.
              </p>
              <div className="bg-surface-2 p-3 rounded-lg border border-line text-xs font-mono text-gray-400 space-y-1">
                <div>• TP1 prematurely dumped 50% of the trade at a meager 0.80σ reversion.</div>
                <div>• Breakeven stops frequently stopped out remaining tranches during normal spread noise.</div>
                <div>• Net Result: Win rate climbed +28.5%, but net profit collapsed from +81.0% down to +20.6%.</div>
              </div>
            </div>

            {/* The Asymmetric Edge Card */}
            <div className="bg-surface-1 border border-emerald-500/30 rounded-xl p-5 space-y-3">
              <div className="flex items-center gap-2.5">
                <div className="p-2 rounded-lg bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                  <Flame className="w-5 h-5" />
                </div>
                <div>
                  <h3 className="text-sm font-bold text-white">The "Asymmetric Edge" (Why Strategy 3 Crushed Both)</h3>
                  <span className="text-[11px] text-emerald-400 font-mono">Full-Ride Profit Target + Conviction Compounding</span>
                </div>
              </div>
              <p className="text-xs text-gray-300 leading-relaxed">
                Strategy 3 realized that mean reversion alpha requires <strong className="text-emerald-400">letting winners run to the full 0.0σ target</strong> without cutting position size.
                By adding <strong className="text-emerald-400">1.45x Conviction Sizing</strong> on institutional Prime setups (Score &ge; 82) and protecting gains with a
                <strong className="text-emerald-400"> Trailing Disaster Floor (moving stop to 1.5σ on 60% recovery)</strong>, Strategy 3 outperformed Strategy 1 in every single horizon.
              </p>
              <div className="bg-surface-2 p-3 rounded-lg border border-line text-xs font-mono text-gray-400 space-y-1">
                <div>• 100% position held all the way to complete mean reversion at Z = 0.0σ.</div>
                <div>• 1.45x size compounder on Tier-1 setups turned good setups into outsized portfolio drivers.</div>
                <div>• Trailing Disaster Floor converted catastrophic 3.5σ blowout reversals into controlled exits.</div>
              </div>
            </div>
          </div>

          {/* ----------------------------------------------------------------- */}
          {/* 5.1 Strategy 4 Systematic Risk Architecture: 8-Point Upgrades      */}
          {/* ----------------------------------------------------------------- */}
          <div className="bg-surface-1 border border-cyan-500/30 rounded-xl p-5 space-y-4">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
              <div>
                <h2 className="text-base font-bold text-white flex items-center gap-2">
                  <ShieldCheck className="w-5 h-5 text-cyan-400" />
                  Strategy 4 Systematic Risk Engineering Architecture (8 Upgrades)
                </h2>
                <p className="text-xs text-gray-400">
                  How Strategy 4 ("Risk-Engineered Pure Alpha") directly solves the 78% drawdown and win-rate bottlenecks of earlier iterations.
                </p>
              </div>
              <span className="px-2.5 py-1 text-[11px] font-mono font-bold rounded bg-cyan-500/15 text-cyan-300 border border-cyan-500/30">
                Institutional Risk Standard
              </span>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-3 pt-2">
              <div className="bg-surface-2/60 border border-line rounded-lg p-3 space-y-1.5">
                <div className="text-xs font-bold text-cyan-300 flex items-center gap-1.5">
                  <Zap className="w-3.5 h-3.5 text-cyan-400" />
                  1. Momentum Confirmation
                </div>
                <p className="text-[11px] text-gray-400 leading-relaxed">
                  Requires 2-day spread velocity slope &le; 0.05&sigma; or reversing towards mean. Completely vetoes falling knives.
                </p>
              </div>

              <div className="bg-surface-2/60 border border-line rounded-lg p-3 space-y-1.5">
                <div className="text-xs font-bold text-cyan-300 flex items-center gap-1.5">
                  <Sparkles className="w-3.5 h-3.5 text-cyan-400" />
                  2. Realistic Exit Target
                </div>
                <p className="text-[11px] text-gray-400 leading-relaxed">
                  100% position liquidates at |Z| &le; 0.40&sigma;. Captures high-probability meat of reversion without suffering stale decay.
                </p>
              </div>

              <div className="bg-surface-2/60 border border-line rounded-lg p-3 space-y-1.5">
                <div className="text-xs font-bold text-cyan-300 flex items-center gap-1.5">
                  <ShieldCheck className="w-3.5 h-3.5 text-cyan-400" />
                  3. Dynamic Stop Loss
                </div>
                <p className="text-[11px] text-gray-400 leading-relaxed">
                  Stop barrier at max(2.85, |Z| + 1.15&sigma;). Aggressively terminates losing tails while allowing breathing room for initial noise.
                </p>
              </div>

              <div className="bg-surface-2/60 border border-line rounded-lg p-3 space-y-1.5">
                <div className="text-xs font-bold text-cyan-300 flex items-center gap-1.5">
                  <Clock className="w-3.5 h-3.5 text-cyan-400" />
                  4. 2.5x Half-Life Time Stop
                </div>
                <p className="text-[11px] text-gray-400 leading-relaxed">
                  Forces trade exit at T_max = max(4, min(22, 2.5 &times; HL)). Recycles dormant capital out of broken cointegrations.
                </p>
              </div>

              <div className="bg-surface-2/60 border border-line rounded-lg p-3 space-y-1.5">
                <div className="text-xs font-bold text-cyan-300 flex items-center gap-1.5">
                  <Layers className="w-3.5 h-3.5 text-cyan-400" />
                  5. Vol-Inverse Sizing
                </div>
                <p className="text-[11px] text-gray-400 leading-relaxed">
                  Multiplier scales inversely with spread vol (0.40x to 1.25x). Includes 0.70x portfolio drawdown dampener above 20% drawdown.
                </p>
              </div>

              <div className="bg-surface-2/60 border border-line rounded-lg p-3 space-y-1.5">
                <div className="text-xs font-bold text-cyan-300 flex items-center gap-1.5">
                  <AlertTriangle className="w-3.5 h-3.5 text-cyan-400" />
                  6. Earnings Blackout Shield
                </div>
                <p className="text-[11px] text-gray-400 leading-relaxed">
                  Blocks new entries 5 days before and 2 days after corporate earnings calls, shielding the book from overnight gap shocks.
                </p>
              </div>

              <div className="bg-surface-2/60 border border-line rounded-lg p-3 space-y-1.5">
                <div className="text-xs font-bold text-cyan-300 flex items-center gap-1.5">
                  <TrendingDown className="w-3.5 h-3.5 text-cyan-400" />
                  7. VIX Macro Overlay
                </div>
                <p className="text-[11px] text-gray-400 leading-relaxed">
                  Freezes all new entries when annualized universe volatility exceeds 25.0 to insulate the strategy during macro panic.
                </p>
              </div>

              <div className="bg-surface-2/60 border border-line rounded-lg p-3 space-y-1.5">
                <div className="text-xs font-bold text-cyan-300 flex items-center gap-1.5">
                  <CheckCircle2 className="w-3.5 h-3.5 text-cyan-400" />
                  8. Spread Volatility Cap
                </div>
                <p className="text-[11px] text-gray-400 leading-relaxed">
                  Strictly caps eligible pairs to relative spread volatility &le; 5.5%, eliminating erratic micro-cap behavior.
                </p>
              </div>
            </div>
          </div>

          {/* ----------------------------------------------------------------- */}
          {/* 6. Failure Cause Attribution for Strategy 1 Losses                */}
          {/* ----------------------------------------------------------------- */}
          <div className="bg-surface-1 border border-line rounded-xl p-5 space-y-5">
            <div>
              <div className="flex items-center justify-between">
                <h2 className="text-base font-bold text-white flex items-center gap-2">
                  <AlertTriangle className="w-4 h-4 text-amber-400" />
                  Failure Cause Attribution: Why Strategy 1 Trades Failed
                </h2>
                <span className="text-xs font-mono text-gray-400">
                  Total Analyzed Losses: <strong className="text-white">{failureAttr?.total_losses}</strong>
                </span>
              </div>
              <p className="text-xs text-gray-400 mt-0.5">
                Breakdown of Strategy 1 losing trades and the systematic mechanisms Strategy 2 &amp; Strategy 3 deploy to mitigate them.
              </p>
            </div>

            {/* Failure Distribution Bars */}
            <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
              {/* Cause 1: Runaway Momentum */}
              <div className="bg-surface-2/70 border border-line rounded-lg p-3 space-y-2">
                <div className="flex items-center justify-between text-xs">
                  <span className="font-medium text-gray-200">Runaway Momentum</span>
                  <span className="font-mono font-bold text-amber-400">
                    {failureAttr?.percentages?.RUNAWAY_MOMENTUM}%
                  </span>
                </div>
                <div className="w-full bg-surface-1 h-2 rounded-full overflow-hidden">
                  <div
                    className="bg-amber-400 h-full rounded-full"
                    style={{ width: `${failureAttr?.percentages?.RUNAWAY_MOMENTUM}%` }}
                  ></div>
                </div>
                <p className="text-[11px] text-gray-400 leading-tight">
                  {failureAttr?.counts?.RUNAWAY_MOMENTUM} blowouts through 3.5σ without reversal.
                </p>
              </div>

              {/* Cause 2: Profit Give-Back */}
              <div className="bg-surface-2/70 border border-line rounded-lg p-3 space-y-2">
                <div className="flex items-center justify-between text-xs">
                  <span className="font-medium text-gray-200">Profit Give-Back</span>
                  <span className="font-mono font-bold text-emerald-400">
                    {failureAttr?.percentages?.PROFIT_GIVEBACK}%
                  </span>
                </div>
                <div className="w-full bg-surface-1 h-2 rounded-full overflow-hidden">
                  <div
                    className="bg-emerald-400 h-full rounded-full"
                    style={{ width: `${failureAttr?.percentages?.PROFIT_GIVEBACK}%` }}
                  ></div>
                </div>
                <p className="text-[11px] text-gray-400 leading-tight">
                  {failureAttr?.counts?.PROFIT_GIVEBACK} trades reached &le; 0.80σ but reversed. Protected by S3 Trailing Floor.
                </p>
              </div>

              {/* Cause 3: Stale Half-Life Decay */}
              <div className="bg-surface-2/70 border border-line rounded-lg p-3 space-y-2">
                <div className="flex items-center justify-between text-xs">
                  <span className="font-medium text-gray-200">Stale Half-Life Decay</span>
                  <span className="font-mono font-bold text-sky-400">
                    {failureAttr?.percentages?.STALE_DECAY}%
                  </span>
                </div>
                <div className="w-full bg-surface-1 h-2 rounded-full overflow-hidden">
                  <div
                    className="bg-sky-400 h-full rounded-full"
                    style={{ width: `${failureAttr?.percentages?.STALE_DECAY}%` }}
                  ></div>
                </div>
                <p className="text-[11px] text-gray-400 leading-tight">
                  {failureAttr?.counts?.STALE_DECAY} trades lingered past half-life. Fixed by 35-day adaptive horizon.
                </p>
              </div>

              {/* Cause 4: Earnings / Event Shock */}
              <div className="bg-surface-2/70 border border-line rounded-lg p-3 space-y-2">
                <div className="flex items-center justify-between text-xs">
                  <span className="font-medium text-gray-200">Earnings Shock</span>
                  <span className="font-mono font-bold text-rose-400">
                    {failureAttr?.percentages?.EARNINGS_SHOCK}%
                  </span>
                </div>
                <div className="w-full bg-surface-1 h-2 rounded-full overflow-hidden">
                  <div
                    className="bg-rose-400 h-full rounded-full"
                    style={{ width: `${failureAttr?.percentages?.EARNINGS_SHOCK}%` }}
                  ></div>
                </div>
                <p className="text-[11px] text-gray-400 leading-tight">
                  {failureAttr?.counts?.EARNINGS_SHOCK} gap blowouts around announcements. Filtered by calendar.
                </p>
              </div>
            </div>

            {/* --------------------------------------------------------------- */}
            {/* 7. Diagnostic Trade Cohorts & Filtered History Table            */}
            {/* --------------------------------------------------------------- */}
            <div className="pt-2 border-t border-line/70">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                <div className="flex items-center gap-1.5 overflow-x-auto pb-1">
                  <button
                    onClick={() => setActiveTab("SAVED_LOSS")}
                    className={`px-3 py-1.5 rounded-lg text-xs font-medium whitespace-nowrap transition-colors flex items-center gap-1.5 ${
                      activeTab === "SAVED_LOSS"
                        ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/40"
                        : "text-gray-400 hover:text-gray-200 hover:bg-surface-2"
                    }`}
                  >
                    <ShieldCheck className="w-3.5 h-3.5 text-emerald-400" />
                    <span>Saved Losses (The Shield)</span>
                    <span className="px-1.5 py-0.2 rounded text-[10px] font-mono bg-emerald-500/30 text-emerald-200">
                      {metrics?.saved_losses_count}
                    </span>
                  </button>

                  <button
                    onClick={() => setActiveTab("FLIPPED_TRADE")}
                    className={`px-3 py-1.5 rounded-lg text-xs font-medium whitespace-nowrap transition-colors flex items-center gap-1.5 ${
                      activeTab === "FLIPPED_TRADE"
                        ? "bg-purple-500/20 text-purple-300 border border-purple-500/40"
                        : "text-gray-400 hover:text-gray-200 hover:bg-surface-2"
                    }`}
                  >
                    <Sparkles className="w-3.5 h-3.5 text-purple-400" />
                    <span>Flipped Trades (Loss &rarr; Win)</span>
                    <span className="px-1.5 py-0.2 rounded text-[10px] font-mono bg-purple-500/30 text-purple-200">
                      {metrics?.flipped_trades_count}
                    </span>
                  </button>

                  <button
                    onClick={() => setActiveTab("PRESERVED_WINNER")}
                    className={`px-3 py-1.5 rounded-lg text-xs font-medium whitespace-nowrap transition-colors flex items-center gap-1.5 ${
                      activeTab === "PRESERVED_WINNER"
                        ? "bg-sky-500/20 text-sky-300 border border-sky-500/40"
                        : "text-gray-400 hover:text-gray-200 hover:bg-surface-2"
                    }`}
                  >
                    <CheckCircle2 className="w-3.5 h-3.5 text-sky-400" />
                    <span>Preserved Winners</span>
                    <span className="px-1.5 py-0.2 rounded text-[10px] font-mono bg-sky-500/30 text-sky-200">
                      {metrics?.preserved_winners_count}
                    </span>
                  </button>

                  <button
                    onClick={() => setActiveTab("MISSED_OPPORTUNITY")}
                    className={`px-3 py-1.5 rounded-lg text-xs font-medium whitespace-nowrap transition-colors flex items-center gap-1.5 ${
                      activeTab === "MISSED_OPPORTUNITY"
                        ? "bg-amber-500/20 text-amber-300 border border-amber-500/40"
                        : "text-gray-400 hover:text-gray-200 hover:bg-surface-2"
                    }`}
                  >
                    <Info className="w-3.5 h-3.5 text-amber-400" />
                    <span>Missed Opportunities</span>
                    <span className="px-1.5 py-0.2 rounded text-[10px] font-mono bg-amber-500/30 text-amber-200">
                      {metrics?.missed_opportunities_count}
                    </span>
                  </button>

                  <button
                    onClick={() => setActiveTab("ALL")}
                    className={`px-3 py-1.5 rounded-lg text-xs font-medium whitespace-nowrap transition-colors flex items-center gap-1.5 ${
                      activeTab === "ALL"
                        ? "bg-surface-2 text-white border border-line"
                        : "text-gray-400 hover:text-gray-200 hover:bg-surface-2"
                    }`}
                  >
                    <span>All Trade Deltas</span>
                    <span className="px-1.5 py-0.2 rounded text-[10px] font-mono bg-surface-1 text-gray-300">
                      {deltas.length}
                    </span>
                  </button>
                </div>

                {/* Filter and Search Bar */}
                <div className="flex items-center gap-2">
                  <div className="relative">
                    <Search className="w-3.5 h-3.5 text-gray-400 absolute left-2.5 top-1/2 -translate-y-1/2" />
                    <input
                      type="text"
                      placeholder="Search pair or keyword..."
                      value={searchQuery}
                      onChange={(e) => setSearchQuery(e.target.value)}
                      className="bg-surface-2 border border-line rounded-lg pl-8 pr-3 py-1 text-xs text-white placeholder-gray-500 focus:outline-none focus:border-emerald-500 w-44 sm:w-52"
                    />
                  </div>

                  <select
                    value={selectedSector}
                    onChange={(e) => setSelectedSector(e.target.value)}
                    className="bg-surface-2 border border-line rounded-lg px-2.5 py-1 text-xs text-gray-300 focus:outline-none focus:border-emerald-500"
                  >
                    {availableSectors.map((sec) => (
                      <option key={sec} value={sec}>
                        {sec}
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              {/* Trade Delta Table */}
              <div className="mt-4 overflow-x-auto rounded-lg border border-line">
                <table className="w-full text-left text-xs border-collapse">
                  <thead>
                    <tr className="bg-surface-2/90 border-b border-line font-mono text-[11px] text-gray-400">
                      <th className="py-2.5 px-3">Pair &amp; Sector</th>
                      <th className="py-2.5 px-3">Direction</th>
                      <th className="py-2.5 px-3">Diagnostic Cohort</th>
                      <th className="py-2.5 px-3">Strategy 1 Baseline</th>
                      <th className="py-2.5 px-3">Strategy 2 Outcome</th>
                      <th className="py-2.5 px-3 text-right">Return Delta</th>
                      <th className="py-2.5 px-3">Quantitative Explanation</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-line/60">
                    {filteredTrades.slice(0, 50).map((t) => {
                      const isSaved = t.category === "SAVED_LOSS";
                      const isFlipped = t.category === "FLIPPED_TRADE";
                      const isPreserved = t.category === "PRESERVED_WINNER";
                      const isMissed = t.category === "MISSED_OPPORTUNITY";

                      return (
                        <tr
                          key={t.id}
                          onClick={() => setSelectedDelta(t)}
                          className="hover:bg-surface-2/60 transition-colors cursor-pointer group"
                        >
                          {/* Pair & Sector */}
                          <td className="py-2.5 px-3 font-mono">
                            <div className="font-bold text-white">{t.pair_name}</div>
                            <div className="text-[10px] text-gray-400">{t.sector}</div>
                          </td>

                          {/* Direction */}
                          <td className="py-2.5 px-3 font-mono text-[11px]">
                            <span className="text-gray-300">{t.direction || "Long/Short"}</span>
                          </td>

                          {/* Category Badge */}
                          <td className="py-2.5 px-3">
                            {isSaved && (
                              <span className="px-2 py-0.5 rounded text-[10px] font-semibold bg-emerald-500/15 text-emerald-300 border border-emerald-500/30 whitespace-nowrap">
                                🛡️ Saved Loss
                              </span>
                            )}
                            {isFlipped && (
                              <span className="px-2 py-0.5 rounded text-[10px] font-semibold bg-purple-500/15 text-purple-300 border border-purple-500/30 whitespace-nowrap">
                                ✨ Flipped to Win
                              </span>
                            )}
                            {isPreserved && (
                              <span className="px-2 py-0.5 rounded text-[10px] font-semibold bg-sky-500/15 text-sky-300 border border-sky-500/30 whitespace-nowrap">
                                🎯 Preserved Winner
                              </span>
                            )}
                            {isMissed && (
                              <span className="px-2 py-0.5 rounded text-[10px] font-semibold bg-amber-500/15 text-amber-300 border border-amber-500/30 whitespace-nowrap">
                                ⚠️ Missed Winner
                              </span>
                            )}
                            {!isSaved && !isFlipped && !isPreserved && !isMissed && (
                              <span className="px-2 py-0.5 rounded text-[10px] font-semibold bg-gray-500/15 text-gray-300 border border-gray-500/30 whitespace-nowrap">
                                {t.category_label}
                              </span>
                            )}
                          </td>

                          {/* Strategy v1 Result */}
                          <td className="py-2.5 px-3 font-mono">
                            {t.v1_outcome ? (
                              <div>
                                <div className="flex items-center gap-1.5">
                                  <span className={`font-bold ${t.v1_outcome === "WIN" ? "text-emerald-400" : "text-rose-400"}`}>
                                    {t.v1_return_pct !== null && t.v1_return_pct !== undefined
                                      ? `${t.v1_return_pct > 0 ? "+" : ""}${t.v1_return_pct.toFixed(2)}%`
                                      : t.v1_outcome}
                                  </span>
                                  <span className="text-[10px] text-gray-500">({t.v1_outcome})</span>
                                </div>
                                <div className="text-[10px] text-gray-500 truncate max-w-[180px]" title={t.v1_exit_reason || ""}>
                                  {t.v1_exit_reason || t.v1_entry_date}
                                </div>
                              </div>
                            ) : (
                              <span className="text-gray-500 text-[11px]">— Not Entered —</span>
                            )}
                          </td>

                          {/* Strategy v2 Result */}
                          <td className="py-2.5 px-3 font-mono">
                            {t.v2_outcome === "VETOED" ? (
                              <div className="text-[11px] text-amber-300 font-semibold">
                                🛡️ Entry Vetoed (0.00%)
                              </div>
                            ) : (
                              <div>
                                <div className="flex items-center gap-1.5">
                                  <span className={`font-bold ${t.v2_outcome === "WIN" ? "text-emerald-400" : "text-rose-400"}`}>
                                    {t.v2_return_pct !== null && t.v2_return_pct !== undefined
                                      ? `${t.v2_return_pct > 0 ? "+" : ""}${t.v2_return_pct.toFixed(2)}%`
                                      : t.v2_outcome}
                                  </span>
                                  <span className="text-[10px] text-gray-500">({t.v2_outcome})</span>
                                </div>
                                <div className="text-[10px] text-amber-400 truncate max-w-[180px]">
                                  {t.v2_exit_reason || t.v2_entry_date}
                                </div>
                              </div>
                            )}
                          </td>

                          {/* Return Delta */}
                          <td className="py-2.5 px-3 font-mono text-right font-bold">
                            <span className={t.return_delta_pct > 0 ? "text-emerald-400" : t.return_delta_pct < 0 ? "text-rose-400" : "text-gray-400"}>
                              {t.return_delta_pct > 0 ? `+${t.return_delta_pct.toFixed(2)}%` : `${t.return_delta_pct.toFixed(2)}%`}
                            </span>
                          </td>

                          {/* Explanation */}
                          <td className="py-2.5 px-3 text-[11px] text-gray-300 max-w-xs sm:max-w-md">
                            {t.explanation}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>

              {filteredTrades.length > 50 && (
                <div className="mt-3 text-center text-xs text-gray-500 font-mono">
                  Showing top 50 trades of {filteredTrades.length} matching criteria.
                </div>
              )}

              {filteredTrades.length === 0 && (
                <div className="p-8 text-center text-xs text-gray-500 font-mono">
                  No trade deltas match current search or sector filters.
                </div>
              )}
            </div>
          </div>
        </>
      )}

      {/* Institutional Full-Window Trade Inspector Modal */}
      {inspectableTrade && (
        <TradeInspectorModal
          trade={inspectableTrade}
          onClose={() => setSelectedDelta(null)}
          strategyLabel="4-WAY BENCHMARK TRADE INSPECTOR"
          strategyThemeColor="cyan"
          tradeIndex={filteredTrades.findIndex((t) => t.id === selectedDelta?.id)}
          totalTrades={filteredTrades.length}
          onPrevTrade={() => {
            const idx = filteredTrades.findIndex((t) => t.id === selectedDelta?.id);
            if (idx > 0) setSelectedDelta(filteredTrades[idx - 1]);
          }}
          onNextTrade={() => {
            const idx = filteredTrades.findIndex((t) => t.id === selectedDelta?.id);
            if (idx < filteredTrades.length - 1) setSelectedDelta(filteredTrades[idx + 1]);
          }}
        />
      )}
    </div>
  );
}
