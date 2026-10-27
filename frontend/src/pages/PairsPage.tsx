import React, { useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import {
  ArrowUpDown,
  ArrowUp,
  ArrowDown,
  Search,
  Download,
  Filter,
  Flame,
  Layers,
  Zap,
  ArrowRight,
} from "lucide-react";
import { api } from "@/lib/api";
import { Button, Card, ErrorBox, Loading, PageTitle, StatCard } from "@/components/ui";
import { cn } from "@/lib/utils";

type SortField =
  | "rank"
  | "ticker_a"
  | "ticker_b"
  | "sector"
  | "correlation"
  | "cointegration_pvalue"
  | "half_life"
  | "hurst_exponent"
  | "adf_t_stat"
  | "zero_crossings";

type SortOrder = "asc" | "desc";

// Sector badge color mappings matching the platform palette
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
    badge: "border-rose-500/30 bg-rose-500/10 text-rose-300",
    dot: "bg-rose-400",
  },
  "Consumer Staples": {
    badge: "border-lime-500/30 bg-lime-500/10 text-lime-300",
    dot: "bg-lime-400",
  },
  Materials: {
    badge: "border-yellow-500/30 bg-yellow-500/10 text-yellow-300",
    dot: "bg-yellow-400",
  },
  "Communication Services": {
    badge: "border-indigo-500/30 bg-indigo-500/10 text-indigo-300",
    dot: "bg-indigo-400",
  },
};

