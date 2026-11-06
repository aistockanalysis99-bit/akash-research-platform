import React, { useState, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  X,
  Search,
  BarChart2,
  CheckCircle2,
  AlertTriangle,
  ShieldAlert,
  ShieldCheck,
  TrendingUp,
  Activity,
  ArrowRight,
  Filter,
  Eye,
  Info,
} from "lucide-react";
import { api } from "@/lib/api";
import type { AutoTradeSignal, AutoTradeRun } from "@/lib/autoTradeTypes";
import type { PairChartResponse } from "@/lib/simulatorTypes";
import { Badge, Button, Card, Loading, Spinner } from "@/components/ui";

interface UniverseInspectionModalProps {
  isOpen: boolean;
  onClose: () => void;
  signals: AutoTradeSignal[];
  summary?: AutoTradeRun["summary"];
}

// Clean helper for human-readable rejection reasons
function formatReason(reason?: string | null, zScore?: number, failedChecks?: string[]): { title: string; detail: string } {
  if (!reason || reason === "QUALIFIED") {
    return {
      title: "Qualified for Entry",
      detail: "Meets all Strategy 4 hurdle, velocity, and risk criteria.",
    };
  }
  switch (reason) {
    case "ENTRY_Z_BELOW_HURDLE":
      return {
        title: "Normal Spread Band (|Z| < 2.10σ)",
        detail: zScore != null
          ? `Current divergence is ${zScore >= 0 ? "+" : ""}${zScore.toFixed(2)}σ. Strategy 4 requires |Z| ≥ 2.10σ.`
          : "Spread is trading within normal cointegrated equilibrium bands.",
      };
    case "ENTRY_Z_ABOVE_MAX":
      return {
        title: "Divergence Exceeds Safe Cap (|Z| ≥ 3.00σ)",
        detail: "Spread divergence is too extreme, indicating structural regime break rather than mean reversion.",
      };
    case "MOMENTUM_NOT_FLATTENING":
      return {
        title: "Falling Knife / Momentum Not Reversing",
        detail: "Spread velocity is still expanding away from the mean. Entry requires slope ≤ 0.05 or active reversal.",
      };
    case "EARNINGS_BLACKOUT":
      return {
        title: "Quarterly Earnings Blackout",
        detail: "One or both companies report earnings within 5 days before or 2 days after today's session.",
      };
    case "SPREAD_VOLATILITY_CAP":
      return {
        title: "Excessive Spread Volatility (> 5.5%)",
        detail: "Relative spread volatility exceeds institutional safety cap.",
      };
    case "VIX_PANIC_FREEZE":
      return {
        title: "Market Macro Volatility Freeze",
        detail: "Market VIX is elevated above 25.0, freezing new statistical arbitrage entries.",
      };
    case "GAUNTLET_FAILED":
      return {
        title: "Econometric Filter Failed",
        detail: failedChecks && failedChecks.length > 0
          ? `Failed checks: ${failedChecks.join(", ")}.`
          : "Pair failed rolling cointegration or ADF stationarity hurdles.",
      };
    case "PAIR_DATA_UNAVAILABLE":
      return {
        title: "Market Data Unavailable",
        detail: "Insufficient daily bars or delisted ticker.",
      };
    default:
      return {
        title: reason.replace(/_/g, " "),
        detail: "Filtered out by Strategy 4 pre-market execution checks.",
      };
  }
}

