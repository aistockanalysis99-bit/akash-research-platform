import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { Button, Card, Loading, PageTitle } from "@/components/ui";
import { cn, fmtPct, shortDate } from "@/lib/utils";
import type { RunRow } from "@/lib/types";

export default function ComparePage() {
  const runs = useQuery({ queryKey: ["runs"], queryFn: () => api.runs(200) });
  const [sel, setSel] = useState<string[]>([]);

  const toggle = (id: string) =>
    setSel((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id]));

  const chosen = (runs.data || []).filter((r) => sel.includes(r.id));

  return (
    <div>
      <PageTitle title="Compare Runs" subtitle="Select two or more runs to compare metrics side by side." />
      {runs.isLoading && <Loading />}
      {runs.data && (
        <div className="grid grid-cols-1 lg:grid-cols-[300px_1fr] gap-5">
          {/* Selector */}
          <Card className="p-0 overflow-hidden max-h-[600px] overflow-y-auto">
            {runs.data.map((r) => (
              <button
                key={r.id}
                onClick={() => toggle(r.id)}
                className={cn(
                  "w-full text-left px-3 py-2 border-b border-line/50 text-sm transition-colors",
                  sel.includes(r.id) ? "bg-brand/15 text-brand" : "hover:bg-bg-hover text-gray-300"
                )}
              >
                <div className="font-medium truncate">{r.name || r.id.slice(0, 8)}</div>
                <div className="text-xs text-gray-500">{shortDate(r.started_at)}</div>
              </button>
            ))}
          </Card>

          {/* Comparison table */}
          <div>
            {chosen.length < 2 ? (
              <Card>
                <div className="py-10 text-center text-gray-500 text-sm">
                  Select at least two runs from the left.
                </div>
              </Card>
            ) : (
              <Card className="p-0 overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-line">
                      <th className="text-left px-3 py-2 text-xs uppercase text-gray-500">Metric</th>
                      {chosen.map((r) => (
                        <th key={r.id} className="text-right px-3 py-2 text-xs text-gray-300">
                          {r.name || r.id.slice(0, 6)}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {METRICS.map((mk) => (
                      <tr key={mk.key} className="border-b border-line/50">
                        <td className="px-3 py-2 text-gray-400">{mk.label}</td>
                        {chosen.map((r) => (
                          <td key={r.id} className="px-3 py-2 text-right stat-num">
                            {mk.fmt((r.metrics || {})[mk.key])}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </Card>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

const METRICS: { key: string; label: string; fmt: (v?: number) => string }[] = [
  { key: "cagr", label: "CAGR", fmt: (v) => (v == null ? "—" : fmtPct(v * 100)) },
  { key: "total_return", label: "Total Return", fmt: (v) => (v == null ? "—" : fmtPct(v * 100)) },
  { key: "max_drawdown", label: "Max Drawdown", fmt: (v) => (v == null ? "—" : fmtPct(v * 100)) },
  { key: "sharpe", label: "Sharpe", fmt: (v) => (v == null ? "—" : v.toFixed(2)) },
  { key: "sortino", label: "Sortino", fmt: (v) => (v == null ? "—" : v.toFixed(2)) },
  { key: "annualized_vol", label: "Volatility", fmt: (v) => (v == null ? "—" : fmtPct(v * 100)) },
  { key: "trades.total_trades", label: "Trades", fmt: (v) => (v == null ? "—" : String(v)) },
];
