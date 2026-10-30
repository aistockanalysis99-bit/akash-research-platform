import React, { useState, useMemo } from "react";
import { AlignedEquityPoint } from "../../lib/simulatorTypes";

interface ComparisonEquityChartProps {
  data: AlignedEquityPoint[];
  height?: number;
  v1Label?: string;
  v2Label?: string;
  v3Label?: string;
  v4Label?: string;
}

export default function ComparisonEquityChart({
  data,
  height = 320,
  v1Label = "Strategy 1 (Baseline)",
  v2Label = "Strategy 2 (Failed Staged)",
  v3Label = "Strategy 3 (Alpha Maximizer)",
  v4Label = "Strategy 4 (Risk-Engineered)",
}: ComparisonEquityChartProps) {
  const [hoverIndex, setHoverIndex] = useState<number | null>(null);

  const { pointsV1, pointsV2, pointsV3, pointsV4, v4Area, minVal, maxVal, range, hasV3, hasV4 } = useMemo(() => {
    if (!data || data.length === 0) {
      return {
        pointsV1: "",
        pointsV2: "",
        pointsV3: "",
        pointsV4: "",
        v4Area: "",
        minVal: 0,
        maxVal: 100,
        range: 100,
        hasV3: false,
        hasV4: false,
      };
    }

    const checkHasV3 = data.some((d) => d.v3_equity !== undefined && d.v3_equity !== null);
    const checkHasV4 = data.some((d) => d.v4_equity !== undefined && d.v4_equity !== null);
    const allValues = data.flatMap((d) => [
      d.v1_equity,
      d.v2_equity,
      ...(checkHasV3 && d.v3_equity !== undefined ? [d.v3_equity] : []),
      ...(checkHasV4 && d.v4_equity !== undefined ? [d.v4_equity] : []),
    ]);

    const computedMin = Math.min(0, ...allValues);
    const computedMax = Math.max(10, ...allValues);
    const padding = (computedMax - computedMin) * 0.08 || 5;
    const effMin = computedMin - padding;
    const effMax = computedMax + padding;
    const effRange = effMax - effMin || 1;

    // SVG coordinates: X from 0 to N-1, Y from 94 (bottom) to 6 (top)
    const toY = (val: number) => 94 - ((val - effMin) / effRange) * 88;

    const v1Pts = data.map((d, i) => `${i},${toY(d.v1_equity)}`).join(" ");
    const v2Pts = data.map((d, i) => `${i},${toY(d.v2_equity)}`).join(" ");
    const v3Pts = checkHasV3
      ? data.map((d, i) => `${i},${toY(d.v3_equity ?? d.v1_equity)}`).join(" ")
      : "";
    const v4Pts = checkHasV4
      ? data.map((d, i) => `${i},${toY(d.v4_equity ?? d.v1_equity)}`).join(" ")
      : "";

    // Area fill under v4 (or v3/v2) down to zero line
    const zeroY = toY(0);
    const primaryPts = checkHasV4 ? v4Pts : (checkHasV3 ? v3Pts : v2Pts);
    const area = primaryPts
      ? `0,${zeroY} ${primaryPts} ${data.length - 1},${zeroY}`
      : "";

    return {
      pointsV1: v1Pts,
      pointsV2: v2Pts,
      pointsV3: v3Pts,
      pointsV4: v4Pts,
      v4Area: area,
      minVal: effMin,
      maxVal: effMax,
      range: effRange,
      hasV3: checkHasV3,
      hasV4: checkHasV4,
    };
  }, [data]);

  const activePoint = hoverIndex !== null && data && data[hoverIndex] ? data[hoverIndex] : null;

  if (!data || data.length === 0) {
    return (
      <div
        className="w-full flex items-center justify-center bg-surface-2/40 border border-line rounded-lg text-xs text-gray-500 font-mono"
        style={{ height }}
      >
        Awaiting synchronized equity curve series...
      </div>
    );
  }

  // Delta between Strategy 4 / 3 and Strategy 1 on hover
  const s4Spread = activePoint && activePoint.v4_equity !== undefined
    ? activePoint.v4_equity - activePoint.v1_equity
    : (activePoint ? (activePoint.v4_spread_alpha ?? 0) : 0);

  const v3Spread = activePoint && activePoint.v3_equity !== undefined
    ? activePoint.v3_equity - activePoint.v1_equity
    : (activePoint ? activePoint.spread_alpha : 0);

  const activeAlphaSpread = hasV4 ? s4Spread : v3Spread;

  return (
    <div className="w-full space-y-3">
      {/* Legend & Active Scrub Stats */}
      <div className="flex flex-wrap items-center justify-between text-xs gap-3">
        <div className="flex flex-wrap items-center gap-4">
          {/* Strategy 1: Sky Blue */}
          <div className="flex items-center gap-2">
            <span className="w-3 h-1.5 rounded-full bg-sky-400"></span>
            <span className="text-gray-300 font-medium">{v1Label}</span>
          </div>

          {/* Strategy 2: Amber / Orange */}
          <div className="flex items-center gap-2">
            <span className="w-3 h-1.5 rounded-full bg-amber-400"></span>
            <span className="text-amber-300 font-medium">{v2Label}</span>
          </div>

          {/* Strategy 3: Glowing Emerald */}
          {hasV3 && (
            <div className="flex items-center gap-2">
              <span className="w-3 h-1.5 rounded-full bg-emerald-400 shadow-sm shadow-emerald-500/50"></span>
              <span className="text-emerald-300 font-bold">{v3Label}</span>
            </div>
          )}

          {/* Strategy 4: Radiant Cyan */}
          {hasV4 && (
            <div className="flex items-center gap-2">
              <span className="w-3 h-1.5 rounded-full bg-cyan-400 shadow-sm shadow-cyan-500/50"></span>
              <span className="text-cyan-300 font-bold">{v4Label}</span>
            </div>
          )}

          {/* Alpha indicator */}
          <div className="hidden sm:flex items-center gap-1.5 text-[11px] text-gray-400">
            <span className="w-2.5 h-2.5 rounded-sm bg-cyan-500/20 border border-cyan-500/40"></span>
            <span>Pure Alpha vs Baseline</span>
          </div>
        </div>

        {/* Dynamic Tooltip Display on Hover */}
        {activePoint ? (
          <div className="flex items-center gap-3 font-mono text-[11px] bg-surface-1 px-3 py-1.5 rounded-lg border border-line shadow-lg">
            <span className="text-gray-400">{activePoint.date}</span>
            <span className="text-sky-400">
              S1: {activePoint.v1_equity >= 0 ? `+${activePoint.v1_equity.toFixed(1)}%` : `${activePoint.v1_equity.toFixed(1)}%`}
            </span>
            <span className="text-amber-400">
              S2: {activePoint.v2_equity >= 0 ? `+${activePoint.v2_equity.toFixed(1)}%` : `${activePoint.v2_equity.toFixed(1)}%`}
            </span>
            {activePoint.v3_equity !== undefined && (
              <span className="text-emerald-400 font-bold">
                S3: {activePoint.v3_equity >= 0 ? `+${activePoint.v3_equity.toFixed(1)}%` : `${activePoint.v3_equity.toFixed(1)}%`}
              </span>
            )}
            {activePoint.v4_equity !== undefined && (
              <span className="text-cyan-400 font-bold">
                S4: {activePoint.v4_equity >= 0 ? `+${activePoint.v4_equity.toFixed(1)}%` : `${activePoint.v4_equity.toFixed(1)}%`}
              </span>
            )}
            <span className={`font-extrabold ${activeAlphaSpread >= 0 ? (hasV4 ? "text-cyan-400" : "text-emerald-400") : "text-rose-400"}`}>
              {hasV4 ? "S4 Alpha:" : (hasV3 ? "S3 Alpha:" : "Alpha:")} {activeAlphaSpread >= 0 ? `+${activeAlphaSpread.toFixed(1)}%` : `${activeAlphaSpread.toFixed(1)}%`}
            </span>
          </div>
        ) : (
          <div className="text-[11px] text-gray-500 font-mono">
            Hover over chart to inspect synchronized 4-way equity & alpha
          </div>
        )}
      </div>

      {/* SVG Canvas */}
      <div
        className="w-full bg-surface-2/60 rounded-xl border border-line p-3 relative overflow-hidden select-none"
        style={{ height }}
        onMouseLeave={() => setHoverIndex(null)}
      >
        <svg
          className="w-full h-full overflow-visible"
          viewBox={`0 0 ${Math.max(1, data.length - 1)} 100`}
          preserveAspectRatio="none"
          onMouseMove={(e) => {
            const rect = e.currentTarget.getBoundingClientRect();
            const relX = (e.clientX - rect.left) / rect.width;
            const idx = Math.min(
              data.length - 1,
              Math.max(0, Math.round(relX * (data.length - 1)))
            );
            setHoverIndex(idx);
          }}
        >
          <defs>
            {/* Glow Filter for Strategy 3 Emerald Line */}
            <filter id="emeraldGlow" x="-20%" y="-20%" width="140%" height="140%">
              <feDropShadow dx="0" dy="0" stdDeviation="2.5" floodColor="#10b981" floodOpacity="0.7" />
            </filter>
            {/* Glow Filter for Strategy 4 Cyan Line */}
            <filter id="cyanGlow" x="-20%" y="-20%" width="140%" height="140%">
              <feDropShadow dx="0" dy="0" stdDeviation="2.5" floodColor="#06b6d4" floodOpacity="0.8" />
            </filter>
            {/* Alpha Fill Gradient for S4 */}
            <linearGradient id="v4AreaGrad" x1="0%" y1="0%" x2="0%" y2="100%">
              <stop offset="0%" stopColor="#06b6d4" stopOpacity="0.25" />
              <stop offset="100%" stopColor="#06b6d4" stopOpacity="0.0" />
            </linearGradient>
            {/* Alpha Fill Gradient for S3 */}
            <linearGradient id="v3AreaGrad" x1="0%" y1="0%" x2="0%" y2="100%">
              <stop offset="0%" stopColor="#10b981" stopOpacity="0.25" />
              <stop offset="100%" stopColor="#10b981" stopOpacity="0.0" />
            </linearGradient>
          </defs>

          {/* Zero Return Reference Line */}
          {minVal <= 0 && maxVal >= 0 && (
            <line
              x1="0"
              y1={94 - ((0 - minVal) / range) * 88}
              x2={data.length - 1}
              y2={94 - ((0 - minVal) / range) * 88}
              stroke="#334155"
              strokeDasharray="4 4"
              strokeWidth="1"
              vectorEffect="non-scaling-stroke"
            />
          )}

          {/* Area Fill for Strategy 4 or 3 */}
          {v4Area && (
            <polygon
              points={v4Area}
              fill="url(#v4AreaGrad)"
              vectorEffect="non-scaling-stroke"
            />
          )}

          {/* Strategy 1 Curve: Sky Blue (#0EA5E9) */}
          <polyline
            fill="none"
            stroke="#0ea5e9"
            strokeWidth="1.8"
            strokeOpacity="0.85"
            strokeDasharray="4 2"
            points={pointsV1}
            strokeLinecap="round"
            strokeLinejoin="round"
            vectorEffect="non-scaling-stroke"
          />

          {/* Strategy 2 Curve: Amber / Orange (#F59E0B) */}
          <polyline
            fill="none"
            stroke="#f59e0b"
            strokeWidth="2.0"
            strokeOpacity="0.9"
            points={pointsV2}
            strokeLinecap="round"
            strokeLinejoin="round"
            vectorEffect="non-scaling-stroke"
          />

          {/* Strategy 3 Curve: Glowing Emerald Green (#10B981) */}
          {hasV3 && pointsV3 && (
            <polyline
              fill="none"
              stroke="#10b981"
              strokeWidth="2.5"
              strokeOpacity="0.9"
              points={pointsV3}
              strokeLinecap="round"
              strokeLinejoin="round"
              vectorEffect="non-scaling-stroke"
            />
          )}

          {/* Strategy 4 Curve: Radiant Glowing Cyan (#06B6D4) */}
          {hasV4 && pointsV4 && (
            <polyline
              fill="none"
              stroke="#06b6d4"
              strokeWidth="3.2"
              filter="url(#cyanGlow)"
              points={pointsV4}
              strokeLinecap="round"
              strokeLinejoin="round"
              vectorEffect="non-scaling-stroke"
            />
          )}

          {/* Vertical Crosshair Line on hover */}
          {hoverIndex !== null && (
            <line
              x1={hoverIndex}
              y1="6"
              x2={hoverIndex}
              y2="94"
              stroke="#94a3b8"
              strokeWidth="1"
              strokeDasharray="2 2"
              vectorEffect="non-scaling-stroke"
            />
          )}
        </svg>

        {/* X-Axis Start and End Date Markers */}
        <div className="absolute bottom-2 left-4 right-4 flex items-center justify-between text-[10px] text-gray-500 font-mono pointer-events-none">
          <span>Start: {data[0]?.date}</span>
          <span>{hasV4 ? "4-Way" : "3-Way"} Synchronized Trajectory ({data.length} Aligned Date Points)</span>
          <span>End: {data[data.length - 1]?.date}</span>
        </div>
      </div>
    </div>
  );
}
