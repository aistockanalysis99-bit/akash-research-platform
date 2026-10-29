import React, { useEffect, useRef, useState, useMemo, useCallback } from "react";
import {
  createChart,
  LineSeries,
  AreaSeries,
  ColorType,
  LineStyle,
  CrosshairMode,
  IChartApi,
  ISeriesApi,
  Time,
  createSeriesMarkers,
  ISeriesMarkersPluginApi,
} from "lightweight-charts";
import {
  Eye,
  Sparkles,
  TrendingUp,
  TrendingDown,
  RotateCcw,
  CheckCircle2,
  XCircle,
  AlertCircle,
  Activity,
  Layers,
  ShieldCheck,
  Zap,
  Lock,
  ArrowRight,
  Maximize2,
  Clock,
  X,
} from "lucide-react";
import { api } from "@/lib/api";
import type {
  PointInTimeSetup,
  HistoricalBar,
  ForwardBar,
  ForwardEvaluationResult,
  PairChartResponse,
} from "@/lib/simulatorTypes";
import { cn } from "@/lib/utils";

export interface ReplayPairChartProps {
  tickerA: string;
  tickerB: string;
  currentDate: string; // Target simulated date T
  setup?: PointInTimeSetup | null;
  onClose?: () => void;
  className?: string;
  height?: number;
}

export type ViewMode = "spread_z" | "normalized_prices";

