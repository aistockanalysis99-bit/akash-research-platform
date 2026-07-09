import { useState } from "react";
import { useParams, Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, History, RefreshCw } from "lucide-react";
import { api } from "@/lib/api";
import { Badge, Button, Card, ErrorBox, Loading, PageTitle, Spinner } from "@/components/ui";
import { cn } from "@/lib/utils";

function pnlCls(v?: number | null): string {
  if (v == null) return "text-gray-400";
  return v >= 0 ? "text-pos" : "text-neg";
}

function cheapCls(c?: number | null): string {
  if (c == null) return "text-gray-400";
  if (c <= 0.8) return "text-pos";
  if (c <= 1.2) return "text-warn";
  return "text-neg";
}

export default function OptionsBacktestPage() {
  const { symbol = "" } = useParams();
  const qc = useQueryClient();
  const q = useQuery({
    queryKey: ["optBacktest", symbol],
    queryFn: () => api.optionsBacktest(symbol),
  });
  const refresh = useMutation({
    mutationFn: () => api.optionsBacktest(symbol, { refresh: true }),
    onSuccess: (data) => qc.setQueryData(["optBacktest", symbol], data),
  });

  const data = q.data;
  const s = data?.summary;

  return (
    <div className="max-w-4xl mx-auto">
      <Link to="/options" className="inline-flex items-center gap-1 text-sm text-gray-400 hover:text-brand mb-4">
        <ArrowLeft className="h-4 w-4" /> Scanner
      </Link>

      <PageTitle
        title={`${symbol} — Earnings Track Record`}
        subtitle="Historical straddle backtest using REAL past option prices (Polygon expired-contract data) — not simulated. Shows what this exact strategy would have done on this stock's actual earnings history."
        actions={
          <Button variant="outline" onClick={() => refresh.mutate()} disabled={refresh.isPending}>
            {refresh.isPending ? <Spinner /> : <RefreshCw className="h-4 w-4" />}
            Recompute
          </Button>
        }
      />

      {q.isLoading && <Loading />}
      {q.error && <ErrorBox error={q.error} />}

      {data?.error && (
        <Card className="border-warn/40">
          <div className="text-sm text-warn">Could not backtest {symbol}: {data.error}</div>
        </Card>
      )}

      {s && (
        <>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-4">
            <Stat label="Events simulated" value={s.events_simulated} />
            <Stat label="Successfully priced" value={s.events_priced} />
            <Stat label="Would have qualified" value={s.qualifying_events} />
            <Stat
              label="Win rate (qualified)"
              value={s.qualifying_win_rate_pct != null ? `${s.qualifying_win_rate_pct}%` : "—"}
              cls={s.qualifying_win_rate_pct != null && s.qualifying_win_rate_pct >= 50 ? "text-pos" : undefined}
            />
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 mb-6">
            <Stat
              label="Avg P&L — qualified events"
              value={s.qualifying_avg_pnl_pct != null ? `${s.qualifying_avg_pnl_pct >= 0 ? "+" : ""}${s.qualifying_avg_pnl_pct}%` : "—"}
              cls={pnlCls(s.qualifying_avg_pnl_pct)}
              bold
            />
            <Stat
              label="Avg P&L — all priced events"
              value={s.all_events_avg_pnl_pct != null ? `${s.all_events_avg_pnl_pct >= 0 ? "+" : ""}${s.all_events_avg_pnl_pct}%` : "—"}
              cls={pnlCls(s.all_events_avg_pnl_pct)}
            />
            <Stat
              label="Avg implied ÷ actual move"
              value={s.avg_implied_vs_actual ?? "—"}
            />
          </div>

          {s.qualifying_events === 0 && s.events_priced > 0 && (
            <div className="text-xs text-gray-500 mb-4 italic">
              No historical event on {symbol} would have passed today's cheapness filter
              (≤0.80) — either this stock rarely gets mispriced into earnings, or the
              filter's threshold is worth revisiting for this name specifically.
            </div>
          )}
        </>
      )}

      {data?.events && data.events.length > 0 && (
        <>
          <h2 className="text-sm font-semibold uppercase tracking-wide text-gray-400 mb-2">
            Event by event
          </h2>
          <Card className="p-0 overflow-hidden">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-line bg-bg-soft text-xs text-gray-500">
                  <th className="text-left p-2">Earnings</th>
                  <th className="text-right p-2">Implied</th>
                  <th className="text-right p-2">Historical</th>
                  <th className="text-right p-2">Actual</th>
                  <th className="text-right p-2">Cheapness</th>
                  <th className="text-right p-2">Trade P&L</th>
                  <th className="text-left p-2 pl-4">Note</th>
                </tr>
              </thead>
              <tbody>
                {data.events.map((e) => (
                  <tr key={e.earnings_date} className="border-b border-line/40">
                    <td className="p-2 font-mono text-xs">{e.earnings_date}</td>
                    {e.error ? (
                      <td colSpan={5} className="p-2 text-xs text-gray-500 italic">
                        skipped — {e.error}
                      </td>
                    ) : (
                      <>
                        <td className="p-2 text-right stat-num">±{e.implied_move_pct}%</td>
                        <td className="p-2 text-right stat-num text-gray-400">±{e.hist_median_move_pct}%</td>
                        <td className="p-2 text-right stat-num text-gray-400">±{e.actual_move_pct}%</td>
                        <td className={cn("p-2 text-right stat-num font-semibold", cheapCls(e.cheapness))}>
                          {e.cheapness}
                        </td>
                        <td className={cn("p-2 text-right stat-num font-semibold", pnlCls(e.trade_pnl_pct))}>
                          {e.trade_pnl_pct != null ? `${e.trade_pnl_pct >= 0 ? "+" : ""}${e.trade_pnl_pct}%` : "—"}
                        </td>
                      </>
                    )}
                    <td className="p-2 pl-4">
                      {!e.error && e.would_qualify && (
                        <Badge className="border-pos/40 bg-pos/10 text-pos text-[10px]">would qualify</Badge>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>
        </>
      )}

      {data?.note && (
        <p className="text-xs text-gray-600 mt-4 italic">{data.note}</p>
      )}

      {!q.isLoading && !data?.events?.length && !data?.error && (
        <Card className="text-center py-12 text-gray-500">
          <History className="h-8 w-8 mx-auto mb-2 text-gray-600" />
          <div>No backtestable events found for {symbol}.</div>
        </Card>
      )}
    </div>
  );
}

function Stat({ label, value, cls, bold }: {
  label: string; value: React.ReactNode; cls?: string; bold?: boolean;
}) {
  return (
    <Card className="py-3">
      <div className="text-[10px] uppercase text-gray-500">{label}</div>
      <div className={cn("text-xl stat-num mt-1", bold && "font-bold", cls || "text-gray-100")}>
        {value}
      </div>
    </Card>
  );
}
