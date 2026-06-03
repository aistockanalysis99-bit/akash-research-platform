import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function fmtUsd(v: number | null | undefined, decimals = 0): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  }).format(v);
}

export function fmtUsdSigned(v: number | null | undefined, decimals = 0): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  const s = fmtUsd(Math.abs(v), decimals);
  return v >= 0 ? `+${s}` : `-${s}`;
}

export function fmtPct(v: number | null | undefined, decimals = 1): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  return `${v >= 0 ? "+" : ""}${v.toFixed(decimals)}%`;
}

export function fmtCompact(v: number | null | undefined): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  const abs = Math.abs(v);
  if (abs >= 1e12) return `${(v / 1e12).toFixed(2)}T`;
  if (abs >= 1e9) return `${(v / 1e9).toFixed(2)}B`;
  if (abs >= 1e6) return `${(v / 1e6).toFixed(1)}M`;
  if (abs >= 1e3) return `${(v / 1e3).toFixed(0)}K`;
  return `${v}`;
}

export function pnlColor(v: number | null | undefined): string {
  if (v === null || v === undefined || v === 0) return "text-gray-300";
  return v > 0 ? "text-pos" : "text-neg";
}

export function decisionColor(d?: string): string {
  switch ((d || "").toUpperCase()) {
    case "APPROVE":
      return "text-pos border-pos/40 bg-pos/10";
    case "RESIZE":
      return "text-warn border-warn/40 bg-warn/10";
    case "REJECT":
      return "text-neg border-neg/40 bg-neg/10";
    case "HOLD":
      return "text-brand border-brand/40 bg-brand/10";
    default:
      return "text-gray-400 border-line bg-bg-hover";
  }
}

export function shortDate(s?: string): string {
  if (!s) return "—";
  return s.slice(0, 10);
}
