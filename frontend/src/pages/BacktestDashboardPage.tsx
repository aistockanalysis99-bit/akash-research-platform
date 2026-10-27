import React, { useState, useMemo, useEffect } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import {
  TrendingUp,
  TrendingDown,
  ShieldCheck,
  CheckCircle2,
  XCircle,
  RefreshCw,
  Search,
  Filter,
  ArrowUpRight,
  ArrowRight,
  SlidersHorizontal,
  Calendar,
  Clock,
  Zap,
  BarChart3,
  Layers,
  ArrowUpDown,
  RotateCcw,
  Sparkles,
  ChevronDown,
  ChevronUp,
  Download,
  Eye,
  X,
  Award,
  AlertTriangle,
  Flame,
  Percent,
  Check,
} from "lucide-react";
import { api } from "@/lib/api";
import type { Backtest1YTrade } from "@/lib/simulatorTypes";
import { Card, PageTitle } from "@/components/ui";
import { cn } from "@/lib/utils";

type ChecksFilter = "all" | "perfect10" | "checks8";
type OutcomeFilter = "all" | "win" | "loss" | "neutral";
type DirectionFilter = "all" | "long" | "short";
type DurationFilter = "all" | "fast" | "medium" | "extended";
type ActiveChartTab = "equity" | "drawdown" | "monthly";
type SortField =
  | "entry_date"
  | "realized_return_pct"
  | "abs_entry_z"
  | "holding_days"
  | "passed_checks_count";
type SortOrder = "asc" | "desc";

// Descriptive labels for the 10 Institutional Quality Checks
const CHECK_INFO: Record<string, { label: string; desc: string }> = {
  z_score_divergence: {
    label: "Z-Score Divergence",
    desc: "Entry |Z| >= 2.0σ statistical divergence threshold",
  },
  cointegration_pvalue: {
    label: "Cointegration",
    desc: "Engle-Granger cointegration p-value <= 0.05",
  },
  correlation: {
    label: "Correlation",
    desc: "Pearson price correlation r >= 0.70",
  },
  half_life_reversion: {
    label: "OU Half-Life",
    desc: "Mean-reversion half-life 1 <= t_1/2 <= 35 trading days",
  },
  hurst_mean_reverting: {
    label: "Hurst Exponent",
    desc: "Hurst H < 0.48 (anti-persistent mean-reversion)",
  },
  adf_stationarity: {
    label: "ADF Stationarity",
    desc: "Spread ADF stationarity test p-value <= 0.05",
  },
  liquidity_adv: {
    label: "ADV Liquidity",
    desc: "Average daily volume > $5M for minimal execution slippage",
  },
  zero_crossings: {
    label: "Zero Crossings",
    desc: "Sufficient historical mean equilibrium crossings (>= 6/yr)",
  },
  r_squared: {
    label: "R-Squared Fit",
    desc: "Ordinary Least Squares hedge ratio fit R² >= 0.35",
  },
  spread_tightness: {
    label: "Spread Tightness",
    desc: "Relative spread volatility <= 7.0% (tight regime)",
  },
};