export default function PairsPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const viewParam = searchParams.get("view");
  const [viewMode, setViewMode] = useState<"elite" | "all">(
    viewParam === "all" ? "all" : "elite"
  );

  const [search, setSearch] = useState("");
  const [selectedSector, setSelectedSector] = useState<string>("All");
  const [minCorrFilter, setMinCorrFilter] = useState<number>(0.9);
  const [sortField, setSortField] = useState<SortField>("correlation");
  const [sortOrder, setSortOrder] = useState<SortOrder>("desc");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(50);

  // Main Pairs Query (53 elite or 128 cointegrated)
  const { data, isLoading, error } = useQuery({
    queryKey: ["pairs-data", viewMode],
    queryFn: () => api.pairs({ elite: viewMode === "elite" }),
  });

  const rawPairs = data?.pairs || [];

  // Extract all distinct sectors with count
  const sectorCounts = useMemo(() => {
    const counts: Record<string, number> = {};
    rawPairs.forEach((p) => {
      counts[p.sector] = (counts[p.sector] || 0) + 1;
    });
    return counts;
  }, [rawPairs]);

  // Client-side filtering
  const filteredPairs = useMemo(() => {
    return rawPairs.filter((p) => {
      if (selectedSector !== "All" && p.sector !== selectedSector) return false;
      if (p.correlation < minCorrFilter) return false;
      if (search.trim()) {
        const query = search.trim().toUpperCase();
        const matchA = p.ticker_a.toUpperCase().includes(query);
        const matchB = p.ticker_b.toUpperCase().includes(query);
        const matchSector = p.sector.toUpperCase().includes(query);
        if (!matchA && !matchB && !matchSector) return false;
      }
      return true;
    });
  }, [rawPairs, selectedSector, minCorrFilter, search]);

  // Client-side sorting
  const sortedPairs = useMemo(() => {
    const copy = [...filteredPairs];
    copy.sort((a, b) => {
      let cmp = 0;
      if (sortField === "correlation") {
        cmp = a.correlation - b.correlation;
      } else if (sortField === "cointegration_pvalue") {
        cmp = a.cointegration_pvalue - b.cointegration_pvalue;
      } else if (sortField === "half_life") {
        cmp = (a.half_life ?? 999) - (b.half_life ?? 999);
      } else if (sortField === "hurst_exponent") {
        cmp = (a.hurst_exponent ?? 999) - (b.hurst_exponent ?? 999);
      } else if (sortField === "adf_t_stat") {
        cmp = (a.adf_t_stat ?? 0) - (b.adf_t_stat ?? 0);
      } else if (sortField === "zero_crossings") {
        cmp = (a.zero_crossings ?? 0) - (b.zero_crossings ?? 0);
      } else if (sortField === "ticker_a") {
        cmp = a.ticker_a.localeCompare(b.ticker_a);
      } else if (sortField === "ticker_b") {
        cmp = a.ticker_b.localeCompare(b.ticker_b);
      } else if (sortField === "sector") {
        cmp = a.sector.localeCompare(b.sector);
      }
      return sortOrder === "asc" ? cmp : -cmp;
    });
    return copy;
  }, [filteredPairs, sortField, sortOrder]);

  // Pagination
  const totalPages = Math.ceil(sortedPairs.length / pageSize) || 1;
  const paginatedPairs = useMemo(() => {
    const start = (page - 1) * pageSize;
    return sortedPairs.slice(start, start + pageSize);
  }, [sortedPairs, page, pageSize]);

  const handleSort = (field: SortField) => {
    if (sortField === field) {
      setSortOrder((prev) => (prev === "asc" ? "desc" : "asc"));
    } else {
      setSortField(field);
      const defaultAsc = ["cointegration_pvalue", "half_life", "hurst_exponent", "adf_t_stat"].includes(field);
      setSortOrder(defaultAsc ? "asc" : "desc");
    }
    setPage(1);
  };

  const handleExportCSV = () => {
    if (!rawPairs.length) return;
    const isElite = viewMode === "elite";
    const filename = isElite ? "elite_curated_pairs.csv" : "sp500_master_pairs.csv";

    const headers = isElite
      ? "ticker_a,ticker_b,sector,correlation,cointegration_pvalue,zero_crossings,half_life,hurst_exponent,adf_t_stat\n"
      : "ticker_a,ticker_b,sector,correlation,cointegration_pvalue\n";

    const rows = sortedPairs
      .map((p) => {
        if (isElite) {
          return `${p.ticker_a},${p.ticker_b},"${p.sector}",${p.correlation},${p.cointegration_pvalue},${p.zero_crossings ?? ""},${p.half_life ?? ""},${p.hurst_exponent ?? ""},${p.adf_t_stat ?? ""}`;
        }
        return `${p.ticker_a},${p.ticker_b},"${p.sector}",${p.correlation},${p.cointegration_pvalue}`;
      })
      .join("\n");

    const blob = new Blob([headers + rows], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.setAttribute("download", filename);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  return (
    <div className="space-y-6">
      {/* Page Title */}
      <PageTitle
        title="Pairs Universe"
        subtitle="S&P 500 cointegrated stock pairs filtered through the 7-stage institutional statistical gauntlet."
        actions={
          <div className="flex items-center gap-2">
            <Link
              to="/setups"
              className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg border border-line bg-surface-2 hover:bg-surface-3 text-gray-200 hover:text-white transition-colors mr-1"
            >
              <Zap className="h-3.5 w-3.5 text-brand" />
              <span>Divergence Setups &rarr;</span>
            </Link>

            <div className="inline-flex rounded-lg border border-line p-0.5 bg-bg-soft">
              <button
                onClick={() => {
                  setViewMode("elite");
                  setSearchParams({ view: "elite" });
                  setPage(1);
                }}
                className={cn(
                  "px-3 py-1 text-xs font-semibold rounded-md transition-all flex items-center gap-1.5",
                  viewMode === "elite"
                    ? "bg-brand text-bg shadow-sm"
                    : "text-gray-400 hover:text-white"
                )}
              >
                <Layers className="h-3.5 w-3.5" />
                Elite Gauntlet (53)
              </button>
              <button
                onClick={() => {
                  setViewMode("all");
                  setSearchParams({ view: "all" });
                  setPage(1);
                }}
                className={cn(
                  "px-3 py-1 text-xs font-semibold rounded-md transition-all flex items-center gap-1.5",
                  viewMode === "all"
                    ? "bg-brand text-bg shadow-sm"
                    : "text-gray-400 hover:text-white"
                )}
              >
                <Layers className="h-3.5 w-3.5" />
                All Cointegrated (128)
              </button>
            </div>
            <Button variant="outline" onClick={handleExportCSV} className="text-xs">
              <Download className="h-3.5 w-3.5 mr-1" />
              Export CSV
            </Button>
          </div>
        }
      />

      {/* Active Setups Quick Action Banner */}
      <Card className="p-4 border-line bg-surface flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-surface-2 border border-line flex items-center justify-center text-brand shrink-0">
            <Zap className="w-4 h-4 text-brand" />
          </div>
          <div>
            <div className="text-sm font-semibold text-white flex items-center gap-2">
              <span>Active Pair Divergence Setups</span>
              <span className="px-2 py-0.5 rounded text-[10px] font-mono bg-surface-2 text-brand border border-line">
                Active Setups
              </span>
            </div>
            <div className="text-xs text-gray-400 mt-0.5">
              Screen pairs for &plusmn;2.0&sigma; spread divergences with TradingView charts and verification criteria.
            </div>
          </div>
        </div>
        <Link
          to="/setups"
          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-brand text-bg hover:opacity-90 font-medium text-xs transition-opacity shrink-0"
        >
          <span>Open Setups</span>
          <ArrowRight className="w-3.5 h-3.5" />
        </Link>
      </Card>

      {/* KPI Stats Row */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <StatCard
          label={viewMode === "elite" ? "Elite Gauntlet Survivors" : "Cointegrated Universe"}
          value={rawPairs.length.toLocaleString()}
          sub={viewMode === "elite" ? "Passed all 7 statistical gates" : "Engle-Granger p ≤ 0.05"}
          valueClass="text-brand"
        />
        <StatCard
          label="Liquidity & Correlation"
          value="ADV > 2M | r ≥ 0.90"
          sub="Zero execution slippage floor"
          valueClass="text-pos text-xl"
        />
        <StatCard
          label="Mean-Reversion Speed"
          value={viewMode === "elite" ? "3.9d – 11.7d" : "p ≤ 0.05"}
          sub="Ornstein-Uhlenbeck Half-Life"
          valueClass="text-brand-glow text-xl"
        />
        <StatCard
          label="Hurst Exponent & ADF"
          value={viewMode === "elite" ? "H < 0.43 | t < -3.3" : "Stationary Spreads"}
          sub="Anti-persistent spread guarantee"
          valueClass="text-info text-xl"
        />
      </div>

      {/* Main Table Card */}
      <Card className="p-5 space-y-4">
        <div className="flex items-center justify-between pb-1 border-b border-line/40">
          <h3 className="text-sm font-bold text-white tracking-wide">
            {viewMode === "elite" ? "All Elite Pairs (Gauntlet-Verified)" : "S&P 500 Master Cointegrated Universe"}
          </h3>
          <span className="text-xs font-mono text-gray-400">
            {filteredPairs.length} matches
          </span>
        </div>

        {/* Controls Bar */}
        <div className="flex flex-col md:flex-row gap-3 items-stretch md:items-center justify-between">
          {/* Search */}
          <div className="relative flex-1 max-w-md">
            <Search className="absolute left-3 top-2.5 h-4 w-4 text-gray-500" />
            <input
              type="text"
              placeholder="Search ticker (e.g. PNC, DELL, HPE, FITB) or sector..."
              value={search}
              onChange={(e) => {
                setSearch(e.target.value);
                setPage(1);
              }}
              className="w-full bg-bg-soft border border-line rounded-lg pl-9 pr-4 py-1.5 text-sm text-gray-200 placeholder-gray-500 focus:outline-none focus:border-brand/60 transition-colors"
            />
          </div>

          {/* Filter pills & Selects */}
          <div className="flex flex-wrap items-center gap-2">
            <div className="flex items-center gap-1.5 text-xs text-gray-400">
              <Filter className="h-3.5 w-3.5 text-gray-500" />
              <span>Sector:</span>
            </div>
            <select
              value={selectedSector}
              onChange={(e) => {
                setSelectedSector(e.target.value);
                setPage(1);
              }}
              className="bg-bg-soft border border-line rounded-lg px-2.5 py-1.5 text-xs text-gray-200 focus:outline-none focus:border-brand/60"
            >
              <option value="All">All Sectors ({rawPairs.length})</option>
              {Object.entries(sectorCounts)
                .sort((a, b) => b[1] - a[1])
                .map(([sec, count]) => (
                  <option key={sec} value={sec}>
                    {sec} ({count})
                  </option>
                ))}
            </select>

            {/* Threshold buttons */}
            <div className="flex items-center gap-1 bg-bg-soft border border-line rounded-lg p-0.5">
              {[
                { label: "r ≥ 0.90", val: 0.9 },
                { label: "r ≥ 0.93", val: 0.93 },
                { label: "r ≥ 0.95", val: 0.95 },
                { label: "r ≥ 0.97", val: 0.97 },
              ].map((th) => (
                <button
                  key={th.val}
                  onClick={() => {
                    setMinCorrFilter(th.val);
                    setPage(1);
                  }}
                  className={cn(
                    "px-2 py-1 text-xs rounded transition-colors font-mono",
                    minCorrFilter === th.val
                      ? "bg-brand/20 text-brand font-semibold"
                      : "text-gray-400 hover:text-gray-200"
                  )}
                >
                  {th.label}
                </button>
              ))}
            </div>

            {/* Rows per page */}
            <select
              value={pageSize}
              onChange={(e) => {
                setPageSize(Number(e.target.value));
                setPage(1);
              }}
              className="bg-bg-soft border border-line rounded-lg px-2 py-1.5 text-xs text-gray-300 focus:outline-none focus:border-brand/60"
            >
              <option value={25}>25 / page</option>
              <option value={50}>50 / page</option>
              <option value={100}>100 / page</option>
            </select>
          </div>
        </div>

        {isLoading && <Loading />}
        {error && <ErrorBox error={error} />}

        {/* Master Table */}
        <div className="overflow-x-auto border border-line rounded-lg">
          <table className="w-full text-left text-sm">
            <thead className="bg-bg-soft/75 text-xs uppercase tracking-wider text-gray-400 border-b border-line select-none">
              <tr>
                <th className="py-3 px-3 w-10 text-center text-gray-500 font-mono">#</th>
                <th
                  className="py-3 px-3 cursor-pointer hover:text-white transition-colors"
                  onClick={() => handleSort("ticker_a")}
                >
                  <div className="flex items-center gap-1">
                    <span>Ticker A</span>
                    {sortField === "ticker_a" ? (
                      sortOrder === "asc" ? <ArrowUp className="h-3 w-3 text-brand" /> : <ArrowDown className="h-3 w-3 text-brand" />
                    ) : (
                      <ArrowUpDown className="h-3 w-3 text-gray-600" />
                    )}
                  </div>
                </th>
                <th
                  className="py-3 px-3 cursor-pointer hover:text-white transition-colors"
                  onClick={() => handleSort("ticker_b")}
                >
                  <div className="flex items-center gap-1">
                    <span>Ticker B</span>
                    {sortField === "ticker_b" ? (
                      sortOrder === "asc" ? <ArrowUp className="h-3 w-3 text-brand" /> : <ArrowDown className="h-3 w-3 text-brand" />
                    ) : (
                      <ArrowUpDown className="h-3 w-3 text-gray-600" />
                    )}
                  </div>
                </th>
                <th
                  className="py-3 px-3 cursor-pointer hover:text-white transition-colors"
                  onClick={() => handleSort("sector")}
                >
                  <div className="flex items-center gap-1">
                    <span>GICS Sector</span>
                    {sortField === "sector" ? (
                      sortOrder === "asc" ? <ArrowUp className="h-3 w-3 text-brand" /> : <ArrowDown className="h-3 w-3 text-brand" />
                    ) : (
                      <ArrowUpDown className="h-3 w-3 text-gray-600" />
                    )}
                  </div>
                </th>
                <th
                  className="py-3 px-3 cursor-pointer hover:text-white transition-colors w-36"
                  onClick={() => handleSort("correlation")}
                >
                  <div className="flex items-center gap-1">
                    <span>Corr (r)</span>
                    {sortField === "correlation" ? (
                      sortOrder === "asc" ? <ArrowUp className="h-3 w-3 text-brand" /> : <ArrowDown className="h-3 w-3 text-brand" />
                    ) : (
                      <ArrowUpDown className="h-3 w-3 text-gray-600" />
                    )}
                  </div>
                </th>
                <th
                  className="py-3 px-3 cursor-pointer hover:text-white transition-colors w-32"
                  onClick={() => handleSort("cointegration_pvalue")}
                >
                  <div className="flex items-center gap-1">
                    <span>Coint (p)</span>
                    {sortField === "cointegration_pvalue" ? (
                      sortOrder === "asc" ? <ArrowUp className="h-3 w-3 text-brand" /> : <ArrowDown className="h-3 w-3 text-brand" />
                    ) : (
                      <ArrowUpDown className="h-3 w-3 text-gray-600" />
                    )}
                  </div>
                </th>
                {viewMode === "elite" && (
                  <>
                    <th
                      className="py-3 px-3 cursor-pointer hover:text-white transition-colors w-28"
                      onClick={() => handleSort("half_life")}
                    >
                      <div className="flex items-center gap-1">
                        <span>Half-Life</span>
                        {sortField === "half_life" ? (
                          sortOrder === "asc" ? <ArrowUp className="h-3 w-3 text-brand" /> : <ArrowDown className="h-3 w-3 text-brand" />
                        ) : (
                          <ArrowUpDown className="h-3 w-3 text-gray-600" />
                        )}
                      </div>
                    </th>
                    <th
                      className="py-3 px-3 cursor-pointer hover:text-white transition-colors w-28"
                      onClick={() => handleSort("hurst_exponent")}
                    >
                      <div className="flex items-center gap-1">
                        <span>Hurst (H)</span>
                        {sortField === "hurst_exponent" ? (
                          sortOrder === "asc" ? <ArrowUp className="h-3 w-3 text-brand" /> : <ArrowDown className="h-3 w-3 text-brand" />
                        ) : (
                          <ArrowUpDown className="h-3 w-3 text-gray-600" />
                        )}
                      </div>
                    </th>
                    <th
                      className="py-3 px-3 cursor-pointer hover:text-white transition-colors w-28"
                      onClick={() => handleSort("adf_t_stat")}
                    >
                      <div className="flex items-center gap-1">
                        <span>ADF t-stat</span>
                        {sortField === "adf_t_stat" ? (
                          sortOrder === "asc" ? <ArrowUp className="h-3 w-3 text-brand" /> : <ArrowDown className="h-3 w-3 text-brand" />
                        ) : (
                          <ArrowUpDown className="h-3 w-3 text-gray-600" />
                        )}
                      </div>
                    </th>
                    <th
                      className="py-3 px-3 cursor-pointer hover:text-white transition-colors w-24 text-center"
                      onClick={() => handleSort("zero_crossings")}
                    >
                      <div className="flex items-center justify-center gap-1">
                        <span>Crossings</span>
                        {sortField === "zero_crossings" ? (
                          sortOrder === "asc" ? <ArrowUp className="h-3 w-3 text-brand" /> : <ArrowDown className="h-3 w-3 text-brand" />
                        ) : (
                          <ArrowUpDown className="h-3 w-3 text-gray-600" />
                        )}
                      </div>
                    </th>
                  </>
                )}
              </tr>
            </thead>
            <tbody className="divide-y divide-line/60 font-sans">
              {paginatedPairs.length === 0 ? (
                <tr>
                  <td colSpan={viewMode === "elite" ? 10 : 6} className="py-10 text-center text-gray-500">
                    No pairs found matching your criteria.
                  </td>
                </tr>
              ) : (
                paginatedPairs.map((p, idx) => {
                  const rowNum = (page - 1) * pageSize + idx + 1;
                  const sectorMeta = SECTOR_STYLES[p.sector] || {
                    badge: "border-line bg-bg-hover text-gray-300",
                    dot: "bg-gray-400",
                  };
                  const pctWidth = Math.max(0, Math.min(100, ((p.correlation - 0.9) / 0.1) * 100));

                  return (
                    <tr
                      key={`${p.ticker_a}-${p.ticker_b}-${idx}`}
                      className="hover:bg-bg-hover/60 transition-colors group"
                    >
                      <td className="py-3 px-3 text-center font-mono text-xs text-gray-500">
                        {rowNum}
                      </td>
                      <td className="py-3 px-3 font-mono font-bold text-white text-sm">
                        <Link
                          to={`/setups/${p.ticker_a}/${p.ticker_b}`}
                          className="hover:text-cyan-400 transition-colors"
                          title={`Open ${p.ticker_a}/${p.ticker_b} Setup Chart`}
                        >
                          {p.ticker_a}
                        </Link>
                      </td>
                      <td className="py-3 px-3 font-mono font-bold text-white text-sm">
                        <Link
                          to={`/setups/${p.ticker_a}/${p.ticker_b}`}
                          className="hover:text-cyan-400 transition-colors"
                          title={`Open ${p.ticker_a}/${p.ticker_b} Setup Chart`}
                        >
                          {p.ticker_b}
                        </Link>
                      </td>
                      <td className="py-3 px-3">
                        <span
                          className={cn(
                            "inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium border",
                            sectorMeta.badge
                          )}
                        >
                          <span className={cn("h-1.5 w-1.5 rounded-full", sectorMeta.dot)} />
                          {p.sector}
                        </span>
                      </td>
                      <td className="py-3 px-3">
                        <div className="space-y-1">
                          <div className="flex justify-between items-baseline text-xs">
                            <span className="font-mono font-bold text-brand-glow">
                              {p.correlation.toFixed(4)}
                            </span>
                            <span className="text-[10px] text-gray-500 font-mono">
                              {(p.correlation * 100).toFixed(1)}%
                            </span>
                          </div>
                          <div className="h-1.5 w-full bg-bg-soft rounded-full overflow-hidden">
                            <div
                              className="h-full rounded-full bg-brand transition-all duration-300"
                              style={{ width: `${Math.max(20, pctWidth)}%` }}
                            />
                          </div>
                        </div>
                      </td>
                      <td className="py-3 px-3">
                        <div className="font-mono text-xs">
                          <span className="font-bold text-pos">
                            {p.cointegration_pvalue.toFixed(4)}
                          </span>
                        </div>
                      </td>
                      {viewMode === "elite" && (
                        <>
                          <td className="py-3 px-3 font-mono text-xs text-white">
                            {p.half_life !== undefined ? (
                              <span className="px-1.5 py-0.5 rounded bg-bg-soft border border-line text-cyan-300 font-semibold">
                                {p.half_life.toFixed(1)}d
                              </span>
                            ) : (
                              "—"
                            )}
                          </td>
                          <td className="py-3 px-3 font-mono text-xs">
                            {p.hurst_exponent !== undefined ? (
                              <span className="text-emerald-300 font-semibold">
                                {p.hurst_exponent.toFixed(3)}
                              </span>
                            ) : (
                              "—"
                            )}
                          </td>
                          <td className="py-3 px-3 font-mono text-xs">
                            {p.adf_t_stat !== undefined ? (
                              <span className="text-amber-300 font-semibold">
                                {p.adf_t_stat.toFixed(2)}
                              </span>
                            ) : (
                              "—"
                            )}
                          </td>
                          <td className="py-3 px-3 font-mono text-xs text-center text-gray-300">
                            {p.zero_crossings ?? "—"}
                          </td>
                        </>
                      )}
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>

        {/* Pagination Footer */}
        {sortedPairs.length > 0 && (
          <div className="flex flex-col sm:flex-row items-center justify-between gap-3 pt-2 text-xs text-gray-400">
            <div>
              Showing{" "}
              <span className="font-mono text-gray-200">
                {Math.min(sortedPairs.length, (page - 1) * pageSize + 1)}
              </span>{" "}
              to{" "}
              <span className="font-mono text-gray-200">
                {Math.min(sortedPairs.length, page * pageSize)}
              </span>{" "}
              of <span className="font-mono text-brand">{sortedPairs.length.toLocaleString()}</span>{" "}
              pairs
            </div>

            <div className="flex items-center gap-1.5">
              <Button
                variant="outline"
                className="px-2.5 py-1 text-xs"
                disabled={page <= 1}
                onClick={() => setPage((p) => Math.max(1, p - 1))}
              >
                Previous
              </Button>
              <div className="px-3 py-1 bg-bg-soft border border-line rounded-lg font-mono text-xs text-gray-300">
                Page {page} of {totalPages}
              </div>
              <Button
                variant="outline"
                className="px-2.5 py-1 text-xs"
                disabled={page >= totalPages}
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
              >
                Next
              </Button>
            </div>
          </div>
        )}
      </Card>
    </div>
  );
}
