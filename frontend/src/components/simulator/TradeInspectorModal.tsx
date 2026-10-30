import React, { useState, useMemo, useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  X,
  ChevronLeft,
  ChevronRight,
  TrendingUp,
  TrendingDown,
  Calendar,
  Clock,
  ShieldAlert,
  ShieldCheck,
  CheckCircle2,
  Target,
  Activity,
  Table as TableIcon,
  LineChart,
  Split,
  Zap,
  ArrowRight,
  DollarSign,
  Percent,
} from "lucide-react";
import { api } from "../../lib/api";
import { TradeChartDataResponse, TradeChartBar } from "../../lib/simulatorTypes";

export interface GenericInspectableTrade {
  id?: string;
  pair_name: string;
  ticker_a?: string;
  ticker_b?: string;
  entry_date: string;
  exit_date?: string | null;
  outcome?: string;
  realized_return_pct?: number;
  raw_return_pct?: number;
  holding_days?: number;
  direction?: string | null;
  direction_label?: string | null;
  sector?: string | null;
  entry_z?: number;
  exit_z?: number | null;
  entry_price_a?: number | null;
  entry_price_b?: number | null;
  exit_price_a?: number | null;
  exit_price_b?: number | null;
  status_reason?: string | null;
  exit_reason?: string | null;
  hedge_ratio?: number;
  spread_mean?: number;
  spread_std?: number;
  sizing_multiplier?: number;
  spread_vol_pct?: number;
  half_life_days?: number;
  max_holding_limit?: number;
  composite_score?: number;
  trajectory?: Array<{
    date: string;
    days_elapsed: number;
    price_a: number;
    price_b: number;
    spread: number;
    z_score: number;
  }>;
}

interface TradeInspectorModalProps {
  trade: GenericInspectableTrade | null;
  onClose: () => void;
  strategyLabel?: string;
  strategyThemeColor?: "cyan" | "emerald" | "amber" | "sky";
  onPrevTrade?: () => void;
  onNextTrade?: () => void;
  tradeIndex?: number;
  totalTrades?: number;
}

type ModalTab = "stacked" | "prices" | "spread" | "ledger";