function MiniDualPriceChart({ chart }: { chart: PairChartResponse }) {
  const bars = chart.historical_bars;
  if (!bars || bars.length < 5) {
    return <div className="text-xs text-gray-500 py-6 text-center">Insufficient historical bars</div>;
  }

  const pricesA = bars.map((b) => b.price_a);
  const pricesB = bars.map((b) => b.price_b);

  const minA = Math.min(...pricesA);
  const maxA = Math.max(...pricesA);
  const rangeA = maxA - minA || 1;

  const minB = Math.min(...pricesB);
  const maxB = Math.max(...pricesB);
  const rangeB = maxB - minB || 1;

  const width = 600;
  const height = 180;
  const padTop = 15;
  const padBottom = 25;
  const padLeft = 45;
  const padRight = 45;
  const chartW = width - padLeft - padRight;
  const chartH = height - padTop - padBottom;

  const ptsA = bars.map((b, i) => {
    const x = padLeft + (i / (bars.length - 1)) * chartW;
    const y = padTop + chartH - ((b.price_a - minA) / rangeA) * chartH;
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  });

  const ptsB = bars.map((b, i) => {
    const x = padLeft + (i / (bars.length - 1)) * chartW;
    const y = padTop + chartH - ((b.price_b - minB) / rangeB) * chartH;
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  });

  const lastA = bars[bars.length - 1].price_a;
  const lastB = bars[bars.length - 1].price_b;

  return (
    <div className="rounded-lg border border-line/60 bg-slate-950 p-3">
      <div className="flex items-center justify-between text-xs mb-1">
        <span className="font-semibold text-gray-300">Historical Raw Dollar Prices (90-Day Lookback)</span>
        <div className="flex gap-4">
          <span className="text-emerald-400 font-mono">
            {chart.ticker_a}: ${lastA.toFixed(2)}
          </span>
          <span className="text-cyan-400 font-mono">
            {chart.ticker_b}: ${lastB.toFixed(2)}
          </span>
        </div>
      </div>
      <svg viewBox={`0 0 ${width} ${height}`} className="w-full h-44 overflow-visible">
        {/* Horizontal gridlines */}
        <line x1={padLeft} y1={padTop} x2={width - padRight} y2={padTop} stroke="#334155" strokeDasharray="3 3" opacity={0.4} />
        <line x1={padLeft} y1={padTop + chartH / 2} x2={width - padRight} y2={padTop + chartH / 2} stroke="#334155" strokeDasharray="3 3" opacity={0.4} />
        <line x1={padLeft} y1={padTop + chartH} x2={width - padRight} y2={padTop + chartH} stroke="#334155" opacity={0.6} />

        {/* Stock A Path */}
        <polyline fill="none" stroke="#10b981" strokeWidth="2" points={ptsA.join(" ")} />
        {/* Stock B Path */}
        <polyline fill="none" stroke="#06b6d4" strokeWidth="2" points={ptsB.join(" ")} />

        {/* Left Axis Labels (Stock A) */}
        <text x={padLeft - 6} y={padTop + 4} fill="#10b981" fontSize="9" textAnchor="end" fontFamily="monospace">
          ${maxA.toFixed(1)}
        </text>
        <text x={padLeft - 6} y={padTop + chartH} fill="#10b981" fontSize="9" textAnchor="end" fontFamily="monospace">
          ${minA.toFixed(1)}
        </text>

        {/* Right Axis Labels (Stock B) */}
        <text x={width - padRight + 6} y={padTop + 4} fill="#06b6d4" fontSize="9" textAnchor="start" fontFamily="monospace">
          ${maxB.toFixed(1)}
        </text>
        <text x={width - padRight + 6} y={padTop + chartH} fill="#06b6d4" fontSize="9" textAnchor="start" fontFamily="monospace">
          ${minB.toFixed(1)}
        </text>

        {/* Date labels */}
        <text x={padLeft} y={height - 6} fill="#64748b" fontSize="9" textAnchor="start" fontFamily="monospace">
          {bars[0].date}
        </text>
        <text x={width - padRight} y={height - 6} fill="#64748b" fontSize="9" textAnchor="end" fontFamily="monospace">
          {bars[bars.length - 1].date}
        </text>
      </svg>
    </div>
  );
}

