import React from "react";
import { Link } from "react-router-dom";
import {
  LayoutDashboard,
  TrendingUp,
  ShieldAlert,
  Flame,
  GitCompare,
  Layers,
} from "lucide-react";
import { cn } from "@/lib/utils";

export type StrategySubNavTab =
  | "dashboard"
  | "strategy-1"
  | "strategy-2"
  | "strategy-3"
  | "compare";

interface StrategySubNavProps {
  activeTab: StrategySubNavTab;
}

export default function StrategySubNav({ activeTab }: StrategySubNavProps) {
  const tabs = [
    {
      key: "dashboard" as const,
      label: "Main Dashboard (12 Strategies Workbench)",
      to: "/backtest",
      icon: LayoutDashboard,
      activeClass: "bg-surface-3 text-white border-line shadow-sm",
      indicatorColor: "bg-cyan-400",
    },
    {
      key: "strategy-1" as const,
      label: "Strategy 1 (Baseline)",
      to: "/backtest/strategy-v1",
      icon: TrendingUp,
      activeClass: "bg-sky-500/20 text-sky-200 border-sky-500/40 shadow-sm",
      indicatorColor: "bg-sky-400",
    },
    {
      key: "strategy-2" as const,
      label: "Strategy 2 (Staged Experiment)",
      to: "/backtest/strategy-v2",
      icon: ShieldAlert,
      activeClass: "bg-amber-500/20 text-amber-200 border-amber-500/40 shadow-sm",
      indicatorColor: "bg-amber-400",
    },
    {
      key: "strategy-3" as const,
      label: "Strategy 3 (Alpha Maximizer)",
      to: "/backtest/strategy-v3",
      icon: Flame,
      activeClass: "bg-emerald-500/20 text-emerald-200 border-emerald-500/40 shadow-sm",
      indicatorColor: "bg-emerald-400",
    },
    {
      key: "compare" as const,
      label: "3-Way Strategy Comparison",
      to: "/backtest/compare-strategies",
      icon: GitCompare,
      activeClass: "bg-purple-500/20 text-purple-200 border-purple-500/40 shadow-sm",
      indicatorColor: "bg-purple-400",
    },
  ];

  return (
    <div className="flex items-center gap-1.5 p-1 bg-surface-2/80 backdrop-blur border border-line rounded-xl overflow-x-auto select-none font-mono text-xs">
      {tabs.map((tab) => {
        const isActive = activeTab === tab.key;
        const Icon = tab.icon;
        return (
          <Link
            key={tab.key}
            to={tab.to}
            className={cn(
              "flex items-center gap-2 px-3 py-1.5 rounded-lg transition-all whitespace-nowrap border border-transparent",
              isActive
                ? tab.activeClass
                : "text-gray-400 hover:text-gray-200 hover:bg-surface-1/60"
            )}
          >
            <span
              className={cn(
                "w-2 h-2 rounded-full",
                isActive ? tab.indicatorColor : "bg-gray-600"
              )}
            />
            <Icon className="w-3.5 h-3.5" />
            <span className="font-semibold">{tab.label}</span>
          </Link>
        );
      })}
    </div>
  );
}