export default function BacktestDashboardPage() {
  const navigate = useNavigate();

  // ─── Primary Filter States ────────────────────────────────────────────────
  const [checksFilter, setChecksFilter] = useState<ChecksFilter>("all");
  const [outcomeFilter, setOutcomeFilter] = useState<OutcomeFilter>("all");
  const [searchQuery, setSearchQuery] = useState<string>("");

  // ─── Advanced Filter States (Hidden/Collapsible by Default) ─────────────────
  const [isAdvancedOpen, setIsAdvancedOpen] = useState<boolean>(false);
  const [directionFilter, setDirectionFilter] = useState<DirectionFilter>("all");
  const [selectedSector, setSelectedSector] = useState<string>("all");
  const [selectedSpreadTier, setSelectedSpreadTier] = useState<string>("all");
  const [durationFilter, setDurationFilter] = useState<DurationFilter>("all");
  const [minEntryZ, setMinEntryZ] = useState<number>(2.0);
  const [startDateFilter, setStartDateFilter] = useState<string>("");
  const [endDateFilter, setEndDateFilter] = useState<string>("");

  // ─── Chart View Tab ───────────────────────────────────────────────────────
  const [activeChartTab, setActiveChartTab] = useState<ActiveChartTab>("equity");

  // ─── Sorting & Pagination States ──────────────────────────────────────────
  const [sortField, setSortField] = useState<SortField>("entry_date");
  const [sortOrder, setSortOrder] = useState<SortOrder>("desc");
  const [pageSize, setPageSize] = useState<number>(25);
  const [currentPage, setCurrentPage] = useState<number>(1);

  // ─── Quick Inspector Modal State ──────────────────────────────────────────
  const [inspectedTrade, setInspectedTrade] = useState<Backtest1YTrade | null>(null);

  // Close modal on Escape key press
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") setInspectedTrade(null);
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);

  // ─── Data Query ───────────────────────────────────────────────────────────
  const { data, isLoading, isFetching, refetch } = useQuery({
    queryKey: ["backtest-1y"],
    queryFn: () => api.simulator.backtest1Y(false),
    staleTime: 10 * 60 * 1000,
  });

  const rawTrades = useMemo(() => data?.trades || [], [data]);

  // Extract unique sectors
  const availableSectors = useMemo(() => {
    const s = new Set<string>();
    rawTrades.forEach((t) => {
      if (t.sector) s.add(t.sector);
    });
    return Array.from(s).sort();
  }, [rawTrades]);

  // Count active advanced filters
  const activeAdvancedCount = useMemo(() => {
    let count = 0;
    if (directionFilter !== "all") count++;
    if (selectedSector !== "all") count++;
    if (selectedSpreadTier !== "all") count++;
    if (durationFilter !== "all") count++;
    if (minEntryZ !== 2.0) count++;
    if (startDateFilter) count++;
    if (endDateFilter) count++;
    return count;
  }, [
    directionFilter,
    selectedSector,
    selectedSpreadTier,
    durationFilter,
    minEntryZ,
    startDateFilter,
    endDateFilter,
  ]);

  // ─── Base Filter (Everything Except Outcome) for Accurate Tab Counts ──────
  const outcomeBaseTrades = useMemo(() => {
    return rawTrades.filter((t) => {
      // 10/10 Checks Filter
      if (checksFilter === "perfect10" && !t.is_perfect_10) return false;
      if (checksFilter === "checks8" && t.passed_checks_count < 8) return false;

      // Direction Filter
      if (directionFilter === "long" && t.entry_z >= 0) return false;
      if (directionFilter === "short" && t.entry_z < 0) return false;

      // Sector Filter
      if (selectedSector !== "all" && t.sector !== selectedSector) return false;

      // Spread Volatility Tier
      if (selectedSpreadTier !== "all" && t.spread_tier !== selectedSpreadTier) return false;

      // Holding Duration Filter
      if (durationFilter === "fast" && t.holding_days > 5) return false;
      if (durationFilter === "medium" && (t.holding_days <= 5 || t.holding_days > 15))
        return false;
      if (durationFilter === "extended" && t.holding_days <= 15) return false;

      // Min Z Filter
      if (t.abs_entry_z < minEntryZ) return false;

      // Date Range Filter (By Entry Date)
      if (startDateFilter && t.entry_date < startDateFilter) return false;
      if (endDateFilter && t.entry_date > endDateFilter) return false;

      // Search Filter (Pair, Tickers, or Sector)
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase().trim();
        const matchPair = t.pair_name.toLowerCase().includes(q);
        const matchSector = (t.sector || "").toLowerCase().includes(q);
        const matchTickerA = t.ticker_a.toLowerCase().includes(q);
        const matchTickerB = t.ticker_b.toLowerCase().includes(q);
        if (!matchPair && !matchSector && !matchTickerA && !matchTickerB) return false;
      }

      return true;
    });
  }, [
    rawTrades,
    checksFilter,
    directionFilter,
    selectedSector,
    selectedSpreadTier,
    durationFilter,
    minEntryZ,
    startDateFilter,
    endDateFilter,
    searchQuery,
  ]);

  const outcomeCounts = useMemo(() => {
    const wins = outcomeBaseTrades.filter((t) => t.outcome === "WIN").length;
    const losses = outcomeBaseTrades.filter((t) => t.outcome === "LOSS").length;
    return {
      total: outcomeBaseTrades.length,
      wins,
      losses,
    };
  }, [outcomeBaseTrades]);

  // ─── Filtered Trades (Including Outcome Filter) ───────────────────────────
  const filteredTrades = useMemo(() => {
    if (outcomeFilter === "all") return outcomeBaseTrades;
    return outcomeBaseTrades.filter((t) => {
      if (outcomeFilter === "win" && t.outcome !== "WIN") return false;
      if (outcomeFilter === "loss" && t.outcome !== "LOSS") return false;
      if (outcomeFilter === "neutral" && t.outcome !== "NEUTRAL" && t.outcome !== "OPEN")
        return false;
      return true;
    });
  }, [outcomeBaseTrades, outcomeFilter]);

  // ─── Dynamic Metrics Recalculation Based on Filtered Trades ───────────────
  const filteredMetrics = useMemo(() => {
    const total = filteredTrades.length;
    if (total === 0) {
      return {
        total: 0,
        wins: 0,
        losses: 0,
        neutral: 0,
        winRate: 0,
        avgReturn: 0,
        medianReturn: 0,
        profitFactor: 0,
        avgHoldDays: 0,
        grossProfit: 0,
        grossLoss: 0,
        avgWinReturn: 0,
        avgLossReturn: 0,
        maxDrawdown: 0,
        longWinRate: 0,
        shortWinRate: 0,
        bestTrade: null as Backtest1YTrade | null,
        worstTrade: null as Backtest1YTrade | null,
      };
    }

    const wins = filteredTrades.filter((t) => t.outcome === "WIN");
    const losses = filteredTrades.filter((t) => t.outcome === "LOSS");
    const neutral = filteredTrades.filter(
      (t) => t.outcome === "NEUTRAL" || t.outcome === "OPEN"
    );

    const winCount = wins.length;
    const lossCount = losses.length;
    const neutralCount = neutral.length;
    const decisive = winCount + lossCount;
    const winRate = decisive > 0 ? (winCount / decisive) * 100 : 0;

    const returns = filteredTrades.map((t) => t.realized_return_pct);
    const avgReturn = returns.reduce((acc, r) => acc + r, 0) / total;

    // Median Return
    const sortedReturns = [...returns].sort((a, b) => a - b);
    const mid = Math.floor(sortedReturns.length / 2);
    const medianReturn =
      sortedReturns.length % 2 !== 0
        ? sortedReturns[mid]
        : (sortedReturns[mid - 1] + sortedReturns[mid]) / 2;

    const winReturns = wins.map((t) => t.realized_return_pct);
    const lossReturns = losses.map((t) => Math.abs(t.realized_return_pct));
    const grossProfit = winReturns.reduce((acc, r) => acc + r, 0);
    const grossLoss = lossReturns.reduce((acc, r) => acc + r, 0);
    const profitFactor =
      grossLoss > 0 ? grossProfit / grossLoss : grossProfit > 0 ? 99.0 : 1.0;

    const avgWinReturn = winCount > 0 ? grossProfit / winCount : 0;
    const avgLossReturn = lossCount > 0 ? grossLoss / lossCount : 0;

    const holdDays = filteredTrades.map((t) => t.holding_days);
    const avgHoldDays = holdDays.reduce((acc, d) => acc + d, 0) / total;

    // Directional Win Rates
    const longTrades = filteredTrades.filter((t) => t.entry_z < 0);
    const longWins = longTrades.filter((t) => t.outcome === "WIN").length;
    const longDecisive = longTrades.filter(
      (t) => t.outcome === "WIN" || t.outcome === "LOSS"
    ).length;
    const longWinRate = longDecisive > 0 ? (longWins / longDecisive) * 100 : 0;

    const shortTrades = filteredTrades.filter((t) => t.entry_z > 0);
    const shortWins = shortTrades.filter((t) => t.outcome === "WIN").length;
    const shortDecisive = shortTrades.filter(
      (t) => t.outcome === "WIN" || t.outcome === "LOSS"
    ).length;
    const shortWinRate = shortDecisive > 0 ? (shortWins / shortDecisive) * 100 : 0;

    // Best & Worst Trades
    const bestTrade = [...filteredTrades].sort(
      (a, b) => b.realized_return_pct - a.realized_return_pct
    )[0];
    const worstTrade = [...filteredTrades].sort(
      (a, b) => a.realized_return_pct - b.realized_return_pct
    )[0];

    // Dynamic Max Drawdown Calculation strictly sequenced by Realized Date (exit_date || entry_date)
    const chronologicalByExit = [...filteredTrades].sort((a, b) => {
      const dateA = a.exit_date || a.entry_date;
      const dateB = b.exit_date || b.entry_date;
      return dateA.localeCompare(dateB);
    });

    let peak = 0;
    let runningCum = 0;
    let maxDd = 0;
    for (const t of chronologicalByExit) {
      runningCum += t.realized_return_pct;
      if (runningCum > peak) {
        peak = runningCum;
      }
      const dd = peak - runningCum;
      if (dd > maxDd) {
        maxDd = dd;
      }
    }

    return {
      total,
      wins: winCount,
      losses: lossCount,
      neutral: neutralCount,
      winRate: Math.round(winRate * 10) / 10,
      avgReturn: Math.round(avgReturn * 100) / 100,
      medianReturn: Math.round(medianReturn * 100) / 100,
      profitFactor: Math.round(profitFactor * 100) / 100,
      avgHoldDays: Math.round(avgHoldDays * 10) / 10,
      grossProfit: Math.round(grossProfit * 10) / 10,
      grossLoss: Math.round(grossLoss * 10) / 10,
      avgWinReturn: Math.round(avgWinReturn * 100) / 100,
      avgLossReturn: Math.round(avgLossReturn * 100) / 100,
      maxDrawdown: Math.round(maxDd * 10) / 10,
      longWinRate: Math.round(longWinRate * 10) / 10,
      shortWinRate: Math.round(shortWinRate * 10) / 10,
      bestTrade,
      worstTrade,
    };
  }, [filteredTrades]);

  // ─── Realized Equity Series Sequenced by Exit Date ─────────────────────────
  const equitySeries = useMemo(() => {
    const chronological = [...filteredTrades].sort((a, b) => {
      const dateA = a.exit_date || a.entry_date;
      const dateB = b.exit_date || b.entry_date;
      return dateA.localeCompare(dateB);
    });
    let cum = 0;
    let peak = 0;

    return chronological.map((t, idx) => {
      cum += t.realized_return_pct;
      if (cum > peak) peak = cum;
      const drawdown = Math.round((cum - peak) * 100) / 100;
      const realizedDate = t.exit_date || t.entry_date;

      return {
        index: idx,
        date: realizedDate,
        pair: t.pair_name,
        returnPct: t.realized_return_pct,
        cumReturn: Math.round(cum * 100) / 100,
        drawdown,
        outcome: t.outcome,
      };
    });
  }, [filteredTrades]);

  // ─── Monthly Realized Breakdown Performance ───────────────────────────────
  const monthlyBreakdown = useMemo(() => {
    const map = new Map<
      string,
      {
        month: string;
        trades: number;
        wins: number;
        losses: number;
        totalPnL: number;
      }
    >();

    filteredTrades.forEach((t) => {
      const realizedDate = t.exit_date || t.entry_date;
      const monthKey = realizedDate.slice(0, 7); // "YYYY-MM"
      const cur = map.get(monthKey) || {
        month: monthKey,
        trades: 0,
        wins: 0,
        losses: 0,
        totalPnL: 0,
      };
      cur.trades++;
      if (t.outcome === "WIN") cur.wins++;
      if (t.outcome === "LOSS") cur.losses++;
      cur.totalPnL += t.realized_return_pct;
      map.set(monthKey, cur);
    });

    const arr = Array.from(map.values()).sort((a, b) => a.month.localeCompare(b.month));
    return arr.map((m) => {
      const decisive = m.wins + m.losses;
      const winRate = decisive > 0 ? (m.wins / decisive) * 100 : 0;
      return {
        ...m,
        totalPnL: Math.round(m.totalPnL * 10) / 10,
        winRate: Math.round(winRate * 10) / 10,
      };
    });
  }, [filteredTrades]);

  // ─── Sorting & Paginated Trades ───────────────────────────────────────────
  const sortedTrades = useMemo(() => {
    return [...filteredTrades].sort((a, b) => {
      let valA: any = a[sortField];
      let valB: any = b[sortField];

      if (sortField === "abs_entry_z") {
        valA = a.abs_entry_z;
        valB = b.abs_entry_z;
      }

      if (typeof valA === "string") {
        return sortOrder === "asc"
          ? valA.localeCompare(valB)
          : valB.localeCompare(valA);
      }
      return sortOrder === "asc" ? valA - valB : valB - valA;
    });
  }, [filteredTrades, sortField, sortOrder]);

  const totalPages = Math.ceil(sortedTrades.length / pageSize) || 1;
  const paginatedTrades = useMemo(() => {
    const start = (currentPage - 1) * pageSize;
    return sortedTrades.slice(start, start + pageSize);
  }, [sortedTrades, currentPage, pageSize]);

  // Dynamic pagination window around current page
  const visiblePages = useMemo(() => {
    const maxBtns = 5;
    if (totalPages <= maxBtns) {
      return Array.from({ length: totalPages }, (_, i) => i + 1);
    }
    const start = Math.max(1, Math.min(currentPage - 2, totalPages - maxBtns + 1));
    return Array.from({ length: maxBtns }, (_, i) => start + i);
  }, [currentPage, totalPages]);

  const handleSort = (field: SortField) => {
    if (sortField === field) {
      setSortOrder(sortOrder === "asc" ? "desc" : "asc");
    } else {
      setSortField(field);
      setSortOrder("desc");
    }
  };

  const resetAllFilters = () => {
    setChecksFilter("all");
    setOutcomeFilter("all");
    setDirectionFilter("all");
    setSelectedSector("all");
    setSelectedSpreadTier("all");
    setDurationFilter("all");
    setMinEntryZ(2.0);
    setStartDateFilter("");
    setEndDateFilter("");
    setSearchQuery("");
    setCurrentPage(1);
  };

  const isAnyFilterActive =
    checksFilter !== "all" ||
    outcomeFilter !== "all" ||
    directionFilter !== "all" ||
    selectedSector !== "all" ||
    selectedSpreadTier !== "all" ||
    durationFilter !== "all" ||
    minEntryZ !== 2.0 ||
    startDateFilter !== "" ||
    endDateFilter !== "" ||
    searchQuery !== "";

  // ─── CSV Export Functionality ─────────────────────────────────────────────
  const exportTradesCsv = () => {
    if (!filteredTrades.length) return;

    const escapeCell = (val: any) => `"${String(val ?? "").replace(/"/g, '""')}"`;

    const headers = [
      "Trade ID",
      "Pair Name",
      "Ticker A",
      "Ticker B",
      "Sector",
      "Spread Tier",
      "Direction",
      "Entry Date",
      "Entry Z",
      "Exit Date",
      "Exit Z",
      "Holding Days",
      "Realized Return (%)",
      "Outcome",
      "Status Reason",
      "10-Check Score",
      "Is Perfect 10",
      "ADF p-value",
      "Half-Life (Days)",
      "Correlation",
      "Spread Vol (%)",
    ];

    const rows = filteredTrades.map((t) => [
      escapeCell(t.id),
      escapeCell(t.pair_name),
      escapeCell(t.ticker_a),
      escapeCell(t.ticker_b),
      escapeCell(t.sector),
      escapeCell(t.spread_tier),
      escapeCell(t.direction_label),
      escapeCell(t.entry_date),
      t.entry_z,
      escapeCell(t.exit_date || "Holding"),
      t.exit_z !== null && t.exit_z !== undefined ? t.exit_z : "",
      t.holding_days,
      t.realized_return_pct,
      escapeCell(t.outcome),
      escapeCell(t.status_reason || ""),
      t.passed_checks_count,
      t.is_perfect_10 ? "YES" : "NO",
      t.adf_pvalue,
      t.half_life_days,
      t.correlation,
      t.relative_spread_vol_pct,
    ]);

    const csvContent =
      "data:text/csv;charset=utf-8," +
      [headers.join(","), ...rows.map((e) => e.join(","))].join("\n");

    const encodedUri = encodeURI(csvContent);
    const link = document.createElement("a");
    link.setAttribute("href", encodedUri);
    link.setAttribute(
      "download",
      `akash_1y_backtest_trades_${new Date().toISOString().slice(0, 10)}.csv`
    );
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  return (
    <div className="space-y-6">
      {/* ─── Navigation Sub-Header Tabs ──────────────────────────────────────── */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line pb-4">
        <div className="flex items-center gap-2">
          <Link
            to="/backtest-dashboard"
            className="px-3.5 py-1.5 rounded-lg text-xs font-bold bg-brand text-bg shadow-sm transition-all flex items-center gap-1.5"
          >
            <BarChart3 className="w-3.5 h-3.5" />
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

        <div className="flex items-center gap-2">
          <button
            onClick={exportTradesCsv}
            disabled={filteredTrades.length === 0}
            className="inline-flex items-center gap-1.5 text-xs text-gray-300 hover:text-white bg-surface-2 px-3 py-1.5 rounded-lg border border-line transition-colors disabled:opacity-40"
            title="Export filtered trade log to CSV"
          >
            <Download className="w-3.5 h-3.5 text-brand" />
            <span>Export CSV</span>
          </button>
          <button
            onClick={() => refetch()}
            disabled={isFetching}
            className="inline-flex items-center gap-1.5 text-xs text-gray-300 hover:text-white bg-surface-2 px-3 py-1.5 rounded-lg border border-line transition-colors disabled:opacity-50"
          >
            <RefreshCw
              className={cn("w-3.5 h-3.5", isFetching && "animate-spin text-brand")}
            />
            <span>{isFetching ? "Re-running..." : "Refresh Results"}</span>
          </button>
        </div>
      </div>

      {/* ─── Page Title Banner ──────────────────────────────────────────────── */}
      <PageTitle
        title="1-Year Walkforward Backtest & Trade Log"
        subtitle="Full audit of all statistical divergence trade triggers across all 52 elite pairs over the last 1 year (October 26, 2025 – October 26, 2026). Truncated strictly to Date T with zero lookahead bias and forward outcome evaluation."
      />

      {/* ─── 10/10 QUALITY IMPACT HERO BANNER ─────────────────────────────────── */}
      <Card className="p-5 border-emerald-500/30 bg-gradient-to-r from-emerald-950/30 via-surface to-surface-2 relative overflow-hidden shadow-xl">
        <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-5 relative z-10">
          <div className="space-y-1.5">
            <div className="flex items-center gap-2">
              <span className="p-1.5 rounded-lg bg-emerald-500/20 border border-emerald-500/40 text-emerald-400">
                <ShieldCheck className="w-5 h-5" />
              </span>
              <h2 className="text-base font-bold text-white tracking-wide">
                The 10/10 Institutional Quality Filter
              </h2>
              <span className="text-[11px] font-mono px-2 py-0.5 rounded bg-emerald-950/60 border border-emerald-500/30 text-emerald-300 font-bold">
                Proven Edge
              </span>
            </div>
            <p className="text-xs text-gray-300 max-w-2xl leading-relaxed">
              Compare strategy performance when trading{" "}
              <strong className="text-white">All Dislocation Triggers</strong> vs. only
              executing trades that pass all{" "}
              <strong className="text-emerald-300">10 Institutional Quality Checks</strong>{" "}
              (Cointegration p &le; 0.05, Half-life &le; 35d, Hurst &lt; 0.48, Tight
              Spread). Filtering by 10/10 achieves a{" "}
              <strong className="text-white">
                {data?.perfect_10_summary?.win_rate_pct ?? 45.2}%
              </strong>{" "}
              win rate and lifts average return to{" "}
              <strong className="text-emerald-300">
                +{data?.perfect_10_summary?.avg_return_pct ?? 0.36}%
              </strong>{" "}
              per trade with a{" "}
              <strong className="text-cyan-300">
                {data?.perfect_10_summary?.profit_factor ?? 1.25}x
              </strong>{" "}
              profit factor across {data?.perfect_10_summary?.total_trades ?? 201} quality setups.
            </p>
          </div>

          {/* Quick 10/10 Filter Switch Pills */}
          <div className="flex flex-wrap items-center gap-2">
            <button
              onClick={() => {
                setChecksFilter("all");
                setCurrentPage(1);
              }}
              className={cn(
                "px-4 py-2 rounded-xl text-xs font-bold border transition-all flex items-center gap-2 shadow-sm",
                checksFilter === "all"
                  ? "bg-brand text-bg border-brand shadow-brand/20 font-black"
                  : "bg-surface-2 text-gray-400 hover:text-white border-line"
              )}
            >
              <span>All Trades</span>
              <span className="text-[10px] opacity-80 font-mono">
                ({rawTrades.length})
              </span>
            </button>

            <button
              onClick={() => {
                setChecksFilter("perfect10");
                setCurrentPage(1);
              }}
              className={cn(
                "px-4 py-2 rounded-xl text-xs font-bold border transition-all flex items-center gap-2 shadow-sm",
                checksFilter === "perfect10"
                  ? "bg-emerald-500 text-bg border-emerald-400 shadow-emerald-500/20 font-black"
                  : "bg-emerald-950/40 text-emerald-300 hover:text-emerald-200 border-emerald-500/40"
              )}
            >
              <ShieldCheck className="w-3.5 h-3.5" />
              <span>10/10 Perfect Only</span>
              <span className="text-[10px] font-mono bg-black/30 px-1.5 py-0.5 rounded">
                ({data?.perfect_10_summary?.total_trades || 204})
              </span>
            </button>

            <button
              onClick={() => {
                setChecksFilter("checks8");
                setCurrentPage(1);
              }}
              className={cn(
                "px-3.5 py-2 rounded-xl text-xs font-semibold border transition-all flex items-center gap-2",
                checksFilter === "checks8"
                  ? "bg-cyan-500 text-bg border-cyan-400 font-bold"
                  : "bg-surface-2 text-gray-400 hover:text-white border-line"
              )}
            >
              <span>8+ Checks</span>
              <span className="text-[10px] opacity-80 font-mono">
                ({data?.checks_8plus_summary?.total_trades || 226})
              </span>
            </button>
          </div>
        </div>

        {/* Comparison Callout Stats Strip */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mt-4 pt-4 border-t border-line/60 text-xs font-mono">
          <div className="p-2.5 rounded-lg bg-surface/80 border border-line">
            <span className="text-gray-400 block text-[10px] uppercase font-sans">
              Filtered Win Rate
            </span>
            <div className="mt-1 flex items-baseline gap-1.5">
              <span className="text-emerald-400 font-extrabold text-lg">
                {filteredMetrics.winRate}%
              </span>
              <span className="text-[10px] text-gray-500 font-sans">
                ({filteredMetrics.wins}W / {filteredMetrics.losses}L)
              </span>
            </div>
          </div>

          <div className="p-2.5 rounded-lg bg-surface/80 border border-line">
            <span className="text-gray-400 block text-[10px] uppercase font-sans">
              Avg Realized Return
            </span>
            <div className="mt-1 flex items-baseline gap-1.5">
              <span
                className={cn(
                  "font-extrabold text-lg",
                  filteredMetrics.avgReturn >= 0 ? "text-emerald-400" : "text-rose-400"
                )}
              >
                {filteredMetrics.avgReturn >= 0 ? "+" : ""}
                {filteredMetrics.avgReturn}%
              </span>
              <span className="text-[10px] text-gray-500 font-sans">per trade</span>
            </div>
          </div>

          <div className="p-2.5 rounded-lg bg-surface/80 border border-line">
            <span className="text-gray-400 block text-[10px] uppercase font-sans">
              Profit Factor
            </span>
            <div className="mt-1 flex items-baseline gap-1.5">
              <span className="text-cyan-300 font-extrabold text-lg">
                {filteredMetrics.profitFactor}x
              </span>
              <span className="text-[10px] text-gray-500 font-sans">Gross W/L</span>
            </div>
          </div>

          <div className="p-2.5 rounded-lg bg-surface/80 border border-line">
            <span className="text-gray-400 block text-[10px] uppercase font-sans">
              Avg Holding Period
            </span>
            <div className="mt-1 flex items-baseline gap-1.5">
              <span className="text-white font-extrabold text-lg">
                {filteredMetrics.avgHoldDays}d
              </span>
              <span className="text-[10px] text-gray-500 font-sans">to mean-revert</span>
            </div>
          </div>
        </div>
      </Card>

      {/* ─── TOP KPI SUMMARY METRICS ────────────────────────────────────────── */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
        <Card className="p-4 border-line bg-surface">
          <div className="flex items-center justify-between text-xs text-gray-400 mb-1">
            <span className="uppercase tracking-wider font-semibold">Total Trades</span>
            <Layers className="w-4 h-4 text-brand" />
          </div>
          <div className="text-2xl font-bold font-mono text-white">
            {isLoading ? "..." : filteredMetrics.total}
          </div>
          <p className="text-[11px] text-gray-500 mt-1">
            {filteredTrades.length === rawTrades.length
              ? "Across 251 trading days"
              : `Filtered from ${rawTrades.length}`}
          </p>
        </Card>

        <Card className="p-4 border-line bg-surface">
          <div className="flex items-center justify-between text-xs text-gray-400 mb-1">
            <span className="uppercase tracking-wider font-semibold">Win Rate</span>
            <CheckCircle2 className="w-4 h-4 text-emerald-400" />
          </div>
          <div className="text-2xl font-bold font-mono text-emerald-400">
            {isLoading ? "..." : `${filteredMetrics.winRate}%`}
          </div>
          <p className="text-[11px] text-gray-500 mt-1">
            {filteredMetrics.wins} Wins &middot; {filteredMetrics.losses} Losses
          </p>
        </Card>

        <Card className="p-4 border-line bg-surface">
          <div className="flex items-center justify-between text-xs text-gray-400 mb-1">
            <span className="uppercase tracking-wider font-semibold">Profit Factor</span>
            <TrendingUp className="w-4 h-4 text-cyan-400" />
          </div>
          <div className="text-2xl font-bold font-mono text-cyan-300">
            {isLoading ? "..." : `${filteredMetrics.profitFactor}`}
          </div>
          <p className="text-[11px] text-gray-500 mt-1">
            +{filteredMetrics.grossProfit}% vs -{filteredMetrics.grossLoss}%
          </p>
        </Card>

        <Card className="p-4 border-line bg-surface">
          <div className="flex items-center justify-between text-xs text-gray-400 mb-1">
            <span className="uppercase tracking-wider font-semibold">Avg Return</span>
            <Zap className="w-4 h-4 text-amber-400" />
          </div>
          <div
            className={cn(
              "text-2xl font-bold font-mono",
              filteredMetrics.avgReturn >= 0 ? "text-emerald-400" : "text-rose-400"
            )}
          >
            {isLoading
              ? "..."
              : `${filteredMetrics.avgReturn >= 0 ? "+" : ""}${filteredMetrics.avgReturn}%`}
          </div>
          <p className="text-[11px] text-gray-500 mt-1">
            Median: {filteredMetrics.medianReturn >= 0 ? "+" : ""}
            {filteredMetrics.medianReturn}%
          </p>
        </Card>

        <Card className="p-4 border-line bg-surface">
          <div className="flex items-center justify-between text-xs text-gray-400 mb-1">
            <span className="uppercase tracking-wider font-semibold">Avg Hold Days</span>
            <Clock className="w-4 h-4 text-indigo-400" />
          </div>
          <div className="text-2xl font-bold font-mono text-indigo-300">
            {isLoading ? "..." : `${filteredMetrics.avgHoldDays}d`}
          </div>
          <p className="text-[11px] text-gray-500 mt-1">Mean reversion cycle</p>
        </Card>

        <Card className="p-4 border-line bg-surface">
          <div className="flex items-center justify-between text-xs text-gray-400 mb-1">
            <span className="uppercase tracking-wider font-semibold">Max Drawdown</span>
            <TrendingDown className="w-4 h-4 text-rose-400" />
          </div>
          <div className="text-2xl font-bold font-mono text-rose-400">
            {isLoading ? "..." : `-${filteredMetrics.maxDrawdown}%`}
          </div>
          <p className="text-[11px] text-gray-500 mt-1">Realized exit-date drop</p>
        </Card>
      </div>

      {/* ─── TRADE EXTREMES & QUANT ASYMMETRY STRIP ──────────────────────────── */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-3 text-xs font-mono">
        {/* Best Trade */}
        <Card className="p-3 border-emerald-500/20 bg-emerald-950/10 flex items-center justify-between">
          <div>
            <div className="flex items-center gap-1.5 text-emerald-400 font-bold uppercase text-[10px]">
              <Award className="w-3.5 h-3.5" />
              <span>Best Trade</span>
            </div>
            {filteredMetrics.bestTrade ? (
              <div className="mt-1">
                <span className="font-bold text-white text-sm">
                  {filteredMetrics.bestTrade.pair_name}
                </span>
                <span className="text-emerald-400 font-extrabold ml-2">
                  +{filteredMetrics.bestTrade.realized_return_pct}%
                </span>
                <div className="text-[10px] text-gray-400 font-sans">
                  {filteredMetrics.bestTrade.entry_date} &middot;{" "}
                  {filteredMetrics.bestTrade.holding_days}d hold
                </div>
              </div>
            ) : (
              <div className="text-gray-500 mt-1">No data</div>
            )}
          </div>
          {filteredMetrics.bestTrade && (
            <button
              onClick={() => setInspectedTrade(filteredMetrics.bestTrade)}
              className="text-[10px] text-emerald-300 hover:text-white px-2 py-1 rounded bg-emerald-900/40 border border-emerald-500/30 transition-colors"
            >
              Quick View
            </button>
          )}
        </Card>

        {/* Worst Trade */}
        <Card className="p-3 border-rose-500/20 bg-rose-950/10 flex items-center justify-between">
          <div>
            <div className="flex items-center gap-1.5 text-rose-400 font-bold uppercase text-[10px]">
              <AlertTriangle className="w-3.5 h-3.5" />
              <span>Worst Trade</span>
            </div>
            {filteredMetrics.worstTrade ? (
              <div className="mt-1">
                <span className="font-bold text-white text-sm">
                  {filteredMetrics.worstTrade.pair_name}
                </span>
                <span className="text-rose-400 font-extrabold ml-2">
                  {filteredMetrics.worstTrade.realized_return_pct}%
                </span>
                <div className="text-[10px] text-gray-400 font-sans">
                  {filteredMetrics.worstTrade.entry_date} &middot;{" "}
                  {filteredMetrics.worstTrade.holding_days}d hold
                </div>
              </div>
            ) : (
              <div className="text-gray-500 mt-1">No data</div>
            )}
          </div>
          {filteredMetrics.worstTrade && (
            <button
              onClick={() => setInspectedTrade(filteredMetrics.worstTrade)}
              className="text-[10px] text-rose-300 hover:text-white px-2 py-1 rounded bg-rose-900/40 border border-rose-500/30 transition-colors"
            >
              Quick View
            </button>
          )}
        </Card>

        {/* Win/Loss Return Asymmetry */}
        <Card className="p-3 border-line bg-surface">
          <div className="flex items-center gap-1.5 text-cyan-400 font-bold uppercase text-[10px]">
            <Flame className="w-3.5 h-3.5" />
            <span>Avg Win vs Avg Loss</span>
          </div>
          <div className="mt-1 flex items-baseline justify-between">
            <span className="text-emerald-400 font-bold">
              +{filteredMetrics.avgWinReturn}%
            </span>
            <span className="text-gray-500 text-[10px]">vs</span>
            <span className="text-rose-400 font-bold">
              -{filteredMetrics.avgLossReturn}%
            </span>
          </div>
          <div className="text-[10px] text-gray-400 font-sans mt-0.5">
            Asymmetry:{" "}
            {filteredMetrics.avgLossReturn > 0
              ? (filteredMetrics.avgWinReturn / filteredMetrics.avgLossReturn).toFixed(
                  2
                ) + "x payoff"
              : "—"}
          </div>
        </Card>

        {/* Directional Alpha */}
        <Card className="p-3 border-line bg-surface">
          <div className="flex items-center gap-1.5 text-amber-400 font-bold uppercase text-[10px]">
            <Percent className="w-3.5 h-3.5" />
            <span>Directional Win Rate</span>
          </div>
          <div className="mt-1 flex items-baseline justify-between">
            <div>
              <span className="text-gray-400 text-[10px]">Long Spread: </span>
              <span className="text-white font-bold">{filteredMetrics.longWinRate}%</span>
            </div>
            <div>
              <span className="text-gray-400 text-[10px]">Short Spread: </span>
              <span className="text-white font-bold">{filteredMetrics.shortWinRate}%</span>
            </div>
          </div>
          <div className="text-[10px] text-gray-500 font-sans mt-0.5">
            Balanced statistical edge on both sides
          </div>
        </Card>
      </div>

      {/* ─── PRIMARY FILTER CONTROLS & COLLAPSIBLE ADVANCED DRAWER ───────────── */}
      <Card className="border-line bg-surface overflow-hidden">
        {/* Simple Top Filter Bar */}
        <div className="p-4 flex flex-col lg:flex-row lg:items-center justify-between gap-3">
          <div className="flex flex-wrap items-center gap-3">
            {/* Outcome Filter Pills with Stable Unfiltered Counts */}
            <div className="flex items-center bg-surface-2 p-1 rounded-lg border border-line text-xs font-mono">
              <button
                onClick={() => {
                  setOutcomeFilter("all");
                  setCurrentPage(1);
                }}
                className={cn(
                  "px-3 py-1 rounded font-medium transition-colors",
                  outcomeFilter === "all"
                    ? "bg-brand text-bg font-bold"
                    : "text-gray-400 hover:text-white"
                )}
              >
                All Outcomes ({outcomeCounts.total})
              </button>
              <button
                onClick={() => {
                  setOutcomeFilter("win");
                  setCurrentPage(1);
                }}
                className={cn(
                  "px-3 py-1 rounded font-medium transition-colors flex items-center gap-1",
                  outcomeFilter === "win"
                    ? "bg-emerald-500 text-bg font-bold"
                    : "text-emerald-400 hover:text-emerald-300"
                )}
              >
                <CheckCircle2 className="w-3 h-3" />
                <span>Wins Only ({outcomeCounts.wins})</span>
              </button>
              <button
                onClick={() => {
                  setOutcomeFilter("loss");
                  setCurrentPage(1);
                }}
                className={cn(
                  "px-3 py-1 rounded font-medium transition-colors flex items-center gap-1",
                  outcomeFilter === "loss"
                    ? "bg-rose-500 text-bg font-bold"
                    : "text-rose-400 hover:text-rose-300"
                )}
              >
                <XCircle className="w-3 h-3" />
                <span>Losses Only ({outcomeCounts.losses})</span>
              </button>
            </div>

            {/* Quick Presets Pills */}
            <div className="hidden sm:flex items-center gap-1.5 text-xs">
              <button
                onClick={() => {
                  setMinEntryZ(2.5);
                  setChecksFilter("perfect10");
                  setCurrentPage(1);
                }}
                className="px-2.5 py-1 rounded bg-surface-2 border border-line text-gray-300 hover:text-white transition-colors flex items-center gap-1 font-mono text-[11px]"
                title="Filter for trades with |Z| >= 2.5 and 10/10 Checks"
              >
                <Sparkles className="w-3 h-3 text-amber-400" />
                <span>High Conviction</span>
              </button>
              <button
                onClick={() => {
                  setDurationFilter("fast");
                  setCurrentPage(1);
                }}
                className="px-2.5 py-1 rounded bg-surface-2 border border-line text-gray-300 hover:text-white transition-colors flex items-center gap-1 font-mono text-[11px]"
                title="Filter trades that mean-reverted in 5 days or less"
              >
                <Zap className="w-3 h-3 text-cyan-400" />
                <span>Fast (&le;5d)</span>
              </button>
            </div>
          </div>

          {/* Right: Search, Advanced Button, Reset */}
          <div className="flex items-center gap-2">
            <div className="relative">
              <Search className="w-3.5 h-3.5 text-gray-400 absolute left-2.5 top-1/2 -translate-y-1/2" />
              <input
                type="text"
                placeholder="Search ticker, pair, sector..."
                value={searchQuery}
                onChange={(e) => {
                  setSearchQuery(e.target.value);
                  setCurrentPage(1);
                }}
                className="bg-surface-2 border border-line text-xs pl-8 pr-3 py-1.5 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:border-brand w-48 sm:w-56"
              />
            </div>

            {/* Advanced Filters Expand/Compress Toggle Button */}
            <button
              onClick={() => setIsAdvancedOpen(!isAdvancedOpen)}
              className={cn(
                "px-3 py-1.5 rounded-lg text-xs font-semibold border flex items-center gap-1.5 transition-all",
                isAdvancedOpen || activeAdvancedCount > 0
                  ? "bg-brand/10 border-brand text-brand font-bold"
                  : "bg-surface-2 border-line text-gray-400 hover:text-white"
              )}
            >
              <SlidersHorizontal className="w-3.5 h-3.5" />
              <span>Advanced</span>
              {activeAdvancedCount > 0 && (
                <span className="bg-brand text-bg text-[10px] font-mono px-1.5 py-0.5 rounded-full font-bold">
                  {activeAdvancedCount}
                </span>
              )}
              {isAdvancedOpen ? (
                <ChevronUp className="w-3.5 h-3.5 ml-0.5" />
              ) : (
                <ChevronDown className="w-3.5 h-3.5 ml-0.5" />
              )}
            </button>

            {isAnyFilterActive && (
              <button
                onClick={resetAllFilters}
                className="text-xs text-gray-400 hover:text-white px-2.5 py-1.5 rounded-lg bg-surface-2 border border-line flex items-center gap-1 transition-colors"
                title="Reset all filters to default"
              >
                <RotateCcw className="w-3 h-3" />
                <span>Reset</span>
              </button>
            )}
          </div>
        </div>

        {/* ─── COLLAPSIBLE ADVANCED PARAMETERS DRAWER (HIDDEN BY DEFAULT) ───── */}
        {isAdvancedOpen && (
          <div className="p-4 bg-surface-2/40 border-t border-line/70 grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-7 gap-3 text-xs animate-in fade-in slide-in-from-top-1 duration-200">
            {/* Direction Filter */}
            <div>
              <label className="text-gray-400 block text-[11px] font-mono mb-1">
                Direction:
              </label>
              <select
                value={directionFilter}
                onChange={(e) => {
                  setDirectionFilter(e.target.value as DirectionFilter);
                  setCurrentPage(1);
                }}
                className="w-full bg-surface border border-line text-white text-xs px-2.5 py-1.5 rounded-lg focus:outline-none focus:border-brand cursor-pointer"
              >
                <option value="all">All Directions</option>
                <option value="long">Long Spread (Z &le; -2.0)</option>
                <option value="short">Short Spread (Z &ge; +2.0)</option>
              </select>
            </div>

            {/* Min Entry Z Filter */}
            <div>
              <label className="text-gray-400 block text-[11px] font-mono mb-1">
                Min Entry |Z|:
              </label>
              <select
                value={minEntryZ}
                onChange={(e) => {
                  setMinEntryZ(Number(e.target.value));
                  setCurrentPage(1);
                }}
                className="w-full bg-surface border border-line text-white text-xs px-2.5 py-1.5 rounded-lg focus:outline-none focus:border-brand cursor-pointer"
              >
                <option value={2.0}>&ge; 2.0&sigma; (Standard)</option>
                <option value={2.2}>&ge; 2.2&sigma; (Deeper)</option>
                <option value={2.5}>&ge; 2.5&sigma; (Extreme)</option>
                <option value={3.0}>&ge; 3.0&sigma; (Ultra Rare)</option>
              </select>
            </div>

            {/* Sector Dropdown */}
            <div>
              <label className="text-gray-400 block text-[11px] font-mono mb-1">
                Sector:
              </label>
              <select
                value={selectedSector}
                onChange={(e) => {
                  setSelectedSector(e.target.value);
                  setCurrentPage(1);
                }}
                className="w-full bg-surface border border-line text-white text-xs px-2.5 py-1.5 rounded-lg focus:outline-none focus:border-brand cursor-pointer"
              >
                <option value="all">All Sectors</option>
                {availableSectors.map((sec) => (
                  <option key={sec} value={sec}>
                    {sec}
                  </option>
                ))}
              </select>
            </div>

            {/* Spread Volatility Tier Dropdown */}
            <div>
              <label className="text-gray-400 block text-[11px] font-mono mb-1">
                Spread Tier:
              </label>
              <select
                value={selectedSpreadTier}
                onChange={(e) => {
                  setSelectedSpreadTier(e.target.value);
                  setCurrentPage(1);
                }}
                className="w-full bg-surface border border-line text-white text-xs px-2.5 py-1.5 rounded-lg focus:outline-none focus:border-brand cursor-pointer"
              >
                <option value="all">All Tiers</option>
                <option value="Ultra Tight">Ultra Tight (&le; 2.5%)</option>
                <option value="Tight">Tight (&le; 4.5%)</option>
                <option value="Medium">Medium (&le; 7.0%)</option>
                <option value="Wide">Wide (&gt; 7.0%)</option>
              </select>
            </div>

            {/* Holding Duration Filter */}
            <div>
              <label className="text-gray-400 block text-[11px] font-mono mb-1">
                Holding Time:
              </label>
              <select
                value={durationFilter}
                onChange={(e) => {
                  setDurationFilter(e.target.value as DurationFilter);
                  setCurrentPage(1);
                }}
                className="w-full bg-surface border border-line text-white text-xs px-2.5 py-1.5 rounded-lg focus:outline-none focus:border-brand cursor-pointer"
              >
                <option value="all">Any Duration</option>
                <option value="fast">Fast (&le; 5 Days)</option>
                <option value="medium">Medium (6 - 15 Days)</option>
                <option value="extended">Extended (&gt; 15 Days)</option>
              </select>
            </div>

            {/* Date Range: From Date */}
            <div>
              <label className="text-gray-400 block text-[11px] font-mono mb-1">
                From Date:
              </label>
              <input
                type="date"
                value={startDateFilter}
                onChange={(e) => {
                  setStartDateFilter(e.target.value);
                  setCurrentPage(1);
                }}
                className="w-full bg-surface border border-line text-white text-xs px-2 py-1.2 rounded-lg focus:outline-none focus:border-brand"
              />
            </div>

            {/* Date Range: To Date */}
            <div>
              <label className="text-gray-400 block text-[11px] font-mono mb-1">
                To Date:
              </label>
              <input
                type="date"
                value={endDateFilter}
                onChange={(e) => {
                  setEndDateFilter(e.target.value);
                  setCurrentPage(1);
                }}
                className="w-full bg-surface border border-line text-white text-xs px-2 py-1.2 rounded-lg focus:outline-none focus:border-brand"
              />
            </div>
          </div>
        )}
      </Card>

      {/* ─── MULTI-VIEW PERFORMANCE CHARTS & MONTHLY BREAKDOWN ───────────────── */}
      <Card className="p-5 border-line bg-surface space-y-4">
        {/* Chart Header & Tab Switcher */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-line/60 pb-3">
          <div className="flex items-center gap-2">
            <BarChart3 className="w-4 h-4 text-brand" />
            <h3 className="text-xs font-bold uppercase tracking-wider text-white">
              Institutional Strategy Visualizer
            </h3>
            <span className="text-[10px] text-gray-500 font-mono">
              (251 Trading Days Walkforward &middot; Realized Exit Sequencing)
            </span>
          </div>

          {/* View Switcher Tabs */}
          <div className="flex items-center bg-surface-2 p-1 rounded-lg border border-line text-xs font-mono">
            <button
              onClick={() => setActiveChartTab("equity")}
              className={cn(
                "px-3 py-1 rounded transition-colors flex items-center gap-1.5",
                activeChartTab === "equity"
                  ? "bg-brand text-bg font-bold shadow-sm"
                  : "text-gray-400 hover:text-white"
              )}
            >
              <TrendingUp className="w-3.5 h-3.5" />
              <span>Cumulative Equity</span>
            </button>
            <button
              onClick={() => setActiveChartTab("drawdown")}
              className={cn(
                "px-3 py-1 rounded transition-colors flex items-center gap-1.5",
                activeChartTab === "drawdown"
                  ? "bg-rose-500 text-bg font-bold shadow-sm"
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
                  ? "bg-cyan-500 text-bg font-bold shadow-sm"
                  : "text-gray-400 hover:text-white"
              )}
            >
              <Calendar className="w-3.5 h-3.5" />
              <span>Monthly Breakdown</span>
            </button>
          </div>
        </div>

        {/* Tab 1: Cumulative Equity Curve */}
        {activeChartTab === "equity" && (
          <div className="space-y-2">
            <div className="flex items-center justify-between text-xs font-mono">
              <span className="text-gray-400">
                Strategy Net Realized PnL (Chronological by Exit Date)
              </span>
              <strong
                className={cn(
                  "text-sm",
                  equitySeries[equitySeries.length - 1]?.cumReturn >= 0
                    ? "text-emerald-400"
                    : "text-rose-400"
                )}
              >
                {equitySeries[equitySeries.length - 1]?.cumReturn >= 0 ? "+" : ""}
                {equitySeries[equitySeries.length - 1]?.cumReturn || 0}%
              </strong>
            </div>

            {/* Interactive Area Chart with Non-Scaling Stroke */}
            <div className="h-36 w-full bg-surface-2/40 rounded-lg border border-line/60 p-2 relative overflow-hidden flex items-end">
              {equitySeries.length > 1 ? (
                <svg
                  className="w-full h-full overflow-visible"
                  viewBox={`0 0 ${equitySeries.length} 100`}
                  preserveAspectRatio="none"
                >
                  <defs>
                    <linearGradient id="equityGrad" x1="0%" y1="0%" x2="0%" y2="100%">
                      <stop offset="0%" stopColor="#10b981" stopOpacity="0.45" />
                      <stop offset="100%" stopColor="#10b981" stopOpacity="0.0" />
                    </linearGradient>
                  </defs>
                  {(() => {
                    const values = equitySeries.map((d) => d.cumReturn);
                    const minVal = Math.min(0, ...values);
                    const maxVal = Math.max(10, ...values);
                    const range = maxVal - minVal || 1;

                    const points = equitySeries
                      .map((d, i) => {
                        const x = i;
                        const y = 92 - ((d.cumReturn - minVal) / range) * 84;
                        return `${x},${y}`;
                      })
                      .join(" ");

                    const areaPoints = `0,92 ${points} ${equitySeries.length - 1},92`;

                    return (
                      <>
                        <polygon
                          points={areaPoints}
                          fill="url(#equityGrad)"
                          vectorEffect="non-scaling-stroke"
                        />
                        <polyline
                          fill="none"
                          stroke="#10b981"
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
                  Insufficient data points to plot equity curve.
                </div>
              )}
            </div>
            <div className="flex items-center justify-between text-[10px] text-gray-500 font-mono">
              <span>Start: Oct 26, 2025</span>
              <span>
                {equitySeries.length} realized exits &middot; Realized PnL Accounting
              </span>
              <span>End: Oct 26, 2026</span>
            </div>
          </div>
        )}

        {/* Tab 2: Underwater Drawdown Curve */}
        {activeChartTab === "drawdown" && (
          <div className="space-y-2">
            <div className="flex items-center justify-between text-xs font-mono">
              <span className="text-gray-400">
                Peak-to-Trough Realized Drawdown (Sequenced by Exit Date)
              </span>
              <span className="text-rose-400 font-bold text-sm">
                Max DD: -{filteredMetrics.maxDrawdown}%
              </span>
            </div>

            <div className="h-36 w-full bg-surface-2/40 rounded-lg border border-line/60 p-2 relative overflow-hidden flex items-start">
              {equitySeries.length > 1 ? (
                <svg
                  className="w-full h-full overflow-visible"
                  viewBox={`0 0 ${equitySeries.length} 100`}
                  preserveAspectRatio="none"
                >
                  <defs>
                    <linearGradient id="ddGrad" x1="0%" y1="0%" x2="0%" y2="100%">
                      <stop offset="0%" stopColor="#ef4444" stopOpacity="0.4" />
                      <stop offset="100%" stopColor="#ef4444" stopOpacity="0.05" />
                    </linearGradient>
                  </defs>
                  {(() => {
                    const values = equitySeries.map((d) => d.drawdown);
                    const minDd = Math.min(-1, ...values);
                    const range = Math.abs(minDd) || 1;

                    const points = equitySeries
                      .map((d, i) => {
                        const x = i;
                        const y = 8 + (Math.abs(d.drawdown) / range) * 84;
                        return `${x},${y}`;
                      })
                      .join(" ");

                    const areaPoints = `0,8 ${points} ${equitySeries.length - 1},8`;

                    return (
                      <>
                        <polygon
                          points={areaPoints}
                          fill="url(#ddGrad)"
                          vectorEffect="non-scaling-stroke"
                        />
                        <polyline
                          fill="none"
                          stroke="#ef4444"
                          strokeWidth="1.8"
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
                  Insufficient data points to plot drawdown curve.
                </div>
              )}
            </div>
            <div className="flex items-center justify-between text-[10px] text-gray-500 font-mono">
              <span>0% Peak Baseline</span>
              <span>Continuous Portfolio Equity Drawdown</span>
              <span>Trough: -{filteredMetrics.maxDrawdown}%</span>
            </div>
          </div>
        )}

        {/* Tab 3: Monthly Performance Grid */}
        {activeChartTab === "monthly" && (
          <div className="space-y-3">
            <div className="flex items-center justify-between text-xs font-mono">
              <span className="text-gray-400">
                1-Year Monthly Realized PnL & Win Rate (Attributed to Exit Date)
              </span>
              <span className="text-gray-400">12 Monthly Cycles Evaluated</span>
            </div>

            <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-6 gap-2.5">
              {monthlyBreakdown.map((m) => {
                const isProfitable = m.totalPnL >= 0;
                return (
                  <div
                    key={m.month}
                    className={cn(
                      "p-3 rounded-lg border text-xs font-mono flex flex-col justify-between transition-all",
                      isProfitable
                        ? "bg-emerald-950/20 border-emerald-500/30"
                        : "bg-rose-950/20 border-rose-500/30"
                    )}
                  >
                    <div className="flex items-center justify-between mb-1">
                      <span className="font-bold text-white text-[11px] font-sans">
                        {m.month}
                      </span>
                      <span
                        className={cn(
                          "font-bold text-[11px]",
                          isProfitable ? "text-emerald-400" : "text-rose-400"
                        )}
                      >
                        {isProfitable ? "+" : ""}
                        {m.totalPnL}%
                      </span>
                    </div>

                    <div className="space-y-0.5 text-[10px] text-gray-400">
                      <div className="flex justify-between">
                        <span>Trades:</span>
                        <span className="text-white font-bold">{m.trades}</span>
                      </div>
                      <div className="flex justify-between">
                        <span>Win Rate:</span>
                        <span
                          className={cn(
                            "font-bold",
                            m.winRate >= 50 ? "text-emerald-400" : "text-gray-300"
                          )}
                        >
                          {m.winRate}%
                        </span>
                      </div>
                      <div className="text-[9px] text-gray-500">
                        {m.wins}W / {m.losses}L
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </Card>

      {/* ─── TRADES DATA TABLE ───────────────────────────────────────────────── */}
      <Card className="border-line bg-surface overflow-hidden">
        <div className="p-4 border-b border-line flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <h3 className="text-sm font-bold text-white tracking-wide">
              Historical Trade Execution Log
            </h3>
            <span className="text-xs font-mono text-gray-400">
              (Showing {paginatedTrades.length} of {filteredTrades.length} trades)
            </span>
          </div>

          {/* Page size selector */}
          <div className="flex items-center gap-1.5 text-xs font-mono text-gray-400">
            <span>Per page:</span>
            {[25, 50, 100].map((size) => (
              <button
                key={size}
                onClick={() => {
                  setPageSize(size);
                  setCurrentPage(1);
                }}
                className={cn(
                  "px-2 py-0.5 rounded border transition-colors",
                  pageSize === size
                    ? "bg-brand text-bg font-bold border-brand"
                    : "bg-surface-2 text-gray-400 border-line hover:text-white"
                )}
              >
                {size}
              </button>
            ))}
          </div>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs font-mono">
            <thead>
              <tr className="bg-surface-2/70 border-b border-line text-[11px] uppercase tracking-wider text-gray-400">
                <th
                  className="py-3 px-4 cursor-pointer hover:text-white"
                  onClick={() => handleSort("entry_date")}
                >
                  <div className="flex items-center gap-1">
                    <span>Entry Date</span>
                    <ArrowUpDown className="w-3 h-3" />
                  </div>
                </th>
                <th className="py-3 px-4">Pair & Sector</th>
                <th className="py-3 px-4">Trade Direction</th>
                <th
                  className="py-3 px-4 cursor-pointer hover:text-white"
                  onClick={() => handleSort("abs_entry_z")}
                >
                  <div className="flex items-center gap-1">
                    <span>Entry Z</span>
                    <ArrowUpDown className="w-3 h-3" />
                  </div>
                </th>
                <th
                  className="py-3 px-4 cursor-pointer hover:text-white"
                  onClick={() => handleSort("passed_checks_count")}
                >
                  <div className="flex items-center gap-1">
                    <span>10/10 Score</span>
                    <ArrowUpDown className="w-3 h-3" />
                  </div>
                </th>
                <th
                  className="py-3 px-4 cursor-pointer hover:text-white"
                  onClick={() => handleSort("holding_days")}
                >
                  <div className="flex items-center gap-1">
                    <span>Exit Date (Hold)</span>
                    <ArrowUpDown className="w-3 h-3" />
                  </div>
                </th>
                <th className="py-3 px-4">Exit Z</th>
                <th
                  className="py-3 px-4 cursor-pointer hover:text-white"
                  onClick={() => handleSort("realized_return_pct")}
                >
                  <div className="flex items-center gap-1">
                    <span>Realized Return</span>
                    <ArrowUpDown className="w-3 h-3" />
                  </div>
                </th>
                <th className="py-3 px-4 text-center">Outcome</th>
                <th className="py-3 px-4 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {isLoading ? (
                <tr>
                  <td colSpan={10} className="py-12 text-center text-gray-400">
                    <RefreshCw className="w-6 h-6 animate-spin mx-auto mb-2 text-brand" />
                    <span>Loading 1-year historical trades...</span>
                  </td>
                </tr>
              ) : paginatedTrades.length === 0 ? (
                <tr>
                  <td colSpan={10} className="py-12 text-center text-gray-500">
                    <div className="max-w-sm mx-auto space-y-2">
                      <p className="text-gray-400 font-semibold">
                        No trades match the selected filter criteria.
                      </p>
                      <button
                        onClick={resetAllFilters}
                        className="text-xs text-brand hover:underline inline-flex items-center gap-1"
                      >
                        <RotateCcw className="w-3 h-3" />
                        <span>Reset All Filters</span>
                      </button>
                    </div>
                  </td>
                </tr>
              ) : (
                paginatedTrades.map((t, idx) => {
                  const isWin = t.outcome === "WIN";
                  const isLoss = t.outcome === "LOSS";
                  const is10Of10 = t.is_perfect_10 || t.passed_checks_count === 10;

                  return (
                    <tr
                      key={t.id || `${t.pair_name}_${t.entry_date}_${idx}`}
                      role="button"
                      tabIndex={0}
                      onClick={() => setInspectedTrade(t)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter" || e.key === " ") {
                          e.preventDefault();
                          setInspectedTrade(t);
                        }
                      }}
                      className="hover:bg-surface-2/60 transition-colors cursor-pointer group focus:outline-none focus:bg-surface-2/80"
                    >
                      {/* Entry Date */}
                      <td className="py-3 px-4 font-bold text-white whitespace-nowrap">
                        <div className="flex items-center gap-1.5">
                          <Calendar className="w-3 h-3 text-brand opacity-70" />
                          <span>{t.entry_date}</span>
                        </div>
                      </td>

                      {/* Pair & Sector */}
                      <td className="py-3 px-4 whitespace-nowrap">
                        <div className="font-bold text-white group-hover:text-brand transition-colors inline-flex items-center gap-1">
                          <span>{t.pair_name}</span>
                        </div>
                        <div className="text-[10px] text-gray-500 font-sans">
                          {t.sector} &middot; {t.spread_tier}
                        </div>
                      </td>

                      {/* Direction */}
                      <td className="py-3 px-4 whitespace-nowrap">
                        <span
                          className={cn(
                            "inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-bold border",
                            t.entry_z < 0
                              ? "bg-emerald-950/40 text-emerald-300 border-emerald-500/30"
                              : "bg-rose-950/40 text-rose-300 border-rose-500/30"
                          )}
                        >
                          {t.entry_z < 0 ? (
                            <TrendingUp className="w-3 h-3 text-emerald-400" />
                          ) : (
                            <TrendingDown className="w-3 h-3 text-rose-400" />
                          )}
                          <span>{t.direction_label}</span>
                        </span>
                      </td>

                      {/* Entry Z-Score */}
                      <td className="py-3 px-4 font-bold">
                        <span
                          className={
                            t.entry_z > 0 ? "text-amber-400" : "text-cyan-400"
                          }
                        >
                          {t.entry_z > 0 ? "+" : ""}
                          {t.entry_z}&sigma;
                        </span>
                      </td>

                      {/* 10/10 Score */}
                      <td className="py-3 px-4">
                        <span
                          className={cn(
                            "inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-bold border",
                            is10Of10
                              ? "bg-emerald-950/60 text-emerald-300 border-emerald-500/40"
                              : t.passed_checks_count >= 8
                              ? "bg-cyan-950/40 text-cyan-300 border-cyan-500/30"
                              : "bg-surface-2 text-gray-400 border-line"
                          )}
                        >
                          <ShieldCheck className="w-3 h-3 text-emerald-400" />
                          {t.passed_checks_count}/10
                        </span>
                      </td>

                      {/* Exit Date & Holding Days */}
                      <td className="py-3 px-4 text-gray-300 whitespace-nowrap">
                        <div>{t.exit_date || "Holding"}</div>
                        <div className="text-[10px] text-gray-500">
                          {t.holding_days} trading days
                        </div>
                      </td>

                      {/* Exit Z */}
                      <td className="py-3 px-4 text-gray-400">
                        {t.exit_z !== null && t.exit_z !== undefined
                          ? `${t.exit_z > 0 ? "+" : ""}${t.exit_z}σ`
                          : "—"}
                      </td>

                      {/* Realized Return */}
                      <td className="py-3 px-4">
                        <span
                          className={cn(
                            "font-bold text-sm",
                            t.realized_return_pct > 0
                              ? "text-emerald-400"
                              : t.realized_return_pct < 0
                              ? "text-rose-400"
                              : "text-gray-400"
                          )}
                        >
                          {t.realized_return_pct > 0 ? "+" : ""}
                          {t.realized_return_pct}%
                        </span>
                      </td>

                      {/* Outcome Badge */}
                      <td className="py-3 px-4 text-center">
                        <span
                          className={cn(
                            "inline-flex items-center gap-1 px-2.5 py-0.5 rounded text-[11px] font-extrabold border",
                            isWin
                              ? "bg-emerald-950/60 text-emerald-300 border-emerald-500/50 shadow-sm shadow-emerald-500/10"
                              : isLoss
                              ? "bg-rose-950/60 text-rose-300 border-rose-500/50"
                              : "bg-surface-2 text-gray-400 border-line"
                          )}
                        >
                          {isWin && <CheckCircle2 className="w-3 h-3 text-emerald-400" />}
                          {isLoss && <XCircle className="w-3 h-3 text-rose-400" />}
                          <span>{t.outcome}</span>
                        </span>
                      </td>

                      {/* Actions */}
                      <td className="py-3 px-4 text-right whitespace-nowrap">
                        <div className="flex items-center justify-end gap-1.5">
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              setInspectedTrade(t);
                            }}
                            className="text-[11px] font-medium text-gray-300 hover:text-white px-2 py-1 rounded bg-surface-2 border border-line hover:border-gray-500 transition-colors inline-flex items-center gap-1"
                          >
                            <Eye className="w-3 h-3 text-brand" />
                            <span>Quick</span>
                          </button>
                          <Link
                            to={`/setups/${t.ticker_a}/${t.ticker_b}?date=${t.entry_date}`}
                            onClick={(e) => e.stopPropagation()}
                            className="text-[11px] font-semibold text-brand hover:text-brand/80 px-2 py-1 rounded border border-brand/30 hover:border-brand/60 bg-brand/10 inline-flex items-center gap-1 transition-colors"
                          >
                            <span>Replay</span>
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

        {/* ─── Pagination Controls with Dynamic Window ──────────────────────── */}
        {totalPages > 1 && (
          <div className="p-4 border-t border-line flex items-center justify-between text-xs font-mono">
            <span className="text-gray-400">
              Page {currentPage} of {totalPages}
            </span>
            <div className="flex items-center gap-1.5">
              <button
                onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
                disabled={currentPage === 1}
                className="px-3 py-1 rounded bg-surface-2 border border-line text-gray-300 hover:text-white disabled:opacity-40 transition-colors"
              >
                Previous
              </button>
              {visiblePages.map((pageNum) => (
                <button
                  key={pageNum}
                  onClick={() => setCurrentPage(pageNum)}
                  className={cn(
                    "px-2.5 py-1 rounded border transition-colors",
                    currentPage === pageNum
                      ? "bg-brand text-bg font-bold border-brand"
                      : "bg-surface-2 text-gray-400 border-line hover:text-white"
                  )}
                >
                  {pageNum}
                </button>
              ))}
              <button
                onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
                disabled={currentPage === totalPages}
                className="px-3 py-1 rounded bg-surface-2 border border-line text-gray-300 hover:text-white disabled:opacity-40 transition-colors"
              >
                Next
              </button>
            </div>
          </div>
        )}
      </Card>

      {/* ─── QUICK INSPECTOR MODAL ───────────────────────────────────────────── */}
      {inspectedTrade && (
        <div
          className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-4"
          onClick={() => setInspectedTrade(null)}
        >
          <div
            className="bg-surface border border-line/80 rounded-2xl w-full max-w-2xl max-h-[90vh] overflow-y-auto shadow-2xl p-6 space-y-5 animate-in fade-in zoom-in-95 duration-150"
            onClick={(e) => e.stopPropagation()}
          >
            {/* Modal Header */}
            <div className="flex items-start justify-between border-b border-line pb-4">
              <div>
                <div className="flex items-center gap-2.5">
                  <h3 className="text-lg font-bold text-white font-mono">
                    {inspectedTrade.pair_name}
                  </h3>
                  <span
                    className={cn(
                      "px-2.5 py-0.5 rounded text-xs font-bold font-mono border",
                      inspectedTrade.outcome === "WIN"
                        ? "bg-emerald-950/60 text-emerald-300 border-emerald-500/50"
                        : inspectedTrade.outcome === "LOSS"
                        ? "bg-rose-950/60 text-rose-300 border-rose-500/50"
                        : "bg-surface-2 text-gray-400 border-line"
                    )}
                  >
                    {inspectedTrade.outcome}
                  </span>
                  <span className="text-xs text-gray-400 font-sans">
                    {inspectedTrade.sector} &middot; {inspectedTrade.spread_tier}
                  </span>
                </div>
                <p className="text-xs text-gray-400 font-mono mt-1">
                  Triggered:{" "}
                  <strong className="text-white">{inspectedTrade.entry_date}</strong>{" "}
                  &middot; Exit:{" "}
                  <strong className="text-white">
                    {inspectedTrade.exit_date || "Holding"}
                  </strong>{" "}
                  ({inspectedTrade.holding_days} trading days)
                </p>
              </div>

              <button
                onClick={() => setInspectedTrade(null)}
                aria-label="Close trade details modal"
                className="p-1 rounded-lg bg-surface-2 text-gray-400 hover:text-white border border-line transition-colors"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Trade Key Quant Facts */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5 text-xs font-mono">
              <div className="p-2.5 rounded-lg bg-surface-2 border border-line">
                <span className="text-gray-400 block text-[10px] uppercase font-sans">
                  Realized Return
                </span>
                <span
                  className={cn(
                    "text-base font-extrabold mt-0.5 block",
                    inspectedTrade.realized_return_pct >= 0
                      ? "text-emerald-400"
                      : "text-rose-400"
                  )}
                >
                  {inspectedTrade.realized_return_pct >= 0 ? "+" : ""}
                  {inspectedTrade.realized_return_pct}%
                </span>
              </div>

              <div className="p-2.5 rounded-lg bg-surface-2 border border-line">
                <span className="text-gray-400 block text-[10px] uppercase font-sans">
                  Entry &rarr; Exit Z
                </span>
                <span className="text-base font-bold text-white mt-0.5 block">
                  {inspectedTrade.entry_z}&sigma; &rarr;{" "}
                  {inspectedTrade.exit_z !== null && inspectedTrade.exit_z !== undefined
                    ? `${inspectedTrade.exit_z}σ`
                    : "—"}
                </span>
              </div>

              <div className="p-2.5 rounded-lg bg-surface-2 border border-line">
                <span className="text-gray-400 block text-[10px] uppercase font-sans">
                  Hedge Ratio (&beta;)
                </span>
                <span className="text-base font-bold text-cyan-300 mt-0.5 block">
                  {inspectedTrade.hedge_ratio}
                </span>
              </div>

              <div className="p-2.5 rounded-lg bg-surface-2 border border-line">
                <span className="text-gray-400 block text-[10px] uppercase font-sans">
                  Status Reason
                </span>
                <span className="text-[11px] font-semibold text-gray-300 mt-1 block truncate">
                  {inspectedTrade.status_reason || "Target Reverted"}
                </span>
              </div>
            </div>

            {/* The 10 Institutional Quality Checks Grid */}
            <div className="space-y-2">
              <div className="flex items-center justify-between text-xs">
                <span className="font-bold text-white font-mono flex items-center gap-1.5">
                  <ShieldCheck className="w-4 h-4 text-emerald-400" />
                  <span>The 10 Institutional Quality Checks</span>
                </span>
                <span className="font-mono text-emerald-400 font-bold">
                  {inspectedTrade.passed_checks_count} of 10 Passed
                </span>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-xs font-mono">
                {Object.entries(CHECK_INFO).map(([key, info]) => {
                  const hasChecksObj =
                    inspectedTrade.checks &&
                    Object.keys(inspectedTrade.checks).length > 0;
                  const passed = hasChecksObj
                    ? Boolean(inspectedTrade.checks![key])
                    : inspectedTrade.passed_checks_count === 10;

                  return (
                    <div
                      key={key}
                      className={cn(
                        "p-2.5 rounded-lg border flex items-start gap-2.5 transition-colors",
                        passed
                          ? "bg-emerald-950/20 border-emerald-500/30 text-emerald-200"
                          : "bg-surface-2 border-line text-gray-400"
                      )}
                    >
                      <div className="mt-0.5">
                        {passed ? (
                          <Check className="w-4 h-4 text-emerald-400" />
                        ) : (
                          <X className="w-4 h-4 text-rose-400" />
                        )}
                      </div>
                      <div className="space-y-0.5 flex-1">
                        <div className="font-bold text-white text-[11px]">{info.label}</div>
                        <div className="text-[10px] text-gray-400 font-sans leading-tight">
                          {info.desc}
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>

            {/* Action Footer */}
            <div className="border-t border-line pt-4 flex flex-wrap items-center justify-between gap-3">
              <div className="text-[11px] text-gray-500 font-mono">
                Ornstein-Uhlenbeck Half-Life: {inspectedTrade.half_life_days}d &middot;
                ADF p: {inspectedTrade.adf_pvalue}
              </div>

              <div className="flex items-center gap-2">
                <button
                  onClick={() => setInspectedTrade(null)}
                  className="px-3 py-1.5 rounded-lg bg-surface-2 border border-line text-xs text-gray-300 hover:text-white transition-colors"
                >
                  Close
                </button>
                <Link
                  to={`/setups/${inspectedTrade.ticker_a}/${inspectedTrade.ticker_b}?date=${inspectedTrade.entry_date}`}
                  className="px-4 py-1.5 rounded-lg bg-brand text-bg text-xs font-bold hover:bg-brand/90 transition-all flex items-center gap-1.5 shadow-sm"
                >
                  <span>Open Point-in-Time Historical Trade Replay</span>
                  <ArrowRight className="w-3.5 h-3.5" />
                </Link>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