export default function TradeInspectorModal({
  trade,
  onClose,
  strategyLabel = "Strategy Trade Inspector",
  strategyThemeColor = "cyan",
  onPrevTrade,
  onNextTrade,
  tradeIndex,
  totalTrades,
}: TradeInspectorModalProps) {
  const [activeTab, setActiveTab] = useState<ModalTab>("stacked");
  const [hoverIndex, setHoverIndex] = useState<number | null>(null);

  // Parse tickers from pair_name (e.g. "WEC/XEL" -> "WEC", "XEL")
  const { tickerA, tickerB } = useMemo(() => {
    if (!trade) return { tickerA: "", tickerB: "" };
    if (trade.ticker_a && trade.ticker_b) {
      return { tickerA: trade.ticker_a, tickerB: trade.ticker_b };
    }
    const parts = trade.pair_name.split(/[/_-]/);
    return {
      tickerA: parts[0] || "",
      tickerB: parts[1] || "",
    };
  }, [trade]);

  // Handle keyboard shortcuts (Escape, Left, Right)
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        onClose();
      } else if (e.key === "ArrowLeft" && onPrevTrade) {
        onPrevTrade();
      } else if (e.key === "ArrowRight" && onNextTrade) {
        onNextTrade();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [onClose, onPrevTrade, onNextTrade]);

  // Query dual-stock price and spread chart window from backend (T-60 to T_exit+15)
  const { data: chartData, isLoading, error } = useQuery<TradeChartDataResponse>({
    queryKey: [
      "trade-chart",
      tickerA,
      tickerB,
      trade?.entry_date,
      trade?.exit_date,
      trade?.hedge_ratio,
      trade?.spread_mean,
      trade?.spread_std,
    ],
    queryFn: () =>
      api.simulator.tradeChart({
        ticker_a: tickerA,
        ticker_b: tickerB,
        entry_date: trade!.entry_date,
        exit_date: trade?.exit_date,
        pre_days: 60,
        post_days: 15,
        hedge_ratio: trade?.hedge_ratio,
        spread_mean: trade?.spread_mean,
        spread_std: trade?.spread_std,
      }),
    enabled: !!trade && !!tickerA && !!tickerB,
    staleTime: 10 * 60 * 1000,
  });

  const bars = chartData?.bars || [];
  const entryIdx = chartData?.entry_index ?? 0;
  const exitIdx = chartData?.exit_index ?? Math.max(0, bars.length - 1);
  const activeBar = hoverIndex !== null && bars[hoverIndex] ? bars[hoverIndex] : null;

  // Compute exact dual-stock execution prices and individual leg PnL
  const execution = useMemo(() => {
    if (!trade) return null;

    const entryBar = bars[entryIdx];
    const exitBar = bars[exitIdx];

    const entryPriceA = trade.entry_price_a ?? entryBar?.price_a ?? 0;
    const exitPriceA = trade.exit_price_a ?? exitBar?.price_a ?? 0;

    const entryPriceB = trade.entry_price_b ?? entryBar?.price_b ?? 0;
    const exitPriceB = trade.exit_price_b ?? exitBar?.price_b ?? 0;

    // Determine Long/Short side for Stock A and B
    // If direction is LONG_A_SHORT_B or entry_z was negative (spread low -> buy A, sell B):
    const isLongA =
      trade.direction === "LONG_A_SHORT_B" ||
      (trade.direction_label?.toLowerCase().includes(`long ${tickerA.toLowerCase()}`) ?? false) ||
      ((trade.entry_z ?? 0) < 0);

    const roleA: "LONG" | "SHORT" = isLongA ? "LONG" : "SHORT";
    const roleB: "LONG" | "SHORT" = isLongA ? "SHORT" : "LONG";

    const beta = trade.hedge_ratio ?? chartData?.hedge_ratio ?? 1.0;
    const sizingMultiplier = trade.sizing_multiplier ?? 1.0;

    // In cointegrated stat-arb: Spread S = P_A - beta * P_B
    // For 1 unit of A, we trade |beta| units of B
    const weightA = 1.0;
    const weightB = Math.abs(beta);

    // Invested capital for 1 spread unit
    const capitalA = entryPriceA * weightA;
    const capitalB = entryPriceB * weightB;
    const totalInvestedCapital = capitalA + capitalB;

    // Stock A Leg PnL
    const diffDollarA = exitPriceA - entryPriceA;
    const pnlDollarPerShareA = roleA === "LONG" ? diffDollarA : -diffDollarA;
    const pnlDollarWeightedA = pnlDollarPerShareA * weightA;
    const pnlPctA = entryPriceA > 0 ? (pnlDollarPerShareA / entryPriceA) * 100 : 0;

    // Stock B Leg PnL
    const diffDollarB = exitPriceB - entryPriceB;
    const pnlDollarPerShareB = roleB === "LONG" ? diffDollarB : -diffDollarB;
    const pnlDollarWeightedB = pnlDollarPerShareB * weightB;
    const pnlPctB = entryPriceB > 0 ? (pnlDollarPerShareB / entryPriceB) * 100 : 0;

    // Net Spread Unit Dollar Profit and Percentage Return
    const netSpreadDollarPnl = pnlDollarWeightedA + pnlDollarWeightedB;
    const calculatedRawReturnPct = totalInvestedCapital > 0 ? (netSpreadDollarPnl / totalInvestedCapital) * 100 : 0;
    const rawReturnPct = trade.raw_return_pct ?? calculatedRawReturnPct;
    const calculatedRealizedReturnPct = rawReturnPct * sizingMultiplier;
    const realizedReturnPct = trade.realized_return_pct ?? calculatedRealizedReturnPct;
    const isWin = trade.outcome === "WIN" || realizedReturnPct >= 0;

    return {
      tickerA,
      tickerB,
      roleA,
      roleB,
      entryPriceA,
      exitPriceA,
      diffDollarA,
      pnlDollarA: pnlDollarPerShareA,
      pnlDollarWeightedA,
      pnlPctA,
      capitalA,
      weightA,
      entryPriceB,
      exitPriceB,
      diffDollarB,
      pnlDollarB: pnlDollarPerShareB,
      pnlDollarWeightedB,
      pnlPctB,
      capitalB,
      weightB,
      beta,
      sizingMultiplier,
      totalInvestedCapital,
      netSpreadDollarPnl,
      rawReturnPct,
      realizedReturnPct,
      isWin,
    };
  }, [trade, bars, entryIdx, exitIdx, tickerA, tickerB]);

  // Plain-English $100,000 Portfolio Example Breakdown
  const portfolio100k = useMemo(() => {
    if (!execution || execution.totalInvestedCapital <= 0) return null;

    const baseCapital = 100000;
    // How many units of this cointegrated pair does $100,000 buy?
    const units = baseCapital / execution.totalInvestedCapital;

    // Actual share counts (rounded to discrete integer shares like real broker orders)
    const sharesA = Math.max(1, Math.round(units * execution.weightA));
    const sharesB = Math.max(1, Math.round(units * execution.weightB));

    // Cash capital allocated to each stock at entry
    const capitalA = sharesA * execution.entryPriceA;
    const capitalB = sharesB * execution.entryPriceB;
    const totalAllocated = capitalA + capitalB;

    // Gross dollar exit value
    const exitValA = sharesA * execution.exitPriceA;
    const exitValB = sharesB * execution.exitPriceB;

    // Exact cash profit or loss on $100k
    const pnlDollar100kA = execution.roleA === "LONG" ? exitValA - capitalA : capitalA - exitValA;
    const pnlDollar100kB = execution.roleB === "LONG" ? exitValB - capitalB : capitalB - exitValB;

    const netRawDollar100k = pnlDollar100kA + pnlDollar100kB;
    const rawPct = totalAllocated > 0 ? (netRawDollar100k / totalAllocated) * 100 : 0;

    const netRealizedDollar100k = netRawDollar100k * execution.sizingMultiplier;
    const realizedPct = rawPct * execution.sizingMultiplier;

    // Risk assessment (worst-case dynamic stop loss)
    const entryZ = Math.abs(trade?.entry_z ?? 2.1);
    const stopZ = Math.max(2.85, entryZ + 1.15);
    const zExcursionToStop = stopZ - entryZ;
    const estimatedRiskPct = Math.min(10.0, Math.max(1.5, zExcursionToStop * 1.5 * execution.sizingMultiplier));
    const estimatedRiskDollar = (totalAllocated * estimatedRiskPct) / 100;

    // Stop Loss and Target prices for individual stocks
    const slPriceA = execution.roleA === "LONG"
      ? execution.entryPriceA * (1 - estimatedRiskPct / 100)
      : execution.entryPriceA * (1 + estimatedRiskPct / 100);

    const slPriceB = execution.roleB === "LONG"
      ? execution.entryPriceB * (1 - estimatedRiskPct / 100)
      : execution.entryPriceB * (1 + estimatedRiskPct / 100);

    const targetPriceA = execution.roleA === "LONG"
      ? (execution.exitPriceA > execution.entryPriceA ? execution.exitPriceA : execution.entryPriceA * 1.08)
      : (execution.exitPriceA < execution.entryPriceA ? execution.exitPriceA : execution.entryPriceA * 0.92);

    const targetPriceB = execution.roleB === "LONG"
      ? (execution.exitPriceB > execution.entryPriceB ? execution.exitPriceB : execution.entryPriceB * 1.08)
      : (execution.exitPriceB < execution.entryPriceB ? execution.exitPriceB : execution.entryPriceB * 0.95);

    return {
      baseCapital,
      units,
      sharesA,
      sharesB,
      capitalA,
      capitalB,
      totalAllocated,
      exitValA,
      exitValB,
      pnlDollar100kA,
      pnlDollar100kB,
      netRawDollar100k,
      rawPct,
      netRealizedDollar100k,
      realizedPct,
      estimatedRiskPct,
      estimatedRiskDollar,
      stopZ,
      slPriceA,
      slPriceB,
      targetPriceA,
      targetPriceB,
    };
  }, [execution, trade]);

  if (!trade) return null;

  const isWin = execution ? execution.isWin : (trade.realized_return_pct ?? 0) >= 0;
  const returnPct = execution ? execution.realizedReturnPct : trade.realized_return_pct ?? 0;

  const themeBorder =
    strategyThemeColor === "cyan"
      ? "border-cyan-500/40"
      : strategyThemeColor === "emerald"
      ? "border-emerald-500/40"
      : strategyThemeColor === "amber"
      ? "border-amber-500/40"
      : "border-sky-500/40";

  const themeBadge =
    strategyThemeColor === "cyan"
      ? "bg-cyan-500/15 text-cyan-300 border-cyan-500/30"
      : strategyThemeColor === "emerald"
      ? "bg-emerald-500/15 text-emerald-300 border-emerald-500/30"
      : strategyThemeColor === "amber"
      ? "bg-amber-500/15 text-amber-300 border-amber-500/30"
      : "bg-sky-500/15 text-sky-300 border-sky-500/30";

  return (
    <div
      className="fixed inset-0 z-50 bg-black/85 backdrop-blur-md flex items-center justify-center p-2 sm:p-4 md:p-6"
      onClick={onClose}
    >
      <div
        className={`w-full max-w-7xl h-[94vh] max-h-[94vh] flex flex-col bg-slate-950 border ${themeBorder} rounded-2xl shadow-2xl overflow-hidden relative`}
        onClick={(e) => e.stopPropagation()}
      >
        {/* ================================================================= */}
        {/* 1. INSTITUTIONAL HEADER BAR                                       */}
        {/* ================================================================= */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 px-6 py-3.5 border-b border-line bg-surface-1/90 backdrop-blur-sm">
          <div className="flex flex-wrap items-center gap-3">
            <span className={`px-2.5 py-1 rounded text-[11px] font-mono font-bold border ${themeBadge}`}>
              {strategyLabel}
            </span>
            <div className="flex items-center gap-2">
              <h2 className="text-xl font-extrabold font-mono text-white tracking-wide">
                {trade.pair_name}
              </h2>
              {trade.sector && (
                <span className="text-xs px-2 py-0.5 rounded bg-surface-2 text-gray-400 border border-line">
                  {trade.sector}
                </span>
              )}
            </div>

            {/* Outcome Badge */}
            <span
              className={`px-3 py-1 rounded-full text-xs font-mono font-bold border flex items-center gap-1.5 ${
                isWin
                  ? "bg-emerald-500/20 text-emerald-300 border-emerald-500/40"
                  : "bg-rose-500/20 text-rose-300 border-rose-500/40"
              }`}
            >
              {isWin ? <CheckCircle2 className="w-3.5 h-3.5" /> : <ShieldAlert className="w-3.5 h-3.5" />}
              <span>
                {trade.outcome || (isWin ? "WIN" : "LOSS")} ({returnPct >= 0 ? "+" : ""}
                {returnPct.toFixed(2)}%)
              </span>
            </span>

            {/* Direction Badge */}
            {execution && (
              <span className="text-xs font-mono text-gray-300 bg-surface-2 px-2.5 py-1 rounded border border-line flex items-center gap-1.5">
                <span className={execution.roleA === "LONG" ? "text-emerald-400 font-bold" : "text-amber-400 font-bold"}>
                  {execution.roleA} {tickerA}
                </span>
                <span className="text-gray-500">/</span>
                <span className={execution.roleB === "LONG" ? "text-emerald-400 font-bold" : "text-amber-400 font-bold"}>
                  {execution.roleB} {tickerB}
                </span>
              </span>
            )}
          </div>

          {/* Right Header Controls: Trade Step Buttons & Close */}
          <div className="flex items-center gap-2 self-end sm:self-auto">
            {totalTrades !== undefined && tradeIndex !== undefined && (
              <span className="text-xs font-mono text-gray-400 mr-2">
                Trade {tradeIndex + 1} of {totalTrades}
              </span>
            )}

            {onPrevTrade && (
              <button
                onClick={onPrevTrade}
                title="Previous Trade (Left Arrow)"
                className="p-1.5 rounded-lg bg-surface-2 text-gray-300 hover:text-white hover:bg-surface-3 border border-line transition-colors"
              >
                <ChevronLeft className="w-4 h-4" />
              </button>
            )}

            {onNextTrade && (
              <button
                onClick={onNextTrade}
                title="Next Trade (Right Arrow)"
                className="p-1.5 rounded-lg bg-surface-2 text-gray-300 hover:text-white hover:bg-surface-3 border border-line transition-colors"
              >
                <ChevronRight className="w-4 h-4" />
              </button>
            )}

            <button
              onClick={onClose}
              title="Close Inspector (Esc)"
              className="p-1.5 rounded-lg bg-surface-2 text-gray-400 hover:text-white hover:bg-rose-500/20 border border-line transition-colors ml-2"
            >
              <X className="w-5 h-5" />
            </button>
          </div>
        </div>

        {/* ================================================================= */}
        {/* 2. DUAL-STOCK EXECUTION & OVERALL P&L TABLE (CALCULATION PART)    */}
        {/* ================================================================= */}
        {portfolio100k && execution && (
          <div className="px-6 py-3 bg-slate-900/90 border-b border-line overflow-x-auto">
            <table className="w-full text-left text-xs font-mono border-collapse">
              <thead>
                <tr className="border-b border-line/80 text-[11px] text-gray-400">
                  <th className="py-2 px-3 whitespace-nowrap">Asset / Side</th>
                  <th className="py-2 px-3 whitespace-nowrap">Entry Price</th>
                  <th className="py-2 px-3 whitespace-nowrap">Qty ($100k Model)</th>
                  <th className="py-2 px-3 whitespace-nowrap">Stop Loss (SL)</th>
                  <th className="py-2 px-3 whitespace-nowrap">Target Price</th>
                  <th className="py-2 px-3 whitespace-nowrap">Sell / Exit Price</th>
                  <th className="py-2 px-3 text-right whitespace-nowrap min-w-[190px]">Overall P&amp;L</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line/40 text-xs">
                {/* ROW 1: Stock A */}
                <tr className="hover:bg-surface-2/40 transition-colors">
                  <td className="py-2.5 px-3 font-bold text-sky-400 whitespace-nowrap">
                    <div className="flex items-center gap-2">
                      <span className="w-2.5 h-2.5 rounded-full bg-sky-400 inline-block shadow shadow-sky-400/50" />
                      <span>{execution.tickerA}</span>
                      <span
                        className={`text-[10px] px-1.5 py-0.5 rounded font-bold uppercase ${
                          execution.roleA === "LONG"
                            ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/40"
                            : "bg-amber-500/20 text-amber-300 border border-amber-500/40"
                        }`}
                      >
                        {execution.roleA}
                      </span>
                    </div>
                  </td>
                  <td className="py-2.5 px-3 font-semibold text-white whitespace-nowrap">
                    ${execution.entryPriceA.toFixed(2)}
                  </td>
                  <td className="py-2.5 px-3 text-gray-300 whitespace-nowrap">
                    <span className="font-bold text-white">{portfolio100k.sharesA.toLocaleString()} sh</span>
                    <span className="text-[10px] text-gray-400 ml-1.5">
                      (${portfolio100k.capitalA.toLocaleString(undefined, { maximumFractionDigits: 0 })})
                    </span>
                  </td>
                  <td className="py-2.5 px-3 text-rose-400 whitespace-nowrap">
                    ${portfolio100k.slPriceA.toFixed(2)}
                    <span className="text-[10px] text-gray-400 ml-1">
                      (-{portfolio100k.estimatedRiskPct.toFixed(1)}%)
                    </span>
                  </td>
                  <td className="py-2.5 px-3 text-emerald-400 whitespace-nowrap">
                    ${portfolio100k.targetPriceA.toFixed(2)}
                    <span className="text-[10px] text-gray-400 ml-1">(0.40σ)</span>
                  </td>
                  <td className="py-2.5 px-3 font-bold text-white whitespace-nowrap">
                    ${execution.exitPriceA.toFixed(2)}
                  </td>
                  <td className="py-2.5 px-3 text-right font-bold whitespace-nowrap min-w-[190px]">
                    <span className="inline-flex items-center justify-end gap-1.5 whitespace-nowrap">
                      <span className={portfolio100k.pnlDollar100kA >= 0 ? "text-emerald-400" : "text-rose-400"}>
                        {portfolio100k.pnlDollar100kA >= 0 ? "+" : ""}${portfolio100k.pnlDollar100kA.toLocaleString(undefined, { maximumFractionDigits: 0 })}
                      </span>
                      <span
                        className={`text-[11px] font-semibold ${
                          execution.pnlPctA >= 0 ? "text-emerald-400" : "text-rose-400"
                        }`}
                      >
                        ({execution.pnlPctA >= 0 ? "+" : ""}
                        {execution.pnlPctA.toFixed(2)}%)
                      </span>
                    </span>
                  </td>
                </tr>

                {/* ROW 2: Stock B */}
                <tr className="hover:bg-surface-2/40 transition-colors">
                  <td className="py-2.5 px-3 font-bold text-amber-400 whitespace-nowrap">
                    <div className="flex items-center gap-2">
                      <span className="w-2.5 h-2.5 rounded-full bg-amber-400 inline-block shadow shadow-amber-400/50" />
                      <span>{execution.tickerB}</span>
                      <span
                        className={`text-[10px] px-1.5 py-0.5 rounded font-bold uppercase ${
                          execution.roleB === "LONG"
                            ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/40"
                            : "bg-amber-500/20 text-amber-300 border border-amber-500/40"
                        }`}
                      >
                        {execution.roleB}
                      </span>
                      <span className="text-[10px] text-gray-400 font-normal">β={execution.beta.toFixed(3)}</span>
                    </div>
                  </td>
                  <td className="py-2.5 px-3 font-semibold text-white whitespace-nowrap">
                    ${execution.entryPriceB.toFixed(2)}
                  </td>
                  <td className="py-2.5 px-3 text-gray-300 whitespace-nowrap">
                    <span className="font-bold text-white">{portfolio100k.sharesB.toLocaleString()} sh</span>
                    <span className="text-[10px] text-gray-400 ml-1.5">
                      (${portfolio100k.capitalB.toLocaleString(undefined, { maximumFractionDigits: 0 })})
                    </span>
                  </td>
                  <td className="py-2.5 px-3 text-rose-400 whitespace-nowrap">
                    ${portfolio100k.slPriceB.toFixed(2)}
                    <span className="text-[10px] text-gray-400 ml-1">
                      (-{portfolio100k.estimatedRiskPct.toFixed(1)}%)
                    </span>
                  </td>
                  <td className="py-2.5 px-3 text-emerald-400 whitespace-nowrap">
                    ${portfolio100k.targetPriceB.toFixed(2)}
                    <span className="text-[10px] text-gray-400 ml-1">(0.40σ)</span>
                  </td>
                  <td className="py-2.5 px-3 font-bold text-white whitespace-nowrap">
                    ${execution.exitPriceB.toFixed(2)}
                  </td>
                  <td className="py-2.5 px-3 text-right font-bold whitespace-nowrap min-w-[190px]">
                    <span className="inline-flex items-center justify-end gap-1.5 whitespace-nowrap">
                      <span className={portfolio100k.pnlDollar100kB >= 0 ? "text-emerald-400" : "text-rose-400"}>
                        {portfolio100k.pnlDollar100kB >= 0 ? "+" : ""}${portfolio100k.pnlDollar100kB.toLocaleString(undefined, { maximumFractionDigits: 0 })}
                      </span>
                      <span
                        className={`text-[11px] font-semibold ${
                          execution.pnlPctB >= 0 ? "text-emerald-400" : "text-rose-400"
                        }`}
                      >
                        ({execution.pnlPctB >= 0 ? "+" : ""}
                        {execution.pnlPctB.toFixed(2)}%)
                      </span>
                    </span>
                  </td>
                </tr>

                {/* ROW 3: Overall P&L Only (Unified Spacious Non-Wrapping Row) */}
                <tr className="bg-surface-2/90 font-bold border-t-2 border-line/90">
                  <td colSpan={4} className="py-3 px-3 text-cyan-300 uppercase tracking-wide whitespace-nowrap">
                    <div className="flex items-center gap-2">
                      <Zap className="w-4 h-4 text-cyan-400 shrink-0" />
                      <span className="text-sm font-extrabold text-white">OVERALL TRADE P&amp;L</span>
                      <span className="text-[11px] text-gray-400 font-normal">
                        ($100,000 Portfolio Model &middot; {trade.holding_days ?? "-"}d held &middot; {execution.sizingMultiplier.toFixed(2)}x size)
                      </span>
                    </div>
                  </td>
                  <td colSpan={3} className="py-3 px-3 text-right whitespace-nowrap">
                    <span
                      className={`inline-flex items-center gap-2 text-sm px-3 py-1 rounded font-black whitespace-nowrap ${
                        execution.isWin
                          ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/40"
                          : "bg-rose-500/20 text-rose-300 border border-rose-500/40"
                      }`}
                    >
                      <span>
                        Net Realized: {portfolio100k.netRealizedDollar100k >= 0 ? "+" : ""}${portfolio100k.netRealizedDollar100k.toLocaleString(undefined, { maximumFractionDigits: 0 })}
                      </span>
                      <span className="text-xs">
                        ({execution.realizedReturnPct >= 0 ? "+" : ""}{execution.realizedReturnPct.toFixed(2)}%)
                      </span>
                      <span
                        className={`text-[10px] px-1.5 py-0.2 rounded font-black uppercase ${
                          execution.isWin ? "bg-emerald-500/30 text-emerald-200" : "bg-rose-500/30 text-rose-200"
                        }`}
                      >
                        {execution.isWin ? "WIN" : "LOSS"}
                      </span>
                    </span>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        )}

        {/* ================================================================= */}
        {/* 3. CHART CONTROLS & TAB SWITCHER                                  */}
        {/* ================================================================= */}
        <div className="flex flex-wrap items-center justify-between gap-3 px-6 py-2.5 bg-surface-1/50 border-b border-line text-xs font-mono">
          <div className="flex items-center gap-1.5 bg-surface-2 p-1 rounded-lg border border-line">
            <button
              onClick={() => setActiveTab("stacked")}
              className={`px-3 py-1 rounded transition-colors flex items-center gap-1.5 ${
                activeTab === "stacked" ? "bg-cyan-600 text-white font-bold" : "text-gray-400 hover:text-white"
              }`}
            >
              <Split className="w-3.5 h-3.5" />
              <span>Stacked Dual View</span>
            </button>
            <button
              onClick={() => setActiveTab("prices")}
              className={`px-3 py-1 rounded transition-colors flex items-center gap-1.5 ${
                activeTab === "prices" ? "bg-cyan-600 text-white font-bold" : "text-gray-400 hover:text-white"
              }`}
            >
              <LineChart className="w-3.5 h-3.5" />
              <span>Dual Stock Prices</span>
            </button>
            <button
              onClick={() => setActiveTab("spread")}
              className={`px-3 py-1 rounded transition-colors flex items-center gap-1.5 ${
                activeTab === "spread" ? "bg-cyan-600 text-white font-bold" : "text-gray-400 hover:text-white"
              }`}
            >
              <Activity className="w-3.5 h-3.5" />
              <span>Spread &amp; Z-Score</span>
            </button>
            <button
              onClick={() => setActiveTab("ledger")}
              className={`px-3 py-1 rounded transition-colors flex items-center gap-1.5 ${
                activeTab === "ledger" ? "bg-cyan-600 text-white font-bold" : "text-gray-400 hover:text-white"
              }`}
            >
              <TableIcon className="w-3.5 h-3.5" />
              <span>Inspection Ledger</span>
            </button>
          </div>

          <div className="flex items-center gap-4">
            <span className="text-[11px] text-gray-400">
              Window: <span className="text-white font-semibold">T-60d</span> &rarr;{" "}
              <span className="text-white font-semibold">T_exit+15d</span> ({bars.length} bars)
            </span>
          </div>
        </div>

        {/* ================================================================= */}
        {/* 4. MAIN VIEWPORT (CHARTS & LEDGER)                                */}
        {/* ================================================================= */}
        <div className="flex-1 overflow-y-auto p-4 sm:p-6 space-y-4">
          {isLoading && (
            <div className="h-96 flex flex-col items-center justify-center gap-3 text-gray-400 font-mono">
              <div className="w-8 h-8 border-2 border-cyan-500 border-t-transparent rounded-full animate-spin" />
              <span>Generating [T-60d, T_exit+15d] dual-stock price matrix...</span>
            </div>
          )}

          {error && (
            <div className="p-4 rounded-xl bg-rose-500/10 border border-rose-500/30 text-rose-300 text-xs font-mono">
              Error fetching trade chart window: {(error as Error).message}
            </div>
          )}

          {!isLoading && !error && bars.length > 0 && execution && (
            <>
              {/* Stacked or Price/Spread Chart */}
              {(activeTab === "stacked" || activeTab === "prices") && (
                <div className="bg-surface-1 border border-line rounded-xl p-4 space-y-2">
                  <div className="flex flex-wrap items-center justify-between text-xs font-mono gap-2">
                    <div className="flex flex-wrap items-center gap-4">
                      <span className="font-bold text-white">Stock Prices &amp; Execution Pins:</span>

                      {/* Stock A Pin Callout Badge */}
                      <span className="flex items-center gap-1.5 px-2 py-0.5 rounded bg-sky-500/10 text-sky-400 border border-sky-500/30">
                        <span className="w-2.5 h-2.5 rounded-full bg-sky-400 shadow shadow-sky-400/50" />
                        <span className="font-bold">{tickerA}</span>
                        <span className="text-[10px] text-gray-400">
                          (${execution.entryPriceA.toFixed(2)} &rarr; ${execution.exitPriceA.toFixed(2)})
                        </span>
                        <span
                          className={`font-bold ml-1 ${
                            execution.pnlPctA >= 0 ? "text-emerald-400" : "text-rose-400"
                          }`}
                        >
                          {execution.pnlPctA >= 0 ? "+" : ""}
                          {execution.pnlPctA.toFixed(2)}%
                        </span>
                      </span>

                      {/* Stock B Pin Callout Badge */}
                      <span className="flex items-center gap-1.5 px-2 py-0.5 rounded bg-amber-500/10 text-amber-400 border border-amber-500/30">
                        <span className="w-2.5 h-2.5 rounded-full bg-amber-400 shadow shadow-amber-400/50" />
                        <span className="font-bold">{tickerB}</span>
                        <span className="text-[10px] text-gray-400">
                          (${execution.entryPriceB.toFixed(2)} &rarr; ${execution.exitPriceB.toFixed(2)})
                        </span>
                        <span
                          className={`font-bold ml-1 ${
                            execution.pnlPctB >= 0 ? "text-emerald-400" : "text-rose-400"
                          }`}
                        >
                          {execution.pnlPctB >= 0 ? "+" : ""}
                          {execution.pnlPctB.toFixed(2)}%
                        </span>
                      </span>
                    </div>

                    {activeBar && (
                      <div className="flex items-center gap-3 text-cyan-300 font-bold">
                        <span>Date: {activeBar.date}</span>
                        <span>
                          {tickerA}: ${activeBar.price_a.toFixed(2)}
                        </span>
                        <span>
                          {tickerB}: ${activeBar.price_b.toFixed(2)}
                        </span>
                      </div>
                    )}
                  </div>

                  {/* SVG Chart with On-Canvas Visual Pins and Trajectory */}
                  <StockPriceWindowSvg
                    bars={bars}
                    entryIdx={entryIdx}
                    exitIdx={exitIdx}
                    tickerA={tickerA}
                    tickerB={tickerB}
                    hoverIndex={hoverIndex}
                    onHover={setHoverIndex}
                    execution={execution}
                    height={activeTab === "stacked" ? 240 : 400}
                  />
                </div>
              )}

              {/* Spread & Z-Score Chart */}
              {(activeTab === "stacked" || activeTab === "spread") && (
                <div className="bg-surface-1 border border-line rounded-xl p-4 space-y-2">
                  <div className="flex items-center justify-between text-xs font-mono">
                    <div className="flex items-center gap-4">
                      <span className="font-bold text-white">
                        Mean-Reversion Spread Excursion (Z-Score):
                      </span>
                      <span className="text-emerald-400 font-semibold text-[11px]">
                        Entry Hurdle: &plusmn;2.10&sigma; &middot; Exit Target: 0.40&sigma;/0.0&sigma; &middot; Stop:
                        &plusmn;2.85&sigma;/3.5&sigma;
                      </span>
                    </div>

                    {activeBar && (
                      <div className="flex items-center gap-3 text-cyan-300 font-bold">
                        <span>Spread: ${activeBar.spread.toFixed(4)}</span>
                        <span className={activeBar.z_score >= 0 ? "text-cyan-400" : "text-amber-400"}>
                          Z-Score: {activeBar.z_score.toFixed(2)}&sigma;
                        </span>
                        {activeBar.is_entry && <span className="text-emerald-400">[ENTRY DAY]</span>}
                        {activeBar.is_exit && <span className="text-purple-400">[EXIT DAY]</span>}
                      </div>
                    )}
                  </div>

                  <SpreadZScoreWindowSvg
                    bars={bars}
                    entryIdx={entryIdx}
                    exitIdx={exitIdx}
                    hoverIndex={hoverIndex}
                    onHover={setHoverIndex}
                    height={activeTab === "stacked" ? 180 : 360}
                  />
                </div>
              )}

              {/* Day-by-Day Tabular Inspection Ledger */}
              {(activeTab === "ledger" || activeTab === "stacked") && (
                <div className="bg-surface-1 border border-line rounded-xl p-4 space-y-3">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <TableIcon className="w-4 h-4 text-cyan-400" />
                      <h3 className="text-xs font-bold font-mono text-white">
                        Day-by-Day Inspection Ledger
                      </h3>
                    </div>
                    <span className="text-[11px] font-mono text-gray-400">
                      Highlighted rows indicate the holding window
                    </span>
                  </div>

                  <div className="max-h-60 overflow-y-auto rounded-lg border border-line">
                    <table className="w-full text-left text-xs font-mono border-collapse">
                      <thead className="sticky top-0 z-10 bg-slate-900 border-b border-line text-[11px] text-gray-300 shadow-md">
                        <tr className="bg-slate-900">
                          <th className="py-2.5 px-3 bg-slate-900 font-bold text-gray-300">Date</th>
                          <th className="py-2.5 px-3 bg-slate-900 font-bold text-gray-300">Status</th>
                          <th className="py-2.5 px-3 bg-slate-900 font-bold text-gray-300">{tickerA} Price</th>
                          <th className="py-2.5 px-3 bg-slate-900 font-bold text-gray-300">{tickerA} Leg Return</th>
                          <th className="py-2.5 px-3 bg-slate-900 font-bold text-gray-300">{tickerB} Price</th>
                          <th className="py-2.5 px-3 bg-slate-900 font-bold text-gray-300">{tickerB} Leg Return</th>
                          <th className="py-2.5 px-3 bg-slate-900 font-bold text-gray-300">Spread ($)</th>
                          <th className="py-2.5 px-3 bg-slate-900 font-bold text-gray-300">Z-Score (&sigma;)</th>
                          <th className="py-2.5 px-3 bg-slate-900 font-bold text-gray-300 text-right">Holding Timeline</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-line/40 text-[11px]">
                        {bars.map((b, i) => {
                          const isHolding = b.in_trade;
                          const rowClass = b.is_entry
                            ? "bg-emerald-500/15 font-bold"
                            : b.is_exit
                            ? "bg-purple-500/15 font-bold"
                            : isHolding
                            ? "bg-cyan-500/[0.07]"
                            : "hover:bg-surface-2/40 text-gray-400";

                          // Calculate running leg returns from entry
                          const legRetA =
                            execution.entryPriceA > 0
                              ? execution.roleA === "LONG"
                                ? ((b.price_a - execution.entryPriceA) / execution.entryPriceA) * 100
                                : ((execution.entryPriceA - b.price_a) / execution.entryPriceA) * 100
                              : 0;

                          const legRetB =
                            execution.entryPriceB > 0
                              ? execution.roleB === "LONG"
                                ? ((b.price_b - execution.entryPriceB) / execution.entryPriceB) * 100
                                : ((execution.entryPriceB - b.price_b) / execution.entryPriceB) * 100
                              : 0;

                          return (
                            <tr
                              key={b.date}
                              onMouseEnter={() => setHoverIndex(i)}
                              className={`transition-colors cursor-pointer ${rowClass}`}
                            >
                              <td className="py-1.5 px-3 font-semibold text-white">{b.date}</td>
                              <td className="py-1.5 px-3">
                                {b.is_entry ? (
                                  <span className="px-1.5 py-0.5 rounded bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 text-[10px] font-bold">
                                    ENTRY
                                  </span>
                                ) : b.is_exit ? (
                                  <span className="px-1.5 py-0.5 rounded bg-purple-500/20 text-purple-300 border border-purple-500/40 text-[10px] font-bold">
                                    EXIT
                                  </span>
                                ) : isHolding ? (
                                  <span className="text-cyan-300 text-[10px]">HOLDING</span>
                                ) : i < entryIdx ? (
                                  <span className="text-gray-500 text-[10px]">PRE-TRADE</span>
                                ) : (
                                  <span className="text-gray-500 text-[10px]">POST-TRADE</span>
                                )}
                              </td>
                              <td className="py-1.5 px-3 text-sky-300">
                                ${b.price_a.toFixed(2)}
                              </td>
                              <td className="py-1.5 px-3">
                                {isHolding || b.is_exit ? (
                                  <span
                                    className={`font-semibold ${
                                      legRetA >= 0 ? "text-emerald-400" : "text-rose-400"
                                    }`}
                                  >
                                    {legRetA >= 0 ? "+" : ""}
                                    {legRetA.toFixed(2)}%
                                  </span>
                                ) : (
                                  <span className="text-gray-500">-</span>
                                )}
                              </td>
                              <td className="py-1.5 px-3 text-amber-300">
                                ${b.price_b.toFixed(2)}
                              </td>
                              <td className="py-1.5 px-3">
                                {isHolding || b.is_exit ? (
                                  <span
                                    className={`font-semibold ${
                                      legRetB >= 0 ? "text-emerald-400" : "text-rose-400"
                                    }`}
                                  >
                                    {legRetB >= 0 ? "+" : ""}
                                    {legRetB.toFixed(2)}%
                                  </span>
                                ) : (
                                  <span className="text-gray-500">-</span>
                                )}
                              </td>
                              <td className="py-1.5 px-3 text-gray-200">${b.spread.toFixed(4)}</td>
                              <td
                                className={`py-1.5 px-3 font-bold ${
                                  Math.abs(b.z_score) >= 2.0 ? "text-cyan-400" : "text-gray-300"
                                }`}
                              >
                                {b.z_score.toFixed(2)}&sigma;
                              </td>
                              <td className="py-1.5 px-3 text-right text-gray-400">
                                {isHolding
                                  ? `Day ${i - entryIdx + 1} of ${exitIdx - entryIdx + 1}`
                                  : i < entryIdx
                                  ? `${entryIdx - i}d before`
                                  : `+${i - exitIdx}d after`}
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </>
          )}
        </div>

        {/* ================================================================= */}
        {/* 5. FOOTER STATUS NARRATIVE                                        */}
        {/* ================================================================= */}
        <div className="px-6 py-3 border-t border-line bg-surface-1/90 flex flex-col sm:flex-row sm:items-center justify-between gap-2 text-xs font-mono text-gray-400">
          <div className="flex items-center gap-2">
            <span className="text-gray-300 font-bold">Execution Narrative:</span>
            <span>{trade.status_reason || trade.exit_reason || "Trade fully settled."}</span>
          </div>
          <div className="text-[11px] text-gray-500">
            Use <span className="text-gray-300 font-semibold">&larr;</span> and{" "}
            <span className="text-gray-300 font-semibold">&rarr;</span> to cycle trades &middot;{" "}
            <span className="text-gray-300 font-semibold">Esc</span> to dismiss
          </div>
        </div>
      </div>
    </div>
  );
}

// =========================================================================== //
// DUAL STOCK PRICE WINDOW SVG CHART WITH ON-CANVAS PINS & LEG PNL             //
// =========================================================================== //
function StockPriceWindowSvg({
  bars,
  entryIdx,
  exitIdx,
  tickerA,
  tickerB,
  hoverIndex,
  onHover,
  execution,
  height,
}: {
  bars: TradeChartBar[];
  entryIdx: number;
  exitIdx: number;
  tickerA: string;
  tickerB: string;
  hoverIndex: number | null;
  onHover: (idx: number | null) => void;
  execution: {
    roleA: "LONG" | "SHORT";
    roleB: "LONG" | "SHORT";
    entryPriceA: number;
    exitPriceA: number;
    pnlDollarA: number;
    pnlDollarWeightedA: number;
    pnlPctA: number;
    entryPriceB: number;
    exitPriceB: number;
    pnlDollarB: number;
    pnlDollarWeightedB: number;
    pnlPctB: number;
  };
  height: number;
}) {
  const n = bars.length;
  if (n === 0) return null;

  // STRICT REAL PRICES ONLY - NO NORMALIZATION
  const valsA = bars.map((b) => b.price_a);
  const valsB = bars.map((b) => b.price_b);

  const minA = Math.min(...valsA);
  const maxA = Math.max(...valsA);
  const padA = (maxA - minA) * 0.12 || 1;
  const effMinA = minA - padA;
  const effMaxA = maxA + padA;
  const effRangeA = effMaxA - effMinA || 1;

  const minB = Math.min(...valsB);
  const maxB = Math.max(...valsB);
  const padB = (maxB - minB) * 0.12 || 1;
  const effMinB = minB - padB;
  const effMaxB = maxB + padB;
  const effRangeB = effMaxB - effMinB || 1;

  const toX = (i: number) => (i / Math.max(1, n - 1)) * 1000;
  const toYA = (v: number) => 195 - ((v - effMinA) / effRangeA) * 180;
  const toYB = (v: number) => 195 - ((v - effMinB) / effRangeB) * 180;

  const ptsA = valsA.map((v, i) => `${toX(i).toFixed(1)},${toYA(v).toFixed(1)}`).join(" ");
  const ptsB = valsB.map((v, i) => `${toX(i).toFixed(1)},${toYB(v).toFixed(1)}`).join(" ");

  const entryX = toX(entryIdx);
  const exitX = toX(exitIdx);

  const entryYA = toYA(valsA[entryIdx] ?? execution.entryPriceA);
  const exitYA = toYA(valsA[exitIdx] ?? execution.exitPriceA);

  const entryYB = toYB(valsB[entryIdx] ?? execution.entryPriceB);
  const exitYB = toYB(valsB[exitIdx] ?? execution.exitPriceB);

  return (
    <div className="relative w-full overflow-hidden select-none" style={{ height }}>
      <svg
        viewBox="0 0 1000 210"
        preserveAspectRatio="none"
        className="w-full h-full cursor-crosshair"
        onMouseMove={(e) => {
          const rect = e.currentTarget.getBoundingClientRect();
          const relX = (e.clientX - rect.left) / rect.width;
          const idx = Math.min(n - 1, Math.max(0, Math.round(relX * (n - 1))));
          onHover(idx);
        }}
        onMouseLeave={() => onHover(null)}
      >
        <defs>
          <linearGradient id="tradeRegionGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#06B6D4" stopOpacity="0.16" />
            <stop offset="100%" stopColor="#06B6D4" stopOpacity="0.03" />
          </linearGradient>
        </defs>

        {/* Shaded Active Trade Region */}
        <rect
          x={entryX}
          y="10"
          width={Math.max(1, exitX - entryX)}
          height="190"
          fill="url(#tradeRegionGrad)"
          stroke="#06B6D4"
          strokeOpacity="0.25"
          strokeDasharray="4 2"
        />

        {/* Horizontal grid lines */}
        {[0.25, 0.5, 0.75].map((pct) => (
          <line
            key={pct}
            x1="0"
            y1={pct * 200}
            x2="1000"
            y2={pct * 200}
            stroke="#1E293B"
            strokeDasharray="4 4"
            strokeWidth="1"
          />
        ))}

        {/* Stock B Line (Amber) */}
        <polyline
          points={ptsB}
          fill="none"
          stroke="#F59E0B"
          strokeWidth="2.5"
          vectorEffect="non-scaling-stroke"
        />

        {/* Stock A Line (Sky Blue) */}
        <polyline
          points={ptsA}
          fill="none"
          stroke="#38BDF8"
          strokeWidth="2.5"
          vectorEffect="non-scaling-stroke"
        />

        {/* Trajectory Guide Vectors (Entry to Exit) */}
        <line
          x1={entryX}
          y1={entryYA}
          x2={exitX}
          y2={exitYA}
          stroke={execution.pnlPctA >= 0 ? "#10B981" : "#EF4444"}
          strokeWidth="2"
          strokeDasharray="5 3"
          vectorEffect="non-scaling-stroke"
        />
        <line
          x1={entryX}
          y1={entryYB}
          x2={exitX}
          y2={exitYB}
          stroke={execution.pnlPctB >= 0 ? "#10B981" : "#EF4444"}
          strokeWidth="2"
          strokeDasharray="5 3"
          vectorEffect="non-scaling-stroke"
        />

        {/* Vertical Entry Marker Line */}
        <line
          x1={entryX}
          y1="8"
          x2={entryX}
          y2="202"
          stroke="#10B981"
          strokeWidth="2"
          strokeDasharray="4 3"
          vectorEffect="non-scaling-stroke"
        />

        {/* Vertical Exit Marker Line */}
        <line
          x1={exitX}
          y1="8"
          x2={exitX}
          y2="202"
          stroke="#A855F7"
          strokeWidth="2"
          strokeDasharray="4 3"
          vectorEffect="non-scaling-stroke"
        />

        {/* ------------------------------------------------------------- */}
        {/* Visual Pins: Stock A (Entry & Exit)                           */}
        {/* ------------------------------------------------------------- */}
        {/* Entry Point A */}
        <circle cx={entryX} cy={entryYA} r="6" fill="#38BDF8" stroke="#0F172A" strokeWidth="2" />
        <circle cx={entryX} cy={entryYA} r="10" fill="none" stroke="#38BDF8" strokeWidth="1.5" strokeOpacity="0.6" />

        {/* Exit Point A */}
        <circle cx={exitX} cy={exitYA} r="6" fill="#38BDF8" stroke="#0F172A" strokeWidth="2" />
        <circle
          cx={exitX}
          cy={exitYA}
          r="10"
          fill="none"
          stroke={execution.pnlPctA >= 0 ? "#10B981" : "#EF4444"}
          strokeWidth="1.5"
          strokeOpacity="0.8"
        />

        {/* ------------------------------------------------------------- */}
        {/* Visual Pins: Stock B (Entry & Exit)                           */}
        {/* ------------------------------------------------------------- */}
        {/* Entry Point B */}
        <circle cx={entryX} cy={entryYB} r="6" fill="#F59E0B" stroke="#0F172A" strokeWidth="2" />
        <circle cx={entryX} cy={entryYB} r="10" fill="none" stroke="#F59E0B" strokeWidth="1.5" strokeOpacity="0.6" />

        {/* Exit Point B */}
        <circle cx={exitX} cy={exitYB} r="6" fill="#F59E0B" stroke="#0F172A" strokeWidth="2" />
        <circle
          cx={exitX}
          cy={exitYB}
          r="10"
          fill="none"
          stroke={execution.pnlPctB >= 0 ? "#10B981" : "#EF4444"}
          strokeWidth="1.5"
          strokeOpacity="0.8"
        />

        {/* Hover Crosshair */}
        {hoverIndex !== null && (
          <line
            x1={toX(hoverIndex)}
            y1="5"
            x2={toX(hoverIndex)}
            y2="205"
            stroke="#FFFFFF"
            strokeWidth="1.5"
            strokeDasharray="2 2"
            vectorEffect="non-scaling-stroke"
          />
        )}
      </svg>

      {/* Clean Interactive Hover Tooltip (Shown ONLY on Hover) */}
      {hoverIndex !== null && bars[hoverIndex] && (
        <div
          className="absolute top-2 px-2.5 py-1 rounded-md bg-slate-900/95 border border-cyan-500/50 text-[10px] font-mono font-bold text-white shadow-xl pointer-events-none z-20 flex items-center gap-3 -translate-x-1/2"
          style={{
            left: `${Math.min(88, Math.max(12, (hoverIndex / Math.max(1, n - 1)) * 100))}%`,
          }}
        >
          <span className="text-gray-400">{bars[hoverIndex].date}</span>
          <span className="text-sky-400">{tickerA}: ${bars[hoverIndex].price_a.toFixed(2)}</span>
          <span className="text-amber-400">{tickerB}: ${bars[hoverIndex].price_b.toFixed(2)}</span>
          {hoverIndex === entryIdx && (
            <span className="px-1.5 py-0.2 rounded bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 text-[9px]">
              ENTRY
            </span>
          )}
          {hoverIndex === exitIdx && (
            <span className="px-1.5 py-0.2 rounded bg-purple-500/20 text-purple-300 border border-purple-500/40 text-[9px]">
              EXIT
            </span>
          )}
        </div>
      )}
    </div>
  );
}

// =========================================================================== //
// SPREAD & Z-SCORE WINDOW SVG CHART                                           //
// =========================================================================== //
function SpreadZScoreWindowSvg({
  bars,
  entryIdx,
  exitIdx,
  hoverIndex,
  onHover,
  height,
}: {
  bars: TradeChartBar[];
  entryIdx: number;
  exitIdx: number;
  hoverIndex: number | null;
  onHover: (idx: number | null) => void;
  height: number;
}) {
  const n = bars.length;
  if (n === 0) return null;

  const zVals = bars.map((b) => b.z_score);
  const minZ = Math.min(-3.8, ...zVals);
  const maxZ = Math.max(3.8, ...zVals);
  const effRange = maxZ - minZ || 1;

  const toX = (i: number) => (i / Math.max(1, n - 1)) * 1000;
  const toY = (z: number) => 190 - ((z - minZ) / effRange) * 180;

  const ptsZ = zVals.map((z, i) => `${toX(i).toFixed(1)},${toY(z).toFixed(1)}`).join(" ");

  const entryX = toX(entryIdx);
  const exitX = toX(exitIdx);

  return (
    <div className="relative w-full overflow-hidden select-none" style={{ height }}>
      <svg
        viewBox="0 0 1000 200"
        preserveAspectRatio="none"
        className="w-full h-full cursor-crosshair"
        onMouseMove={(e) => {
          const rect = e.currentTarget.getBoundingClientRect();
          const relX = (e.clientX - rect.left) / rect.width;
          const idx = Math.min(n - 1, Math.max(0, Math.round(relX * (n - 1))));
          onHover(idx);
        }}
        onMouseLeave={() => onHover(null)}
      >
        {/* Shaded Active Trade Region */}
        <rect
          x={entryX}
          y="10"
          width={Math.max(1, exitX - entryX)}
          height="180"
          fill="#10B981"
          fillOpacity="0.08"
        />

        {/* 0.0 Zero Line */}
        <line
          x1="0"
          y1={toY(0)}
          x2="1000"
          y2={toY(0)}
          stroke="#475569"
          strokeWidth="1.5"
          vectorEffect="non-scaling-stroke"
        />

        {/* Reversion Target Line (0.40σ / -0.40σ) */}
        <line
          x1="0"
          y1={toY(0.4)}
          x2="1000"
          y2={toY(0.4)}
          stroke="#10B981"
          strokeDasharray="4 3"
          strokeWidth="1"
          vectorEffect="non-scaling-stroke"
        />
        <line
          x1="0"
          y1={toY(-0.4)}
          x2="1000"
          y2={toY(-0.4)}
          stroke="#10B981"
          strokeDasharray="4 3"
          strokeWidth="1"
          vectorEffect="non-scaling-stroke"
        />

        {/* Entry Hurdle (2.10σ / -2.10σ) */}
        <line
          x1="0"
          y1={toY(2.1)}
          x2="1000"
          y2={toY(2.1)}
          stroke="#06B6D4"
          strokeDasharray="4 3"
          strokeWidth="1"
          vectorEffect="non-scaling-stroke"
        />
        <line
          x1="0"
          y1={toY(-2.1)}
          x2="1000"
          y2={toY(-2.1)}
          stroke="#06B6D4"
          strokeDasharray="4 3"
          strokeWidth="1"
          vectorEffect="non-scaling-stroke"
        />

        {/* Stop Loss Barrier (2.85σ / -2.85σ) */}
        <line
          x1="0"
          y1={toY(2.85)}
          x2="1000"
          y2={toY(2.85)}
          stroke="#EF4444"
          strokeDasharray="4 3"
          strokeWidth="1"
          vectorEffect="non-scaling-stroke"
        />
        <line
          x1="0"
          y1={toY(-2.85)}
          x2="1000"
          y2={toY(-2.85)}
          stroke="#EF4444"
          strokeDasharray="4 3"
          strokeWidth="1"
          vectorEffect="non-scaling-stroke"
        />

        {/* Z-Score Curve */}
        <polyline
          points={ptsZ}
          fill="none"
          stroke="#22D3EE"
          strokeWidth="2.5"
          vectorEffect="non-scaling-stroke"
        />

        {/* Vertical Entry Marker */}
        <line
          x1={entryX}
          y1="10"
          x2={entryX}
          y2="190"
          stroke="#10B981"
          strokeWidth="2"
          strokeDasharray="4 3"
          vectorEffect="non-scaling-stroke"
        />

        {/* Vertical Exit Marker */}
        <line
          x1={exitX}
          y1="10"
          x2={exitX}
          y2="190"
          stroke="#A855F7"
          strokeWidth="2"
          strokeDasharray="4 3"
          vectorEffect="non-scaling-stroke"
        />

        {/* Hover Crosshair */}
        {hoverIndex !== null && (
          <line
            x1={toX(hoverIndex)}
            y1="5"
            x2={toX(hoverIndex)}
            y2="195"
            stroke="#FFFFFF"
            strokeWidth="1.5"
            strokeDasharray="2 2"
            vectorEffect="non-scaling-stroke"
          />
        )}
      </svg>
    </div>
  );
}
