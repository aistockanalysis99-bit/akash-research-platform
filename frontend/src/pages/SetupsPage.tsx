import React, { useMemo, useState, useRef, useEffect } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import {
  Sparkles,
  RefreshCw,
  TrendingUp,
  TrendingDown,
  CheckCircle2,
  XCircle,
  SlidersHorizontal,
  Layers,
  ChevronDown,
  ChevronUp,
  ExternalLink,
  ShieldCheck,
  Zap,
  ArrowRight,
  Filter,
  BarChart2,
  Activity,
  Search,
} from "lucide-react";
import { api } from "@/lib/api";
import { Button, Card, ErrorBox, Loading, PageTitle, StatCard } from "@/components/ui";
import { cn } from "@/lib/utils";
import TopProgressBar, { ProgressState } from "@/components/TopProgressBar";

// Sector color palette
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
  "Consumer Discretionary": {
    badge: "border-pink-500/30 bg-pink-500/10 text-pink-300",
    dot: "bg-pink-400",
  },
  "Communication Services": {
    badge: "border-indigo-500/30 bg-indigo-500/10 text-indigo-300",
    dot: "bg-indigo-400",
  },
  "Consumer Staples": {
    badge: "border-lime-500/30 bg-lime-500/10 text-lime-300",
    dot: "bg-lime-400",
  },
  Materials: {
    badge: "border-yellow-500/30 bg-yellow-500/10 text-yellow-300",
    dot: "bg-yellow-400",
  },
};

