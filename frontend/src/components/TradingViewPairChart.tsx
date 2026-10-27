import React, { useEffect, useRef, useState, useMemo } from "react";
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
} from "lightweight-charts";
import {
  RotateCcw,
  ZoomIn,
  ZoomOut,
  MoveVertical,
  MoveHorizontal,
  Hand,
} from "lucide-react";
import { cn } from "@/lib/utils";

export type ChartDisplayMode = "price" | "spread" | "returns";
export type RangePreset = "60D" | "90D" | "1Y" | "3Y" | "5Y" | "ALL";

export interface PairBarData {
  date: string;
  price_a: number;
  price_b: number;
  price_b_overlay?: number;
  norm_a: number;
  norm_b: number;
  return_pct_a?: number;
  return_pct_b?: number;
  spread: number;
  spread_mean: number;
  spread_std: number;
  z_score: number;
}

interface TradingViewPairChartProps {
  tickerA: string;
  tickerB: string;
  hedgeRatio: number;
  bars: PairBarData[];
  defaultRange?: RangePreset;
  onRangeChange?: (range: RangePreset) => void;
  metadata?: Record<string, any>;
}

export default function TradingViewPairChart({
  tickerA,
  tickerB,
  hedgeRatio = 1,
  bars,
  defaultRange = "1Y",
  onRangeChange,
  metadata,
}: TradingViewPairChartProps) {
  const chartContainerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);

  // Default to "price": Stock A and Stock B overlapping on unified price scale
  const [mode, setMode] = useState<ChartDisplayMode>("price");
  const [range, setRange] = useState<RangePreset>(defaultRange);
  const [hoverData, setHoverData] = useState<{
    time?: string;
    priceA?: number;
    priceB?: number;
    spread?: number;
    returnA?: number;
    returnB?: number;
  } | null>(null);

  const safeHedgeRatio = useMemo(
    () => (Number.isFinite(hedgeRatio) && hedgeRatio > 0 ? hedgeRatio : 1),
    [hedgeRatio]
  );

  // Defensive chronological sort and O(1) date lookup map
  const sortedBars: PairBarData[] = useMemo(
    () => [...(bars || [])].sort((a: PairBarData, b: PairBarData) => a.date.localeCompare(b.date)),
    [bars]
  );

  const dateMap = useMemo(
    () => new Map<string, PairBarData>(sortedBars.map((b: PairBarData) => [b.date, b])),
    [sortedBars]
  );

  // Initialize or update the TradingView canvas chart
  useEffect(() => {
    if (!chartContainerRef.current || !sortedBars.length) return;

    // Clean up previous instance
    if (chartRef.current) {
      chartRef.current.remove();
      chartRef.current = null;
    }

    const container = chartContainerRef.current;

    // TradingView Official Canvas Chart Config
    // Note: We deliberately use a single rightPriceScale and set leftPriceScale to false
    // so both stocks stretch, compress, and scale TOGETHER on the exact same axis.
    const chart = createChart(container, {
      width: container.clientWidth,
      height: 480,
      layout: {
        background: { type: ColorType.Solid, color: "#0b0e17" },
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
          color: "#64748b",
          width: 1,
          style: LineStyle.Dashed,
          labelBackgroundColor: "#1e293b",
        },
        horzLine: {
          color: "#64748b",
          width: 1,
          style: LineStyle.Dashed,
          labelBackgroundColor: "#1e293b",
        },
      },
      // Unified Right Price Scale for BOTH Stocks (synchronous stretch and zoom)
      rightPriceScale: {
        visible: true,
        borderColor: "#334155",
        scaleMargins: { top: 0.08, bottom: 0.08 },
        autoScale: true,
      },
      // Left Price Scale DISABLED so both stocks share the EXACT same unified scale
      leftPriceScale: {
        visible: false,
      },
      timeScale: {
        borderColor: "#334155",
        timeVisible: true,
        secondsVisible: false,
        rightOffset: 6,
        barSpacing: 8,
        minBarSpacing: 3,
      },
      handleScale: {
        axisPressedMouseMove: {
          time: true, // Drag horizontal time scale to stretch/compress both stocks horizontally (↔)
          price: true, // Drag vertical price scale to stretch/compress vertically (↕)
        },
        mouseWheel: true, // Scroll wheel zooms both stocks in/out together
        pinch: true,
      },
      handleScroll: {
        mouseWheel: false,
        pressedMouseMove: true, // Drag canvas to pan both stocks together
        horzTouchDrag: true,
        vertTouchDrag: true,
      },
    });

    chartRef.current = chart;

    // Series references
    let seriesA: ISeriesApi<"Line"> | null = null;
    let seriesB: ISeriesApi<"Line"> | null = null;
    let seriesSpread: ISeriesApi<"Area"> | null = null;

    const firstA = sortedBars[0]?.price_a || 1;
    const firstB = sortedBars[0]?.price_b || 1;

    if (mode === "price") {
      // Stock A in Vivid Blue (#2962FF) on UNIFIED Right Price Scale (Real Raw Market Price)
      seriesA = chart.addSeries(LineSeries, {
        color: "#2962FF",
        lineWidth: 2,
        priceScaleId: "right",
        title: `${tickerA} ($)`,
        priceFormat: { type: "price", precision: 2, minMove: 0.01 },
      });
      seriesA.setData(
        sortedBars.map((b: PairBarData) => ({
          time: b.date as Time,
          value: b.price_a,
        }))
      );

      // Stock B in Vivid Red (#FF5252) on the EXACT SAME UNIFIED Right Price Scale (Real Raw Market Price)
      // Both stocks share the identical axis so dragging/zooming scales them TOGETHER synchronously!
      seriesB = chart.addSeries(LineSeries, {
        color: "#FF5252",
        lineWidth: 2,
        priceScaleId: "right",
        title: `${tickerB} ($)`,
        priceFormat: { type: "price", precision: 2, minMove: 0.01 },
      });
      seriesB.setData(
        sortedBars.map((b: PairBarData) => ({
          time: b.date as Time,
          value: b.price_b,
        }))
      );
    } else if (mode === "returns") {
      // % Returns / Trend Mode: Both assets plotted as percentage return from 0.0% baseline
      seriesA = chart.addSeries(LineSeries, {
        color: "#2962FF",
        lineWidth: 2,
        priceScaleId: "right",
        title: `${tickerA} (% Return)`,
        priceFormat: {
          type: "custom",
          formatter: (v: number) => `${v >= 0 ? "+" : ""}${v.toFixed(1)}%`,
        },
      });
      seriesA.setData(
        sortedBars.map((b: PairBarData) => ({
          time: b.date as Time,
          value: b.return_pct_a ?? Number((((b.price_a - firstA) / firstA) * 100).toFixed(2)),
        }))
      );

      seriesB = chart.addSeries(LineSeries, {
        color: "#FF5252",
        lineWidth: 2,
        priceScaleId: "right",
        title: `${tickerB} (% Return)`,
        priceFormat: {
          type: "custom",
          formatter: (v: number) => `${v >= 0 ? "+" : ""}${v.toFixed(1)}%`,
        },
      });
      seriesB.setData(
        sortedBars.map((b: PairBarData) => ({
          time: b.date as Time,
          value: b.return_pct_b ?? Number((((b.price_b - firstB) / firstB) * 100).toFixed(2)),
        }))
      );

      // Baseline reference line at 0.0%
      seriesA.createPriceLine({
        price: 0,
        color: "#64748b",
        lineWidth: 1,
        lineStyle: LineStyle.Dashed,
        axisLabelVisible: true,
        title: "0.0% Baseline",
      });
    } else {
      // Cointegrated Spread Area Series (Mode === "spread")
      seriesSpread = chart.addSeries(AreaSeries, {
        lineColor: "#f59e0b",
        topColor: "rgba(245, 158, 11, 0.4)",
        bottomColor: "rgba(245, 158, 11, 0.02)",
        lineWidth: 2,
        priceScaleId: "right",
        title: "Cointegrated Spread ($)",
        priceFormat: { type: "price", precision: 2, minMove: 0.01 },
      });
      seriesSpread.setData(
        sortedBars.map((b: PairBarData) => ({
          time: b.date as Time,
          value: b.spread,
        }))
      );

      // Add Mean Spread reference line
      const meanVal = sortedBars[sortedBars.length - 1]?.spread_mean ?? sortedBars[0]?.spread ?? 0;
      seriesSpread.createPriceLine({
        price: meanVal,
        color: "#cbd5e1",
        lineWidth: 1,
        lineStyle: LineStyle.Dashed,
        axisLabelVisible: true,
        title: `Mean Spread ($${meanVal.toFixed(2)})`,
      });
    }

    // Crosshair move listener with O(1) map lookup and BusinessDay normalization
    chart.subscribeCrosshairMove((param) => {
      if (!param.time || !param.point) {
        setHoverData(null);
        return;
      }
      let timeStr: string;
      if (typeof param.time === "object" && param.time !== null) {
        const t = param.time as { year: number; month: number; day: number };
        timeStr = `${t.year}-${String(t.month).padStart(2, "0")}-${String(t.day).padStart(2, "0")}`;
      } else {
        timeStr = String(param.time);
      }
      const match = dateMap.get(timeStr);
      if (match) {
        setHoverData({
          time: match.date,
          priceA: match.price_a,
          priceB: match.price_b,
          spread: match.spread,
          returnA: match.return_pct_a ?? Number((((match.price_a - firstA) / firstA) * 100).toFixed(2)),
          returnB: match.return_pct_b ?? Number((((match.price_b - firstB) / firstB) * 100).toFixed(2)),
        });
      } else {
        setHoverData(null);
      }
    });

    // Set initial visible time range: Default is LAST 60 DAYS (as requested)
    if (sortedBars.length > 1) {
      let startIndex = Math.max(0, sortedBars.length - 60);
      if (range === "90D") startIndex = Math.max(0, sortedBars.length - 90);
      else if (range === "1Y") startIndex = Math.max(0, sortedBars.length - 252);
      else if (range === "3Y") startIndex = Math.max(0, sortedBars.length - 756);
      else if (range === "5Y" || range === "ALL") startIndex = 0;

      chart.timeScale().setVisibleRange({
        from: sortedBars[startIndex].date as Time,
        to: sortedBars[sortedBars.length - 1].date as Time,
      });
    } else if (sortedBars.length === 1) {
      chart.timeScale().fitContent();
    }

    // Responsive resize observer
    const resizeObserver = new ResizeObserver((entries) => {
      for (const entry of entries) {
        if (entry.contentRect.width > 0 && chartRef.current) {
          chartRef.current.applyOptions({ width: entry.contentRect.width });
        }
      }
    });
    resizeObserver.observe(container);

    return () => {
      resizeObserver.disconnect();
      if (chartRef.current) {
        chartRef.current.remove();
        chartRef.current = null;
      }
    };
  }, [sortedBars, dateMap, mode, tickerA, tickerB, safeHedgeRatio]);

  // Handle Range Preset Switch
  const handleRangePreset = (newRange: RangePreset) => {
    setRange(newRange);
    onRangeChange?.(newRange);
    if (!chartRef.current || sortedBars.length <= 1) return;

    let startIndex = Math.max(0, sortedBars.length - 60);
    if (newRange === "90D") startIndex = Math.max(0, sortedBars.length - 90);
    else if (newRange === "1Y") startIndex = Math.max(0, sortedBars.length - 252);
    else if (newRange === "3Y") startIndex = Math.max(0, sortedBars.length - 756);
    else if (newRange === "5Y" || newRange === "ALL") startIndex = 0;

    chartRef.current.timeScale().setVisibleRange({
      from: sortedBars[startIndex].date as Time,
      to: sortedBars[sortedBars.length - 1].date as Time,
    });
  };

  // Zoom In on visible bars (both stocks together)
  const handleZoomIn = () => {
    if (!chartRef.current) return;
    const timeScale = chartRef.current.timeScale();
    const logicalRange = timeScale.getVisibleLogicalRange();
    if (!logicalRange) return;
    const count = logicalRange.to - logicalRange.from;
    if (count <= 8) return;
    const step = Math.max(2, Math.floor(count * 0.15));
    timeScale.setVisibleLogicalRange({
      from: logicalRange.from + step,
      to: logicalRange.to - step,
    });
  };

  // Zoom Out on visible bars (both stocks together)
  const handleZoomOut = () => {
    if (!chartRef.current) return;
    const timeScale = chartRef.current.timeScale();
    const logicalRange = timeScale.getVisibleLogicalRange();
    if (!logicalRange) return;
    const count = logicalRange.to - logicalRange.from;
    const step = Math.max(2, Math.floor(count * 0.15));
    timeScale.setVisibleLogicalRange({
      from: logicalRange.from - step,
      to: logicalRange.to + step,
    });
  };

  // Reset Scale to Default (both stocks and axes auto-scale together)
  const handleResetScale = () => {
    if (!chartRef.current || !sortedBars.length) return;
    chartRef.current.timeScale().resetTimeScale();
    try {
      chartRef.current.priceScale("right").applyOptions({ autoScale: true });
      chartRef.current.priceScale("left").applyOptions({ autoScale: true });
    } catch {
      // ignore
    }

    if (sortedBars.length > 1) {
      let startIndex = Math.max(0, sortedBars.length - 60);
      if (range === "90D") startIndex = Math.max(0, sortedBars.length - 90);
      else if (range === "1Y") startIndex = Math.max(0, sortedBars.length - 252);
      else if (range === "3Y") startIndex = Math.max(0, sortedBars.length - 756);
      else if (range === "5Y" || range === "ALL") startIndex = 0;

      chartRef.current.timeScale().setVisibleRange({
        from: sortedBars[startIndex].date as Time,
        to: sortedBars[sortedBars.length - 1].date as Time,
      });
    } else {
      chartRef.current.timeScale().fitContent();
    }
  };

  const latestBar = sortedBars[sortedBars.length - 1] || {};

  return (
    <div className="rounded-xl border border-line bg-[#0b0e17] overflow-hidden shadow-2xl">
      {/* TradingView Top Toolbar */}
      <div className="p-3 bg-[#121824] border-b border-line flex flex-wrap items-center justify-between gap-3 text-xs">
        {/* Left: Dynamic Cursor Values & Legend */}
        <div className="flex flex-wrap items-center gap-4">
          {/* Stock A Legend */}
          <div className="flex items-center gap-2">
            <span className="w-3 h-3 rounded-full bg-[#2962FF] shadow-sm shadow-blue-500/50" />
            <span className="font-mono font-bold text-blue-400">{tickerA} (Stock A)</span>
            <span className="text-white font-mono font-bold">
              ${(hoverData?.priceA ?? latestBar.price_a ?? 0).toFixed(2)}
            </span>
            {hoverData?.returnA !== undefined ? (
              <span className={cn("text-[10px] font-mono", hoverData.returnA >= 0 ? "text-emerald-400" : "text-rose-400")}>
                ({hoverData.returnA >= 0 ? "+" : ""}{hoverData.returnA.toFixed(1)}%)
              </span>
            ) : metadata?.return_5y_a !== undefined ? (
              <span className={cn("text-[10px] font-mono", metadata.return_5y_a >= 0 ? "text-emerald-400" : "text-rose-400")}>
                (5Y: {metadata.return_5y_a >= 0 ? "+" : ""}{metadata.return_5y_a}%)
              </span>
            ) : null}
          </div>

          {/* Stock B Legend */}
          <div className="flex items-center gap-2">
            <span className="w-3 h-3 rounded-full bg-[#FF5252] shadow-sm shadow-rose-500/50" />
            <span className="font-mono font-bold text-rose-400">{tickerB} (Stock B)</span>
            <span className="text-white font-mono font-bold">
              ${(hoverData?.priceB ?? latestBar.price_b ?? 0).toFixed(2)}
            </span>
            {hoverData?.returnB !== undefined ? (
              <span className={cn("text-[10px] font-mono", hoverData.returnB >= 0 ? "text-emerald-400" : "text-rose-400")}>
                ({hoverData.returnB >= 0 ? "+" : ""}{hoverData.returnB.toFixed(1)}%)
              </span>
            ) : metadata?.return_5y_b !== undefined ? (
              <span className={cn("text-[10px] font-mono", metadata.return_5y_b >= 0 ? "text-emerald-400" : "text-rose-400")}>
                (5Y: {metadata.return_5y_b >= 0 ? "+" : ""}{metadata.return_5y_b}%)
              </span>
            ) : null}
          </div>

          {/* Spread Legend */}
          <div className="hidden sm:flex items-center gap-3 pl-3 border-l border-line text-gray-400 font-mono text-[11px]">
            <span>
              Spread:{" "}
              <strong className="text-amber-300">
                ${(hoverData?.spread ?? latestBar.spread ?? 0).toFixed(2)}
              </strong>
            </span>
            {hoverData?.time && (
              <span className="text-gray-500">Date: {hoverData.time}</span>
            )}
          </div>

          {mode === "price" && (
            <span className="hidden md:inline-flex items-center gap-1 text-[10px] font-mono text-gray-300 bg-surface-2 border border-line px-2 py-0.5 rounded">
              <span>Real Raw Prices (Single Unified Axis)</span>
            </span>
          )}
          {mode === "spread" && (
            <span className="hidden md:inline-flex items-center gap-1 text-[10px] font-mono text-gray-300 bg-surface-2 border border-line px-2 py-0.5 rounded">
              <span>Cointegrated Spread &amp; Mean</span>
            </span>
          )}
          {mode === "returns" && (
            <span className="hidden md:inline-flex items-center gap-1 text-[10px] font-mono text-gray-300 bg-surface-2 border border-line px-2 py-0.5 rounded">
              <span>% Return Comparison</span>
            </span>
          )}
        </div>

        {/* Right: Unified Mode & Scale Controls */}
        <div className="flex flex-wrap items-center gap-2.5">
          {/* Mode Switcher */}
          <div className="inline-flex rounded-lg border border-line bg-surface-2 p-0.5 text-[11px]">
            <button
              onClick={() => setMode("price")}
              className={cn(
                "px-3 py-1 rounded font-medium transition-colors",
                mode === "price"
                  ? "bg-brand text-bg shadow-sm"
                  : "text-gray-400 hover:text-white"
              )}
            >
              Price ($)
            </button>
            <button
              onClick={() => setMode("spread")}
              className={cn(
                "px-3 py-1 rounded font-medium transition-colors",
                mode === "spread"
                  ? "bg-brand text-bg shadow-sm"
                  : "text-gray-400 hover:text-white"
              )}
            >
              Spread ($)
            </button>
            <button
              onClick={() => setMode("returns")}
              className={cn(
                "px-3 py-1 rounded font-medium transition-colors",
                mode === "returns"
                  ? "bg-brand text-bg shadow-sm"
                  : "text-gray-400 hover:text-white"
              )}
            >
              % Returns
            </button>
          </div>

          {/* Range Presets (TradingView Style) */}
          <div className="inline-flex rounded-lg border border-line bg-[#0c1017] p-0.5 text-[11px] font-mono">
            {(["60D", "90D", "1Y", "3Y", "5Y", "ALL"] as RangePreset[]).map((r) => (
              <button
                key={r}
                onClick={() => handleRangePreset(r)}
                className={cn(
                  "px-2.5 py-1 rounded font-semibold transition-colors",
                  range === r
                    ? "bg-brand text-bg shadow-sm"
                    : "text-gray-400 hover:text-white"
                )}
              >
                {r}
              </button>
            ))}
          </div>

          {/* Unified Zoom In / Zoom Out / Reset Buttons */}
          <div className="inline-flex rounded-lg border border-line bg-[#0c1017] p-0.5 text-[11px]">
            <button
              onClick={handleZoomIn}
              title="Zoom In (Both Stocks Together)"
              className="p-1.5 rounded text-gray-400 hover:text-white hover:bg-surface-2 transition-colors"
            >
              <ZoomIn className="w-3.5 h-3.5" />
            </button>
            <button
              onClick={handleZoomOut}
              title="Zoom Out (Both Stocks Together)"
              className="p-1.5 rounded text-gray-400 hover:text-white hover:bg-surface-2 transition-colors"
            >
              <ZoomOut className="w-3.5 h-3.5" />
            </button>
            <button
              onClick={handleResetScale}
              title="Reset Auto-Scale (Both Stocks Together)"
              className="p-1.5 rounded text-gray-400 hover:text-white hover:bg-surface-2 transition-colors"
            >
              <RotateCcw className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>
      </div>

      {/* TradingView Native Canvas Chart */}
      <div className="relative">
        <div ref={chartContainerRef} className="w-full h-[480px] cursor-crosshair" />

        {/* Interaction Hint Bar */}
        <div className="px-4 py-2 bg-surface-2 border-t border-line flex flex-wrap items-center justify-between text-[11px] text-gray-400 font-mono">
          <div className="flex flex-wrap items-center gap-4">
            <span className="flex items-center gap-1.5 text-gray-300">
              <MoveVertical className="w-3.5 h-3.5 text-gray-400" />
              <span>Drag Right Price Scale (↕) &rarr; Stretches BOTH Stocks Together</span>
            </span>
            <span className="flex items-center gap-1.5 text-gray-300">
              <MoveHorizontal className="w-3.5 h-3.5 text-gray-400" />
              <span>Drag Bottom Time Scale (↔) &rarr; Stretches Horizontally Together</span>
            </span>
            <span className="flex items-center gap-1.5 text-gray-300">
              <Hand className="w-3.5 h-3.5 text-gray-400" />
              <span>Drag Canvas &rarr; Pans Both Stocks Together</span>
            </span>
          </div>

          <div className="flex items-center gap-3">
            <span>Scroll Wheel Zooms Both &middot; Reset to Auto-Fit</span>
            <span className="px-2 py-0.5 rounded bg-surface border border-line text-gray-300 font-semibold text-[10px]">
              Unified Scale
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}
