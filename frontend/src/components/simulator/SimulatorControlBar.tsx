import React, { useState, useMemo } from "react";
import {
  Calendar,
  Lock,
  Unlock,
  ChevronLeft,
  ChevronRight,
  Play,
  Pause,
  RotateCcw,
  Zap,
  Activity,
  SlidersHorizontal,
  ChevronDown,
  ChevronUp,
  Settings2,
  RefreshCw,
} from "lucide-react";
import { cn } from "@/lib/utils";

export interface StrategyParams {
  minZ: number;
  maxAdf: number;
  minCorr: number;
  stopLossZ: number;
  horizonDays: number;
}

export const DEFAULT_STRATEGY_PARAMS: StrategyParams = {
  minZ: 2.0,
  maxAdf: 0.05,
  minCorr: 0.85,
  stopLossZ: 3.5,
  horizonDays: 30,
};

interface SimulatorControlBarProps {
  anchorDate: string;
  currentDate: string;
  isAnchorLocked: boolean;
  isPlaying: boolean;
  speed: number;
  minDate: string;
  maxDate: string;
  activeSetupsCount: number;
  scanLatencyMs?: number;
  isLoading?: boolean;
  strategyParams?: StrategyParams;
  onAnchorDateChange: (date: string) => void;
  onToggleAnchorLock: () => void;
  onStep: (direction: "-1" | "+1") => void;
  onTogglePlay: () => void;
  onSpeedChange: (speed: number) => void;
  onResetToAnchor: () => void;
  onStrategyParamsChange?: (params: StrategyParams) => void;
  onResetStrategyParams?: () => void;
}

