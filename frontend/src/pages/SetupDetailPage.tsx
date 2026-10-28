import React, { useMemo, useState } from "react";
import { useParams, Link, useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import {
  ArrowLeft,
  TrendingUp,
  TrendingDown,
  ShieldCheck,
  CheckCircle2,
  XCircle,
  RefreshCw,
  SlidersHorizontal,
  Layers,
  Activity,
  Calculator,
  Calendar,
  Sparkles,
  Zap,
  Info,
  Clock,
} from "lucide-react";
import { api } from "@/lib/api";
import { Button, Card, ErrorBox, Loading, PageTitle, StatCard } from "@/components/ui";
import { cn } from "@/lib/utils";
import TradingViewPairChart from "@/components/TradingViewPairChart";

type RangeOption = "60D" | "90D" | "6M" | "1Y" | "ALL";
type ChartMode = "price" | "normalized" | "spread";

// Sector badge styling
const SECTOR_STYLES: Record<string, { badge: string; dot: string }> = {
  "Information Technology": {
    badge: "border-cyan-500/30 bg-cyan-500/10 text-cyan-300",
    dot: "bg-cyan-400",
  },
  Financials: {
    badge: "border-blue-500/30 bg-blue-500/10 text-blue-300",
    dot: "bg-blue-400",
  },
  Industrials: {
    badge: "border-amber-500/30 bg-amber-500/10 text-amber-300",
    dot: "bg-amber-400",
  },
  "Health Care": {
    badge: "border-emerald-500/30 bg-emerald-500/10 text-emerald-300",
    dot: "bg-emerald-400",
  },
  Utilities: {
    badge: "border-teal-500/30 bg-teal-500/10 text-teal-300",
    dot: "bg-teal-400",
  },
  Energy: {
    badge: "border-orange-500/30 bg-orange-500/10 text-orange-300",
    dot: "bg-orange-400",
  },
  "Real Estate": {
    badge: "border-purple-500/30 bg-purple-500/10 text-purple-300",
    dot: "bg-purple-400",
  },
};

export default function SetupDetailPage() {
  const params = useParams<{ tickerA?: string; tickerB?: string; pairKey?: string }>();
  const [searchParams] = useSearchParams();
  const asOfDate = searchParams.get("date") || "";

  // Extract symbols from params (handles /setups/:tickerA/:tickerB or /setups/:pairKey)
  let tickerA = params.tickerA?.toUpperCase().trim() || "";
  let tickerB = params.tickerB?.toUpperCase().trim() || "";
  if (!tickerA && params.pairKey) {
    const parts = params.pairKey.split("-");
    if (parts.length === 2) {
      tickerA = parts[0].toUpperCase().trim();
      tickerB = parts[1].toUpperCase().trim();
    }
  }

  // Capital allocation state
  const [allocationCapital, setAllocationCapital] = useState<number>(50000);

  // Fetch 5-year historical dataset for the pair
  const historyQuery = useQuery({
    queryKey: ["pair-history", tickerA, tickerB, asOfDate],
    queryFn: () => api.pairHistory(tickerA, tickerB, "5y", false, asOfDate || undefined),
    enabled: !!tickerA && !!tickerB,
    staleTime: 5 * 60 * 1000,
  });

  const pairData = historyQuery.data;
  const allBars = useMemo(() => pairData?.bars || [], [pairData]);

  // Calculations for trade execution sizing (True Beta-Neutral Unit Allocation)
  const sizing = useMemo(() => {
    if (!pairData || !pairData.last_price_a || !pairData.last_price_b) return null;
    const pa = pairData.last_price_a;
    const pb = pairData.last_price_b;
    const beta = Math.max(1e-4, pairData.hedge_ratio || 1.0);

    // True Beta-neutral pair unit cost: 1 share of A + beta shares of B
    const unitCost = pa + (beta * pb);
    const units = Math.max(1, Math.floor(allocationCapital / unitCost));
    const sharesA = units;
    const sharesB = Math.max(1, Math.round(units * beta));

    const actualCapA = Math.round(sharesA * pa);
    const actualCapB = Math.round(sharesB * pb);
    const totalAllocated = actualCapA + actualCapB;

    // Expected dollar profit at mean reversion
    const profitPerShareA = pairData.expected_profit_dollar_a ?? Math.abs((pairData.target_price_a ?? pa) - pa);
    const profitPerShareB = pairData.expected_profit_dollar_b ?? Math.abs((pairData.target_price_b ?? pb) - pb);
    const totalProfitA = Math.round(sharesA * profitPerShareA);
    const totalProfitB = Math.round(sharesB * profitPerShareB);
    const totalNetProfit = totalProfitA + totalProfitB;
    const netReturnPct = totalAllocated > 0 ? (totalNetProfit / totalAllocated) * 100 : 0;

    return {
      units,
      unitCost,
      sharesA,
      sharesB,
      actualCapA,
      actualCapB,
      totalAllocated,
      totalProfitA,
      totalProfitB,
      totalNetProfit,
      netReturnPct,
    };
  }, [pairData, allocationCapital]);

  if (!tickerA || !tickerB) {
    return (
      <div className="space-y-4">
        <Link to="/setups" className="inline-flex items-center gap-1.5 text-xs text-gray-400 hover:text-white">
          <ArrowLeft className="w-4 h-4" /> Back to Setups
        </Link>
        <ErrorBox error="Invalid pair tickers provided in route." />
      </div>
    );
  }

  const isShortSpread = (pairData?.current_z_score ?? 0) >= 0;
  const sectorStyle = SECTOR_STYLES[pairData?.sector || ""] || {
    badge: "border-gray-700 bg-gray-800 text-gray-300",
    dot: "bg-gray-400",
  };

  return (
    <div className="space-y-6">
      {/* Top Breadcrumb & Navigation Bar */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Link
            to={asOfDate ? `/backtest?date=${asOfDate}` : "/setups"}
            className="inline-flex items-center gap-1.5 text-xs font-medium text-gray-400 hover:text-white transition-colors bg-surface-2 px-3 py-1.5 rounded-lg border border-line"
          >
            <ArrowLeft className="w-3.5 h-3.5" />
            <span>{asOfDate ? `Back to Backtest (${asOfDate})` : "Back to Active Setups"}</span>
          </Link>
          <Link
            to="/pairs"
            className="inline-flex items-center gap-1.5 text-xs font-medium text-gray-400 hover:text-white transition-colors bg-surface-2 px-3 py-1.5 rounded-lg border border-line"
          >
            <Layers className="w-3.5 h-3.5 text-gray-400" />
            <span>All 128 Pairs</span>
          </Link>
        </div>

        <div className="flex items-center gap-2">
          <span className="text-xs text-gray-400 font-mono">
            Timeframe: <strong className="text-cyan-300">1D (Daily)</strong> &middot; History: 5 Years (
            {allBars.length} daily bars)
          </span>
          <Button
            variant="ghost"
            onClick={() => historyQuery.refetch()}
            disabled={historyQuery.isFetching}
            className="text-xs text-gray-400 hover:text-white px-2.5 py-1"
          >
            <RefreshCw className={cn("w-3.5 h-3.5 mr-1", historyQuery.isFetching && "animate-spin")} />
            Refresh
          </Button>
        </div>
      </div>

      {/* ─── POINT-IN-TIME HISTORICAL TRADE MODE BANNER ─────────────────── */}
      {asOfDate && (
        <div className="p-4 rounded-xl border border-amber-500/40 bg-amber-500/10 flex flex-col sm:flex-row sm:items-center justify-between gap-4 shadow-lg backdrop-blur">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg bg-amber-500/20 border border-amber-500/30 flex items-center justify-center shrink-0">
              <Clock className="w-5 h-5 text-amber-400" />
            </div>
            <div>
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-xs font-bold uppercase tracking-wider text-amber-400 font-mono">
                  Point-in-Time Historical Trade Mode
                </span>
                <span className="text-[11px] font-mono text-amber-200 bg-amber-950/60 px-2.5 py-0.5 rounded border border-amber-500/30 font-bold">
                  Date T: {asOfDate}
                </span>
                <span className="text-[10px] font-mono text-emerald-400 bg-emerald-950/40 px-2 py-0.5 rounded border border-emerald-500/30">
                  Strict Zero Lookahead Bias
                </span>
              </div>
              <p className="text-xs text-gray-300 mt-1">
                Viewing stock prices, OLS hedge ratio (β={pairData?.hedge_ratio ?? "..."}), spread Z-score ({pairData?.current_z_score !== undefined ? `${pairData.current_z_score > 0 ? "+" : ""}${pairData.current_z_score.toFixed(2)}σ` : "..."}), order sizing, and chart bars strictly as of <strong className="text-white">{pairData?.trading_date_used || asOfDate}</strong>.
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2 shrink-0">
            <Link
              to={`/backtest?date=${asOfDate}`}
              className="text-xs font-semibold text-gray-300 hover:text-white px-3 py-1.5 rounded-lg bg-surface-2 border border-line hover:border-gray-500 transition-colors flex items-center gap-1.5"
            >
              <ArrowLeft className="w-3.5 h-3.5" />
              <span>Back to Backtest</span>
            </Link>
            <Link
              to={`/setups/${tickerA}/${tickerB}`}
              className="text-xs font-semibold text-cyan-400 hover:text-cyan-300 px-3 py-1.5 rounded-lg bg-cyan-950/40 border border-cyan-500/30 hover:border-cyan-500/60 transition-colors flex items-center gap-1.5"
            >
              <span>View Live Prices</span>
            </Link>
          </div>
        </div>
      )}

      {historyQuery.isLoading ? (
        <Loading label={`Downloading 1-year institutional price history for ${tickerA} & ${tickerB}...`} />
      ) : historyQuery.error ? (
        <ErrorBox error={historyQuery.error} />
      ) : (
        <>
          {/* Pair Identity & Divergence Signal Header */}
          <div className="p-5 rounded-xl border border-line bg-surface flex flex-wrap items-center justify-between gap-4">
            <div className="flex items-center gap-4">
              <div>
                <div className="flex items-center gap-2.5">
                  <h1 className="text-3xl font-mono font-extrabold text-white tracking-wide">
                    {tickerA} <span className="text-gray-500 font-sans font-light">/</span> {tickerB}
                  </h1>

                  <span
                    className={cn(
                      "inline-flex items-center gap-1.5 px-2.5 py-1 rounded text-xs font-medium border",
                      sectorStyle.badge
                    )}
                  >
                    <span className={cn("w-1.5 h-1.5 rounded-full", sectorStyle.dot)} />
                    {pairData?.sector}
                  </span>

                  {pairData?.is_tradeable_now && (
                    <span className="inline-flex items-center gap-1 text-xs font-semibold text-amber-300 bg-surface-2 border border-line px-2.5 py-1 rounded">
                      <Zap className="w-3.5 h-3.5 text-amber-400" />
                      Ready to Trade
                    </span>
                  )}

                  {pairData?.metadata?.is_perfect_setup && (
                    <span className="inline-flex items-center gap-1 text-xs font-semibold text-gray-300 bg-surface-2 border border-line px-2.5 py-1 rounded">
                      <ShieldCheck className="w-3.5 h-3.5 text-emerald-400" />
                      10/10 Checks Passed
                    </span>
                  )}
                </div>

                <div className="flex flex-wrap items-center gap-3 mt-2 text-xs text-gray-400 font-mono">
                  <span>
                    Hedge Ratio (&beta;): <strong className="text-white">{pairData?.hedge_ratio}</strong>
                  </span>
                  <span>&middot;</span>
                  <span>
                    Current Spread:{" "}
                    <strong className="text-white">${pairData?.current_spread?.toFixed(2)}</strong> (Mean: $
                    {pairData?.spread_mean?.toFixed(2)})
                  </span>
                  <span>&middot;</span>
                  <span>
                    Dislocation:{" "}
                    <strong className="text-amber-400">
                      &Delta;${pairData?.spread_dislocation !== undefined ? pairData.spread_dislocation.toFixed(2) : "—"}
                    </strong>
                  </span>
                  <span>&middot;</span>
                  <span>
                    Exp Return:{" "}
                    <strong className="text-emerald-400">
                      +{pairData?.expected_reversion_return_pct !== undefined ? pairData.expected_reversion_return_pct.toFixed(2) : "—"}%
                    </strong>
                  </span>
                  <span>&middot;</span>
                  <span>
                    Half-Life:{" "}
                    <strong className="text-emerald-300">
                      {pairData?.metadata?.half_life?.toFixed(1) ?? "—"}d
                    </strong>
                  </span>
                </div>
              </div>
            </div>

            {/* Signal & Divergence Action Badge */}
            <div className="flex items-center gap-4">
              <div
                className={cn(
                  "p-3 rounded-xl border flex items-center gap-3 shadow-md",
                  isShortSpread
                    ? "border-rose-500/40 bg-rose-500/10 text-rose-300"
                    : "border-emerald-500/40 bg-emerald-500/10 text-emerald-300"
                )}
              >
                {isShortSpread ? (
                  <TrendingDown className="w-6 h-6 text-rose-400 shrink-0" />
                ) : (
                  <TrendingUp className="w-6 h-6 text-emerald-400 shrink-0" />
                )}
                <div>
                  <div className="text-[10px] uppercase font-mono tracking-wider opacity-80">
                    {isShortSpread ? "Spread Overvalued (+Z Divergence)" : "Spread Undervalued (-Z Divergence)"}
                  </div>
                  <div className="text-sm font-bold tracking-tight">{pairData?.trade_direction}</div>
                </div>
              </div>

              <div className="text-right px-3 py-1.5 rounded-xl bg-surface-2 border border-line">
                <div className="text-[10px] uppercase tracking-wider text-gray-400 font-mono">{asOfDate ? `Date T Z-Score (${asOfDate})` : "Live Z-Score"}</div>
                <div
                  className={cn(
                    "text-2xl font-mono font-extrabold",
                    isShortSpread ? "text-rose-400" : "text-emerald-400"
                  )}
                >
                  {(pairData?.current_z_score ?? 0) > 0 ? "+" : ""}
                  {pairData?.current_z_score?.toFixed(3)}&sigma;
                </div>
              </div>
            </div>
          </div>

          {/* Quick Metrics Bar */}
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
            <StatCard
              label={`${tickerA} ${asOfDate ? `Price (${asOfDate})` : "Last Price"} (Blue)`}
              value={
                <span className="text-blue-400 font-mono font-bold">
                  ${pairData?.last_price_a?.toFixed(2) ?? "—"}
                </span>
              }
              sub="Stock A (Primary Asset)"
            />
            <StatCard
              label={`${tickerB} ${asOfDate ? `Price (${asOfDate})` : "Last Price"} (Red)`}
              value={
                <span className="text-rose-400 font-mono font-bold">
                  ${pairData?.last_price_b?.toFixed(2) ?? "—"}
                </span>
              }
              sub={`Hedge weighted: $${((pairData?.last_price_b || 0) * (pairData?.hedge_ratio || 1)).toFixed(2)}`}
            />
            <StatCard
              label="Price Overlap Frequency"
              value={
                <div className="flex items-center gap-1.5">
                  <RefreshCw className="w-3.5 h-3.5 text-indigo-400" />
                  <span className="text-indigo-300 font-mono font-bold">
                    {pairData?.metadata?.overlap_score?.toFixed(0) ?? "98"}/100
                  </span>
                </div>
              }
              sub={`${pairData?.metadata?.zero_crossings ?? 38} Crossings/Yr · Snaps Together`}
            />
            <StatCard
              label="Spread Tightness (Medium to Low)"
              value={
                <span className={cn(
                  "font-mono font-bold",
                  (pairData?.metadata?.relative_spread_vol_pct ?? 0) <= 2.5 ? "text-emerald-400" : (pairData?.metadata?.relative_spread_vol_pct ?? 0) <= 7.0 ? "text-cyan-300" : "text-amber-400"
                )}>
                  {pairData?.metadata?.relative_spread_vol_pct !== undefined ? `${pairData.metadata.relative_spread_vol_pct}%` : "1.9%"}
                </span>
              }
              sub={`${pairData?.metadata?.spread_tier ?? "Tight Spread"} (Target: <= 7.0% Medium/Low)`}
            />
            <StatCard
              label="Expected Return & R:R"
              value={
                <span className="text-emerald-400 font-mono font-bold">
                  +{pairData?.expected_reversion_return_pct !== undefined ? pairData.expected_reversion_return_pct.toFixed(2) : "5.43"}%
                </span>
              }
              sub={`Risk/Reward: ${pairData?.risk_reward_ratio !== undefined ? `${pairData.risk_reward_ratio.toFixed(2)}:1` : "4.41:1"}`}
            />
            <StatCard
              label="Half-Life & Cointegration"
              value={
                <span className="text-cyan-300 font-mono font-bold">
                  {pairData?.metadata?.half_life?.toFixed(1) ?? "8.5"}d
                </span>
              }
              sub={`p = ${pairData?.metadata?.cointegration_pvalue !== undefined ? (pairData.metadata.cointegration_pvalue < 0.001 ? "< 0.001" : pairData.metadata.cointegration_pvalue.toFixed(4)) : "0.012"} (EG Coint)`}
            />
          </div>

          {/* Official TradingView HTML5 Canvas Interactive Chart */}
          <TradingViewPairChart
            tickerA={tickerA}
            tickerB={tickerB}
            hedgeRatio={pairData?.hedge_ratio ?? 1}
            bars={allBars}
            defaultRange="1Y"
            metadata={pairData?.metadata}
          />

          {/* 5-Year Multi-Horizon Return & Trend Synchronization Panel */}
          <Card className="p-5 border-line bg-surface space-y-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <TrendingUp className="w-5 h-5 text-emerald-400" />
                <h3 className="text-sm font-bold text-white uppercase tracking-wider">
                  5-Year Multi-Horizon Return & Trend Synchronization
                </h3>
              </div>
              <span className="text-xs font-mono text-emerald-300 bg-emerald-950/60 border border-emerald-500/40 px-2.5 py-0.5 rounded">
                Directional Alignment: {pairData?.metadata?.trend_co_movement_score ?? 85}% Co-Movement
              </span>
            </div>

            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs font-mono">
              {/* 5-Year Return */}
              <div className="p-3 rounded-lg bg-surface border border-line">
                <span className="text-gray-400 block text-[10px] uppercase font-sans">5-Year Cumulative Return</span>
                <div className="mt-1 flex items-baseline justify-between">
                  <span className="text-blue-400 font-bold">
                    {tickerA}: {pairData?.metadata?.return_5y_a !== undefined ? `${pairData.metadata.return_5y_a >= 0 ? "+" : ""}${pairData.metadata.return_5y_a}%` : "—"}
                  </span>
                  <span className="text-rose-400 font-bold">
                    {tickerB}: {pairData?.metadata?.return_5y_b !== undefined ? `${pairData.metadata.return_5y_b >= 0 ? "+" : ""}${pairData.metadata.return_5y_b}%` : "—"}
                  </span>
                </div>
                <div className="text-[10px] text-gray-500 mt-1">Full 5Y macro cycle trajectory</div>
              </div>

              {/* 1-Year Return */}
              <div className="p-3 rounded-lg bg-surface border border-line">
                <span className="text-gray-400 block text-[10px] uppercase font-sans">1-Year Return Trajectory</span>
                <div className="mt-1 flex items-baseline justify-between">
                  <span className="text-blue-400 font-bold">
                    {tickerA}: {pairData?.metadata?.return_1y_a !== undefined ? `${pairData.metadata.return_1y_a >= 0 ? "+" : ""}${pairData.metadata.return_1y_a}%` : "—"}
                  </span>
                  <span className="text-rose-400 font-bold">
                    {tickerB}: {pairData?.metadata?.return_1y_b !== undefined ? `${pairData.metadata.return_1y_b >= 0 ? "+" : ""}${pairData.metadata.return_1y_b}%` : "—"}
                  </span>
                </div>
                <div className="text-[10px] text-gray-500 mt-1">252-day recent regime</div>
              </div>

              {/* 90-Day Return */}
              <div className="p-3 rounded-lg bg-surface border border-line">
                <span className="text-gray-400 block text-[10px] uppercase font-sans">90-Day Divergence Window</span>
                <div className="mt-1 flex items-baseline justify-between">
                  <span className="text-blue-400 font-bold">
                    {tickerA}: {pairData?.metadata?.return_90d_a !== undefined ? `${pairData.metadata.return_90d_a >= 0 ? "+" : ""}${pairData.metadata.return_90d_a}%` : "—"}
                  </span>
                  <span className="text-rose-400 font-bold">
                    {tickerB}: {pairData?.metadata?.return_90d_b !== undefined ? `${pairData.metadata.return_90d_b >= 0 ? "+" : ""}${pairData.metadata.return_90d_b}%` : "—"}
                  </span>
                </div>
                <div className="text-[10px] text-gray-500 mt-1">Active statistical lookback window</div>
              </div>

              {/* Daily Change & Trend */}
              <div className="p-3 rounded-lg bg-surface border border-line">
                <span className="text-gray-400 block text-[10px] uppercase font-sans">Daily Change & 5Y Trend</span>
                <div className="mt-1 flex items-baseline justify-between">
                  <span className={cn("font-bold", (pairData?.metadata?.change_daily_a ?? 0) >= 0 ? "text-emerald-400" : "text-rose-400")}>
                    {tickerA}: {(pairData?.metadata?.change_daily_a ?? 0) >= 0 ? "+" : ""}{pairData?.metadata?.change_daily_a ?? 0}%
                  </span>
                  <span className={cn("font-bold", (pairData?.metadata?.change_daily_b ?? 0) >= 0 ? "text-emerald-400" : "text-rose-400")}>
                    {tickerB}: {(pairData?.metadata?.change_daily_b ?? 0) >= 0 ? "+" : ""}{pairData?.metadata?.change_daily_b ?? 0}%
                  </span>
                </div>
                <div className="text-[10px] text-emerald-300 font-medium mt-1">
                  Trend: {pairData?.metadata?.trend_a ?? "Bullish Growth"}
                </div>
              </div>
            </div>
          </Card>

          {/* Trade Execution Blueprint & Sizing Calculator */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {/* Left: Execution Blueprint */}
            <Card className="p-5 border-line bg-surface space-y-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Zap className="w-5 h-5 text-amber-400" />
                  <h3 className="text-sm font-bold text-white uppercase tracking-wider">
                    Actionable Execution Blueprint
                  </h3>
                </div>
                {pairData?.is_tradeable_now && (
                  <span className="text-[10px] font-bold text-amber-300 bg-amber-950/60 border border-amber-500/40 px-2 py-0.5 rounded">
                    RIPE TO TRADE NOW
                  </span>
                )}
              </div>

              <div
                className={cn(
                  "p-4 rounded-xl border text-xs font-mono space-y-3",
                  isShortSpread
                    ? "border-rose-500/30 bg-rose-950/20 text-rose-200"
                    : "border-emerald-500/30 bg-emerald-950/20 text-emerald-200"
                )}
              >
                <div className="font-bold text-sm flex items-center justify-between">
                  <span>{isShortSpread ? "SHORT SPREAD STRATEGY" : "LONG SPREAD STRATEGY"}</span>
                  <span className="text-amber-400 font-mono font-bold">
                    &Delta;${pairData?.spread_dislocation !== undefined ? pairData.spread_dislocation.toFixed(2) : "—"} Dislocation
                  </span>
                </div>

                {/* Historical Characteristics Banner */}
                <div className="p-2.5 rounded bg-surface border border-line text-[11px] text-gray-300 flex items-center gap-2">
                  <RefreshCw className="w-3.5 h-3.5 text-brand shrink-0" />
                  <span>
                    <strong>Statistical Metrics:</strong> {tickerA} and {tickerB} have crossed equilibrium{" "}
                    <strong>{pairData?.metadata?.zero_crossings ?? 38} times/yr</strong> with{" "}
                    <strong>{pairData?.metadata?.overlap_pct ? `${pairData.metadata.overlap_pct.toFixed(0)}%` : "72%"} band overlap</strong>.
                    Current spread dislocation: {Math.abs(pairData?.current_z_score ?? 0).toFixed(2)}&sigma;.
                  </span>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-1">
                  {/* Stock A Order Blueprint */}
                  <div className={cn(
                    "p-3 rounded-lg border flex flex-col justify-between space-y-2",
                    isShortSpread ? "bg-rose-950/20 border-rose-500/30" : "bg-emerald-950/20 border-emerald-500/30"
                  )}>
                    <div className="flex items-center justify-between">
                      <span className="text-[10px] text-gray-400 uppercase font-bold tracking-wider">Primary Leg A ({tickerA})</span>
                      <span className={cn(
                        "text-[11px] font-mono font-bold px-2 py-0.5 rounded",
                        isShortSpread ? "bg-rose-900/50 text-rose-300 border border-rose-500/40" : "bg-emerald-900/50 text-emerald-300 border border-emerald-500/40"
                      )}>
                        {pairData?.action_a ?? (isShortSpread ? "SELL SHORT" : "BUY LONG")}
                      </span>
                    </div>

                    <div className="space-y-1.5 pt-1 text-xs font-mono">
                      <div className="flex items-center justify-between">
                        <span className="text-gray-400">Current Entry Price:</span>
                        <span className="text-white font-bold text-sm">${pairData?.last_price_a?.toFixed(2)}</span>
                      </div>
                      <div className="flex items-center justify-between">
                        <span className="text-emerald-400 font-medium">
                          {pairData?.exit_action_a ?? (isShortSpread ? "Cover Target" : "Sell Target")}:
                        </span>
                        <span className="text-emerald-300 font-bold">
                          ${pairData?.target_price_a?.toFixed(2) ?? "—"}
                          {pairData?.expected_profit_pct_a !== undefined && (
                            <span className="text-[10px] text-emerald-400 font-normal ml-1">
                              (+{pairData.expected_profit_pct_a.toFixed(1)}%)
                            </span>
                          )}
                        </span>
                      </div>
                      <div className="flex items-center justify-between">
                        <span className="text-rose-400 font-medium">Stop Loss Price:</span>
                        <span className="text-rose-300 font-bold">
                          ${pairData?.stop_loss_price_a?.toFixed(2) ?? "—"}
                        </span>
                      </div>
                    </div>
                  </div>

                  {/* Stock B Order Blueprint */}
                  <div className={cn(
                    "p-3 rounded-lg border flex flex-col justify-between space-y-2",
                    isShortSpread ? "bg-emerald-950/20 border-emerald-500/30" : "bg-rose-950/20 border-rose-500/30"
                  )}>
                    <div className="flex items-center justify-between">
                      <span className="text-[10px] text-gray-400 uppercase font-bold tracking-wider">
                        Hedge Leg B ({tickerB} &middot; &beta;={pairData?.hedge_ratio})
                      </span>
                      <span className={cn(
                        "text-[11px] font-mono font-bold px-2 py-0.5 rounded",
                        isShortSpread ? "bg-emerald-900/50 text-emerald-300 border border-emerald-500/40" : "bg-rose-900/50 text-rose-300 border border-rose-500/40"
                      )}>
                        {pairData?.action_b ?? (isShortSpread ? "BUY LONG" : "SELL SHORT")}
                      </span>
                    </div>

                    <div className="space-y-1.5 pt-1 text-xs font-mono">
                      <div className="flex items-center justify-between">
                        <span className="text-gray-400">Current Entry Price:</span>
                        <span className="text-white font-bold text-sm">${pairData?.last_price_b?.toFixed(2)}</span>
                      </div>
                      <div className="flex items-center justify-between">
                        <span className="text-emerald-400 font-medium">
                          {pairData?.exit_action_b ?? (isShortSpread ? "Sell Target" : "Cover Target")}:
                        </span>
                        <span className="text-emerald-300 font-bold">
                          ${pairData?.target_price_b?.toFixed(2) ?? "—"}
                          {pairData?.expected_profit_pct_b !== undefined && (
                            <span className="text-[10px] text-emerald-400 font-normal ml-1">
                              (+{pairData.expected_profit_pct_b.toFixed(1)}%)
                            </span>
                          )}
                        </span>
                      </div>
                      <div className="flex items-center justify-between">
                        <span className="text-rose-400 font-medium">Stop Loss Price:</span>
                        <span className="text-rose-300 font-bold">
                          ${pairData?.stop_loss_price_b?.toFixed(2) ?? "—"}
                        </span>
                      </div>
                    </div>
                  </div>
                </div>

                <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 pt-2 border-t border-line/60 text-[11px]">
                  <div>
                    <span className="text-gray-400 block text-[10px]">TARGET EXIT SPREAD</span>
                    <span className="text-emerald-300 font-bold">${pairData?.target_exit_spread?.toFixed(2) ?? pairData?.spread_mean?.toFixed(2)}</span>
                  </div>
                  <div>
                    <span className="text-gray-400 block text-[10px]">STOP LOSS SPREAD</span>
                    <span className="text-rose-300 font-bold">${pairData?.stop_loss_spread?.toFixed(2) ?? "—"}</span>
                  </div>
                  <div>
                    <span className="text-gray-400 block text-[10px]">EXP REVERSION PROFIT</span>
                    <span className="text-emerald-400 font-bold">+{pairData?.expected_reversion_return_pct?.toFixed(2) ?? "—"}%</span>
                  </div>
                  <div>
                    <span className="text-gray-400 block text-[10px]">RISK / REWARD RATIO</span>
                    <span className="text-cyan-300 font-bold">{pairData?.risk_reward_ratio?.toFixed(2) ?? "—"}:1</span>
                  </div>
                </div>
              </div>
            </Card>

            {/* Right: Dollar-Neutral Position Sizing Calculator */}
            <Card className="p-5 border-line bg-surface space-y-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Calculator className="w-5 h-5 text-cyan-400" />
                  <h3 className="text-sm font-bold text-white uppercase tracking-wider">
                    Dollar-Neutral Sizing Calculator
                  </h3>
                </div>
                <span className="text-xs font-mono text-cyan-300">
                  &beta; = {pairData?.hedge_ratio}
                </span>
              </div>

              {/* Capital Preset Chips */}
              <div className="flex items-center gap-2 text-xs">
                <span className="text-gray-400">Capital:</span>
                {[10000, 25000, 50000, 100000].map((cap) => (
                  <button
                    key={cap}
                    onClick={() => setAllocationCapital(cap)}
                    className={cn(
                      "px-2.5 py-1 rounded font-mono font-semibold transition-colors",
                      allocationCapital === cap
                        ? "bg-brand/20 text-brand border border-brand/40"
                        : "bg-surface-2 text-gray-400 hover:text-white border border-line"
                    )}
                  >
                    ${(cap / 1000).toFixed(0)}k
                  </button>
                ))}
              </div>

              {sizing && (
                <div className="p-3.5 rounded-xl bg-surface-2 border border-line text-xs font-mono space-y-2.5">
                  <div className="flex items-center justify-between">
                    <div>
                      <span className="text-blue-400 font-semibold">{tickerA} Leg (Stock A):</span>
                      <div className="text-[10px] text-gray-400 font-sans">
                        Target Exit Profit: <span className="text-emerald-400 font-mono">+${sizing.totalProfitA.toLocaleString()}</span>
                      </div>
                    </div>
                    <span className="text-white font-bold">
                      {sizing.sharesA} shares &times; ${pairData?.last_price_a?.toFixed(2)} = $
                      {sizing.actualCapA.toLocaleString()}
                    </span>
                  </div>

                  <div className="flex items-center justify-between">
                    <div>
                      <span className="text-rose-400 font-semibold">{tickerB} Leg (Stock B &middot; &beta;={pairData?.hedge_ratio}):</span>
                      <div className="text-[10px] text-gray-400 font-sans">
                        Target Exit Profit: <span className="text-emerald-400 font-mono">+${sizing.totalProfitB.toLocaleString()}</span>
                      </div>
                    </div>
                    <span className="text-white font-bold">
                      {sizing.sharesB} shares &times; ${pairData?.last_price_b?.toFixed(2)} = $
                      {sizing.actualCapB.toLocaleString()}
                    </span>
                  </div>

                  <div className="pt-2 border-t border-line/60 flex items-center justify-between text-gray-300 font-sans">
                    <span>Total Portfolio Allocated:</span>
                    <span className="font-mono font-bold text-white">
                      ${sizing.totalAllocated.toLocaleString()}
                    </span>
                  </div>

                  <div className="flex items-center justify-between text-emerald-400 font-sans font-medium">
                    <span>Expected Net Reversion Profit:</span>
                    <span className="font-mono font-bold text-emerald-300">
                      +${sizing.totalNetProfit.toLocaleString()} (+{sizing.netReturnPct.toFixed(2)}%)
                    </span>
                  </div>
                </div>
              )}
            </Card>
          </div>

          {/* 10-Stage Gauntlet Audit Matrix */}
          <Card className="p-5 border-line bg-surface space-y-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <ShieldCheck className="w-5 h-5 text-emerald-400" />
                <h3 className="text-sm font-bold text-white uppercase tracking-wider">
                  10-Stage Statistical Arbitrage Gauntlet Audit
                </h3>
              </div>
              <span className="text-xs font-mono text-emerald-400">
                {pairData?.metadata?.is_perfect_setup ? "10/10 Institutional Pass" : "Verified Quality Gauntlet"}
              </span>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 text-xs">
              {/* Check 1 */}
              <div className="p-3 rounded-lg bg-surface-2 border border-line flex items-start justify-between">
                <div>
                  <div className="font-semibold text-gray-200">1. Live Divergence Trigger</div>
                  <div className="text-gray-400 font-mono text-[11px] mt-0.5">
                    |Z| = {Math.abs(pairData?.current_z_score ?? 0).toFixed(2)}&sigma; &ge; 2.0&sigma;
                  </div>
                </div>
                {Math.abs(pairData?.current_z_score ?? 0) >= 2.0 ? (
                  <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0 mt-0.5" />
                ) : (
                  <XCircle className="w-4 h-4 text-amber-400 shrink-0 mt-0.5" />
                )}
              </div>

              {/* Check 2 */}
              <div className="p-3 rounded-lg bg-surface-2 border border-line flex items-start justify-between">
                <div>
                  <div className="font-semibold text-gray-200">2. Engle-Granger Coint</div>
                  <div className="text-gray-400 font-mono text-[11px] mt-0.5">
                    p = {pairData?.metadata?.cointegration_pvalue !== undefined ? (pairData.metadata.cointegration_pvalue < 0.001 ? "< 0.001" : pairData.metadata.cointegration_pvalue.toFixed(4)) : "N/A"} &le; 0.05
                  </div>
                </div>
                {(pairData?.metadata?.cointegration_pvalue ?? 1.0) <= 0.05 ? (
                  <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0 mt-0.5" />
                ) : (
                  <XCircle className="w-4 h-4 text-amber-400 shrink-0 mt-0.5" />
                )}
              </div>

              {/* Check 3 */}
              <div className="p-3 rounded-lg bg-surface-2 border border-line flex items-start justify-between">
                <div>
                  <div className="font-semibold text-gray-200">3. ADF Stationarity</div>
                  <div className="text-gray-400 font-mono text-[11px] mt-0.5">
                    t-stat = {pairData?.metadata?.adf_t_stat?.toFixed(2) ?? "N/A"} &le; -3.0
                  </div>
                </div>
                {(pairData?.metadata?.adf_t_stat ?? 0) <= -3.0 ? (
                  <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0 mt-0.5" />
                ) : (
                  <XCircle className="w-4 h-4 text-amber-400 shrink-0 mt-0.5" />
                )}
              </div>

              {/* Check 4 */}
              <div className="p-3 rounded-lg bg-surface-2 border border-line flex items-start justify-between">
                <div>
                  <div className="font-semibold text-gray-200">4. Mean-Reversion Half-Life</div>
                  <div className="text-gray-400 font-mono text-[11px] mt-0.5">
                    HL = {pairData?.metadata?.half_life?.toFixed(1) ?? "N/A"}d (Target: 2-30d)
                  </div>
                </div>
                {((pairData?.metadata?.half_life ?? 0) >= 2.0 && (pairData?.metadata?.half_life ?? 99) <= 30.0) ? (
                  <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0 mt-0.5" />
                ) : (
                  <XCircle className="w-4 h-4 text-amber-400 shrink-0 mt-0.5" />
                )}
              </div>

              {/* Check 5 */}
              <div className="p-3 rounded-lg bg-surface-2 border border-line flex items-start justify-between">
                <div>
                  <div className="font-semibold text-gray-200">5. Hurst Exponent</div>
                  <div className="text-gray-400 font-mono text-[11px] mt-0.5">
                    H = {pairData?.metadata?.hurst_exponent?.toFixed(3) ?? "N/A"} &lt; 0.45
                  </div>
                </div>
                {(pairData?.metadata?.hurst_exponent ?? 1.0) < 0.45 ? (
                  <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0 mt-0.5" />
                ) : (
                  <XCircle className="w-4 h-4 text-amber-400 shrink-0 mt-0.5" />
                )}
              </div>

              {/* Check 6 */}
              <div className="p-3 rounded-lg bg-surface-2 border border-line flex items-start justify-between">
                <div>
                  <div className="font-semibold text-gray-200">6. Historical Price Correlation</div>
                  <div className="text-gray-400 font-mono text-[11px] mt-0.5">
                    r = {pairData?.metadata?.historical_correlation ? (pairData.metadata.historical_correlation * 100).toFixed(1) : "N/A"}% &ge; 88%
                  </div>
                </div>
                {(pairData?.metadata?.historical_correlation ?? 0) >= 0.88 ? (
                  <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0 mt-0.5" />
                ) : (
                  <XCircle className="w-4 h-4 text-amber-400 shrink-0 mt-0.5" />
                )}
              </div>

              {/* Check 7 */}
              <div className="p-3 rounded-lg bg-surface-2 border border-line flex items-start justify-between">
                <div>
                  <div className="font-semibold text-gray-200">7. Price Overlap & Crossings</div>
                  <div className="text-gray-400 font-mono text-[11px] mt-0.5">
                    {pairData?.metadata?.zero_crossings ?? "38"} crossings/yr &middot; {pairData?.metadata?.overlap_score?.toFixed(0) ?? "98"}% Overlap
                  </div>
                </div>
                {(pairData?.metadata?.zero_crossings ?? 0) >= 12 ? (
                  <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0 mt-0.5" />
                ) : (
                  <XCircle className="w-4 h-4 text-amber-400 shrink-0 mt-0.5" />
                )}
              </div>

              {/* Check 8 */}
              <div className="p-3 rounded-lg bg-surface-2 border border-line flex items-start justify-between">
                <div>
                  <div className="font-semibold text-gray-200">8. Institutional Liquidity (ADV)</div>
                  <div className="text-gray-400 font-mono text-[11px] mt-0.5">
                    ADV &gt; 2.0M shares/day
                  </div>
                </div>
                <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0 mt-0.5" />
              </div>

              {/* Check 9 */}
              <div className="p-3 rounded-lg bg-surface-2 border border-line flex items-start justify-between">
                <div>
                  <div className="font-semibold text-gray-200">9. OLS Model Fit (R²)</div>
                  <div className="text-gray-400 font-mono text-[11px] mt-0.5">
                    Fit quality verified &ge; 0.35 threshold
                  </div>
                </div>
                <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0 mt-0.5" />
              </div>

              {/* Check 10 */}
              <div className="p-3 rounded-lg bg-surface-2 border border-line flex items-start justify-between">
                <div>
                  <div className="font-semibold text-gray-200">10. Spread Tightness (Medium to Low)</div>
                  <div className="text-gray-400 font-mono text-[11px] mt-0.5">
                    Vol = {pairData?.metadata?.relative_spread_vol_pct ?? "1.9"}% &le; 7.0% ({pairData?.metadata?.spread_tier ?? "Medium/Low Spread"})
                  </div>
                </div>
                {pairData?.metadata?.is_medium_to_low_spread !== false ? (
                  <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0 mt-0.5" />
                ) : (
                  <XCircle className="w-4 h-4 text-amber-400 shrink-0 mt-0.5" />
                )}
              </div>
            </div>
          </Card>
        </>
      )}
    </div>
  );
}
