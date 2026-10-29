import React from "react";
import {
  TrendingUp,
  TrendingDown,
  BarChart2,
  ShieldCheck,
  Zap,
  Activity,
  Layers,
  Sparkles,
  ArrowRight,
  ExternalLink,
} from "lucide-react";
import type { PointInTimeSetup } from "@/lib/simulatorTypes";
import { cn } from "@/lib/utils";

interface SimulatorSetupsTableProps {
  setups: PointInTimeSetup[];
  currentDate: string;
  isLoading?: boolean;
  selectedPairName?: string;
  onSelectPair: (setup: PointInTimeSetup) => void;
}

export const SimulatorSetupsTable: React.FC<SimulatorSetupsTableProps> = ({
  setups,
  currentDate,
  isLoading = false,
  selectedPairName,
  onSelectPair,
}) => {
  // Helper to color-code spread tier
  const getSpreadTierBadge = (tier: string) => {
    switch (tier.toLowerCase()) {
      case "ultra tight":
        return "border-cyan-500/30 bg-cyan-500/10 text-cyan-300";
      case "tight":
        return "border-blue-500/30 bg-blue-500/10 text-blue-300";
      case "medium":
      case "medium / moderate":
        return "border-amber-500/30 bg-amber-500/10 text-amber-300";
      default:
        return "border-purple-500/30 bg-purple-500/10 text-purple-300";
    }
  };

  // Helper for score badge
  const getScoreBadge = (score: number) => {
    if (score >= 80) return "text-emerald-400 bg-emerald-500/10 border-emerald-500/30";
    if (score >= 70) return "text-cyan-400 bg-cyan-500/10 border-cyan-500/30";
    if (score >= 60) return "text-amber-400 bg-amber-500/10 border-amber-500/30";
    return "text-gray-400 bg-gray-800/40 border-gray-700/40";
  };

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-2xl shadow-2xl overflow-hidden mb-6">
      {/* Table Header Controls */}
      <div className="flex items-center justify-between px-5 py-4 border-b border-gray-800/80 bg-gray-950/40">
        <div className="flex items-center gap-3">
          <Layers className="w-5 h-5 text-cyan-400" />
          <div>
            <h2 className="text-base font-bold text-white tracking-wide">
              Point-in-Time Divergence Setups
            </h2>
            <p className="text-xs text-gray-400 font-mono">
              Evaluated strictly on historical data known on or before {currentDate} (Zero Lookahead)
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <span className="text-xs font-mono px-2.5 py-1 rounded-lg bg-gray-800/80 text-gray-300 border border-gray-700/60">
            {setups.length} triggered pairs
          </span>
        </div>
      </div>

      {/* Loading Skeleton */}
      {isLoading ? (
        <div className="py-20 flex flex-col items-center justify-center gap-3">
          <div className="w-8 h-8 border-2 border-cyan-500 border-t-transparent rounded-full animate-spin" />
          <span className="text-sm font-mono text-gray-400">
            Slicing historical universe matrix for {currentDate}...
          </span>
        </div>
      ) : setups.length === 0 ? (
        /* Constraint 1: Graceful Empty State Handling */
        <div className="py-16 px-6 flex flex-col items-center justify-center text-center">
          <div className="w-14 h-14 rounded-2xl bg-gray-800/40 border border-gray-700/40 flex items-center justify-center mb-4 text-gray-500">
            <Activity className="w-7 h-7" />
          </div>
          <h3 className="text-base font-bold text-gray-200 mb-1">
            No Active Divergence Setups on {currentDate}
          </h3>
          <p className="text-xs text-gray-400 max-w-md font-mono mb-5">
            The cointegrated universe is currently in statistical equilibrium with no pairs breaching
            the <span className="text-cyan-400 font-semibold">|Z| ≥ 2.0σ</span> dislocation entry gate.
          </p>
          <div className="inline-flex items-center gap-2 px-3.5 py-1.5 rounded-xl bg-gray-800/60 border border-gray-700 text-xs font-mono text-gray-300">
            <span>Tip: Click</span>
            <span className="px-1.5 py-0.5 rounded bg-gray-700 text-cyan-300 font-bold">+1 Day</span>
            <span>or</span>
            <span className="px-1.5 py-0.5 rounded bg-emerald-500/20 text-emerald-300 font-bold">Play Auto</span>
            <span>to advance forward</span>
          </div>
        </div>
      ) : (
        /* Data Grid Table */
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm font-mono">
            <thead>
              <tr className="border-b border-gray-800 text-[11px] uppercase tracking-wider text-gray-400 bg-gray-950/60">
                <th className="py-3 px-4 font-semibold">Pair Name</th>
                <th className="py-3 px-4 font-semibold">Action & Direction</th>
                <th className="py-3 px-4 font-semibold">Z-Score Dislocation</th>
                <th className="py-3 px-4 font-semibold">Hedge Ratio (β)</th>
                <th className="py-3 px-4 font-semibold">ADF Stationarity</th>
                <th className="py-3 px-4 font-semibold">Spread Tier</th>
                <th className="py-3 px-4 font-semibold">Composite Score</th>
                <th className="py-3 px-4 font-semibold text-right">Inspect</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-800/60">
              {setups.map((setup) => {
                const isSelected = selectedPairName === setup.pair_name;
                const isLongSpread = setup.direction === "LONG_A_SHORT_B";

                return (
                  <tr
                    key={setup.pair_name}
                    className={cn(
                      "transition-colors group hover:bg-gray-800/30",
                      isSelected ? "bg-cyan-500/10 border-l-2 border-cyan-400" : ""
                    )}
                  >
                    {/* Pair Name */}
                    <td className="py-3.5 px-4 font-bold text-white">
                      <div className="flex items-center gap-2">
                        <span className="text-cyan-300 text-sm">{setup.ticker_a}</span>
                        <span className="text-gray-600">/</span>
                        <span className="text-gray-300 text-sm">{setup.ticker_b}</span>
                      </div>
                      <div className="text-[10px] text-gray-500 mt-0.5">
                        corr: {(setup.correlation * 100).toFixed(1)}% · r²: {setup.r_squared.toFixed(2)}
                      </div>
                    </td>

                    {/* Action & Direction */}
                    <td className="py-3.5 px-4">
                      {isLongSpread ? (
                        <div className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg border border-emerald-500/30 bg-emerald-500/10 text-emerald-300 text-xs font-semibold">
                          <TrendingUp className="w-3.5 h-3.5" />
                          <span>BUY {setup.ticker_a} / SHORT {setup.ticker_b}</span>
                        </div>
                      ) : (
                        <div className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg border border-rose-500/30 bg-rose-500/10 text-rose-300 text-xs font-semibold">
                          <TrendingDown className="w-3.5 h-3.5" />
                          <span>SHORT {setup.ticker_a} / BUY {setup.ticker_b}</span>
                        </div>
                      )}
                      <div className="text-[10px] text-gray-500 mt-1">
                        Entry: ${setup.price_a_entry.toFixed(2)} vs ${setup.price_b_entry.toFixed(2)}
                      </div>
                    </td>

                    {/* Z-Score Dislocation */}
                    <td className="py-3.5 px-4">
                      <div className="flex items-baseline gap-1.5">
                        <span
                          className={cn(
                            "text-sm font-bold",
                            setup.current_z_score >= 0 ? "text-rose-400" : "text-emerald-400"
                          )}
                        >
                          {setup.current_z_score >= 0 ? "+" : ""}
                          {setup.current_z_score.toFixed(2)}σ
                        </span>
                        <span className="text-[10px] text-gray-500">
                          (target: 0.0σ)
                        </span>
                      </div>
                      <div className="text-[10px] text-gray-500 mt-0.5">
                        spread: {setup.current_spread.toFixed(2)} (μ: {setup.spread_mean.toFixed(2)})
                      </div>
                    </td>

                    {/* Hedge Ratio (Beta) */}
                    <td className="py-3.5 px-4">
                      <div className="text-gray-200 text-xs font-semibold">
                        β = {setup.hedge_ratio.toFixed(4)}
                      </div>
                      <div className="text-[10px] text-gray-500 mt-0.5">
                        α = {setup.alpha.toFixed(2)}
                      </div>
                    </td>

                    {/* ADF Stationarity & Half-Life */}
                    <td className="py-3.5 px-4">
                      <div className="flex items-center gap-1.5">
                        <ShieldCheck className="w-3.5 h-3.5 text-cyan-400" />
                        <span className="text-xs text-gray-200">
                          p = {setup.adf_pvalue.toFixed(4)}
                        </span>
                      </div>
                      <div className="text-[10px] text-gray-500 mt-0.5">
                        t½: {setup.half_life_days > 365 ? "> 1y" : `${setup.half_life_days.toFixed(1)}d`} · {setup.zero_crossings} crosses
                      </div>
                    </td>

                    {/* Spread Tier */}
                    <td className="py-3.5 px-4">
                      <span
                        className={cn(
                          "inline-block px-2 py-0.5 rounded-md text-[11px] font-semibold border",
                          getSpreadTierBadge(setup.spread_tier)
                        )}
                      >
                        {setup.spread_tier}
                      </span>
                      <div className="text-[10px] text-gray-500 mt-0.5">
                        vol: {setup.relative_spread_vol_pct.toFixed(2)}%
                      </div>
                    </td>

                    {/* Composite Score */}
                    <td className="py-3.5 px-4">
                      <div className="flex items-center gap-2">
                        <span
                          className={cn(
                            "px-2.5 py-1 rounded-lg text-xs font-bold border",
                            getScoreBadge(setup.composite_score)
                          )}
                        >
                          {setup.composite_score.toFixed(1)}
                        </span>
                      </div>
                    </td>

                    {/* Inspect Button */}
                    <td className="py-3.5 px-4 text-right">
                      <button
                        type="button"
                        onClick={() => onSelectPair(setup)}
                        className={cn(
                          "inline-flex items-center gap-1 px-3 py-1.5 rounded-lg text-xs font-medium transition-all shadow-sm active:scale-95",
                          isSelected
                            ? "bg-cyan-500 text-gray-950 font-bold"
                            : "bg-gray-800 text-gray-200 hover:bg-gray-700 hover:text-white border border-gray-700"
                        )}
                      >
                        <BarChart2 className="w-3.5 h-3.5" />
                        <span>Inspect Chart</span>
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
};