function MiniZScoreChart({ chart }: { chart: PairChartResponse }) {
  const bars = chart.historical_bars;
  if (!bars || bars.length < 5) return null;

  const zScores = bars.map((b) => b.z_score);
  const minZ = Math.min(-3.2, Math.min(...zScores) - 0.3);
  const maxZ = Math.max(3.2, Math.max(...zScores) + 0.3);
  const rangeZ = maxZ - minZ || 1;

  const width = 600;
  const height = 150;
  const padTop = 15;
  const padBottom = 20;
  const padLeft = 45;
  const padRight = 45;
  const chartW = width - padLeft - padRight;
  const chartH = height - padTop - padBottom;

  const yForZ = (z: number) => padTop + chartH - ((z - minZ) / rangeZ) * chartH;

  const ptsZ = bars.map((b, i) => {
    const x = padLeft + (i / (bars.length - 1)) * chartW;
    const y = yForZ(b.z_score);
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  });

  const lastBar = bars[bars.length - 1];
  const lastX = padLeft + chartW;
  const lastY = yForZ(lastBar.z_score);

  return (
    <div className="rounded-lg border border-line/60 bg-slate-950 p-3 mt-3">
      <div className="flex items-center justify-between text-xs mb-1">
        <span className="font-semibold text-gray-300">Spread Z-Score Trajectory & Hurdle Bands</span>
        <span className={`font-mono font-bold ${Math.abs(lastBar.z_score) >= 2.1 ? "text-emerald-400" : "text-amber-300"}`}>
          Current Z: {lastBar.z_score >= 0 ? "+" : ""}{lastBar.z_score.toFixed(2)}σ
        </span>
      </div>
      <svg viewBox={`0 0 ${width} ${height}`} className="w-full h-36 overflow-visible">
        {/* Stop Loss Upper (+2.85) */}
        <line x1={padLeft} y1={yForZ(2.85)} x2={width - padRight} y2={yForZ(2.85)} stroke="#ef4444" strokeDasharray="3 3" opacity={0.6} />
        <text x={width - padRight + 4} y={yForZ(2.85) + 3} fill="#ef4444" fontSize="8" fontFamily="monospace">+2.85σ SL</text>

        {/* Upper Entry Hurdle (+2.10) */}
        <line x1={padLeft} y1={yForZ(2.10)} x2={width - padRight} y2={yForZ(2.10)} stroke="#f59e0b" strokeDasharray="4 2" opacity={0.8} />
        <text x={width - padRight + 4} y={yForZ(2.10) + 3} fill="#f59e0b" fontSize="8" fontFamily="monospace">+2.10σ Entry</text>

        {/* Center Mean Line (0.00) */}
        <line x1={padLeft} y1={yForZ(0.0)} x2={width - padRight} y2={yForZ(0.0)} stroke="#94a3b8" strokeDasharray="2 2" opacity={0.5} />
        <text x={width - padRight + 4} y={yForZ(0.0) + 3} fill="#94a3b8" fontSize="8" fontFamily="monospace">0.00σ Mean</text>

        {/* Lower Entry Hurdle (-2.10) */}
        <line x1={padLeft} y1={yForZ(-2.10)} x2={width - padRight} y2={yForZ(-2.10)} stroke="#f59e0b" strokeDasharray="4 2" opacity={0.8} />
        <text x={width - padRight + 4} y={yForZ(-2.10) + 3} fill="#f59e0b" fontSize="8" fontFamily="monospace">-2.10σ Entry</text>

        {/* Stop Loss Lower (-2.85) */}
        <line x1={padLeft} y1={yForZ(-2.85)} x2={width - padRight} y2={yForZ(-2.85)} stroke="#ef4444" strokeDasharray="3 3" opacity={0.6} />
        <text x={width - padRight + 4} y={yForZ(-2.85) + 3} fill="#ef4444" fontSize="8" fontFamily="monospace">-2.85σ SL</text>

        {/* Z-Score Path */}
        <polyline fill="none" stroke="#38bdf8" strokeWidth="2.2" points={ptsZ.join(" ")} />

        {/* Current position dot */}
        <circle cx={lastX} cy={lastY} r="4.5" fill="#38bdf8" stroke="#ffffff" strokeWidth="1.5" />
      </svg>
    </div>
  );
}

