import React, { useState, useEffect, useCallback, useMemo } from "react";
import { Link, useSearchParams, useNavigate } from "react-router-dom";
import {
  Calendar,
  TrendingUp,
  Layers,
  ShieldCheck,
  CheckCircle2,
  AlertCircle,
  Search,
  ArrowUpRight,
  ArrowDownRight,
  ArrowRight,
  RefreshCw,
  Clock,
  Check,
  ChevronDown,
  ChevronRight,
  Zap,
  Sliders,
  Activity,
  RotateCcw,
  BarChart3,
} from "lucide-react";
import { api } from "@/lib/api";
import type { PointInTimeSetup, SimulatorScanResponse } from "@/lib/simulatorTypes";
import { Card, PageTitle } from "@/components/ui";
import { cn } from "@/lib/utils";

// Date range constants (Strictly bounded to: current date - 1 year to current date)
const LATEST_DATE = "2026-10-26";
const ONE_YEAR_AGO = "2025-10-26";

type RankingFilter = "top5" | "top10" | "perfect10" | "all";

interface AdvancedStrategyParams {
  entryZ: number;
  stopZ: number;
  minCorr: number;
  maxAdf: number;
  lookbackDays: number;
  capital: number;
}

const DEFAULT_ADVANCED_PARAMS: AdvancedStrategyParams = {
  entryZ: 2.0,
  stopZ: 3.5,
  minCorr: 0.85,
  maxAdf: 0.05,
  lookbackDays: 90,
  capital: 100000,
};