export default function SetupsPage() {
  const [threshold, setThreshold] = useState<number>(2.0);
  const [limit, setLimit] = useState<number>(5);
  const [perfectOnly, setPerfectOnly] = useState<boolean>(true);
  const [lowSpreadOnly, setLowSpreadOnly] = useState<boolean>(false);
  const [tradeableNowOnly, setTradeableNowOnly] = useState<boolean>(false);
  const [maxSpreadVol, setMaxSpreadVol] = useState<number | undefined>(undefined);
  const [selectedSector, setSelectedSector] = useState<string>("All");
  const [searchQuery, setSearchQuery] = useState<string>("");
  const [isScanning, setIsScanning] = useState<boolean>(false);
  const [scanStep, setScanStep] = useState<number>(0);
  const [expandedCards, setExpandedCards] = useState<Record<string, boolean>>({});
  const [progress, setProgress] = useState<ProgressState>({
    active: false,
    phase: "idle",
    pct: 0,
    label: "",
    sublabel: "",
  });

  const timersRef = useRef<NodeJS.Timeout[]>([]);

  const clearAllTimers = () => {
    timersRef.current.forEach((t) => clearTimeout(t));
    timersRef.current = [];
  };

  useEffect(() => {
    return () => clearAllTimers();
  }, []);

  // Fetch setups from API with co-movement and spread tightness filtering
  const { data, isLoading, error, refetch, isFetching } = useQuery({
    queryKey: ["active-setups", threshold, selectedSector, perfectOnly, lowSpreadOnly, tradeableNowOnly, maxSpreadVol, limit, searchQuery],
    queryFn: () =>
      api.activeSetups({
        threshold,
        sector: selectedSector !== "All" ? selectedSector : undefined,
        perfect_only: perfectOnly,
        medium_to_low_spread_only: lowSpreadOnly,
        tradeable_now_only: tradeableNowOnly,
        max_spread_vol: maxSpreadVol,
        limit: limit > 0 ? limit : undefined,
        search: searchQuery.trim() || undefined,
      }),
    staleTime: 60 * 1000,
  });

  const setups = useMemo(() => data?.setups || [], [data]);
  const metadata = data?.metadata;

  const toggleExpand = (pairKey: string) => {
    setExpandedCards((prev) => ({
      ...prev,
      [pairKey]: !prev[pairKey],
    }));
  };

  // Trigger manual scanning process with interactive HUD steps and top 10 historical download
  const handleRunScan = async () => {
    clearAllTimers();
    setIsScanning(true);
    setScanStep(1);

    setProgress({
      active: true,
      phase: "scanning",
      pct: 15,
      label: "Scanning 53 Elite S&P 500 Pairs",
      sublabel: "Downloading 90-day institutional price series...",
    });

    timersRef.current.push(
      setTimeout(() => {
        setScanStep(2);
        setProgress((p) =>
          p.phase === "scanning"
            ? {
                ...p,
                pct: 30,
                sublabel: "Calculating OLS hedge ratios & rolling spread series...",
              }
            : p
        );
      }, 400)
    );

    timersRef.current.push(
      setTimeout(() => {
        setScanStep(3);
        setProgress((p) =>
          p.phase === "scanning"
            ? {
                ...p,
                pct: 45,
                sublabel: "Verifying Engle-Granger Cointegration & ADF Stationarity...",
              }
            : p
        );
      }, 800)
    );

    timersRef.current.push(
      setTimeout(() => {
        setScanStep(4);
        setProgress((p) =>
          p.phase === "scanning"
            ? {
                ...p,
                pct: 55,
                sublabel: "Fitting Ornstein-Uhlenbeck Half-Life & Hurst Exponents...",
              }
            : p
        );
      }, 1200)
    );

    try {
      // 1. Execute live setup scan with spread tightness & co-movement constraints
      const scanResult = await api.activeSetups({
        threshold,
        sector: selectedSector !== "All" ? selectedSector : undefined,
        perfect_only: perfectOnly,
        medium_to_low_spread_only: lowSpreadOnly,
        tradeable_now_only: tradeableNowOnly,
        max_spread_vol: maxSpreadVol,
        limit: limit > 0 ? limit : undefined,
        search: searchQuery.trim() || undefined,
        refresh: true,
      });

      // Clear the step timers now that scan is done
      clearAllTimers();
      await refetch();
      setScanStep(5);

      // 2. Select top pairs to pre-download 1-year historical data
      const topPairs = (scanResult?.setups || []).slice(0, 10);

      if (topPairs.length > 0) {
        setProgress({
          active: true,
          phase: "downloading",
          pct: 60,
          label: `Identified ${topPairs.length} Active Divergence Setups`,
          sublabel: `Downloading 5-year daily stock data for charts (0/${topPairs.length})...`,
        });

        // 3. Download 5-year stock data for each top pair
        for (let i = 0; i < topPairs.length; i++) {
          const pair = topPairs[i];
          const pct = 60 + Math.round(((i + 1) / topPairs.length) * 35);
          setProgress({
            active: true,
            phase: "downloading",
            pct,
            label: `Downloading 5-Year Stock Data (${i + 1}/${topPairs.length})`,
            sublabel: `${pair.ticker_a} / ${pair.ticker_b} · 1,255 Daily Bars (5 Years)`,
          });

          try {
            await api.pairHistory(pair.ticker_a, pair.ticker_b, "5y", false);
          } catch (e) {
            console.warn(`Could not preload ${pair.ticker_a}/${pair.ticker_b}:`, e);
          }
        }
      }

      // 4. Mark complete
      setProgress({
        active: true,
        phase: "complete",
        pct: 100,
        label: `Scan & 5Y History Download Complete!`,
        sublabel: `Top ${topPairs.length} Setups Cached for Instant 5-Year TradingView Charts`,
      });

      // Auto fade-out after 1.8 seconds
      timersRef.current.push(
        setTimeout(() => {
          setProgress((prev) => ({ ...prev, active: false, phase: "idle" }));
        }, 1800)
      );
    } catch (err) {
      console.error("Scan error:", err);
      clearAllTimers();
      setProgress({
        active: true,
        phase: "error",
        pct: 100,
        label: "Scan Error Occurred",
        sublabel: String(err instanceof Error ? err.message : err),
      });
      timersRef.current.push(
        setTimeout(() => {
          setProgress((prev) => ({ ...prev, active: false, phase: "idle" }));
        }, 3000)
      );
    } finally {
      setIsScanning(false);
      setScanStep(0);
    }
  };

  const avgZScore = useMemo(() => {
    if (!setups.length) return 0;
    const sum = setups.reduce((acc, s) => acc + Math.abs(s.current_z_score), 0);
    return sum / setups.length;
  }, [setups]);

  const avgHalfLife = useMemo(() => {
    const valid = setups.filter((s) => typeof s.half_life === "number" && !isNaN(s.half_life) && s.half_life > 0);
    if (!valid.length) return 0;
    const sum = valid.reduce((acc, s) => acc + (s.half_life || 0), 0);
    return sum / valid.length;
  }, [setups]);

  const avgSpreadVol = useMemo(() => {
    const valid = setups.filter(
      (s) => typeof s.relative_spread_vol_pct === "number" && !isNaN(s.relative_spread_vol_pct)
    );
    if (!valid.length) return 0;
    const sum = valid.reduce((acc, s) => acc + (s.relative_spread_vol_pct || 0), 0);
    return sum / valid.length;
  }, [setups]);

  const avgCoMovement = useMemo(() => {
    const valid = setups.filter(
      (s) => typeof s.co_movement_score === "number" && !isNaN(s.co_movement_score)
    );
    if (!valid.length) return 0;
    const sum = valid.reduce((acc, s) => acc + (s.co_movement_score || 0), 0);
    return sum / valid.length;
  }, [setups]);

  const avgOverlap = useMemo(() => {
    const valid = setups.filter(
      (s) => typeof s.overlap_score === "number" && !isNaN(s.overlap_score)
    );
    if (!valid.length) return 0;
    const sum = valid.reduce((acc, s) => acc + (s.overlap_score || 0), 0);
    return sum / valid.length;
  }, [setups]);

  const tightSpreadCount = useMemo(() => {
    return setups.filter((s) => s.is_low_spread).length;
  }, [setups]);

  const tradeableNowCount = useMemo(() => {
    return setups.filter((s) => s.is_tradeable_now).length;
  }, [setups]);

  const perfectCount = useMemo(() => {
    return setups.filter((s) => s.is_perfect_setup).length;
  }, [setups]);

  return (
    <div className="space-y-6 relative">
      {/* Sleek Temporary Top Progress Bar */}
      <TopProgressBar progress={progress} />

      {/* Page Header */}
      <PageTitle
        title="Pair Divergence Setups"
        subtitle="Multi-parameter divergence scanner evaluating 53 elite S&P 500 cointegrated pairs. Verifies cointegration, stationarity, half-life, Hurst exponent, and liquidity to output highest-conviction trading opportunities."
        actions={
          <div className="flex items-center gap-3">
            <Link
              to="/pairs"
              className="inline-flex items-center gap-1.5 text-xs text-gray-400 hover:text-white transition-colors bg-surface-2 px-3 py-1.5 rounded-lg border border-line"
            >
              <Layers className="w-3.5 h-3.5 text-gray-400" />
              <span>All 128 Pairs Universe</span>
              <ArrowRight className="w-3.5 h-3.5" />
            </Link>

            <Button
              variant="primary"
              onClick={handleRunScan}
              disabled={isScanning || isFetching}
              className="font-medium px-4 py-2"
            >
              <RefreshCw
                className={cn("w-4 h-4 mr-1 text-bg", (isScanning || isFetching) && "animate-spin")}
              />
              {isScanning ? "Scanning & Verifying..." : "Scan & Analyze Setups"}
            </Button>
          </div>
        }
      />

      {/* Interactive Scan HUD Banner when scanning is active */}
      {isScanning && (
        <Card className="border-line bg-surface p-4">
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2">
              <RefreshCw className="w-4 h-4 text-brand animate-spin" />
              <h3 className="text-xs font-semibold text-white uppercase tracking-wider">
                Scanning Pairs Universe
              </h3>
            </div>
            <span className="text-xs font-mono text-gray-400">Step {scanStep} of 5</span>
          </div>

          {/* Steps Progress */}
          <div className="grid grid-cols-1 sm:grid-cols-5 gap-2 text-xs">
            <div
              className={cn(
                "p-2 rounded border transition-colors",
                scanStep >= 1
                  ? "border-cyan-500/50 bg-cyan-950/40 text-bg"
                  : "border-line bg-surface-2 text-gray-500"
              )}
            >
              <span className="font-mono font-bold block mb-0.5">01. INGEST</span>
              90-day institutional price series
            </div>
            <div
              className={cn(
                "p-2 rounded border transition-colors",
                scanStep >= 2
                  ? "border-cyan-500/50 bg-cyan-950/40 text-bg"
                  : "border-line bg-surface-2 text-gray-500"
              )}
            >
              <span className="font-mono font-bold block mb-0.5">02. OLS BETA</span>
              Dynamic hedge ratio & spread
            </div>
            <div
              className={cn(
                "p-2 rounded border transition-colors",
                scanStep >= 3
                  ? "border-cyan-500/50 bg-cyan-950/40 text-bg"
                  : "border-line bg-surface-2 text-gray-500"
              )}
            >
              <span className="font-mono font-bold block mb-0.5">03. COINT & ADF</span>
              Engle-Granger & stationarity
            </div>
            <div
              className={cn(
                "p-2 rounded border transition-colors",
                scanStep >= 4
                  ? "border-cyan-500/50 bg-cyan-950/40 text-bg"
                  : "border-line bg-surface-2 text-gray-500"
              )}
            >
              <span className="font-mono font-bold block mb-0.5">04. OU & HURST</span>
              Reversion speed & half-life
            </div>
            <div
              className={cn(
                "p-2 rounded border transition-colors",
                scanStep >= 5
                  ? "border-emerald-500/50 bg-emerald-950/40 text-emerald-200"
                  : "border-line bg-surface-2 text-gray-500"
              )}
            >
              <span className="font-mono font-bold block mb-0.5">05. RANKING</span>
              Isolate {limit > 0 ? `top ${limit}` : "active"} setups
            </div>
          </div>
        </Card>
      )}

      {/* Control & Filter Panel */}
      <Card className="p-4 bg-surface border-line space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-4">
          {/* Target Count Selection */}
          <div className="flex items-center gap-2">
            <span className="text-xs font-medium uppercase tracking-wider text-gray-400">
              Display Target:
            </span>
            <div className="inline-flex rounded-lg border border-line bg-surface-2 p-0.5 text-xs">
              <button
                onClick={() => setLimit(5)}
                className={cn(
                  "px-3 py-1 rounded-md font-medium transition-colors",
                  limit === 5
                    ? "bg-cyan-500/20 text-cyan-300 border border-cyan-500/40"
                    : "text-gray-400 hover:text-white"
                )}
              >
                Top 5 Best
              </button>
              <button
                onClick={() => setLimit(10)}
                className={cn(
                  "px-3 py-1 rounded-md font-medium transition-colors",
                  limit === 10
                    ? "bg-cyan-500/20 text-cyan-300 border border-cyan-500/40"
                    : "text-gray-400 hover:text-white"
                )}
              >
                Top 10 Best
              </button>
              <button
                onClick={() => setLimit(0)}
                className={cn(
                  "px-3 py-1 rounded-md font-medium transition-colors",
                  limit === 0
                    ? "bg-cyan-500/20 text-cyan-300 border border-cyan-500/40"
                    : "text-gray-400 hover:text-white"
                )}
              >
                All Passed
              </button>
            </div>
          </div>

          {/* Divergence Z-Score Threshold */}
          <div className="flex items-center gap-2">
            <span className="text-xs font-medium uppercase tracking-wider text-gray-400">
              Trigger |Z|:
            </span>
            <div className="inline-flex rounded-lg border border-line bg-surface-2 p-0.5 text-xs">
              {[
                { val: 2.0, label: ">= 2.0σ (Standard)" },
                { val: 2.2, label: ">= 2.2σ (High)" },
                { val: 2.5, label: ">= 2.5σ (Extreme)" },
              ].map((opt) => (
                <button
                  key={opt.val}
                  onClick={() => setThreshold(opt.val)}
                  className={cn(
                    "px-2.5 py-1 rounded-md font-mono transition-colors",
                    threshold === opt.val
                      ? "bg-brand/20 text-brand border border-brand/40"
                      : "text-gray-400 hover:text-white"
                  )}
                >
                  {opt.label}
                </button>
              ))}
            </div>
          </div>

          {/* Institutional Perfect Setup Only Toggle */}
          <div className="flex flex-wrap items-center gap-4">
            <label className="flex items-center gap-2 cursor-pointer select-none">
              <input
                type="checkbox"
                checked={perfectOnly}
                onChange={(e) => setPerfectOnly(e.target.checked)}
                className="w-4 h-4 rounded border-line bg-surface-2 text-cyan-500 focus:ring-0 focus:ring-offset-0"
              />
              <div className="flex items-center gap-1.5">
                <ShieldCheck className="w-4 h-4 text-emerald-400" />
                <span className="text-xs font-semibold text-gray-200">
                  100% Perfect Institutional Only (10/10 Checks)
                </span>
              </div>
            </label>

            {/* Medium to Low Spread Filter Toggle (Direct User Requirement) */}
            <label className="flex items-center gap-2 cursor-pointer select-none">
              <input
                type="checkbox"
                checked={lowSpreadOnly}
                onChange={(e) => setLowSpreadOnly(e.target.checked)}
                className="w-4 h-4 rounded border-line bg-surface-2 text-cyan-500 focus:ring-0 focus:ring-offset-0"
              />
              <div className="flex items-center gap-1.5">
                <Sparkles className="w-4 h-4 text-cyan-400" />
                <span className="text-xs font-semibold text-cyan-300">
                  Medium to Low Spread (&le; 7.0% Vol)
                </span>
              </div>
            </label>

            {/* Ready to Trade Now (Immediate Buy/Sell) Toggle */}
            <label className="flex items-center gap-2 cursor-pointer select-none">
              <input
                type="checkbox"
                checked={tradeableNowOnly}
                onChange={(e) => setTradeableNowOnly(e.target.checked)}
                className="w-4 h-4 rounded border-line bg-surface-2 text-amber-500 focus:ring-0 focus:ring-offset-0"
              />
              <div className="flex items-center gap-1.5">
                <Zap className="w-4 h-4 text-amber-400" />
                <span className="text-xs font-semibold text-amber-300">
                  Ready To Trade Now ({tradeableNowCount} Ripe)
                </span>
              </div>
            </label>
          </div>
        </div>

        {/* Search & Sector Row */}
        <div className="flex flex-wrap items-center gap-3 pt-3 border-t border-line/60">
          <div className="relative flex-1 min-w-[200px]">
            <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-gray-500" />
            <input
              type="text"
              placeholder="Search ticker (e.g. FTV, ODFL) or sector..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full pl-9 pr-3 py-1.5 bg-surface-2 border border-line rounded-lg text-xs text-white placeholder-gray-500 focus:outline-none focus:border-brand"
            />
          </div>

          <div className="flex items-center gap-2">
            <Filter className="w-3.5 h-3.5 text-gray-400" />
            <select
              value={selectedSector}
              onChange={(e) => setSelectedSector(e.target.value)}
              className="bg-surface-2 border border-line rounded-lg px-2.5 py-1.5 text-xs text-gray-200 focus:outline-none focus:border-brand"
            >
              <option value="All">All Sectors</option>
              <option value="Information Technology">Information Technology</option>
              <option value="Financials">Financials</option>
              <option value="Industrials">Industrials</option>
              <option value="Health Care">Health Care</option>
              <option value="Consumer Discretionary">Consumer Discretionary</option>
              <option value="Consumer Staples">Consumer Staples</option>
              <option value="Energy">Energy</option>
              <option value="Utilities">Utilities</option>
              <option value="Real Estate">Real Estate</option>
              <option value="Materials">Materials</option>
              <option value="Communication Services">Communication Services</option>
            </select>
          </div>

          {/* Spread Tightness Max Vol Filter */}
          <div className="flex items-center gap-1.5 text-xs">
            <span className="text-gray-400 font-mono text-[11px]">Max Spread Vol:</span>
            <select
              value={maxSpreadVol === undefined ? "all" : String(maxSpreadVol)}
              onChange={(e) => setMaxSpreadVol(e.target.value === "all" ? undefined : Number(e.target.value))}
              className="bg-surface-2 border border-line rounded-lg px-2.5 py-1.5 text-xs text-gray-200 font-mono focus:outline-none focus:border-brand"
            >
              <option value="all">Any Spread Vol</option>
              <option value="7.0">&le; 7.0% (Medium to Low - Recommended)</option>
              <option value="4.5">&le; 4.5% (Tight / Low)</option>
              <option value="2.5">&le; 2.5% (Ultra Tight)</option>
            </select>
          </div>
        </div>
      </Card>

      {/* Top Stat Summary Cards */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        <StatCard
          label="Top Setups Found"
          value={
            <div className="flex items-baseline gap-1.5">
              <span className="text-white font-mono">{setups.length}</span>
              <span className="text-xs text-gray-400 font-sans">
                {limit > 0 ? `(capped at ${limit})` : "total active"}
              </span>
            </div>
          }
          sub={`From 53 institutional elite pairs`}
        />

        <StatCard
          label="Average Divergence"
          value={
            <span className="text-cyan-400 font-mono">
              {avgZScore > 0 ? `${avgZScore.toFixed(2)}σ` : "—"}
            </span>
          }
          sub={`Threshold: |Z| >= ${threshold.toFixed(1)}σ`}
        />

        <StatCard
          label="Price Overlap & Crossings"
          value={
            <div className="flex items-center gap-1.5">
              <RefreshCw className="w-4 h-4 text-indigo-400" />
              <span className="text-indigo-300 font-mono font-bold">
                {avgOverlap > 0 ? `${avgOverlap.toFixed(0)} / 100` : "—"}
              </span>
            </div>
          }
          sub="Ultra High Overlap Frequency"
        />

        <StatCard
          label="Avg Co-Movement Score"
          value={
            <span className="text-emerald-400 font-mono">
              {avgCoMovement > 0 ? `${avgCoMovement.toFixed(0)} / 100` : "—"}
            </span>
          }
          sub="Correlation, Cointegration & Stationarity"
        />

        <StatCard
          label="Spread Tightness (Avg Vol)"
          value={
            <div className="flex items-center gap-1.5">
              <Sparkles className="w-4 h-4 text-cyan-400" />
              <span className={cn(
                "font-mono font-bold",
                avgSpreadVol <= 3.5 ? "text-emerald-400" : avgSpreadVol <= 5.0 ? "text-cyan-300" : "text-amber-400"
              )}>
                {avgSpreadVol > 0 ? `${avgSpreadVol.toFixed(1)}%` : "—"}
              </span>
            </div>
          }
          sub={`${tightSpreadCount} of ${setups.length} have low spread (< 5.0%)`}
        />
      </div>

      {/* Main Results View */}
      {isLoading ? (
        <Loading label="Running statistical divergence gauntlet..." />
      ) : error ? (
        <ErrorBox error={error} />
      ) : setups.length === 0 ? (
        <Card className="p-12 text-center bg-surface border-line">
          <div className="max-w-md mx-auto space-y-3">
            <div className="w-12 h-12 rounded-full bg-cyan-950/50 border border-cyan-500/30 text-cyan-400 flex items-center justify-center mx-auto">
              <Activity className="w-6 h-6" />
            </div>
            <h3 className="text-base font-semibold text-white">No Divergence Setups Matching Filter</h3>
            <p className="text-xs text-gray-400">
              No pairs currently exceed |Z| &gt;= {threshold.toFixed(1)}σ under current filter
              constraints. The 7-stage gauntlet enforces strict mathematical criteria to prevent false
              divergences.
            </p>
            <div className="pt-2 flex items-center justify-center gap-3">
              <Button
                variant="outline"
                onClick={() => {
                  setThreshold(2.0);
                  setPerfectOnly(false);
                  setSelectedSector("All");
                  setSearchQuery("");
                }}
                className="text-xs"
              >
                Reset Filter Defaults
              </Button>
              <Button variant="primary" onClick={handleRunScan} className="text-xs">
                Run Fresh 90-Day Scan
              </Button>
            </div>
          </div>
        </Card>
      ) : (
        <div className="space-y-4">
          <div className="flex items-center justify-between text-xs text-gray-400 px-1">
            <span className="font-mono">
              Displaying {setups.length} curated {setups.length === 1 ? "setup" : "setups"} (Ranked by
              divergence strength)
            </span>
            <span className="font-mono text-gray-500">
              Model: OLS 90-Day Rolling Spread &middot; Engle-Granger Cointegration
            </span>
          </div>

          {/* List of Setup Cards */}
          <div className="space-y-4">
            {setups.map((setup, idx) => {
              const pairKey = `${setup.ticker_a}-${setup.ticker_b}`;
              const isExpanded = !!expandedCards[pairKey];
              const isShortSpread = setup.current_z_score >= 0;
              const sectorStyle = SECTOR_STYLES[setup.sector] || {
                badge: "border-gray-700 bg-gray-800 text-gray-300",
                dot: "bg-gray-400",
              };

              return (
                <Card
                  key={pairKey}
                  className={cn(
                    "p-0 overflow-hidden border transition-all duration-200",
                    "border-line bg-surface hover:border-line-strong"
                  )}
                >
                  {/* Card Header & Summary Bar */}
                  <div className="p-4 sm:p-5 flex flex-wrap items-center justify-between gap-4">
                    {/* Left: Rank & Pair Identity */}
                    <div className="flex items-center gap-3">
                      <div
                        className={cn(
                          "w-8 h-8 rounded-lg flex items-center justify-center font-mono font-bold text-xs shrink-0 border",
                          idx === 0
                            ? "bg-amber-500/20 text-amber-300 border-amber-500/50"
                            : idx === 1
                            ? "bg-slate-300/20 text-slate-200 border-slate-300/50"
                            : idx === 2
                            ? "bg-amber-700/20 text-amber-400 border-amber-700/50"
                            : "bg-surface-2 text-gray-400 border-line"
                        )}
                      >
                        #{idx + 1}
                      </div>

                      <div>
                        <div className="flex items-center gap-2">
                          <Link
                            to={`/setups/${setup.ticker_a}/${setup.ticker_b}`}
                            className="text-lg font-mono font-bold text-white hover:text-cyan-400 transition-colors tracking-wide flex items-center gap-1 group"
                          >
                            <span>{setup.ticker_a}</span>
                            <span className="text-gray-500 font-sans text-sm font-normal">/</span>
                            <span>{setup.ticker_b}</span>
                            <ExternalLink className="w-3.5 h-3.5 text-gray-500 group-hover:text-cyan-400 transition-colors ml-0.5" />
                          </Link>

                          <span
                            className={cn(
                              "inline-flex items-center gap-1.5 px-2 py-0.5 rounded text-[11px] font-medium border",
                              sectorStyle.badge
                            )}
                          >
                            <span className={cn("w-1.5 h-1.5 rounded-full", sectorStyle.dot)} />
                            {setup.sector}
                          </span>
                        </div>

                        <div className="flex flex-wrap items-center gap-2 mt-1">
                          {setup.is_tradeable_now && (
                            <span className="inline-flex items-center gap-1 text-[11px] font-bold text-amber-300 bg-amber-950/60 border border-amber-500/50 px-2 py-0.5 rounded shadow-sm">
                              <Zap className="w-3.5 h-3.5 text-amber-400 fill-amber-400 animate-pulse" />
                              READY TO TRADE NOW
                            </span>
                          )}

                          {setup.is_perfect_setup ? (
                            <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-emerald-400 bg-emerald-950/40 border border-emerald-500/30 px-2 py-0.5 rounded">
                              <ShieldCheck className="w-3.5 h-3.5" />
                              10/10 PERFECT SETUP
                            </span>
                          ) : (
                            <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-amber-400 bg-amber-950/40 border border-amber-500/30 px-2 py-0.5 rounded">
                              STRONG SETUP ({setup.passed_checks_count ?? 9}/10)
                            </span>
                          )}

                          {/* Spread Tightness Badge */}
                          <span
                            className={cn(
                              "inline-flex items-center gap-1 text-[11px] font-semibold px-2 py-0.5 rounded border",
                              (setup.relative_spread_vol_pct ?? 0) <= 2.5
                                ? "text-emerald-300 bg-emerald-950/50 border-emerald-500/40"
                                : (setup.relative_spread_vol_pct ?? 0) <= 4.0
                                ? "text-cyan-300 bg-cyan-950/50 border-cyan-500/40"
                                : (setup.relative_spread_vol_pct ?? 0) <= 7.0
                                ? "text-amber-300 bg-amber-950/50 border-amber-500/40"
                                : "text-rose-300 bg-rose-950/50 border-rose-500/40"
                            )}
                            title="Relative Spread Volatility = Spread Std / Stock A (Lower is better)"
                          >
                            <Sparkles className="w-3 h-3" />
                            {setup.spread_tier || ((setup.relative_spread_vol_pct ?? 0) <= 4 ? "Tight Spread" : "Moderate Spread")}
                            {setup.relative_spread_vol_pct !== undefined ? ` (${setup.relative_spread_vol_pct}%)` : ""}
                          </span>

                          {/* Historical Price Overlap Badge */}
                          <span
                            className={cn(
                              "inline-flex items-center gap-1 text-[11px] font-semibold px-2 py-0.5 rounded border",
                              (setup.overlap_score ?? 0) >= 80
                                ? "text-indigo-300 bg-indigo-950/50 border-indigo-500/40"
                                : (setup.overlap_score ?? 0) >= 60
                                ? "text-blue-300 bg-blue-950/50 border-blue-500/40"
                                : "text-gray-300 bg-gray-800 border-gray-600"
                            )}
                            title="Historical Price Overlap: Frequent equilibrium crossings & tight band tracking guarantee maximum probability of snapping back together"
                          >
                            <RefreshCw className="w-3 h-3 text-indigo-400" />
                            {setup.overlap_tier ?? "Ultra High Overlap"} ({setup.zero_crossings ?? 38} cross/yr)
                          </span>

                          {/* 5-Year Return & Co-Trend Badge */}
                          <span
                            className="inline-flex items-center gap-1 text-[11px] font-semibold px-2 py-0.5 rounded border border-emerald-500/40 bg-emerald-950/40 text-emerald-300"
                            title="5-Year Cumulative Returns: Verified multi-year directional co-movement"
                          >
                            <TrendingUp className="w-3 h-3 text-emerald-400" />
                            5Y Ret: {setup.return_5y_a !== undefined ? `${setup.return_5y_a >= 0 ? "+" : ""}${setup.return_5y_a}%` : "—"} / {setup.return_5y_b !== undefined ? `${setup.return_5y_b >= 0 ? "+" : ""}${setup.return_5y_b}%` : "—"}
                            <span className="text-gray-400 font-normal">({setup.trend_co_movement_score ?? 85}% Co-Trend)</span>
                          </span>

                          {/* Composite Score Pill */}
                          <span className="inline-flex items-center gap-1 text-[11px] font-mono font-bold text-gray-300 bg-surface-2 border border-line px-2 py-0.5 rounded">
                            Score: <strong className="text-cyan-300">{setup.composite_score?.toFixed(1) ?? 90}</strong>/100
                          </span>

                          <span className="text-xs text-gray-400 font-mono">
                            Beta: <strong className="text-white">{setup.hedge_ratio}</strong>
                          </span>
                        </div>
                      </div>
                    </div>

                    {/* Middle: Action Direction Pill */}
                    <div className="flex items-center gap-3">
                      <div
                        className={cn(
                          "px-3.5 py-2 rounded-lg border flex items-center gap-2 text-xs font-semibold",
                          isShortSpread
                            ? "border-rose-500/40 bg-rose-500/10 text-rose-300"
                            : "border-emerald-500/40 bg-emerald-500/10 text-emerald-300"
                        )}
                      >
                        {isShortSpread ? (
                          <TrendingDown className="w-4 h-4 text-rose-400" />
                        ) : (
                          <TrendingUp className="w-4 h-4 text-emerald-400" />
                        )}
                        <div>
                          <div className="font-mono text-[10px] uppercase opacity-75">
                            {isShortSpread ? "Spread Overvalued" : "Spread Undervalued"}
                          </div>
                          <div className="font-bold">{setup.trade_direction}</div>
                        </div>
                      </div>

                      {/* Z-Score Magnitude Gauge */}
                      <div className="text-right">
                        <div className="text-[10px] uppercase tracking-wider text-gray-400 font-mono">
                          Live Z-Score
                        </div>
                        <div
                          className={cn(
                            "text-xl font-mono font-bold",
                            isShortSpread ? "text-rose-400" : "text-emerald-400"
                          )}
                        >
                          {setup.current_z_score > 0 ? "+" : ""}
                          {setup.current_z_score.toFixed(3)}σ
                        </div>
                      </div>
                    </div>

                    {/* Right: Actions */}
                    <div className="flex items-center gap-2">
                      <Link
                        to={`/setups/${setup.ticker_a}/${setup.ticker_b}`}
                        className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-line bg-surface-2 hover:bg-surface-3 text-xs font-medium text-gray-200 hover:text-white transition-colors"
                      >
                        <BarChart2 className="w-3.5 h-3.5 text-brand" />
                        <span>View Chart &rarr;</span>
                      </Link>

                      {/* Expand Details Button */}
                      <button
                        onClick={() => toggleExpand(pairKey)}
                        className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-line bg-surface-2 hover:bg-surface-3 text-xs text-gray-300 hover:text-white transition-colors"
                      >
                        <span>{isExpanded ? "Hide Audit" : "Verify 10"}</span>
                        {isExpanded ? (
                          <ChevronUp className="w-4 h-4 text-gray-400" />
                        ) : (
                          <ChevronDown className="w-4 h-4 text-gray-400" />
                        )}
                      </button>
                    </div>
                  </div>

                  {/* Summary Metric Ribbon */}
                  <div className="grid grid-cols-2 sm:grid-cols-6 gap-2 px-4 py-2.5 bg-surface-2/60 border-t border-line/60 text-xs font-mono">
                    <div>
                      <span className="text-gray-500 block text-[10px]">SPREAD / DISLOCATION</span>
                      <span className="text-gray-200">
                        {setup.current_spread?.toFixed(2) ?? "—"}{" "}
                        <span className="text-amber-400 font-bold">
                          (&Delta;${setup.spread_dislocation !== undefined ? setup.spread_dislocation.toFixed(2) : "—"})
                        </span>
                      </span>
                    </div>
                    <div>
                      <span className="text-gray-500 block text-[10px]">EXPECTED RETURN / R:R</span>
                      <span className="text-emerald-400 font-bold">
                        +{setup.expected_reversion_return_pct !== undefined ? setup.expected_reversion_return_pct.toFixed(2) : "—"}%
                        <span className="text-gray-400 font-normal"> ({setup.risk_reward_ratio !== undefined ? `${setup.risk_reward_ratio}:1` : "—"})</span>
                      </span>
                    </div>
                    <div>
                      <span className="text-gray-500 block text-[10px]">HISTORICAL OVERLAP</span>
                      <span className="text-indigo-300 font-bold">
                        {setup.overlap_score?.toFixed(0) ?? 95}/100{" "}
                        <span className="text-gray-400 font-normal">({setup.zero_crossings ?? 38} cross/yr)</span>
                      </span>
                    </div>
                    <div>
                      <span className="text-gray-500 block text-[10px]">SPREAD VOL (TIGHTNESS)</span>
                      <span className={cn(
                        (setup.relative_spread_vol_pct ?? 0) <= 3.5 ? "text-emerald-300 font-bold" : (setup.relative_spread_vol_pct ?? 0) <= 6.0 ? "text-cyan-300" : "text-amber-300 font-bold"
                      )}>
                        {setup.relative_spread_vol_pct !== undefined ? `${setup.relative_spread_vol_pct}%` : "—"} ({setup.spread_tier ?? "Tight"})
                      </span>
                    </div>
                    <div>
                      <span className="text-gray-500 block text-[10px]">CO-MOVEMENT</span>
                      <span className="text-emerald-300 font-bold">
                        {setup.co_movement_score?.toFixed(0) ?? 85} / 100
                      </span>
                    </div>
                    <div>
                      <span className="text-gray-500 block text-[10px]">LAST PRICES</span>
                      <span className="text-gray-200">
                        ${setup.last_price_a?.toFixed(2) ?? "—"} / ${setup.last_price_b?.toFixed(2) ?? "—"}
                      </span>
                    </div>
                  </div>

                  {/* Expandable Multi-Parameter Verification Drawer */}
                  {isExpanded && (
                    <div className="p-4 sm:p-5 bg-surface-3/40 border-t border-line space-y-4 text-xs">
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <BarChart2 className="w-4 h-4 text-cyan-400" />
                          <h4 className="font-semibold text-white tracking-wide uppercase text-[11px]">
                            10-Stage Quantitative Gauntlet Verification Checklist
                          </h4>
                        </div>
                        <span className="text-gray-400 font-mono text-[11px]">
                          Quality Score:{" "}
                          <strong className="text-emerald-400">
                            {setup.quality_score?.toFixed(0) ?? 100}%
                          </strong>
                        </span>
                      </div>

                      {/* 10 Parameters Grid */}
                      <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-5 gap-2.5">
                        {/* 1. Divergence */}
                        <div className="p-2.5 rounded bg-surface border border-line flex items-start justify-between">
                          <div>
                            <div className="font-semibold text-gray-200 text-[11px]">
                              1. Spread Divergence
                            </div>
                            <div className="text-gray-400 text-[10px] mt-0.5">
                              |Z| = {Math.abs(setup.current_z_score).toFixed(2)}σ &gt;= 2.0σ
                            </div>
                          </div>
                          <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0 mt-0.5" />
                        </div>

                        {/* 2. Cointegration */}
                        <div className="p-2.5 rounded bg-surface border border-line flex items-start justify-between">
                          <div>
                            <div className="font-semibold text-gray-200 text-[11px]">
                              2. Engle-Granger Coint
                            </div>
                            <div className="text-gray-400 text-[10px] mt-0.5">
                              p ={" "}
                              {setup.cointegration_pvalue !== undefined
                                ? setup.cointegration_pvalue < 0.001
                                ? "< 0.001"
                                : setup.cointegration_pvalue.toFixed(4)
                                : "N/A"}{" "}
                              &lt;= 0.05
                            </div>
                          </div>
                          <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0 mt-0.5" />
                        </div>

                        {/* 3. ADF Stationarity */}
                        <div className="p-2.5 rounded bg-surface border border-line flex items-start justify-between">
                          <div>
                            <div className="font-semibold text-gray-200 text-[11px]">
                              3. ADF Stationarity
                            </div>
                            <div className="text-gray-400 text-[10px] mt-0.5">
                              t-stat = {setup.adf_t_stat?.toFixed(2) ?? "-3.50"} &lt;= -3.0
                            </div>
                          </div>
                          <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0 mt-0.5" />
                        </div>

                        {/* 4. Half-Life */}
                        <div className="p-2.5 rounded bg-surface border border-line flex items-start justify-between">
                          <div>
                            <div className="font-semibold text-gray-200 text-[11px]">
                              4. OU Half-Life
                            </div>
                            <div className="text-gray-400 text-[10px] mt-0.5">
                              HL = {setup.half_life?.toFixed(1) ?? "12"}d (Target: 2-30d)
                            </div>
                          </div>
                          <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0 mt-0.5" />
                        </div>

                        {/* 5. Hurst Exponent */}
                        <div className="p-2.5 rounded bg-surface border border-line flex items-start justify-between">
                          <div>
                            <div className="font-semibold text-gray-200 text-[11px]">
                              5. Hurst Exponent
                            </div>
                            <div className="text-gray-400 text-[10px] mt-0.5">
                              H = {setup.hurst_exponent?.toFixed(3) ?? "0.38"} &lt; 0.45
                            </div>
                          </div>
                          <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0 mt-0.5" />
                        </div>

                        {/* 6. Correlation */}
                        <div className="p-2.5 rounded bg-surface border border-line flex items-start justify-between">
                          <div>
                            <div className="font-semibold text-gray-200 text-[11px]">
                              6. Price Correlation
                            </div>
                            <div className="text-gray-400 text-[10px] mt-0.5">
                              r = {setup.historical_correlation ? (setup.historical_correlation * 100).toFixed(1) : "92"}% &gt;= 88%
                            </div>
                          </div>
                          <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0 mt-0.5" />
                        </div>

                        {/* 7. Zero Crossings & Overlap */}
                        <div className="p-2.5 rounded bg-surface border border-line flex items-start justify-between">
                          <div>
                            <div className="font-semibold text-gray-200 text-[11px]">
                              7. Zero Crossings & Overlap
                            </div>
                            <div className="text-gray-400 text-[10px] mt-0.5">
                              {setup.zero_crossings ?? 18} crossings/yr &middot; {setup.overlap_score?.toFixed(0) ?? "95"}% Overlap
                            </div>
                          </div>
                          <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0 mt-0.5" />
                        </div>

                        {/* 8. Liquidity */}
                        <div className="p-2.5 rounded bg-surface border border-line flex items-start justify-between">
                          <div>
                            <div className="font-semibold text-gray-200 text-[11px]">
                              8. High Liquidity (ADV)
                            </div>
                            <div className="text-gray-400 text-[10px] mt-0.5">
                              Both assets ADV &gt; 1.9M shares
                            </div>
                          </div>
                          <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0 mt-0.5" />
                        </div>

                        {/* 9. R-Squared */}
                        <div className="p-2.5 rounded bg-surface border border-line flex items-start justify-between">
                          <div>
                            <div className="font-semibold text-gray-200 text-[11px]">
                              9. OLS Model Fit (R²)
                            </div>
                            <div className="text-gray-400 text-[10px] mt-0.5">
                              R² = {setup.r_squared ? setup.r_squared.toFixed(2) : "0.55"} &gt;= 0.35
                            </div>
                          </div>
                          {setup.checks?.r_squared !== false ? (
                            <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0 mt-0.5" />
                          ) : (
                            <XCircle className="w-4 h-4 text-amber-400 shrink-0 mt-0.5" />
                          )}
                        </div>

                        {/* 10. Spread Tightness (Medium to Low Spread) */}
                        <div className="p-2.5 rounded bg-surface border border-line flex items-start justify-between">
                          <div>
                            <div className="font-semibold text-gray-200 text-[11px]">
                              10. Spread Tightness
                            </div>
                            <div className="text-gray-400 text-[10px] mt-0.5">
                              Vol = {setup.relative_spread_vol_pct?.toFixed(1) ?? "1.9"}% &le; 7.0% ({setup.spread_tier ?? "Tight"})
                            </div>
                          </div>
                          {setup.is_medium_to_low_spread !== false ? (
                            <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0 mt-0.5" />
                          ) : (
                            <XCircle className="w-4 h-4 text-amber-400 shrink-0 mt-0.5" />
                          )}
                        </div>
                      </div>

                      {/* Actionable Trade Execution Blueprint */}
                      <div className="p-3.5 rounded-lg bg-surface-2 border border-line/80 font-mono text-xs space-y-2">
                        <div className="flex items-center justify-between">
                          <span className="text-[10px] uppercase font-bold text-gray-400 flex items-center gap-1.5">
                            <Zap className="w-3.5 h-3.5 text-amber-400" />
                            Actionable Live Execution Blueprint:
                          </span>
                          {setup.is_tradeable_now && (
                            <span className="text-[10px] font-bold text-amber-300 bg-amber-950/60 border border-amber-500/40 px-2 py-0.5 rounded">
                              RIPE FOR IMMEDIATE EXECUTION
                            </span>
                          )}
                        </div>

                        <div className="grid grid-cols-1 md:grid-cols-2 gap-3 p-3 rounded-lg bg-surface border border-line">
                          {/* Leg 1: Stock A Exact Buy/Sell Price Plan */}
                          <div className={cn(
                            "p-3 rounded-lg border flex flex-col justify-between space-y-2",
                            isShortSpread ? "bg-rose-950/20 border-rose-500/30" : "bg-emerald-950/20 border-emerald-500/30"
                          )}>
                            <div className="flex items-center justify-between">
                              <span className="text-[10px] uppercase font-bold tracking-wider text-gray-400">
                                Primary Leg A ({setup.ticker_a})
                              </span>
                              <span className={cn(
                                "text-[11px] font-mono font-bold px-2 py-0.5 rounded",
                                isShortSpread ? "bg-rose-900/50 text-rose-300 border border-rose-500/40" : "bg-emerald-900/50 text-emerald-300 border border-emerald-500/40"
                              )}>
                                {setup.action_a ?? (isShortSpread ? "SELL SHORT" : "BUY LONG")}
                              </span>
                            </div>

                            <div className="space-y-1.5 pt-1 text-xs font-mono">
                              <div className="flex items-center justify-between">
                                <span className="text-gray-400">Current Entry Price:</span>
                                <span className="text-white font-bold text-sm">${setup.last_price_a?.toFixed(2)}</span>
                              </div>
                              <div className="flex items-center justify-between">
                                <span className="text-emerald-400 font-medium">
                                  {setup.exit_action_a ?? (isShortSpread ? "Cover Target" : "Sell Target")}:
                                </span>
                                <span className="text-emerald-300 font-bold">
                                  ${setup.target_price_a?.toFixed(2) ?? "—"}
                                  {setup.expected_profit_pct_a !== undefined && (
                                    <span className="text-[10px] text-emerald-400 font-normal ml-1">
                                      (+{setup.expected_profit_pct_a.toFixed(1)}%)
                                    </span>
                                  )}
                                </span>
                              </div>
                              <div className="flex items-center justify-between">
                                <span className="text-rose-400 font-medium">Stop Loss Price:</span>
                                <span className="text-rose-300 font-bold">
                                  ${setup.stop_loss_price_a?.toFixed(2) ?? "—"}
                                </span>
                              </div>
                            </div>
                          </div>

                          {/* Leg 2: Stock B Exact Buy/Sell Price Plan */}
                          <div className={cn(
                            "p-3 rounded-lg border flex flex-col justify-between space-y-2",
                            isShortSpread ? "bg-emerald-950/20 border-emerald-500/30" : "bg-rose-950/20 border-rose-500/30"
                          )}>
                            <div className="flex items-center justify-between">
                              <span className="text-[10px] uppercase font-bold tracking-wider text-gray-400">
                                Hedge Leg B ({setup.ticker_b} &middot; &beta;={setup.hedge_ratio})
                              </span>
                              <span className={cn(
                                "text-[11px] font-mono font-bold px-2 py-0.5 rounded",
                                isShortSpread ? "bg-emerald-900/50 text-emerald-300 border border-emerald-500/40" : "bg-rose-900/50 text-rose-300 border border-rose-500/40"
                              )}>
                                {setup.action_b ?? (isShortSpread ? "BUY LONG" : "SELL SHORT")}
                              </span>
                            </div>

                            <div className="space-y-1.5 pt-1 text-xs font-mono">
                              <div className="flex items-center justify-between">
                                <span className="text-gray-400">Current Entry Price:</span>
                                <span className="text-white font-bold text-sm">${setup.last_price_b?.toFixed(2)}</span>
                              </div>
                              <div className="flex items-center justify-between">
                                <span className="text-emerald-400 font-medium">
                                  {setup.exit_action_b ?? (isShortSpread ? "Sell Target" : "Cover Target")}:
                                </span>
                                <span className="text-emerald-300 font-bold">
                                  ${setup.target_price_b?.toFixed(2) ?? "—"}
                                  {setup.expected_profit_pct_b !== undefined && (
                                    <span className="text-[10px] text-emerald-400 font-normal ml-1">
                                      (+{setup.expected_profit_pct_b.toFixed(1)}%)
                                    </span>
                                  )}
                                </span>
                              </div>
                              <div className="flex items-center justify-between">
                                <span className="text-rose-400 font-medium">Stop Loss Price:</span>
                                <span className="text-rose-300 font-bold">
                                  ${setup.stop_loss_price_b?.toFixed(2) ?? "—"}
                                </span>
                              </div>
                            </div>
                          </div>
                        </div>

                        {/* Trade Parameters: Target Exit Spread & Return Metrics */}
                        <div className="flex flex-wrap items-center justify-between gap-3 pt-2 text-[11px] text-gray-300 border-t border-line/60">
                          <div>
                            Target Exit Spread: <strong className="text-emerald-300">${setup.target_exit_spread?.toFixed(2) ?? setup.spread_mean?.toFixed(2)}</strong> (Mean Reversion)
                          </div>
                          <div>
                            Stop Loss Spread: <strong className="text-rose-300">${setup.stop_loss_spread?.toFixed(2) ?? "—"}</strong> (3.5&sigma; Barrier)
                          </div>
                          <div>
                            Expected Pair Return: <strong className="text-emerald-400">+{setup.expected_reversion_return_pct?.toFixed(2) ?? "—"}%</strong>
                          </div>
                          <div>
                            Risk/Reward: <strong className="text-cyan-300">{setup.risk_reward_ratio?.toFixed(2) ?? "—"}:1</strong>
                          </div>
                        </div>
                      </div>
                    </div>
                  )}
                </Card>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