export const ReplayPairChart: React.FC<ReplayPairChartProps> = ({
  tickerA,
  tickerB,
  currentDate,
  setup,
  onClose,
  className,
  height = 480,
}) => {
  const chartContainerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);

  // Series references kept in refs to avoid React re-render unmounts (Constraint 1)
  const historicalSpreadSeriesRef = useRef<ISeriesApi<"Area"> | null>(null);
  const futureSpreadSeriesRef = useRef<ISeriesApi<"Line"> | null>(null);
  const historicalSeriesARef = useRef<ISeriesApi<"Line"> | null>(null);
  const historicalSeriesBRef = useRef<ISeriesApi<"Line"> | null>(null);
  const futureSeriesARef = useRef<ISeriesApi<"Line"> | null>(null);
  const futureSeriesBRef = useRef<ISeriesApi<"Line"> | null>(null);
  const markersPluginRef = useRef<ISeriesMarkersPluginApi<Time> | null>(null);

  // Animation timer ref
  const animTimerRef = useRef<NodeJS.Timeout | null>(null);

  // State
  const [viewMode, setViewMode] = useState<ViewMode>("spread_z");
  const [isLoadingHistory, setIsLoadingHistory] = useState<boolean>(true);
  const [historicalBars, setHistoricalBars] = useState<HistoricalBar[]>([]);
  const [isRevealing, setIsRevealing] = useState<boolean>(false);
  const [revealed, setRevealed] = useState<boolean>(false);
  const [forwardOutcome, setForwardOutcome] = useState<ForwardEvaluationResult | null>(null);
  const [isAnimating, setIsAnimating] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [hoverData, setHoverData] = useState<{
    date?: string;
    zScore?: number;
    spread?: number;
    priceA?: number;
    priceB?: number;
  } | null>(null);

  const pairName = `${tickerA}/${tickerB}`;

  // 1. Fetch Historical Data strictly bounded by t <= currentDate
  const fetchHistoricalData = useCallback(async () => {
    setIsLoadingHistory(true);
    setError(null);
    setRevealed(false);
    setForwardOutcome(null);
    setIsAnimating(false);

    if (animTimerRef.current) {
      clearInterval(animTimerRef.current);
      animTimerRef.current = null;
    }

    try {
      const res: PairChartResponse = await api.simulator.pairChart({
        ticker_a: tickerA,
        ticker_b: tickerB,
        current_date: currentDate,
        lookback_days: 90,
        reveal: false, // Strict lookahead guard
      });

      // Defensive chronological sort
      const sorted = [...(res.historical_bars || [])].sort((a, b) =>
        a.date.localeCompare(b.date)
      );
      setHistoricalBars(sorted);
    } catch (err: any) {
      console.error("Failed to load historical chart data:", err);
      setError(err?.message || `Failed to load chart series for ${pairName}`);
    } finally {
      setIsLoadingHistory(false);
    }
  }, [tickerA, tickerB, currentDate, pairName]);

  useEffect(() => {
    fetchHistoricalData();
  }, [fetchHistoricalData]);

  // 2. Initialize and configure Lightweight Charts Canvas
  useEffect(() => {
    if (!chartContainerRef.current || !historicalBars.length) return;

    // Clean up any existing chart instance
    if (chartRef.current) {
      chartRef.current.remove();
      chartRef.current = null;
    }
    markersPluginRef.current = null;

    const container = chartContainerRef.current;

    // Create institutional dark-themed canvas chart
    const chart = createChart(container, {
      width: container.clientWidth,
      height: height,
      layout: {
        background: { type: ColorType.Solid, color: "#090d16" },
        textColor: "#94a3b8",
        fontFamily: "'JetBrains Mono', monospace",
        fontSize: 11,
      },
      grid: {
        vertLines: { color: "#1e293b", style: LineStyle.Dotted },
        horzLines: { color: "#1e293b", style: LineStyle.Dotted },
      },
      crosshair: {
        mode: CrosshairMode.Normal,
        vertLine: {
          color: "#475569",
          width: 1,
          style: LineStyle.Dashed,
          labelBackgroundColor: "#1e293b",
        },
        horzLine: {
          color: "#475569",
          width: 1,
          style: LineStyle.Dashed,
          labelBackgroundColor: "#1e293b",
        },
      },
      // Unified Right Price Scale with AutoScale (Constraint 3)
      rightPriceScale: {
        visible: true,
        borderColor: "#334155",
        scaleMargins: { top: 0.12, bottom: 0.12 },
        autoScale: true,
      },
      leftPriceScale: {
        visible: false,
      },
      timeScale: {
        borderColor: "#334155",
        timeVisible: true,
        secondsVisible: false,
        // Reserve 25 bars on the right for the Frosted Glass Future Zone
        rightOffset: 25,
        barSpacing: 9,
        minBarSpacing: 3,
      },
      handleScale: {
        axisPressedMouseMove: { time: true, price: true },
        mouseWheel: true,
        pinch: true,
      },
      handleScroll: {
        pressedMouseMove: true,
        mouseWheel: false,
        horzTouchDrag: true,
        vertTouchDrag: true,
      },
    });

    chartRef.current = chart;

    // Build series depending on View Mode
    if (viewMode === "spread_z") {
      // Historical Spread Z-Score (Cyan Area)
      const spreadSeries = chart.addSeries(AreaSeries, {
        topColor: "rgba(6, 182, 212, 0.28)",
        bottomColor: "rgba(6, 182, 212, 0.02)",
        lineColor: "#06B6D4",
        lineWidth: 2,
        priceScaleId: "right",
        title: "Spread Z-Score (σ)",
        priceFormat: {
          type: "custom",
          formatter: (price: number) => `${price >= 0 ? "+" : ""}${price.toFixed(2)}σ`,
        },
      });

      spreadSeries.setData(
        historicalBars.map((b) => ({
          time: b.date as Time,
          value: b.z_score,
        }))
      );
      historicalSpreadSeriesRef.current = spreadSeries;

      // Quantitative Reference Price Lines
      // Mean Reversion Target line: z = 0.0σ
      spreadSeries.createPriceLine({
        price: 0.0,
        color: "#10B981",
        lineWidth: 1,
        lineStyle: LineStyle.Dashed,
        axisLabelVisible: true,
        title: "Mean Target (0.0σ)",
      });

      // Entry Dislocation Gates: ±2.0σ
      spreadSeries.createPriceLine({
        price: 2.0,
        color: "#F59E0B",
        lineWidth: 1,
        lineStyle: LineStyle.Dotted,
        axisLabelVisible: true,
        title: "Short Spread Entry (+2.0σ)",
      });
      spreadSeries.createPriceLine({
        price: -2.0,
        color: "#F59E0B",
        lineWidth: 1,
        lineStyle: LineStyle.Dotted,
        axisLabelVisible: true,
        title: "Long Spread Entry (-2.0σ)",
      });

      // Stop Loss Boundaries: ±3.5σ
      spreadSeries.createPriceLine({
        price: 3.5,
        color: "#EF4444",
        lineWidth: 1,
        lineStyle: LineStyle.Dashed,
        axisLabelVisible: true,
        title: "Stop Loss (+3.5σ)",
      });
      spreadSeries.createPriceLine({
        price: -3.5,
        color: "#EF4444",
        lineWidth: 1,
        lineStyle: LineStyle.Dashed,
        axisLabelVisible: true,
        title: "Stop Loss (-3.5σ)",
      });

      // Initial Entry Marker at Date T
      const lastBar = historicalBars[historicalBars.length - 1];
      if (lastBar) {
        const markersPlugin = createSeriesMarkers(spreadSeries, [
          {
            time: lastBar.date as Time,
            position: lastBar.z_score >= 0 ? "aboveBar" : "belowBar",
            color: "#06B6D4",
            shape: lastBar.z_score >= 0 ? "arrowDown" : "arrowUp",
            text: `DATE T: ${lastBar.z_score >= 0 ? "+" : ""}${lastBar.z_score.toFixed(2)}σ`,
            size: 1,
          },
        ]);
        markersPluginRef.current = markersPlugin;
      }
    } else {
      // Normalized Prices Mode (rebased to 100 on first bar)
      const baseA = historicalBars[0]?.price_a || 1;
      const baseB = historicalBars[0]?.price_b || 1;

      const seriesA = chart.addSeries(LineSeries, {
        color: "#38BDF8", // Cyan-400
        lineWidth: 2,
        priceScaleId: "right",
        title: `${tickerA} (Norm)`,
        priceFormat: { type: "price", precision: 2, minMove: 0.01 },
      });
      seriesA.setData(
        historicalBars.map((b) => ({
          time: b.date as Time,
          value: Number(((b.price_a / baseA) * 100).toFixed(2)),
        }))
      );
      historicalSeriesARef.current = seriesA;

      const seriesB = chart.addSeries(LineSeries, {
        color: "#C084FC", // Purple-400
        lineWidth: 2,
        priceScaleId: "right",
        title: `${tickerB} (Norm)`,
        priceFormat: { type: "price", precision: 2, minMove: 0.01 },
      });
      seriesB.setData(
        historicalBars.map((b) => ({
          time: b.date as Time,
          value: Number(((b.price_b / baseB) * 100).toFixed(2)),
        }))
      );
      historicalSeriesBRef.current = seriesB;
    }

    // Subscribe to crosshair move for quantitative tooltip
    chart.subscribeCrosshairMove((param) => {
      if (!param.time || !param.seriesData) {
        setHoverData(null);
        return;
      }

      const dateStr = String(param.time);
      const match = historicalBars.find((b) => b.date === dateStr);
      if (match) {
        setHoverData({
          date: match.date,
          zScore: match.z_score,
          spread: match.spread,
          priceA: match.price_a,
          priceB: match.price_b,
        });
      }
    });

    // Handle responsive container resize
    const handleResize = () => {
      if (chartContainerRef.current && chartRef.current) {
        chartRef.current.applyOptions({
          width: chartContainerRef.current.clientWidth,
        });
      }
    };

    window.addEventListener("resize", handleResize);

    return () => {
      window.removeEventListener("resize", handleResize);
      if (animTimerRef.current) {
        clearInterval(animTimerRef.current);
        animTimerRef.current = null;
      }
      if (chartRef.current) {
        chartRef.current.remove();
        chartRef.current = null;
      }
      markersPluginRef.current = null;
    };
  }, [historicalBars, viewMode, height, tickerA, tickerB]);

  // 3. Reveal Action: Call POST /api/simulator/reveal & Animate Trajectory
  const handleReveal = async () => {
    if (isRevealing || isAnimating || revealed) return;

    setIsRevealing(true);
    setError(null);

    try {
      // Task 3: Call POST /api/simulator/reveal
      const outcomeRes: ForwardEvaluationResult = await api.simulator.reveal({
        ticker_a: tickerA,
        ticker_b: tickerB,
        target_date: currentDate,
        max_horizon_days: 30,
        lookback_days: 90,
      });

      setForwardOutcome(outcomeRes);
      setRevealed(true);
      setIsAnimating(true);

      // Task 4: Animate future trajectory on the chart
      animateFutureTrajectory(outcomeRes);
    } catch (err: any) {
      console.error("Failed to reveal forward trajectory:", err);
      setError(err?.message || "Failed to reveal forward outcome");
      setIsRevealing(false);
    } finally {
      setIsRevealing(false);
    }
  };

  // Task 4: Animate Future Trajectory using lightweight-charts without full page re-render (Constraint 1)
  const animateFutureTrajectory = (outcomeData: ForwardEvaluationResult) => {
    const chart = chartRef.current;
    if (!chart || !historicalBars.length) {
      setIsAnimating(false);
      return;
    }

    const path = outcomeData.path || [];
    if (!path.length) {
      setIsAnimating(false);
      return;
    }

    const lastHistorical = historicalBars[historicalBars.length - 1];
    const isWin = outcomeData.outcome === "WIN";
    const isLoss = outcomeData.outcome === "LOSS";

    // Task 4: Glowing Emerald Green (#10B981) for WIN, Rose Red (#EF4444) for LOSS
    const outcomeStrokeColor = isWin ? "#10B981" : isLoss ? "#EF4444" : "#F59E0B";

    if (viewMode === "spread_z") {
      // Remove any previous future series
      if (futureSpreadSeriesRef.current) {
        try {
          chart.removeSeries(futureSpreadSeriesRef.current);
        } catch {}
        futureSpreadSeriesRef.current = null;
      }

      // Add Future Trajectory Line Series with glowing stroke
      const futureSeries = chart.addSeries(LineSeries, {
        color: outcomeStrokeColor,
        lineWidth: 3,
        lineStyle: LineStyle.Solid,
        priceScaleId: "right",
        title: `Future Trajectory (${outcomeData.outcome})`,
        lastValueVisible: true,
        priceLineVisible: true,
      });
      futureSpreadSeriesRef.current = futureSeries;

      // Seed animation starting from Date T (seamless bridge)
      const animatedPoints: { time: Time; value: number }[] = [
        {
          time: lastHistorical.date as Time,
          value: lastHistorical.z_score,
        },
      ];
      futureSeries.setData(animatedPoints);

      let stepIndex = 0;
      // Progressive day-by-day animation loop (40ms per bar)
      animTimerRef.current = setInterval(() => {
        if (stepIndex < path.length) {
          const pt = path[stepIndex];
          animatedPoints.push({
            time: pt.date as Time,
            value: pt.z_score,
          });
          futureSeries.setData([...animatedPoints]);
          stepIndex++;
        } else {
          // Animation Complete
          if (animTimerRef.current) {
            clearInterval(animTimerRef.current);
            animTimerRef.current = null;
          }
          setIsAnimating(false);

          // Task 5: Place Visual Pin/Marker at exact exit date displaying outcome text
          attachOutcomeMarkers(outcomeData, futureSeries, lastHistorical.z_score);

          // Constraint 3: Scale Y-axis and horizontally fit newly revealed trajectory
          chart.timeScale().fitContent();
        }
      }, 40);
    } else {
      // Normalized Prices Animation
      const baseA = historicalBars[0]?.price_a || 1;
      const baseB = historicalBars[0]?.price_b || 1;

      if (futureSeriesARef.current) {
        try { chart.removeSeries(futureSeriesARef.current); } catch {}
      }
      if (futureSeriesBRef.current) {
        try { chart.removeSeries(futureSeriesBRef.current); } catch {}
      }

      const futureA = chart.addSeries(LineSeries, {
        color: outcomeStrokeColor,
        lineWidth: 3,
        priceScaleId: "right",
        title: `${tickerA} (Future)`,
      });
      const futureB = chart.addSeries(LineSeries, {
        color: "#F472B6", // Pink-400
        lineWidth: 2,
        lineStyle: LineStyle.Dashed,
        priceScaleId: "right",
        title: `${tickerB} (Future)`,
      });
      futureSeriesARef.current = futureA;
      futureSeriesBRef.current = futureB;

      const animA = [{
        time: lastHistorical.date as Time,
        value: Number(((lastHistorical.price_a / baseA) * 100).toFixed(2)),
      }];
      const animB = [{
        time: lastHistorical.date as Time,
        value: Number(((lastHistorical.price_b / baseB) * 100).toFixed(2)),
      }];

      futureA.setData(animA);
      futureB.setData(animB);

      let stepIndex = 0;
      animTimerRef.current = setInterval(() => {
        if (stepIndex < path.length) {
          const pt = path[stepIndex];
          animA.push({
            time: pt.date as Time,
            value: Number(((pt.price_a / baseA) * 100).toFixed(2)),
          });
          animB.push({
            time: pt.date as Time,
            value: Number(((pt.price_b / baseB) * 100).toFixed(2)),
          });
          futureA.setData([...animA]);
          futureB.setData([...animB]);
          stepIndex++;
        } else {
          if (animTimerRef.current) {
            clearInterval(animTimerRef.current);
            animTimerRef.current = null;
          }
          setIsAnimating(false);
          attachOutcomeMarkers(outcomeData, futureA, lastHistorical.z_score);
          chart.timeScale().fitContent();
        }
      }, 40);
    }
  };

  // Task 5: Attach visual pin/marker on the chart at the exact exit date
  const attachOutcomeMarkers = (
    outcomeData: ForwardEvaluationResult,
    targetSeries: ISeriesApi<any>,
    entryZ: number
  ) => {
    if (!targetSeries) return;

    const isWin = outcomeData.outcome === "WIN";
    const isLoss = outcomeData.outcome === "LOSS";
    const exitDateStr = outcomeData.exit_date;

    const markersList: any[] = [
      // 1. Entry Marker at Date T
      {
        time: currentDate as Time,
        position: entryZ >= 0 ? "aboveBar" : "belowBar",
        color: "#06B6D4",
        shape: entryZ >= 0 ? "arrowDown" : "arrowUp",
        text: `ENTRY T (${entryZ >= 0 ? "+" : ""}${entryZ.toFixed(2)}σ)`,
        size: 1,
      },
    ];

    // 2. Exit Marker at exact exit date displaying outcome text
    if (exitDateStr) {
      const pnlText = `${outcomeData.realized_pnl_pct >= 0 ? "+" : ""}${outcomeData.realized_pnl_pct.toFixed(2)}%`;
      const outcomeLabel = isWin
        ? `WIN: TARGET HIT (${outcomeData.exit_days_held}d, PnL: ${pnlText})`
        : isLoss
        ? `LOSS: STOP BREACHED (${outcomeData.exit_days_held}d, PnL: ${pnlText})`
        : `NEUTRAL: EXPIRED (${outcomeData.exit_days_held}d)`;

      markersList.push({
        time: exitDateStr as Time,
        position: isWin ? "belowBar" : "aboveBar",
        color: isWin ? "#10B981" : isLoss ? "#EF4444" : "#F59E0B",
        shape: isWin ? "arrowUp" : "arrowDown",
        text: outcomeLabel,
        size: 2,
      });
    }

    try {
      if (markersPluginRef.current) {
        markersPluginRef.current.setMarkers(markersList);
      } else {
        markersPluginRef.current = createSeriesMarkers(targetSeries, markersList);
      }
    } catch (e) {
      console.warn("Could not attach markers via v5 plugin:", e);
    }
  };

  // Reset simulation to re-cloak the future mask
  const handleResetReplay = () => {
    if (animTimerRef.current) {
      clearInterval(animTimerRef.current);
      animTimerRef.current = null;
    }
    const chart = chartRef.current;
    if (chart) {
      if (futureSpreadSeriesRef.current) {
        try { chart.removeSeries(futureSpreadSeriesRef.current); } catch {}
        futureSpreadSeriesRef.current = null;
      }
      if (futureSeriesARef.current) {
        try { chart.removeSeries(futureSeriesARef.current); } catch {}
        futureSeriesARef.current = null;
      }
      if (futureSeriesBRef.current) {
        try { chart.removeSeries(futureSeriesBRef.current); } catch {}
        futureSeriesBRef.current = null;
      }
    }
    setRevealed(false);
    setForwardOutcome(null);
    setIsAnimating(false);
    fetchHistoricalData();
  };

  return (
    <div
      className={cn(
        "bg-gray-900 border border-gray-800 rounded-2xl shadow-2xl overflow-hidden flex flex-col font-sans",
        className
      )}
    >
      {/* Viewport Top Header & Controls */}
      <div className="p-4 bg-gray-950/80 border-b border-gray-800/80 flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-xl bg-cyan-950/80 border border-cyan-800/60 flex items-center justify-center text-cyan-400">
            <Activity className="w-5 h-5" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h3 className="text-base font-bold font-mono text-white tracking-wide">
                {pairName}
              </h3>
              <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-cyan-950/80 text-cyan-400 border border-cyan-800/60">
                Date T: {currentDate}
              </span>
              {setup?.hedge_ratio && (
                <span className="text-[10px] font-mono text-gray-400">
                  β = {setup.hedge_ratio.toFixed(4)}
                </span>
              )}
            </div>
            <div className="text-xs text-gray-400 font-mono flex items-center gap-2 mt-0.5">
              <span>90-Day Rolling Window</span>
              <span>&bull;</span>
              <span>Point-in-Time Trajectory</span>
            </div>
          </div>
        </div>

        {/* Action Controls & View Mode Toggles */}
        <div className="flex items-center gap-2.5">
          {/* View Mode Toggle Buttons */}
          <div className="flex items-center bg-gray-900 border border-gray-800 rounded-lg p-0.5">
            <button
              onClick={() => setViewMode("spread_z")}
              className={cn(
                "px-2.5 py-1 text-xs font-mono font-medium rounded-md transition",
                viewMode === "spread_z"
                  ? "bg-cyan-500/20 text-cyan-300 border border-cyan-500/40 shadow-sm"
                  : "text-gray-400 hover:text-gray-200"
              )}
            >
              Spread Z-Score
            </button>
            <button
              onClick={() => setViewMode("normalized_prices")}
              className={cn(
                "px-2.5 py-1 text-xs font-mono font-medium rounded-md transition",
                viewMode === "normalized_prices"
                  ? "bg-cyan-500/20 text-cyan-300 border border-cyan-500/40 shadow-sm"
                  : "text-gray-400 hover:text-gray-200"
              )}
            >
              Prices (A vs B)
            </button>
          </div>

          {/* Re-cloak / Replay Reset Button */}
          {revealed && (
            <button
              onClick={handleResetReplay}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-gray-800 hover:bg-gray-700 text-xs font-mono text-gray-300 border border-gray-700 transition"
              title="Re-cloak future mask to test again"
            >
              <RotateCcw className="w-3.5 h-3.5" />
              <span>Reset Mask</span>
            </button>
          )}

          {/* Dismiss / Close button */}
          {onClose && (
            <button
              onClick={onClose}
              className="p-1.5 rounded-lg text-gray-400 hover:text-white hover:bg-gray-800 transition"
            >
              <X className="w-5 h-5" />
            </button>
          )}
        </div>
      </div>

      {/* Outcome Scorecard HUD Strip (Shown upon reveal) */}
      {revealed && forwardOutcome && (
        <div
          className={cn(
            "px-4 py-2.5 border-b font-mono text-xs flex flex-wrap items-center justify-between gap-3 animate-in fade-in duration-500",
            forwardOutcome.outcome === "WIN"
              ? "bg-emerald-950/40 border-emerald-800/60 text-emerald-200"
              : forwardOutcome.outcome === "LOSS"
              ? "bg-rose-950/40 border-rose-800/60 text-rose-200"
              : "bg-amber-950/40 border-amber-800/60 text-amber-200"
          )}
        >
          <div className="flex items-center gap-2.5">
            <span
              className={cn(
                "px-2 py-0.5 rounded font-extrabold tracking-wider border text-xs shadow-md",
                forwardOutcome.outcome === "WIN"
                  ? "bg-emerald-500/20 border-emerald-500/50 text-emerald-300"
                  : forwardOutcome.outcome === "LOSS"
                  ? "bg-rose-500/20 border-rose-500/50 text-rose-300"
                  : "bg-amber-500/20 border-amber-500/50 text-amber-300"
              )}
            >
              {forwardOutcome.outcome === "WIN" ? "✓ WIN (TARGET HIT)" : forwardOutcome.outcome === "LOSS" ? "✗ STOP LOSS HIT" : "NEUTRAL EXPIRED"}
            </span>
            <span className="font-semibold text-white">
              {forwardOutcome.status_reason}
            </span>
          </div>

          <div className="flex items-center gap-4 text-[11px]">
            <div>
              <span className="text-gray-400">Exit Date: </span>
              <span className="font-bold text-white">{forwardOutcome.exit_date || "Horizon End"}</span>
            </div>
            <div>
              <span className="text-gray-400">Duration: </span>
              <span className="font-bold text-white">{forwardOutcome.exit_days_held} trading days</span>
            </div>
            <div>
              <span className="text-gray-400">Simulated PnL: </span>
              <span
                className={cn(
                  "font-bold text-sm",
                  forwardOutcome.realized_pnl_pct >= 0 ? "text-emerald-400" : "text-rose-400"
                )}
              >
                {forwardOutcome.realized_pnl_pct >= 0 ? "+" : ""}
                {forwardOutcome.realized_pnl_pct.toFixed(2)}%
              </span>
            </div>
          </div>
        </div>
      )}

      {/* Main Chart Canvas Area with Dual-Zone Frosted Glass Mask */}
      <div className="relative w-full overflow-hidden bg-[#090d16]" style={{ height }}>
        {/* Loading Overlay */}
        {isLoadingHistory && (
          <div className="absolute inset-0 z-30 bg-gray-950/80 backdrop-blur-sm flex flex-col items-center justify-center gap-3">
            <div className="w-8 h-8 border-2 border-cyan-500 border-t-transparent rounded-full animate-spin" />
            <span className="text-xs font-mono text-cyan-300">
              Generating Point-in-Time Chart Series...
            </span>
          </div>
        )}

        {/* Error Overlay */}
        {error && (
          <div className="absolute inset-0 z-30 bg-gray-950/90 flex flex-col items-center justify-center gap-2 p-6 text-center">
            <AlertCircle className="w-8 h-8 text-rose-400 mb-1" />
            <h4 className="text-sm font-bold text-white font-mono">Chart Rendering Error</h4>
            <p className="text-xs text-rose-300 font-mono max-w-md">{error}</p>
            <button
              onClick={fetchHistoricalData}
              className="mt-3 px-3 py-1.5 rounded-lg bg-gray-800 hover:bg-gray-700 text-xs font-mono text-gray-200 border border-gray-700"
            >
              Retry
            </button>
          </div>
        )}

        {/* TradingView Canvas Mount Point */}
        <div ref={chartContainerRef} className="w-full h-full" />

        {/* Task 2 & Constraint 2: Dual-Zone Frosted Glass Future Mask */}
        {/* Rendered on the right 38% of the viewport completely obscuring future outcomes */}
        <div
          className={cn(
            "absolute top-0 right-0 bottom-0 z-20 pointer-events-auto",
            "w-[38%] min-w-[240px] transition-all duration-700 ease-in-out",
            "flex flex-col items-center justify-center p-6 text-center select-none",
            revealed
              ? "opacity-0 pointer-events-none translate-x-8"
              : "backdrop-blur-xl bg-gray-950/90 border-l-2 border-dashed border-cyan-500/50 shadow-2xl"
          )}
        >
          <div className="w-12 h-12 rounded-2xl bg-cyan-950/80 border border-cyan-500/40 flex items-center justify-center text-cyan-400 shadow-[0_0_20px_rgba(6,182,212,0.3)] mb-3 animate-pulse">
            <Lock className="w-6 h-6" />
          </div>

          <div className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[10px] font-mono font-semibold bg-cyan-950/60 text-cyan-300 border border-cyan-800/80 mb-2">
            <ShieldCheck className="w-3.5 h-3.5 text-cyan-400" />
            TEMPORAL BARRIER (t &gt; T)
          </div>

          <h4 className="text-sm font-bold font-mono text-white mb-1">
            Future Horizon Locked
          </h4>
          <p className="text-[11px] font-mono text-gray-400 max-w-[220px] mb-5 leading-relaxed">
            Strict zero-lookahead mode active. Peek forward 30 trading days to evaluate mean-reversion.
          </p>

          {/* Task 2 & 3: [ 👁️ Reveal Outcome ] Glowing Button */}
          <button
            onClick={handleReveal}
            disabled={isRevealing || isLoadingHistory}
            className="group relative px-5 py-2.5 rounded-xl bg-gradient-to-r from-cyan-500 to-blue-600 hover:from-cyan-400 hover:to-blue-500 text-white font-mono font-bold text-xs shadow-[0_0_25px_rgba(6,182,212,0.4)] hover:shadow-[0_0_35px_rgba(6,182,212,0.65)] transition-all duration-300 transform hover:-translate-y-0.5 active:translate-y-0 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <span className="flex items-center gap-2">
              {isRevealing ? (
                <>
                  <div className="w-3.5 h-3.5 border-2 border-white border-t-transparent rounded-full animate-spin" />
                  <span>Simulating Future...</span>
                </>
              ) : (
                <>
                  <Eye className="w-4 h-4 group-hover:scale-110 transition-transform" />
                  <span>[ 👁️ Reveal Outcome ]</span>
                </>
              )}
            </span>
          </button>
        </div>

        {/* Live Hover Crosshair Tooltip HUD */}
        {hoverData && (
          <div className="absolute top-3 left-3 z-10 bg-gray-950/85 backdrop-blur-md border border-gray-800 rounded-xl p-2.5 font-mono text-xs shadow-xl pointer-events-none">
            <div className="text-[10px] text-gray-500 uppercase tracking-wider mb-1">
              Date: <span className="text-white font-bold">{hoverData.date}</span>
            </div>
            {viewMode === "spread_z" && hoverData.zScore !== undefined && (
              <div className="flex items-center gap-3">
                <div>
                  <span className="text-gray-400">Z-Score: </span>
                  <span
                    className={cn(
                      "font-bold",
                      hoverData.zScore >= 0 ? "text-rose-400" : "text-emerald-400"
                    )}
                  >
                    {hoverData.zScore >= 0 ? "+" : ""}
                    {hoverData.zScore.toFixed(2)}σ
                  </span>
                </div>
                {hoverData.spread !== undefined && (
                  <div>
                    <span className="text-gray-400">Spread: </span>
                    <span className="text-gray-200 font-bold">
                      {hoverData.spread.toFixed(2)}
                    </span>
                  </div>
                )}
              </div>
            )}
            {viewMode === "normalized_prices" && (
              <div className="flex items-center gap-3">
                <div>
                  <span className="text-cyan-400">{tickerA}: </span>
                  <span className="text-white font-bold">${hoverData.priceA?.toFixed(2)}</span>
                </div>
                <div>
                  <span className="text-purple-400">{tickerB}: </span>
                  <span className="text-white font-bold">${hoverData.priceB?.toFixed(2)}</span>
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Bottom Chart Footer Legend */}
      <div className="px-4 py-2 bg-gray-950/90 border-t border-gray-800/80 flex flex-wrap items-center justify-between text-[11px] font-mono text-gray-400">
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 rounded-full bg-cyan-400" />
            <span>Historical (t &le; T)</span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 rounded-full bg-emerald-400" />
            <span>Target Mean (0.0σ)</span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 rounded-full bg-amber-400" />
            <span>Dislocation Entry (&plusmn;2.0σ)</span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 rounded-full bg-rose-400" />
            <span>Stop Loss Gate (&plusmn;3.5σ)</span>
          </div>
        </div>

        <div className="flex items-center gap-2 text-gray-500">
          <span>Drag canvas to pan &bull; Scroll to zoom</span>
        </div>
      </div>
    </div>
  );
};

export default ReplayPairChart;
