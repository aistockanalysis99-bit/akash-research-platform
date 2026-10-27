import React from "react";
import { RefreshCw, Download, CheckCircle2, AlertTriangle } from "lucide-react";
import { cn } from "@/lib/utils";

export interface ProgressState {
  active: boolean;
  phase: "scanning" | "downloading" | "complete" | "error" | "idle";
  pct: number;
  label: string;
  sublabel?: string;
}

interface TopProgressBarProps {
  progress: ProgressState;
}

export default function TopProgressBar({ progress }: TopProgressBarProps) {
  if (!progress.active && progress.phase === "idle") return null;

  const isComplete = progress.phase === "complete" || progress.pct >= 100;
  const isError = progress.phase === "error";

  return (
    <div className="fixed top-0 left-0 right-0 z-50 pointer-events-none transition-all duration-500 ease-in-out">
      {/* 4px Top Gradient Bar */}
      <div className="w-full h-1 bg-surface-3/50 overflow-hidden relative shadow-sm">
        <div
          className={cn(
            "h-full transition-all duration-300 ease-out",
            isError ? "bg-rose-500" : isComplete ? "bg-emerald-500" : "bg-brand"
          )}
          style={{ width: `${Math.min(100, Math.max(2, progress.pct))}%` }}
        />
      </div>

      {/* Floating Status Notification Pill */}
      <div className="flex justify-center pt-2">
        <div
          className={cn(
            "pointer-events-auto inline-flex items-center gap-2.5 px-4 py-2 rounded-md border border-line shadow-md text-xs font-mono transition-all duration-300 transform",
            isError ? "bg-surface border-rose-500/50 text-rose-300 translate-y-0 scale-100" : isComplete ? "bg-surface border-emerald-500/50 text-emerald-300 translate-y-0 scale-100" : "bg-surface border-line text-gray-200 translate-y-0 scale-100"
          )}
        >
          {isError ? (
            <AlertTriangle className="w-4 h-4 text-rose-400 shrink-0" />
          ) : isComplete ? (
            <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
          ) : progress.phase === "scanning" ? (
            <RefreshCw className="w-4 h-4 text-brand animate-spin shrink-0" />
          ) : (
            <Download className="w-4 h-4 text-brand animate-bounce shrink-0" />
          )}

          <div className="flex items-center gap-2">
            <span className="font-bold tracking-wide">{progress.label}</span>
            {progress.sublabel && (
              <span className="text-gray-400 hidden sm:inline">&middot; {progress.sublabel}</span>
            )}
          </div>

          <span
            className={cn(
              "px-2 py-0.5 rounded-full font-bold text-[11px]",
              isError
                ? "bg-rose-500/20 text-rose-300 border border-rose-500/40"
                : isComplete
                ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/40"
                : "bg-cyan-500/20 text-cyan-300 border border-cyan-500/40"
            )}
          >
            {Math.round(progress.pct)}%
          </span>
        </div>
      </div>
    </div>
  );
}
