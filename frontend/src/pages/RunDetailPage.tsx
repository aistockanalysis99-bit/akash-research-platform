import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import { ArrowLeft } from "lucide-react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { api } from "@/lib/api";
import { Card, ErrorBox, Loading, PageTitle, StatCard } from "@/components/ui";
import { fmtPct, fmtUsd } from "@/lib/utils";
import type { RunMetrics } from "@/lib/types";

export default function RunDetailPage() {
  const { runId = "" } = useParams();

  // Poll the run while it's still computing; stop once done/failed.
  const run = useQuery({
    queryKey: ["run", runId],
    queryFn: () => api.run(runId),
    refetchInterval: (q) => {
      const st = (q.state.data as Record<string, any> | undefined)?.status;
      return st === "done" || st === "failed" ? false : 1500;
    },
  });

  const r = run.data as Record<string, any> | undefined;
  const isDone = r?.status === "done";
  const isFailed = r?.status === "failed";
  const isRunning = !!r && !isDone && !isFailed;

  // Equity + trades only exist once the run has finished — fetch then.
  const equity = useQuery({
    queryKey: ["equity", runId],
    queryFn: () => api.runEquity(runId),
    enabled: isDone,
  });
  const trades = useQuery({
    queryKey: ["trades", runId],
    queryFn: () => api.runTrades(runId),
    enabled: isDone,
  });

  const m: RunMetrics = (r?.metrics as RunMetrics) || {};

  return (
    <div>
      <Link to="/runs" className="inline-flex items-center gap-1 text-sm text-gray-400 hover:text-brand mb-3">
        <ArrowLeft className="h-4 w-4" /> All runs
      </Link>
      <PageTitle
        title={(r?.name as string) || runId.slice(0, 8)}
        subtitle={`${r?.universe_name ?? ""} · ${r?.timeframe ?? ""}`}
      />

      {run.isLoading && <Loading />}
      {run.error && <ErrorBox error={run.error} />}

      {isRunning && (
        <Card className="mb-6 flex items-center gap-3 border-brand/30">
          <Loading label={`Backtest running… ${r?.progress_msg || ""} (${Math.round((r?.progress || 0) * 100)}%)`} />
        </Card>
      )}
      {isFailed && (
        <div className="mb-6">
          <ErrorBox error={`Backtest failed: ${r?.progress_msg || "unknown error"}`} />
        </div>
      )}

      {isDone && (
        <div className="flex flex-wrap gap-3 mb-6">
          <StatCard label="CAGR" value={pct(m.cagr)} valueClass={pos(m.cagr)} />
          <StatCard label="Total Return" value={pct(m.total_return)} valueClass={pos(m.total_return)} />
          <StatCard label="Max Drawdown" value={pct(m.max_drawdown)} valueClass="text-neg" />
          <StatCard label="Sharpe" value={m.sharpe?.toFixed(2) ?? "—"} />
          <StatCard label="Sortino" value={m.sortino?.toFixed(2) ?? "—"} />
          <StatCard label="Final Equity" value={fmtUsd(m.final_equity)} valueClass="text-white" />
          <StatCard label="Trades" value={String(m["trades.total_trades"] ?? "—")} />
        </div>
      )}

      {isDone && (
      <>
      <h2 className="text-sm font-semibold uppercase tracking-wide text-gray-400 mb-2">Equity Curve</h2>
      <Card className="mb-6">
        {equity.isLoading && <Loading />}
        {equity.data && equity.data.length > 0 ? (
          <ResponsiveContainer width="100%" height={320}>
            <AreaChart data={equity.data} margin={{ top: 5, right: 10, bottom: 5, left: 0 }}>
              <defs>
                <linearGradient id="eq" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#2dd4bf" stopOpacity={0.35} />
                  <stop offset="100%" stopColor="#2dd4bf" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid stroke="#1e2a3d" strokeDasharray="3 3" />
              <XAxis
                dataKey="timestamp"
                tick={{ fill: "#64748b", fontSize: 11 }}
                tickFormatter={(d) => String(d).slice(0, 10)}
                minTickGap={50}
              />
              <YAxis
                tick={{ fill: "#64748b", fontSize: 11 }}
                tickFormatter={(v) => `$${(v / 1000).toFixed(0)}k`}
                width={55}
                domain={["auto", "auto"]}
              />
              <Tooltip
                contentStyle={{
                  background: "#111824",
                  border: "1px solid #1e2a3d",
                  borderRadius: 8,
                  fontSize: 12,
                }}
                labelStyle={{ color: "#94a3b8" }}
                formatter={(v: number) => [fmtUsd(v), "Equity"]}
              />
              <Area type="monotone" dataKey="equity" stroke="#2dd4bf" strokeWidth={2} fill="url(#eq)" />
            </AreaChart>
          </ResponsiveContainer>
        ) : (
          !equity.isLoading && <div className="py-10 text-center text-gray-500 text-sm">No equity data.</div>
        )}
      </Card>

      <h2 className="text-sm font-semibold uppercase tracking-wide text-gray-400 mb-2">
        Trades {trades.data ? `(${trades.data.length})` : ""}
      </h2>
      {trades.isLoading && <Loading />}
      {trades.data && trades.data.length > 0 && (
        <Card className="p-0 overflow-hidden">
          <div className="max-h-[480px] overflow-auto">
            <table className="w-full text-sm">
              <thead className="sticky top-0 bg-bg-card">
                <tr className="text-xs uppercase text-gray-500 border-b border-line">
                  <th className="text-left px-3 py-2">Symbol</th>
                  <th className="text-left px-3 py-2">Entry</th>
                  <th className="text-left px-3 py-2">Exit</th>
                  <th className="text-right px-3 py-2">Qty</th>
                  <th className="text-right px-3 py-2">P&L</th>
                  <th className="text-right px-3 py-2">Return</th>
                  <th className="text-right px-3 py-2">Bars</th>
                  <th className="text-left px-3 py-2">Exit reason</th>
                </tr>
              </thead>
              <tbody>
                {trades.data.map((t: any, i) => (
                  <tr key={t.id ?? i} className="border-b border-line/50">
                    <td className="px-3 py-2 font-mono font-semibold">{t.symbol}</td>
                    <td className="px-3 py-2 text-xs text-gray-500 font-mono">
                      {String(t.entry_time || "").slice(0, 10)}
                    </td>
                    <td className="px-3 py-2 text-xs text-gray-500 font-mono">
                      {String(t.exit_time || "").slice(0, 10)}
                    </td>
                    <td className="px-3 py-2 text-right stat-num text-gray-400">
                      {t.qty != null ? Math.round(t.qty) : "—"}
                    </td>
                    <td className={`px-3 py-2 text-right stat-num ${pos(t.pnl)}`}>
                      {fmtUsd(t.pnl, 0)}
                    </td>
                    <td className={`px-3 py-2 text-right stat-num ${pos(t.pnl_pct)}`}>
                      {t.pnl_pct != null ? fmtPct(t.pnl_pct * 100) : "—"}
                    </td>
                    <td className="px-3 py-2 text-right stat-num text-gray-400">
                      {t.bars_held ?? "—"}
                    </td>
                    <td className="px-3 py-2 text-xs text-gray-400">{t.exit_reason || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}
      </>
      )}
    </div>
  );
}

function pct(v?: number) {
  return v == null ? "—" : fmtPct(v * 100);
}
function pos(v?: number) {
  if (v == null) return "text-gray-400";
  return v >= 0 ? "text-pos" : "text-neg";
}