export function UniverseInspectionModal({
  isOpen,
  onClose,
  signals,
  summary,
}: UniverseInspectionModalProps) {
  const [search, setSearch] = useState("");
  const [filterTab, setFilterTab] = useState<"ALL" | "NEAR_HURDLE" | "NORMAL" | "QUALIFIED" | "GAUNTLET">("ALL");
  const [selectedPair, setSelectedPair] = useState<AutoTradeSignal | null>(null);

  // Auto-select first pair when modal opens
  React.useEffect(() => {
    if (isOpen && signals.length > 0 && !selectedPair) {
      setSelectedPair(signals[0]);
    }
  }, [isOpen, signals, selectedPair]);

  // Fetch detailed chart data for selected pair
  const cutoffDate = summary?.data_cutoff_date || "2026-11-04";
  const tickerA = selectedPair?.ticker_a;
  const tickerB = selectedPair?.ticker_b;
  const scanChart = selectedPair?.payload.chart_snapshot;

  const chartQuery = useQuery({
    queryKey: ["pair-chart-inspect", tickerA, tickerB, cutoffDate],
    queryFn: () => {
      if (!tickerA || !tickerB) return Promise.reject("No pair selected");
      return api.simulator.pairChart({
        ticker_a: tickerA,
        ticker_b: tickerB,
        current_date: cutoffDate,
        lookback_days: 90,
      });
    },
    enabled: isOpen && !!tickerA && !!tickerB && !scanChart,
    staleTime: 60000,
    retry: 1,
  });

  const filteredSignals = useMemo(() => {
    return signals.filter((s) => {
      const q = search.trim().toUpperCase();
      const p = s.payload;
      const matchesSearch =
        !q ||
        s.ticker_a.toUpperCase().includes(q) ||
        s.ticker_b.toUpperCase().includes(q) ||
        p.pair_name.toUpperCase().includes(q);

      if (!matchesSearch) return false;

      const zAbs = p.z_score != null ? Math.abs(p.z_score) : null;
      if (filterTab === "QUALIFIED") return s.decision === "QUALIFIED";
      if (filterTab === "NEAR_HURDLE") return zAbs != null && zAbs >= 1.5;
      if (filterTab === "NORMAL") return zAbs != null && zAbs < 1.5;
      if (filterTab === "GAUNTLET") return s.rejection_reason === "GAUNTLET_FAILED";
      return true;
    });
  }, [signals, search, filterTab]);

  if (!isOpen) return null;

  const qualifiedCount = signals.filter((s) => s.decision === "QUALIFIED").length;
  const nearCount = signals.filter((s) => s.payload.z_score != null && Math.abs(s.payload.z_score) >= 1.5).length;
  const gauntletCount = signals.filter((s) => s.rejection_reason === "GAUNTLET_FAILED").length;
  const normalCount = signals.filter((s) => s.payload.z_score != null && Math.abs(s.payload.z_score) < 1.5).length;

  const selP = selectedPair?.payload;
  const chartData = scanChart ?? chartQuery.data;
  const reasonFmt = selectedPair ? formatReason(selectedPair.rejection_reason, selP?.z_score, selP?.failed_checks) : null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm p-4">
      <div className="relative flex flex-col w-full max-w-7xl max-h-[92vh] rounded-xl border border-line bg-bg shadow-2xl overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-line/80 px-6 py-4 bg-slate-900/60">
          <div>
            <div className="flex items-center gap-2">
              <BarChart2 className="h-5 w-5 text-brand" />
              <h2 className="text-xl font-bold text-white">Strategy 4 Scanned Universe &amp; Divergence Diagnostics</h2>
              <Badge className="border-gray-700 bg-gray-800 text-gray-300">
                Session {summary?.session_date ?? "Today"}
              </Badge>
            </div>
            <p className="text-xs text-gray-400 mt-1">
              Data Cutoff: <span className="font-mono text-gray-300">{summary?.data_cutoff_date ?? "—"}</span> ·{" "}
              Market Volatility: <span className="font-mono text-gray-300">{summary?.market_vol_pct ?? "—"}%</span> ·{" "}
              Total Evaluated: <span className="font-mono text-gray-300">{signals.length} pairs</span> (
              <span className="text-pos font-semibold">{qualifiedCount} Qualified</span>,{" "}
              <span className="text-gray-400 font-semibold">{signals.length - qualifiedCount} Uncrossed</span>)
            </p>
          </div>
          <button
            onClick={onClose}
            className="rounded-lg p-2 text-gray-400 hover:bg-bg-hover hover:text-white transition-colors"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Toolbar */}
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line/60 px-6 py-3 bg-bg-soft/40">
          {/* Filter Pills */}
          <div className="flex items-center gap-1.5 text-xs">
            <button
              onClick={() => setFilterTab("ALL")}
              className={`rounded-md px-2.5 py-1 font-medium transition-colors ${
                filterTab === "ALL" ? "bg-brand text-bg font-semibold" : "text-gray-400 hover:text-white hover:bg-bg-hover"
              }`}
            >
              All ({signals.length})
            </button>
            <button
              onClick={() => setFilterTab("NEAR_HURDLE")}
              className={`rounded-md px-2.5 py-1 font-medium transition-colors ${
                filterTab === "NEAR_HURDLE" ? "bg-amber-500 text-bg font-semibold" : "text-gray-400 hover:text-white hover:bg-bg-hover"
              }`}
            >
              Near Hurdle |Z| ≥ 1.5σ ({nearCount})
            </button>
            <button
              onClick={() => setFilterTab("NORMAL")}
              className={`rounded-md px-2.5 py-1 font-medium transition-colors ${
                filterTab === "NORMAL" ? "bg-sky-500 text-bg font-semibold" : "text-gray-400 hover:text-white hover:bg-bg-hover"
              }`}
            >
              Normal Band ({normalCount})
            </button>
            <button
              onClick={() => setFilterTab("GAUNTLET")}
              className={`rounded-md px-2.5 py-1 font-medium transition-colors ${
                filterTab === "GAUNTLET" ? "bg-slate-700 text-white font-semibold" : "text-gray-400 hover:text-white hover:bg-bg-hover"
              }`}
            >
              Gauntlet Filtered ({gauntletCount})
            </button>
            <button
              onClick={() => setFilterTab("QUALIFIED")}
              className={`rounded-md px-2.5 py-1 font-medium transition-colors ${
                filterTab === "QUALIFIED" ? "bg-pos text-bg font-semibold" : "text-gray-400 hover:text-white hover:bg-bg-hover"
              }`}
            >
              Qualified ({qualifiedCount})
            </button>
          </div>

          {/* Search box */}
          <div className="relative min-w-[220px]">
            <Search className="absolute left-2.5 top-2.5 h-3.5 w-3.5 text-gray-500" />
            <input
              type="text"
              placeholder="Filter pair (e.g. AAPL, KLAC)..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-full rounded-lg border border-line bg-bg px-8 py-1.5 text-xs text-white placeholder-gray-500 focus:border-brand focus:outline-none"
            />
          </div>
        </div>

        {/* Content Body: Master / Detail Split */}
        <div className="flex-1 grid grid-cols-1 md:grid-cols-12 min-h-0 overflow-hidden">
          {/* Left: Pair List (5 cols) */}
          <div className="md:col-span-5 border-r border-line/60 overflow-y-auto p-4 space-y-2">
            {filteredSignals.length === 0 && (
              <div className="py-12 text-center text-xs text-gray-500">No pairs match the active filter.</div>
            )}
            {filteredSignals.map((sig) => {
              const isSelected = selectedPair?.signal_id === sig.signal_id;
              const p = sig.payload;
              const zVal = p.z_score;
              const isQualified = sig.decision === "QUALIFIED";
              const zColor =
                zVal == null
                  ? "text-gray-500"
                  : Math.abs(zVal) >= 2.1
                  ? "text-emerald-400 font-bold"
                  : Math.abs(zVal) >= 1.5
                  ? "text-amber-400 font-semibold"
                  : "text-sky-300";

              return (
                <div
                  key={sig.signal_id}
                  onClick={() => setSelectedPair(sig)}
                  className={`cursor-pointer rounded-lg border p-3 transition-all ${
                    isSelected
                      ? "border-brand bg-brand/10 shadow-md"
                      : "border-line/60 bg-bg-soft/40 hover:border-line hover:bg-bg-hover/60"
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <span className="font-semibold text-white text-sm">{p.pair_name}</span>
                    <div className="flex items-center gap-2">
                      <span className={`font-mono text-xs ${zColor}`}>
                        {zVal != null ? `Z ${zVal >= 0 ? "+" : ""}${zVal.toFixed(2)}σ` : "Z —"}
                      </span>
                      <Badge
                        className={
                          isQualified
                            ? "border-pos/40 bg-pos/10 text-pos text-[10px]"
                            : "border-gray-700 bg-gray-800 text-gray-400 text-[10px]"
                        }
                      >
                        {sig.decision}
                      </Badge>
                    </div>
                  </div>

                  <div className="mt-1 flex items-center justify-between text-xs text-gray-400">
                    <span>
                      {sig.rejection_reason === "ENTRY_Z_BELOW_HURDLE"
                        ? "Normal Band (|Z| < 2.10σ)"
                        : sig.rejection_reason === "MOMENTUM_NOT_FLATTENING"
                        ? "Falling Knife Guard"
                        : sig.rejection_reason === "EARNINGS_BLACKOUT"
                        ? "Earnings Blackout"
                        : sig.rejection_reason === "GAUNTLET_FAILED"
                        ? "Gauntlet Filtered"
                        : sig.rejection_reason ?? "Qualified"}
                    </span>
                    <span className="font-mono text-[11px] text-gray-500">
                      β {p.hedge_ratio != null ? p.hedge_ratio.toFixed(3) : "—"} · vol{" "}
                      {p.spread_vol_pct != null ? `${p.spread_vol_pct.toFixed(1)}%` : "—"}
                    </span>
                  </div>
                </div>
              );
            })}
          </div>

          {/* Right: Detailed Inspection & Charts (7 cols) */}
          <div className="md:col-span-7 overflow-y-auto p-5 bg-slate-900/20">
            {selectedPair && reasonFmt ? (
              <div className="space-y-4">
                {/* Pair Diagnostic Header */}
                <div className="flex items-start justify-between rounded-lg border border-line/60 bg-bg-soft/60 p-4">
                  <div>
                    <div className="flex items-center gap-2">
                      <h3 className="text-lg font-bold text-white">{selectedPair.payload.pair_name}</h3>
                      <Badge
                        className={
                          selectedPair.decision === "QUALIFIED"
                            ? "border-pos/40 bg-pos/10 text-pos"
                            : "border-gray-700 bg-gray-800 text-gray-400"
                        }
                      >
                        {selectedPair.decision}
                      </Badge>
                    </div>
                    <div className="mt-1 text-sm font-medium text-amber-300 flex items-center gap-1.5">
                      <Info className="h-4 w-4 shrink-0 text-amber-400" />
                      <span>{reasonFmt.title}</span>
                    </div>
                    <p className="text-xs text-gray-400 mt-0.5">{reasonFmt.detail}</p>
                  </div>

                  <div className="text-right">
                    <div className="text-xs uppercase text-gray-500">Current Spread Z</div>
                    <div
                      className={`text-xl font-bold font-mono stat-num ${
                        selP?.z_score != null && Math.abs(selP.z_score) >= 2.1
                          ? "text-emerald-400"
                          : "text-amber-300"
                      }`}
                    >
                      {selP?.z_score != null ? `${selP.z_score >= 0 ? "+" : ""}${selP.z_score.toFixed(2)}σ` : "—"}
                    </div>
                  </div>
                </div>

                {/* Scorecard Grid */}
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs">
                  <div className="rounded border border-line/60 bg-bg-soft p-2.5">
                    <span className="text-gray-500 uppercase tracking-wider text-[10px]">Hedge Ratio (β)</span>
                    <div className="text-sm font-bold font-mono text-white mt-0.5">
                      {selP?.hedge_ratio != null ? selP.hedge_ratio.toFixed(4) : "—"}
                    </div>
                  </div>
                  <div className="rounded border border-line/60 bg-bg-soft p-2.5">
                    <span className="text-gray-500 uppercase tracking-wider text-[10px]">Spread Volatility</span>
                    <div className="text-sm font-bold font-mono text-white mt-0.5">
                      {selP?.spread_vol_pct != null ? `${selP.spread_vol_pct.toFixed(2)}%` : "—"}
                    </div>
                  </div>
                  <div className="rounded border border-line/60 bg-bg-soft p-2.5">
                    <span className="text-gray-500 uppercase tracking-wider text-[10px]">Mean Reversion Half-Life</span>
                    <div className="text-sm font-bold font-mono text-white mt-0.5">
                      {selP?.half_life_days != null ? `${selP.half_life_days.toFixed(1)}d` : "—"}
                    </div>
                  </div>
                  <div className="rounded border border-line/60 bg-bg-soft p-2.5">
                    <span className="text-gray-500 uppercase tracking-wider text-[10px]">Composite Score</span>
                    <div className="text-sm font-bold font-mono text-brand mt-0.5">
                      {selP?.composite_score != null ? selP.composite_score.toFixed(1) : "—"}
                    </div>
                  </div>
                </div>

                {/* Interactive Visual Inspection: Dual Price Chart & Z-Score Trajectory */}
                <div>
                  {chartQuery.isLoading && !scanChart && <Loading label="Fetching 90-day price series and spread trajectory…" />}
                  {chartQuery.isError && !scanChart && (
                    <div className="rounded-lg border border-line/60 bg-bg-soft/40 p-4 text-xs text-gray-400">
                      Historical bar data unavailable for this ticker pair.
                    </div>
                  )}
                  {chartData && (
                    <>
                      <MiniDualPriceChart chart={chartData} />
                      <MiniZScoreChart chart={chartData} />
                    </>
                  )}
                </div>
              </div>
            ) : (
              <div className="py-20 text-center text-sm text-gray-500">
                Select a pair on the left to inspect its live charts and quantitative scorecard.
              </div>
            )}
          </div>
        </div>

        {/* Modal Footer */}
        <div className="flex items-center justify-between border-t border-line/80 px-6 py-3 bg-slate-900/60 text-xs text-gray-400">
          <span>
            Strategy 4 Rule: New entries are triggered strictly when |Z| ≥ 2.10σ with velocity confirmation.
          </span>
          <Button variant="outline" onClick={onClose}>
            Close Inspection
          </Button>
        </div>
      </div>
    </div>
  );
}