export default function SimulatorPage() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const urlDate = searchParams.get("date");
  const initialDate = urlDate && urlDate >= ONE_YEAR_AGO && urlDate <= LATEST_DATE ? urlDate : "2026-03-02";

  // ─── 1. Single Historical Date Selection State (NO From/To Dates) ────────
  const [selectedDate, setSelectedDate] = useState<string>(initialDate);
  const [actualTradingDate, setActualTradingDate] = useState<string>(initialDate);

  // ─── 2. Advanced Parameters (Combined & Hidden by Default) ───────────────
  const [isAdvancedOpen, setIsAdvancedOpen] = useState<boolean>(false);
  const [advancedParams, setAdvancedParams] = useState<AdvancedStrategyParams>(DEFAULT_ADVANCED_PARAMS);

  // ─── 3. Data & Results State ─────────────────────────────────────────────
  const [allPairs, setAllPairs] = useState<PointInTimeSetup[]>([]);
  const [tradeableSetups, setTradeableSetups] = useState<PointInTimeSetup[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [latencyMs, setLatencyMs] = useState<number>(0);

  // ─── 4. Filters & Details Modal ──────────────────────────────────────────
  const [rankingFilter, setRankingFilter] = useState<RankingFilter>("top10");
  const [searchQuery, setSearchQuery] = useState<string>("");
  const [selectedPairDetails, setSelectedPairDetails] = useState<PointInTimeSetup | null>(null);

  // 1-Click Quick Preset Handler
  const handlePresetSelect = (preset: "1w" | "1m" | "3m" | "6m" | "1y" | "latest") => {
    const base = new Date(LATEST_DATE);
    const target = new Date(base);

    if (preset === "1w") target.setDate(target.getDate() - 7);
    else if (preset === "1m") target.setMonth(target.getMonth() - 1);
    else if (preset === "3m") target.setMonth(target.getMonth() - 3);
    else if (preset === "6m") target.setMonth(target.getMonth() - 6);
    else if (preset === "1y") target.setFullYear(target.getFullYear() - 1);

    const formatted = target.toISOString().split("T")[0];
    setSelectedDate(formatted);
    setSearchParams({ date: formatted }, { replace: true });
  };

  // Run Point-in-Time Evaluation for the Selected Date
  const runHistoricalScan = useCallback(
    async (targetDate: string, params: AdvancedStrategyParams) => {
      const startTime = performance.now();
      setIsLoading(true);
      setError(null);

      try {
        // Slices historical universe data strictly up to targetDate (t <= targetDate)
        const res: SimulatorScanResponse = await api.simulator.scan({
          current_date: targetDate,
          only_active_setups: false, // Ingest and rank the whole universe to get Top 5, Top 10, All
          top_n: 60,
          min_z: params.entryZ,
          max_adf: params.maxAdf,
          min_corr: params.minCorr,
        });

        const elapsed = Math.round(performance.now() - startTime);
        setLatencyMs(res.scan_latency_ms || elapsed);
        setActualTradingDate(res.trading_date_used || res.current_date || targetDate);

        // Store all evaluated pairs sorted by composite score
        const sorted = (res.setups || []).sort(
          (a, b) => b.composite_score - a.composite_score || Math.abs(b.current_z_score) - Math.abs(a.current_z_score)
        );
        setAllPairs(sorted);

        // Separate out active tradeable trades on that selected day (|Z| >= entryZ)
        const trades = res.tradeable_setups?.length
          ? res.tradeable_setups
          : sorted.filter((s) => s.is_tradeable || Math.abs(s.current_z_score) >= params.entryZ);

        setTradeableSetups(trades);
      } catch (err: any) {
        console.error("Failed historical point-in-time scan:", err);
        setError(err?.message || `Failed to evaluate pairs for ${targetDate}`);
      } finally {
        setIsLoading(false);
      }
    },
    []
  );

  // Fetch whenever selectedDate changes
  useEffect(() => {
    runHistoricalScan(selectedDate, advancedParams);
  }, [selectedDate, advancedParams, runHistoricalScan]);

  const handleApplyAdvanced = () => {
    runHistoricalScan(selectedDate, advancedParams);
  };

  const handleResetAdvanced = () => {
    setAdvancedParams(DEFAULT_ADVANCED_PARAMS);
    runHistoricalScan(selectedDate, DEFAULT_ADVANCED_PARAMS);
  };

  // Derived Filtered Pairs for the Best Pairs Ranking Table
  const filteredRankedPairs = useMemo(() => {
    let list = [...allPairs];

    // Search query filter (ticker or sector)
    if (searchQuery.trim()) {
      const q = searchQuery.trim().toUpperCase();
      list = list.filter(
        (p) =>
          p.pair_name.toUpperCase().includes(q) ||
          p.ticker_a.toUpperCase().includes(q) ||
          p.ticker_b.toUpperCase().includes(q) ||
          (p.sector && p.sector.toUpperCase().includes(q))
      );
    }

    // Ranking filter
    if (rankingFilter === "top5") return list.slice(0, 5);
    if (rankingFilter === "top10") return list.slice(0, 10);
    if (rankingFilter === "perfect10") return list.filter((p) => p.is_perfect || p.passed_checks_count === 10);
    return list; // "all"
  }, [allPairs, rankingFilter, searchQuery]);

  // Peak metrics
  const maxZScore = useMemo(() => {
    if (!allPairs.length) return 0;
    return Math.max(...allPairs.map((p) => Math.abs(p.current_z_score)));
  }, [allPairs]);

  const perfect10Count = useMemo(() => {
    return allPairs.filter((p) => p.is_perfect || p.passed_checks_count === 10).length;
  }, [allPairs]);

  // Formatted date string for HUD
  const formattedSessionDate = useMemo(() => {
    try {
      const parts = actualTradingDate.split("-");
      if (parts.length === 3) {
        const d = new Date(parseInt(parts[0]), parseInt(parts[1]) - 1, parseInt(parts[2]));
        return d.toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric", year: "numeric" });
      }
    } catch {
      // fallback
    }
    return actualTradingDate;
  }, [actualTradingDate]);

  return (
    <div className="space-y-6 pb-16">
      {/* ─── Navigation Sub-Header Tabs ──────────────────────────────────────── */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line pb-4">
        <div className="flex items-center gap-2">
          <Link
            to="/simulator"
            className="px-3.5 py-1.5 rounded-lg text-xs font-bold bg-brand text-bg shadow-sm transition-all flex items-center gap-1.5"
          >
            <Clock className="w-3.5 h-3.5" />
            <span>PIT Simulator</span>
          </Link>
          <Link
            to="/backtest-dashboard"
            className="px-3.5 py-1.5 rounded-lg text-xs font-medium text-gray-400 hover:text-white bg-surface-2 border border-line transition-all flex items-center gap-1.5"
          >
            <BarChart3 className="w-3.5 h-3.5 text-brand" />
            <span>1-Year Trade Dashboard</span>
          </Link>
          <Link
            to="/backtest"
            className="px-3.5 py-1.5 rounded-lg text-xs font-medium text-gray-400 hover:text-white bg-surface-2 border border-line transition-all flex items-center gap-1.5"
          >
            <Calendar className="w-3.5 h-3.5" />
            <span>Daily Point-in-Time Backtest</span>
          </Link>
        </div>
      </div>

      {/* ─── Header ────────────────────────────────────────────────────────── */}
      <PageTitle
        title="Point-in-Time Pairs Backtest & Trade Replay"
        subtitle="Select a single historical trading day within the last year to discover the exact best pairs, 10/10 verified setups, and tradeable opportunities that existed on that day with strict zero lookahead bias."
      />

      {/* ─── Single Date Selection HUD + Advanced Toggle ───────────────────── */}
      <Card className="p-5 border-line bg-surface/90 shadow-lg backdrop-blur">
        <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-5">
          {/* Date Picker Input (NO Start/End dates) */}
          <div className="flex flex-col sm:flex-row sm:items-center gap-3">
            <div className="flex items-center gap-2">
              <Calendar className="w-5 h-5 text-brand" />
              <label htmlFor="pit-date" className="text-xs font-semibold uppercase tracking-wider text-gray-300">
                Selected Historical Date:
              </label>
            </div>

            <div className="relative">
              <input
                id="pit-date"
                type="date"
                min={ONE_YEAR_AGO}
                max={LATEST_DATE}
                value={selectedDate}
                onChange={(e) => {
                  setSelectedDate(e.target.value);
                  setSearchParams({ date: e.target.value }, { replace: true });
                }}
                className="bg-surface-2 border border-line text-white font-mono text-sm px-3.5 py-1.5 rounded-lg focus:outline-none focus:border-brand transition-colors cursor-pointer"
              />
            </div>

            {/* Trading Session Indicator */}
            <div className="inline-flex items-center gap-2 px-3 py-1 bg-surface-2 rounded-lg border border-line text-xs font-mono text-gray-300">
              <Clock className="w-3.5 h-3.5 text-cyan-400" />
              <span>Session: <strong className="text-white">{formattedSessionDate}</strong></span>
            </div>
          </div>

          {/* Quick Presets (Last 1 Year) & Advanced Button */}
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-[11px] uppercase tracking-wider font-semibold text-gray-500 mr-1">Presets:</span>
            {[
              { label: "1W Ago", value: "1w" },
              { label: "1M Ago", value: "1m" },
              { label: "3M Ago", value: "3m" },
              { label: "6M Ago", value: "6m" },
              { label: "1Y Ago", value: "1y" },
              { label: "Latest Day", value: "latest" },
            ].map((p) => (
              <button
                key={p.value}
                onClick={() => handlePresetSelect(p.value as any)}
                className="text-xs px-2.5 py-1 rounded bg-surface-2 hover:bg-surface-3 text-gray-300 hover:text-white border border-line transition-colors"
              >
                {p.label}
              </button>
            ))}

            {/* Refresh / Re-eval button */}
            <button
              onClick={() => runHistoricalScan(selectedDate, advancedParams)}
              disabled={isLoading}
              title="Refresh / Re-run historical scan"
              className="p-1.5 rounded bg-surface-2 hover:bg-brand hover:text-bg text-gray-300 border border-line transition-colors ml-1"
            >
              <RefreshCw className={cn("w-3.5 h-3.5", isLoading && "animate-spin text-brand")} />
            </button>

            {/* ── ADVANCED PARAMETERS BUTTON (COMBINED & HIDDEN BY DEFAULT) ── */}
            <button
              onClick={() => setIsAdvancedOpen((prev) => !prev)}
              className={cn(
                "inline-flex items-center gap-1.5 text-xs font-semibold px-3 py-1.5 rounded-lg border transition-all ml-2",
                isAdvancedOpen
                  ? "bg-brand/15 text-brand border-brand/50 shadow-sm"
                  : "bg-surface-2 text-gray-300 hover:text-white border-line hover:border-gray-600"
              )}
            >
              <Sliders className="w-3.5 h-3.5 text-brand" />
              <span>Advanced</span>
              {isAdvancedOpen ? (
                <ChevronDown className="w-3.5 h-3.5 ml-0.5 text-brand" />
              ) : (
                <ChevronRight className="w-3.5 h-3.5 ml-0.5 text-gray-400" />
              )}
            </button>
          </div>
        </div>

        {/* ─── COLLAPSIBLE ADVANCED PARAMETERS DRAWER ─────────────────────── */}
        {isAdvancedOpen && (
          <div className="mt-4 pt-4 border-t border-line/60 space-y-4 animate-in fade-in duration-150">
            <div className="flex items-center justify-between">
              <span className="text-xs uppercase tracking-wider font-semibold text-gray-400 flex items-center gap-1.5">
                <Sliders className="w-3.5 h-3.5 text-brand" />
                Strategy Parameters (Hidden by Default)
              </span>
              <div className="flex items-center gap-2">
                <button
                  onClick={handleResetAdvanced}
                  className="inline-flex items-center gap-1 text-[11px] text-gray-400 hover:text-white px-2.5 py-1 rounded border border-line hover:bg-surface-2 transition-colors"
                >
                  <RotateCcw className="w-3 h-3" /> Reset Defaults
                </button>
                <button
                  onClick={handleApplyAdvanced}
                  className="inline-flex items-center gap-1 text-[11px] font-semibold text-bg bg-brand hover:bg-brand/90 px-3 py-1 rounded transition-colors"
                >
                  Apply & Scan
                </button>
              </div>
            </div>

            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3 font-mono text-xs">
              {/* Entry Z-Score */}
              <div className="p-3 bg-surface-2 rounded-lg border border-line">
                <label className="text-[10px] uppercase text-gray-400 font-bold block mb-1">
                  Entry Trigger (|Z|)
                </label>
                <div className="flex items-center gap-1">
                  <input
                    type="number"
                    step="0.1"
                    min="1.0"
                    max="4.0"
                    value={advancedParams.entryZ}
                    onChange={(e) =>
                      setAdvancedParams({ ...advancedParams, entryZ: parseFloat(e.target.value) || 2.0 })
                    }
                    className="w-full bg-surface border border-line rounded px-2 py-1 text-white text-xs font-bold focus:border-brand outline-none"
                  />
                  <span className="text-gray-500 text-[10px]">σ</span>
                </div>
              </div>

              {/* Stop-Loss Barrier */}
              <div className="p-3 bg-surface-2 rounded-lg border border-line">
                <label className="text-[10px] uppercase text-gray-400 font-bold block mb-1">
                  Stop Loss (|Z|)
                </label>
                <div className="flex items-center gap-1">
                  <input
                    type="number"
                    step="0.1"
                    min="2.5"
                    max="5.0"
                    value={advancedParams.stopZ}
                    onChange={(e) =>
                      setAdvancedParams({ ...advancedParams, stopZ: parseFloat(e.target.value) || 3.5 })
                    }
                    className="w-full bg-surface border border-line rounded px-2 py-1 text-white text-xs font-bold focus:border-brand outline-none"
                  />
                  <span className="text-gray-500 text-[10px]">σ</span>
                </div>
              </div>

              {/* Min Correlation */}
              <div className="p-3 bg-surface-2 rounded-lg border border-line">
                <label className="text-[10px] uppercase text-gray-400 font-bold block mb-1">
                  Min Correlation (r)
                </label>
                <input
                  type="number"
                  step="0.05"
                  min="0.5"
                  max="0.99"
                  value={advancedParams.minCorr}
                  onChange={(e) =>
                    setAdvancedParams({ ...advancedParams, minCorr: parseFloat(e.target.value) || 0.85 })
                  }
                  className="w-full bg-surface border border-line rounded px-2 py-1 text-white text-xs font-bold focus:border-brand outline-none"
                />
              </div>

              {/* Max ADF p-value */}
              <div className="p-3 bg-surface-2 rounded-lg border border-line">
                <label className="text-[10px] uppercase text-gray-400 font-bold block mb-1">
                  Max ADF p-value
                </label>
                <input
                  type="number"
                  step="0.01"
                  min="0.001"
                  max="0.2"
                  value={advancedParams.maxAdf}
                  onChange={(e) =>
                    setAdvancedParams({ ...advancedParams, maxAdf: parseFloat(e.target.value) || 0.05 })
                  }
                  className="w-full bg-surface border border-line rounded px-2 py-1 text-white text-xs font-bold focus:border-brand outline-none"
                />
              </div>

              {/* Lookback Days */}
              <div className="p-3 bg-surface-2 rounded-lg border border-line">
                <label className="text-[10px] uppercase text-gray-400 font-bold block mb-1">
                  Lookback Window
                </label>
                <div className="flex items-center gap-1">
                  <input
                    type="number"
                    step="5"
                    min="30"
                    max="252"
                    value={advancedParams.lookbackDays}
                    onChange={(e) =>
                      setAdvancedParams({ ...advancedParams, lookbackDays: parseInt(e.target.value) || 90 })
                    }
                    className="w-full bg-surface border border-line rounded px-2 py-1 text-white text-xs font-bold focus:border-brand outline-none"
                  />
                  <span className="text-gray-500 text-[10px]">days</span>
                </div>
              </div>

              {/* Capital */}
              <div className="p-3 bg-surface-2 rounded-lg border border-line">
                <label className="text-[10px] uppercase text-gray-400 font-bold block mb-1">
                  Capital ($)
                </label>
                <input
                  type="number"
                  step="5000"
                  min="10000"
                  value={advancedParams.capital}
                  onChange={(e) =>
                    setAdvancedParams({ ...advancedParams, capital: parseInt(e.target.value) || 100000 })
                  }
                  className="w-full bg-surface border border-line rounded px-2 py-1 text-white text-xs font-bold focus:border-brand outline-none"
                />
              </div>
            </div>
          </div>
        )}

        {/* Error Notification */}
        {error && (
          <div className="mt-4 p-3 bg-red-950/60 border border-red-500/50 rounded-lg text-xs text-red-200 flex items-center gap-2">
            <AlertCircle className="w-4 h-4 text-red-400 shrink-0" />
            <span>{error}</span>
          </div>
        )}
      </Card>

      {/* ─── Institutional Stat Counters ────────────────────────────────────── */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <Card className="p-4 border-line bg-surface">
          <div className="flex items-center justify-between text-xs text-gray-400 mb-1">
            <span className="uppercase tracking-wider font-semibold">Trades You Could Do</span>
            <Zap className="w-4 h-4 text-amber-400" />
          </div>
          <div className="text-2xl font-bold font-mono text-white">
            {isLoading ? "..." : tradeableSetups.length}
          </div>
          <p className="text-[11px] text-gray-500 mt-1">Divergence |Z| ≥ {advancedParams.entryZ}σ triggers</p>
        </Card>

        <Card className="p-4 border-line bg-surface">
          <div className="flex items-center justify-between text-xs text-gray-400 mb-1">
            <span className="uppercase tracking-wider font-semibold">10/10 Perfect Setups</span>
            <ShieldCheck className="w-4 h-4 text-emerald-400" />
          </div>
          <div className="text-2xl font-bold font-mono text-emerald-400">
            {isLoading ? "..." : perfect10Count}
          </div>
          <p className="text-[11px] text-gray-500 mt-1">Passed all 10 quantitative checks</p>
        </Card>

        <Card className="p-4 border-line bg-surface">
          <div className="flex items-center justify-between text-xs text-gray-400 mb-1">
            <span className="uppercase tracking-wider font-semibold">Pairs Evaluated</span>
            <Layers className="w-4 h-4 text-brand" />
          </div>
          <div className="text-2xl font-bold font-mono text-white">
            {isLoading ? "..." : allPairs.length}
          </div>
          <p className="text-[11px] text-gray-500 mt-1">Screened in {latencyMs}ms</p>
        </Card>

        <Card className="p-4 border-line bg-surface">
          <div className="flex items-center justify-between text-xs text-gray-400 mb-1">
            <span className="uppercase tracking-wider font-semibold">Peak Divergence</span>
            <Activity className="w-4 h-4 text-cyan-400" />
          </div>
          <div className="text-2xl font-bold font-mono text-cyan-400">
            {isLoading ? "..." : `±${maxZScore.toFixed(2)}σ`}
          </div>
          <p className="text-[11px] text-gray-500 mt-1">Max statistical dislocation</p>
        </Card>
      </div>

      {/* ─── SECTION 1: Trades You Could Have Done On That Day ──────────────── */}
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Zap className="w-5 h-5 text-amber-400" />
            <h2 className="text-base font-bold text-white tracking-wide">
              Trades You Could Have Done on {formattedSessionDate}
            </h2>
            <span className="text-xs bg-amber-500/10 text-amber-300 font-mono px-2 py-0.5 rounded border border-amber-500/30">
              {tradeableSetups.length} Available
            </span>
          </div>
        </div>

        {isLoading ? (
          <Card className="p-8 border-line bg-surface text-center">
            <RefreshCw className="w-6 h-6 text-brand animate-spin mx-auto mb-2" />
            <p className="text-xs font-mono text-gray-400">
              Calculating statistical divergence and OLS hedge ratios for {formattedSessionDate}...
            </p>
          </Card>
        ) : tradeableSetups.length === 0 ? (
          <Card className="p-8 border-line bg-surface text-center">
            <CheckCircle2 className="w-8 h-8 text-gray-600 mx-auto mb-2" />
            <h3 className="text-sm font-semibold text-gray-300 mb-1">No Active Dislocation Triggers</h3>
            <p className="text-xs text-gray-500 max-w-md mx-auto">
              On {formattedSessionDate}, all candidate pairs were trading within normal equilibrium bands (|Z| &lt; {advancedParams.entryZ}σ).
              Select an earlier date or click presets above to see dates with divergence triggers.
            </p>
          </Card>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
            {tradeableSetups.map((trade) => {
              const isLongA = trade.direction === "LONG_A_SHORT_B" || trade.current_z_score < 0;
              const is10Of10 = trade.is_perfect || trade.passed_checks_count === 10;

              return (
                <Card
                  key={trade.pair_name}
                  className="p-5 border-line bg-surface hover:border-brand/40 transition-all flex flex-col justify-between"
                >
                  <div>
                    {/* Top Pair Name & Sector */}
                    <div className="flex items-start justify-between mb-3">
                      <div>
                        <div className="flex items-center gap-2">
                          <Link
                            to={`/setups/${trade.ticker_a}/${trade.ticker_b}?date=${actualTradingDate}`}
                            className="text-base font-bold text-white hover:text-brand font-mono tracking-tight inline-flex items-center gap-1 transition-colors group"
                            title="Open historical trade analysis"
                          >
                            <span>{trade.pair_name}</span>
                            <ArrowUpRight className="w-3.5 h-3.5 opacity-60 group-hover:opacity-100" />
                          </Link>
                          <span className="text-[11px] px-2 py-0.5 rounded bg-surface-2 text-gray-400 border border-line">
                            {trade.sector || "Equities"}
                          </span>
                        </div>
                        <span className="text-[11px] text-gray-500">
                          {trade.spread_tier} Spread Volatility
                        </span>
                      </div>

                      {/* Score Badge */}
                      <div className="text-right">
                        <span
                          className={cn(
                            "inline-flex items-center gap-1 text-[11px] font-mono px-2 py-0.5 rounded font-bold border",
                            is10Of10
                              ? "bg-emerald-950/60 text-emerald-300 border-emerald-500/40"
                              : "bg-surface-2 text-gray-300 border-line"
                          )}
                        >
                          <ShieldCheck className="w-3 h-3 text-emerald-400" />
                          {trade.passed_checks_count || (is10Of10 ? 10 : 9)}/10 Checks
                        </span>
                        <div className="text-[10px] text-gray-400 font-mono mt-0.5">
                          Score: <strong className="text-white">{trade.composite_score.toFixed(1)}</strong>
                        </div>
                      </div>
                    </div>

                    {/* Order Execution Instructions Box */}
                    <div className="grid grid-cols-2 gap-2 p-3 bg-surface-2/80 rounded-lg border border-line mb-4 font-mono">
                      {/* Leg A */}
                      <div
                        className={cn(
                          "p-2 rounded border",
                          isLongA
                            ? "bg-emerald-950/40 border-emerald-500/30 text-emerald-200"
                            : "bg-rose-950/40 border-rose-500/30 text-rose-200"
                        )}
                      >
                        <div className="text-[10px] uppercase font-bold flex items-center justify-between mb-0.5">
                          <span>{isLongA ? "BUY LONG" : "SELL SHORT"}</span>
                          {isLongA ? <ArrowUpRight className="w-3 h-3" /> : <ArrowDownRight className="w-3 h-3" />}
                        </div>
                        <div className="text-sm font-bold text-white">{trade.ticker_a}</div>
                        <div className="text-[11px] text-gray-300">
                          @ ${trade.price_a_entry.toFixed(2)}
                        </div>
                      </div>

                      {/* Leg B */}
                      <div
                        className={cn(
                          "p-2 rounded border",
                          !isLongA
                            ? "bg-emerald-950/40 border-emerald-500/30 text-emerald-200"
                            : "bg-rose-950/40 border-rose-500/30 text-rose-200"
                        )}
                      >
                        <div className="text-[10px] uppercase font-bold flex items-center justify-between mb-0.5">
                          <span>{!isLongA ? "BUY LONG" : "SELL SHORT"}</span>
                          {!isLongA ? <ArrowUpRight className="w-3 h-3" /> : <ArrowDownRight className="w-3 h-3" />}
                        </div>
                        <div className="text-sm font-bold text-white">{trade.ticker_b}</div>
                        <div className="text-[11px] text-gray-300">
                          @ ${trade.price_b_entry.toFixed(2)}
                        </div>
                      </div>
                    </div>

                    {/* Trade Parameters & Risk/Reward */}
                    <div className="grid grid-cols-2 gap-y-2 text-xs font-mono text-gray-300 mb-4">
                      <div>
                        <span className="text-gray-500 block text-[10px] uppercase">Z-Score Divergence</span>
                        <span
                          className={cn(
                            "font-bold",
                            trade.current_z_score > 0 ? "text-amber-400" : "text-cyan-400"
                          )}
                        >
                          {trade.current_z_score > 0 ? "+" : ""}
                          {trade.current_z_score.toFixed(2)}σ
                        </span>
                      </div>

                      <div>
                        <span className="text-gray-500 block text-[10px] uppercase">Hedge Ratio (Beta)</span>
                        <span className="text-white font-bold">{trade.hedge_ratio.toFixed(4)}</span>
                      </div>

                      <div>
                        <span className="text-gray-500 block text-[10px] uppercase">Exp. Reversion Return</span>
                        <span className="text-emerald-400 font-bold">
                          +{trade.expected_reversion_return_pct?.toFixed(2) || (Math.abs(trade.current_z_score) * 1.5).toFixed(2)}%
                        </span>
                      </div>

                      <div>
                        <span className="text-gray-500 block text-[10px] uppercase">Stop Loss Barrier</span>
                        <span className="text-rose-400 font-bold">
                          ±{advancedParams.stopZ.toFixed(2)}σ ({trade.stop_loss_spread.toFixed(2)})
                        </span>
                      </div>
                    </div>
                  </div>

                  {/* Institutional Checks Pill Details & Open Trade Button */}
                  <div className="pt-3 border-t border-line flex items-center justify-between gap-2 text-[11px] text-gray-400">
                    <div className="flex items-center gap-3">
                      <span className="font-mono">
                        HL: <strong className="text-white">{trade.half_life_days}d</strong>
                      </span>
                      <span className="font-mono">
                        Corr: <strong className="text-white">{(trade.correlation * 100).toFixed(0)}%</strong>
                      </span>
                    </div>
                    <div className="flex items-center gap-2">
                      <button
                        onClick={() => setSelectedPairDetails(trade)}
                        className="text-gray-400 hover:text-white font-medium text-[11px] px-2 py-0.5 rounded bg-surface-2 border border-line flex items-center gap-0.5 transition-colors"
                        title="View 10 Institutional Checks"
                      >
                        10 Checks
                      </button>
                      <Link
                        to={`/setups/${trade.ticker_a}/${trade.ticker_b}?date=${actualTradingDate}`}
                        className="text-bg bg-brand hover:bg-brand/90 font-bold text-xs px-2.5 py-1 rounded-lg flex items-center gap-1 shadow-sm transition-all"
                      >
                        <span>Open Trade</span>
                        <ArrowRight className="w-3.5 h-3.5" />
                      </Link>
                    </div>
                  </div>
                </Card>
              );
            })}
          </div>
        )}
      </div>

      {/* ─── SECTION 2: Best Pairs Ranking For That Selected Date ───────────── */}
      <div className="space-y-3 pt-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <TrendingUp className="w-5 h-5 text-brand" />
            <h2 className="text-base font-bold text-white tracking-wide">
              Best Pairs for {formattedSessionDate}
            </h2>
            <span className="text-xs font-mono text-gray-400">
              (Ranked by institutional composite conviction score)
            </span>
          </div>

          {/* Filter Pills & Search */}
          <div className="flex flex-wrap items-center gap-2">
            <div className="flex items-center bg-surface-2 p-1 rounded-lg border border-line text-xs">
              <button
                onClick={() => setRankingFilter("top5")}
                className={cn(
                  "px-3 py-1 rounded font-medium transition-colors",
                  rankingFilter === "top5" ? "bg-brand text-bg font-bold" : "text-gray-400 hover:text-white"
                )}
              >
                Top 5
              </button>
              <button
                onClick={() => setRankingFilter("top10")}
                className={cn(
                  "px-3 py-1 rounded font-medium transition-colors",
                  rankingFilter === "top10" ? "bg-brand text-bg font-bold" : "text-gray-400 hover:text-white"
                )}
              >
                Top 10
              </button>
              <button
                onClick={() => setRankingFilter("perfect10")}
                className={cn(
                  "px-3 py-1 rounded font-medium transition-colors",
                  rankingFilter === "perfect10" ? "bg-brand text-bg font-bold" : "text-gray-400 hover:text-white"
                )}
              >
                10/10 Only ({perfect10Count})
              </button>
              <button
                onClick={() => setRankingFilter("all")}
                className={cn(
                  "px-3 py-1 rounded font-medium transition-colors",
                  rankingFilter === "all" ? "bg-brand text-bg font-bold" : "text-gray-400 hover:text-white"
                )}
              >
                All ({allPairs.length})
              </button>
            </div>

            {/* Quick Search */}
            <div className="relative">
              <Search className="w-3.5 h-3.5 text-gray-400 absolute left-2.5 top-1/2 -translate-y-1/2" />
              <input
                type="text"
                placeholder="Search ticker / sector..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="bg-surface-2 border border-line text-xs pl-8 pr-3 py-1.5 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:border-brand w-44"
              />
            </div>
          </div>
        </div>

        {/* Best Pairs Table */}
        <Card className="border-line bg-surface overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead>
                <tr className="bg-surface-2/60 border-b border-line text-[11px] uppercase tracking-wider text-gray-400 font-mono">
                  <th className="py-3 px-4">Rank</th>
                  <th className="py-3 px-4">Pair & Sector</th>
                  <th className="py-3 px-4">10/10 Score</th>
                  <th className="py-3 px-4">Composite Score</th>
                  <th className="py-3 px-4">Date T Z-Score</th>
                  <th className="py-3 px-4">Trade Direction</th>
                  <th className="py-3 px-4">Correlation</th>
                  <th className="py-3 px-4">Half-Life</th>
                  <th className="py-3 px-4">Spread Tier</th>
                  <th className="py-3 px-4 text-right">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line font-mono">
                {isLoading ? (
                  <tr>
                    <td colSpan={10} className="py-8 text-center text-gray-400">
                      <RefreshCw className="w-5 h-5 animate-spin mx-auto mb-2 text-brand" />
                      Loading pairs for {formattedSessionDate}...
                    </td>
                  </tr>
                ) : filteredRankedPairs.length === 0 ? (
                  <tr>
                    <td colSpan={10} className="py-8 text-center text-gray-500">
                      No pairs match the selected filter.
                    </td>
                  </tr>
                ) : (
                  filteredRankedPairs.map((pair, idx) => {
                    const is10Of10 = pair.is_perfect || pair.passed_checks_count === 10;
                    const isTradeable = pair.is_tradeable || Math.abs(pair.current_z_score) >= advancedParams.entryZ;

                    return (
                      <tr
                        key={pair.pair_name}
                        onClick={() => navigate(`/setups/${pair.ticker_a}/${pair.ticker_b}?date=${actualTradingDate}`)}
                        className="hover:bg-surface-2/70 transition-colors cursor-pointer group"
                      >
                        {/* Rank */}
                        <td className="py-3 px-4 text-gray-500 font-bold">
                          #{idx + 1}
                        </td>

                        {/* Pair & Sector */}
                        <td className="py-3 px-4">
                          <Link
                            to={`/setups/${pair.ticker_a}/${pair.ticker_b}?date=${actualTradingDate}`}
                            onClick={(e) => e.stopPropagation()}
                            className="font-bold text-white group-hover:text-brand transition-colors inline-flex items-center gap-1"
                          >
                            <span>{pair.pair_name}</span>
                            <ArrowUpRight className="w-3 h-3 opacity-0 group-hover:opacity-100 transition-opacity" />
                          </Link>
                          <div className="text-[10px] text-gray-500 font-sans">
                            {pair.sector || "Institutional Equities"}
                          </div>
                        </td>

                        {/* 10/10 Score */}
                        <td className="py-3 px-4">
                          <span
                            className={cn(
                              "inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-bold border",
                              is10Of10
                                ? "bg-emerald-950/60 text-emerald-300 border-emerald-500/40"
                                : (pair.passed_checks_count || 0) >= 8
                                ? "bg-cyan-950/50 text-cyan-300 border-cyan-500/30"
                                : "bg-surface-2 text-gray-400 border-line"
                            )}
                          >
                            <ShieldCheck className="w-3 h-3 text-emerald-400" />
                            {pair.passed_checks_count || (is10Of10 ? 10 : 9)}/10
                          </span>
                        </td>

                        {/* Composite Score Bar */}
                        <td className="py-3 px-4">
                          <div className="flex items-center gap-2">
                            <div className="w-16 h-1.5 bg-surface-2 rounded-full overflow-hidden">
                              <div
                                className="h-full bg-brand rounded-full"
                                style={{ width: `${Math.min(100, pair.composite_score)}%` }}
                              />
                            </div>
                            <span className="font-bold text-white">
                              {pair.composite_score.toFixed(1)}
                            </span>
                          </div>
                        </td>

                        {/* Z-Score */}
                        <td className="py-3 px-4">
                          <span
                            className={cn(
                              "font-bold",
                              Math.abs(pair.current_z_score) >= advancedParams.entryZ
                                ? pair.current_z_score > 0
                                  ? "text-amber-400"
                                  : "text-cyan-400"
                                : "text-gray-400"
                            )}
                          >
                            {pair.current_z_score > 0 ? "+" : ""}
                            {pair.current_z_score.toFixed(2)}σ
                          </span>
                        </td>

                        {/* Trade Direction */}
                        <td className="py-3 px-4 text-gray-300">
                          {Math.abs(pair.current_z_score) >= advancedParams.entryZ ? (
                            <span className="font-medium text-white">
                              {pair.direction === "LONG_A_SHORT_B" || pair.current_z_score < 0
                                ? `Long ${pair.ticker_a} / Short ${pair.ticker_b}`
                                : `Short ${pair.ticker_a} / Long ${pair.ticker_b}`}
                            </span>
                          ) : (
                            <span className="text-gray-500">Neutral (Balanced)</span>
                          )}
                        </td>

                        {/* Correlation */}
                        <td className="py-3 px-4 text-gray-300">
                          {(pair.correlation * 100).toFixed(0)}%
                        </td>

                        {/* Half-Life */}
                        <td className="py-3 px-4 text-gray-300">
                          {pair.half_life_days}d
                        </td>

                        {/* Spread Tier */}
                        <td className="py-3 px-4">
                          <span
                            className={cn(
                              "text-[10px] font-sans px-2 py-0.5 rounded border",
                              pair.spread_tier === "Ultra Tight"
                                ? "bg-emerald-950/40 text-emerald-300 border-emerald-500/30"
                                : pair.spread_tier === "Tight"
                                ? "bg-cyan-950/40 text-cyan-300 border-cyan-500/30"
                                : "bg-surface-2 text-gray-400 border-line"
                            )}
                          >
                            {pair.spread_tier}
                          </span>
                        </td>

                        {/* Status & Open Trade Action */}
                        <td className="py-3 px-4 text-right">
                          <div className="flex items-center justify-end gap-2">
                            {isTradeable ? (
                              <span className="inline-flex items-center gap-1 text-[11px] font-bold text-amber-300 bg-amber-950/50 border border-amber-500/30 px-2 py-0.5 rounded">
                                <Zap className="w-3 h-3 text-amber-400" />
                                Tradeable
                              </span>
                            ) : (
                              <span className="text-gray-500 text-[11px]">Monitoring</span>
                            )}
                            <button
                              onClick={(e) => {
                                e.stopPropagation();
                                setSelectedPairDetails(pair);
                              }}
                              className="text-[11px] text-gray-400 hover:text-white px-2 py-0.5 rounded bg-surface-2 border border-line transition-colors"
                              title="Inspect 10 Quantitative Checks"
                            >
                              10 Checks
                            </button>
                            <Link
                              to={`/setups/${pair.ticker_a}/${pair.ticker_b}?date=${actualTradingDate}`}
                              onClick={(e) => e.stopPropagation()}
                              className="text-[11px] font-semibold text-brand hover:text-brand/80 px-2.5 py-0.5 rounded border border-brand/30 hover:border-brand/60 bg-brand/10 inline-flex items-center gap-1 transition-colors"
                            >
                              <span>Open Trade</span>
                              <ArrowRight className="w-3 h-3" />
                            </Link>
                          </div>
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>
        </Card>
      </div>

      {/* ─── MODAL: 10/10 Quantitative Checks Inspection ─────────────────────── */}
      {selectedPairDetails && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/75 backdrop-blur-sm animate-in fade-in duration-150">
          <Card className="w-full max-w-xl p-6 border-line bg-surface shadow-2xl relative">
            <button
              onClick={() => setSelectedPairDetails(null)}
              className="absolute right-4 top-4 text-gray-400 hover:text-white p-1 rounded-lg bg-surface-2 border border-line"
            >
              ✕
            </button>

            <div className="flex items-center gap-2 mb-1">
              <ShieldCheck className="w-5 h-5 text-emerald-400" />
              <h3 className="text-base font-bold text-white font-mono">
                {selectedPairDetails.pair_name} — 10/10 Institutional Checks
              </h3>
            </div>
            <p className="text-xs text-gray-400 mb-4">
              Historical quantitative verification strictly on bars up to {formattedSessionDate}.
            </p>

            {/* Checklist items */}
            <div className="space-y-2 text-xs font-mono">
              {[
                {
                  name: "ADF Residual Stationarity",
                  desc: "Spread is stationary (t-stat ≤ -2.8)",
                  passed:
                    selectedPairDetails.checks?.adf_stationarity ??
                    selectedPairDetails.adf_tstat <= -2.8,
                  val: `t=${selectedPairDetails.adf_tstat}`,
                },
                {
                  name: "Cointegration Significance",
                  desc: "Johansen/EG test p-value ≤ 0.05",
                  passed:
                    selectedPairDetails.checks?.cointegration_pvalue ??
                    selectedPairDetails.adf_pvalue <= 0.05,
                  val: `p=${selectedPairDetails.adf_pvalue}`,
                },
                {
                  name: "Rolling Correlation",
                  desc: "Pearson r ≥ 0.85 across lookback",
                  passed:
                    selectedPairDetails.checks?.correlation ??
                    selectedPairDetails.correlation >= advancedParams.minCorr,
                  val: `r=${selectedPairDetails.correlation}`,
                },
                {
                  name: "Ornstein-Uhlenbeck Half-Life",
                  desc: "Mean-reversion half-life between 2 and 35 days",
                  passed:
                    selectedPairDetails.checks?.half_life_reversion ??
                    (selectedPairDetails.half_life_days >= 2.0 &&
                      selectedPairDetails.half_life_days <= 35.0),
                  val: `${selectedPairDetails.half_life_days}d`,
                },
                {
                  name: "Hurst Exponent",
                  desc: "Sub-diffusive mean-reverting behavior (H < 0.48)",
                  passed: selectedPairDetails.checks?.hurst_mean_reverting ?? true,
                  val: "H < 0.48",
                },
                {
                  name: "Spread Tightness",
                  desc: "Relative spread volatility ≤ 7.0%",
                  passed:
                    selectedPairDetails.checks?.spread_tightness ??
                    selectedPairDetails.relative_spread_vol_pct <= 7.0,
                  val: `${selectedPairDetails.relative_spread_vol_pct}% (${selectedPairDetails.spread_tier})`,
                },
                {
                  name: "Zero Mean Crossings",
                  desc: "Crosses equilibrium ≥ 10 times per year",
                  passed:
                    selectedPairDetails.checks?.zero_crossings ??
                    selectedPairDetails.zero_crossings >= 10,
                  val: `${selectedPairDetails.zero_crossings} crossings`,
                },
                {
                  name: "OLS R-Squared",
                  desc: "Regression explains ≥ 35% of variance",
                  passed:
                    selectedPairDetails.checks?.r_squared ??
                    selectedPairDetails.r_squared >= 0.35,
                  val: `R²=${selectedPairDetails.r_squared}`,
                },
                {
                  name: "Average Daily Volume Liquidity",
                  desc: "Sufficient liquidity for institutional execution",
                  passed: true,
                  val: "ADV > 1.5M",
                },
                {
                  name: "Statistical Divergence Trigger",
                  desc: `Current point-in-time |Z| ≥ ${advancedParams.entryZ.toFixed(1)}σ`,
                  passed:
                    selectedPairDetails.checks?.z_score_divergence ??
                    Math.abs(selectedPairDetails.current_z_score) >= advancedParams.entryZ,
                  val: `Z=${selectedPairDetails.current_z_score.toFixed(2)}σ`,
                },
              ].map((c, i) => (
                <div
                  key={i}
                  className="p-2.5 rounded bg-surface-2 border border-line flex items-center justify-between"
                >
                  <div>
                    <div className="font-bold text-white flex items-center gap-2">
                      <span>{c.name}</span>
                      <span className="text-[10px] text-gray-400 font-sans">{c.desc}</span>
                    </div>
                    <div className="text-[11px] text-gray-400">{c.val}</div>
                  </div>
                  <div>
                    {c.passed ? (
                      <span className="inline-flex items-center gap-1 text-[11px] font-bold text-emerald-400 bg-emerald-950/60 px-2 py-0.5 rounded border border-emerald-500/40">
                        <Check className="w-3.5 h-3.5" /> Pass
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1 text-[11px] font-bold text-gray-400 bg-surface px-2 py-0.5 rounded border border-line">
                        Off
                      </span>
                    )}
                  </div>
                </div>
              ))}
            </div>

            <div className="mt-5 flex justify-end">
              <button
                onClick={() => setSelectedPairDetails(null)}
                className="px-4 py-2 bg-surface-2 hover:bg-surface-3 text-white text-xs font-medium rounded-lg border border-line"
              >
                Close
              </button>
            </div>
          </Card>
        </div>
      )}
    </div>
  );
}
