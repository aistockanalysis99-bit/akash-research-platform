import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { Trash2 } from "lucide-react";
import { api } from "@/lib/api";
import { Card, EmptyState, ErrorBox, Loading, PageTitle } from "@/components/ui";
import { cn, fmtPct, shortDate } from "@/lib/utils";
import type { RunRow } from "@/lib/types";

export default function RunsPage() {
  const qc = useQueryClient();
  const { data, isLoading, error } = useQuery({ queryKey: ["runs"], queryFn: () => api.runs(200) });
  const del = useMutation({
    mutationFn: (id: string) => api.runDelete(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["runs"] }),
  });

  return (
    <div>
      <PageTitle title="Run History" subtitle="Every backtest run, newest first." />
      {isLoading && <Loading />}
      {error && <ErrorBox error={error} />}
      {data && data.length === 0 && (
        <Card>
          <EmptyState title="No backtests yet" hint="Launch one from the Backtest tab." />
        </Card>
      )}
      {data && data.length > 0 && (
        <Card className="p-0 overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-xs uppercase text-gray-500 border-b border-line">
                <th className="text-left px-3 py-2">Name</th>
                <th className="text-left px-3 py-2">Universe</th>
                <th className="text-left px-3 py-2">TF</th>
                <th className="text-right px-3 py-2">CAGR</th>
                <th className="text-right px-3 py-2">Max DD</th>
                <th className="text-right px-3 py-2">Sharpe</th>
                <th className="text-right px-3 py-2">Trades</th>
                <th className="text-left px-3 py-2">When</th>
                <th className="px-3 py-2"></th>
              </tr>
            </thead>
            <tbody>
              {data.map((r: RunRow) => {
                const m = r.metrics || {};
                return (
                  <tr key={r.id} className="border-b border-line/50 hover:bg-bg-hover/50">
                    <td className="px-3 py-2.5">
                      <Link to={`/runs/${r.id}`} className="text-brand hover:text-brand-glow font-medium">
                        {r.name || r.id.slice(0, 8)}
                      </Link>
                    </td>
                    <td className="px-3 py-2.5 text-gray-400">{r.universe_name || "—"}</td>
                    <td className="px-3 py-2.5 text-gray-400">{r.timeframe || "—"}</td>
                    <td className={cn("px-3 py-2.5 text-right stat-num", pos(m.cagr))}>
                      {pctOrDash(m.cagr)}
                    </td>
                    <td className="px-3 py-2.5 text-right stat-num text-neg">
                      {pctOrDash(m.max_drawdown)}
                    </td>
                    <td className="px-3 py-2.5 text-right stat-num">
                      {m.sharpe != null ? m.sharpe.toFixed(2) : "—"}
                    </td>
                    <td className="px-3 py-2.5 text-right stat-num text-gray-400">
                      {m["trades.total_trades"] ?? "—"}
                    </td>
                    <td className="px-3 py-2.5 text-gray-500 text-xs font-mono">
                      {shortDate(r.started_at)}
                    </td>
                    <td className="px-3 py-2.5 text-right">
                      <button
                        onClick={() => del.mutate(r.id)}
                        className="text-gray-600 hover:text-neg"
                        title="Delete run"
                      >
                        <Trash2 className="h-4 w-4" />
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </Card>
      )}
    </div>
  );
}

function pctOrDash(v?: number) {
  return v == null ? "—" : fmtPct(v * 100);
}
function pos(v?: number) {
  if (v == null) return "text-gray-400";
  return v >= 0 ? "text-pos" : "text-neg";
}