export const SimulatorControlBar: React.FC<SimulatorControlBarProps> = ({
  anchorDate,
  currentDate,
  isAnchorLocked,
  isPlaying,
  speed,
  minDate,
  maxDate,
  activeSetupsCount,
  scanLatencyMs,
  isLoading = false,
  strategyParams = DEFAULT_STRATEGY_PARAMS,
  onAnchorDateChange,
  onToggleAnchorLock,
  onStep,
  onTogglePlay,
  onSpeedChange,
  onResetToAnchor,
  onStrategyParamsChange,
  onResetStrategyParams,
}) => {
  // Advanced strategy parameter drawer state (HIDDEN / COMPRESSED BY DEFAULT as requested)
  const [isAdvancedOpen, setIsAdvancedOpen] = useState<boolean>(false);

  // Constraint 2: -1 Day button MUST be disabled if currentDate equals anchorDate (or <= anchorDate when locked)
  const isBackDisabled = isAnchorLocked ? currentDate <= anchorDate : currentDate <= minDate;
  const isForwardDisabled = currentDate >= maxDate;

  // Calculate days offset between anchorDate and currentDate
  const daysOffset = useMemo(() => {
    try {
      const a = new Date(anchorDate).getTime();
      const c = new Date(currentDate).getTime();
      const diff = Math.round((c - a) / (1000 * 60 * 60 * 24));
      if (diff === 0) return "+0d";
      return diff > 0 ? `+${diff}d` : `${diff}d`;
    } catch {
      return "+0d";
    }
  }, [anchorDate, currentDate]);

  // Check if current parameters deviate from defaults
  const isCustomParams = useMemo(() => {
    return (
      strategyParams.minZ !== DEFAULT_STRATEGY_PARAMS.minZ ||
      strategyParams.maxAdf !== DEFAULT_STRATEGY_PARAMS.maxAdf ||
      strategyParams.minCorr !== DEFAULT_STRATEGY_PARAMS.minCorr ||
      strategyParams.stopLossZ !== DEFAULT_STRATEGY_PARAMS.stopLossZ ||
      strategyParams.horizonDays !== DEFAULT_STRATEGY_PARAMS.horizonDays
    );
  }, [strategyParams]);

  const handleParamChange = (key: keyof StrategyParams, value: number) => {
    if (onStrategyParamsChange) {
      onStrategyParamsChange({
        ...strategyParams,
        [key]: value,
      });
    }
  };

  return (
    <div className="bg-gray-900/95 border border-gray-800 rounded-2xl p-4 shadow-2xl backdrop-blur-md mb-6 font-sans">
      {/* Primary Clean Control Row */}
      <div className="flex flex-wrap items-center justify-between gap-4">
        {/* Left: Anchor Date & Lock Controller */}
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2 bg-gray-950/80 border border-gray-800/80 rounded-xl px-3 py-2 shadow-inner">
            <Calendar className="w-4 h-4 text-cyan-400 shrink-0" />
            <div className="flex flex-col">
              <span className="text-[10px] uppercase tracking-wider text-gray-500 font-semibold font-mono">
                Anchor T (Entry Base)
              </span>
              <input
                type="date"
                value={anchorDate}
                min={minDate}
                max={maxDate}
                onChange={(e) => onAnchorDateChange(e.target.value)}
                disabled={isPlaying}
                className="bg-transparent text-sm font-mono text-cyan-200 outline-none cursor-pointer disabled:opacity-50"
              />
            </div>
          </div>

          {/* Anchor Lock Toggle Button */}
          <button
            type="button"
            onClick={onToggleAnchorLock}
            title={
              isAnchorLocked
                ? "Anchor Locked: Prevents stepping behind base date T"
                : "Anchor Unlocked: Freely step before anchor"
            }
            className={cn(
              "flex items-center gap-1.5 px-3 py-2 rounded-xl text-xs font-mono font-medium border transition-all duration-200 shadow-sm",
              isAnchorLocked
                ? "bg-amber-500/10 border-amber-500/30 text-amber-300 hover:bg-amber-500/20"
                : "bg-gray-800/60 border-gray-700/60 text-gray-400 hover:text-gray-200 hover:bg-gray-800"
            )}
          >
            {isAnchorLocked ? (
              <>
                <Lock className="w-3.5 h-3.5 text-amber-400" />
                <span>Locked</span>
              </>
            ) : (
              <>
                <Unlock className="w-3.5 h-3.5 text-gray-400" />
                <span>Unlocked</span>
              </>
            )}
          </button>

          {/* Advanced Strategy Parameters Toggle Button (Compressible / Openable, Hidden by Default) */}
          <button
            type="button"
            onClick={() => setIsAdvancedOpen(!isAdvancedOpen)}
            className={cn(
              "flex items-center gap-1.5 px-3 py-2 rounded-xl text-xs font-mono font-medium border transition-all duration-200 shadow-sm",
              isAdvancedOpen
                ? "bg-cyan-500/20 border-cyan-500/50 text-cyan-300"
                : isCustomParams
                ? "bg-amber-500/10 border-amber-500/40 text-amber-300 hover:bg-amber-500/20"
                : "bg-gray-800/60 border-gray-700/60 text-gray-400 hover:text-white hover:bg-gray-800"
            )}
            title="Toggle advanced strategy parameters (Z-score gate, ADF stationarity, correlation)"
          >
            <SlidersHorizontal className="w-3.5 h-3.5 text-cyan-400" />
            <span>Advanced</span>
            {isCustomParams && (
              <span className="w-1.5 h-1.5 rounded-full bg-amber-400 animate-pulse" />
            )}
            {isAdvancedOpen ? (
              <ChevronUp className="w-3.5 h-3.5 text-gray-400" />
            ) : (
              <ChevronDown className="w-3.5 h-3.5 text-gray-400" />
            )}
          </button>
        </div>

        {/* Center: VCR Playback Controls */}
        <div className="flex items-center gap-2 bg-gray-950/80 border border-gray-800/80 rounded-xl p-1.5 shadow-inner">
          {/* Step -1 Day Button (Constraint 2: Disabled when currentDate === anchorDate) */}
          <button
            type="button"
            onClick={() => onStep("-1")}
            disabled={isBackDisabled || isLoading || isPlaying}
            title={
              isBackDisabled
                ? "Cannot step behind anchor date T (Constraint 2)"
                : "Step backward 1 trading day (-1 Day)"
            }
            className={cn(
              "flex items-center gap-1 px-3 py-1.5 rounded-lg text-xs font-mono font-medium transition-all",
              isBackDisabled
                ? "opacity-30 cursor-not-allowed text-gray-600 bg-gray-900/40"
                : "text-gray-300 hover:text-white hover:bg-gray-800/80 active:scale-95 bg-gray-900 border border-gray-800"
            )}
          >
            <ChevronLeft className="w-4 h-4" />
            <span>-1 Day</span>
          </button>

          {/* Play / Pause Auto Stepper */}
          <button
            type="button"
            onClick={onTogglePlay}
            disabled={isForwardDisabled || isLoading}
            className={cn(
              "flex items-center gap-1.5 px-4 py-1.5 rounded-lg text-xs font-mono font-semibold transition-all shadow-md active:scale-95",
              isPlaying
                ? "bg-rose-500/20 border border-rose-500/40 text-rose-300 hover:bg-rose-500/30 animate-pulse"
                : "bg-emerald-500/20 border border-emerald-500/40 text-emerald-300 hover:bg-emerald-500/30"
            )}
          >
            {isPlaying ? (
              <>
                <Pause className="w-4 h-4 fill-current" />
                <span>Pause</span>
              </>
            ) : (
              <>
                <Play className="w-4 h-4 fill-current" />
                <span>Play Auto</span>
              </>
            )}
          </button>

          {/* Step +1 Day Button */}
          <button
            type="button"
            onClick={() => onStep("+1")}
            disabled={isForwardDisabled || isLoading || isPlaying}
            title="Step forward 1 trading day (+1 Day)"
            className={cn(
              "flex items-center gap-1 px-3 py-1.5 rounded-lg text-xs font-mono font-medium transition-all",
              isForwardDisabled
                ? "opacity-30 cursor-not-allowed text-gray-600 bg-gray-900/40"
                : "text-gray-300 hover:text-white hover:bg-gray-800/80 active:scale-95 bg-gray-900 border border-gray-800"
            )}
          >
            <span>+1 Day</span>
            <ChevronRight className="w-4 h-4" />
          </button>

          {/* Speed Selector (1x, 2x, 5x) */}
          <div className="flex items-center gap-0.5 ml-2 border-l border-gray-800 pl-2">
            {[1, 2, 5].map((s) => (
              <button
                key={s}
                type="button"
                onClick={() => onSpeedChange(s)}
                className={cn(
                  "px-2 py-1 text-[11px] font-mono rounded transition-colors",
                  speed === s
                    ? "bg-cyan-500/20 text-cyan-300 font-bold border border-cyan-500/40"
                    : "text-gray-500 hover:text-gray-300"
                )}
              >
                {s}x
              </button>
            ))}
          </div>

          {/* Reset to Anchor */}
          <button
            type="button"
            onClick={onResetToAnchor}
            disabled={currentDate === anchorDate || isPlaying}
            title="Reset simulation to Anchor Date T"
            className="p-1.5 rounded-lg text-gray-500 hover:text-gray-300 hover:bg-gray-800/50 disabled:opacity-30 transition-all ml-1"
          >
            <RotateCcw className="w-3.5 h-3.5" />
          </button>
        </div>

        {/* Right: Current Simulated Status Readout */}
        <div className="flex items-center gap-3">
          {/* Simulated Date Badge */}
          <div className="bg-gray-950/90 border border-cyan-500/30 rounded-xl px-3.5 py-1.5 shadow-sm flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-cyan-400 animate-ping" />
            <div className="flex flex-col">
              <span className="text-[9px] uppercase tracking-wider text-gray-500 font-mono font-semibold">
                Simulated Date
              </span>
              <div className="flex items-baseline gap-1.5">
                <span className="text-base font-bold font-mono text-white tracking-tight">
                  {currentDate}
                </span>
                <span className="text-xs font-mono text-cyan-400 font-semibold">
                  ({daysOffset})
                </span>
              </div>
            </div>
          </div>

          {/* Active Setups Pill */}
          <div className="bg-gray-950/80 border border-gray-800 rounded-xl px-3 py-1.5 flex flex-col items-center min-w-[90px]">
            <span className="text-[9px] uppercase tracking-wider text-gray-500 font-mono">
              Active Setups
            </span>
            <div className="flex items-center gap-1 mt-0.5">
              <Activity className="w-3.5 h-3.5 text-emerald-400" />
              <span className="text-sm font-bold font-mono text-emerald-300">
                {activeSetupsCount}
              </span>
            </div>
          </div>

          {/* PIT Latency Pill */}
          {scanLatencyMs !== undefined && (
            <div className="hidden xl:flex bg-gray-950/80 border border-gray-800 rounded-xl px-3 py-1.5 flex-col items-center min-w-[80px]">
              <span className="text-[9px] uppercase tracking-wider text-gray-500 font-mono">
                PIT Latency
              </span>
              <div className="flex items-center gap-1 mt-0.5">
                <Zap className="w-3 h-3 text-amber-400" />
                <span className="text-xs font-bold font-mono text-amber-300">
                  {scanLatencyMs}ms
                </span>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Advanced Strategy Parameters Tray (Collapsible & Hidden by Default) */}
      {isAdvancedOpen && (
        <div className="mt-4 pt-4 border-t border-gray-800/80 bg-gray-950/70 rounded-xl p-4 shadow-inner animate-in slide-in-from-top-2 duration-200">
          <div className="flex items-center justify-between pb-3 mb-4 border-b border-gray-800/60">
            <div className="flex items-center gap-2">
              <Settings2 className="w-4 h-4 text-cyan-400" />
              <span className="text-xs font-mono font-bold text-white tracking-wider uppercase">
                Quantitative Strategy Parameter Configuration
              </span>
              {isCustomParams && (
                <span className="px-2 py-0.5 text-[10px] font-mono rounded bg-amber-500/20 text-amber-300 border border-amber-500/40">
                  Custom Values Active
                </span>
              )}
            </div>

            {onResetStrategyParams && (
              <button
                type="button"
                onClick={onResetStrategyParams}
                disabled={!isCustomParams}
                className="flex items-center gap-1.5 px-2.5 py-1 text-xs font-mono text-gray-400 hover:text-white hover:bg-gray-800 rounded-lg disabled:opacity-30 disabled:cursor-not-allowed transition"
              >
                <RefreshCw className="w-3 h-3" />
                <span>Reset to Defaults</span>
              </button>
            )}
          </div>

          {/* 5 Strategy Parameter Controls Grid */}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-4 font-mono">
            {/* 1. Min Divergence |Z| */}
            <div className="bg-gray-900/80 border border-gray-800 rounded-lg p-3">
              <div className="flex items-center justify-between text-xs mb-1.5">
                <span className="text-gray-400 font-semibold">Min Entry |Z|</span>
                <span className="font-bold text-cyan-300">{strategyParams.minZ.toFixed(1)}σ</span>
              </div>
              <input
                type="range"
                min="1.0"
                max="3.5"
                step="0.1"
                value={strategyParams.minZ}
                onChange={(e) => handleParamChange("minZ", parseFloat(e.target.value))}
                className="w-full accent-cyan-400 cursor-pointer h-1.5 bg-gray-800 rounded-lg"
              />
              <div className="text-[10px] text-gray-500 mt-1.5">
                Default: 2.0σ entry trigger
              </div>
            </div>

            {/* 2. Max ADF p-value */}
            <div className="bg-gray-900/80 border border-gray-800 rounded-lg p-3">
              <div className="flex items-center justify-between text-xs mb-1.5">
                <span className="text-gray-400 font-semibold">Max ADF p-value</span>
                <span className="font-bold text-emerald-300">{strategyParams.maxAdf.toFixed(2)}</span>
              </div>
              <input
                type="range"
                min="0.01"
                max="0.20"
                step="0.01"
                value={strategyParams.maxAdf}
                onChange={(e) => handleParamChange("maxAdf", parseFloat(e.target.value))}
                className="w-full accent-emerald-400 cursor-pointer h-1.5 bg-gray-800 rounded-lg"
              />
              <div className="text-[10px] text-gray-500 mt-1.5">
                Default: 0.05 (95% stationary)
              </div>
            </div>

            {/* 3. Min Correlation */}
            <div className="bg-gray-900/80 border border-gray-800 rounded-lg p-3">
              <div className="flex items-center justify-between text-xs mb-1.5">
                <span className="text-gray-400 font-semibold">Min 90d Correlation</span>
                <span className="font-bold text-purple-300">{(strategyParams.minCorr * 100).toFixed(0)}%</span>
              </div>
              <input
                type="range"
                min="0.50"
                max="0.95"
                step="0.05"
                value={strategyParams.minCorr}
                onChange={(e) => handleParamChange("minCorr", parseFloat(e.target.value))}
                className="w-full accent-purple-400 cursor-pointer h-1.5 bg-gray-800 rounded-lg"
              />
              <div className="text-[10px] text-gray-500 mt-1.5">
                Default: 85% Pearson cutoff
              </div>
            </div>

            {/* 4. Stop-Loss Barrier */}
            <div className="bg-gray-900/80 border border-gray-800 rounded-lg p-3">
              <div className="flex items-center justify-between text-xs mb-1.5">
                <span className="text-gray-400 font-semibold">Stop Barrier |Z|</span>
                <span className="font-bold text-rose-300">{strategyParams.stopLossZ.toFixed(1)}σ</span>
              </div>
              <input
                type="range"
                min="2.5"
                max="5.0"
                step="0.1"
                value={strategyParams.stopLossZ}
                onChange={(e) => handleParamChange("stopLossZ", parseFloat(e.target.value))}
                className="w-full accent-rose-400 cursor-pointer h-1.5 bg-gray-800 rounded-lg"
              />
              <div className="text-[10px] text-gray-500 mt-1.5">
                Default: 3.5σ stop out
              </div>
            </div>

            {/* 5. Max Horizon Days */}
            <div className="bg-gray-900/80 border border-gray-800 rounded-lg p-3">
              <div className="flex items-center justify-between text-xs mb-1.5">
                <span className="text-gray-400 font-semibold">Max Horizon</span>
                <span className="font-bold text-amber-300">{strategyParams.horizonDays}d</span>
              </div>
              <input
                type="range"
                min="10"
                max="60"
                step="5"
                value={strategyParams.horizonDays}
                onChange={(e) => handleParamChange("horizonDays", parseInt(e.target.value, 10))}
                className="w-full accent-amber-400 cursor-pointer h-1.5 bg-gray-800 rounded-lg"
              />
              <div className="text-[10px] text-gray-500 mt-1.5">
                Default: 30 trading days
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
