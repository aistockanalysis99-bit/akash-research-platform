import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Trophy, PlayCircle } from "lucide-react";
import { api } from "@/lib/api";
import { Badge, Button, Card, ErrorBox, Loading, PageTitle, Spinner } from "@/components/ui";
import { cn } from "@/lib/utils";

function pnlCls(v?: number | null): string {
  if (v == null) return "text-gray-400";
  return v >= 0 ? "text-pos" : "text-neg";
}

const STATUS_STYLE: Record<string, string> = {
  live: "border-pos/40 bg-pos/10 text-pos",
  paper: "border-warn/40 bg-warn/10 text-warn",
  planned: "border-line bg-bg-hover text-gray-400",
};

export default function LeagueTablePage() {
  const qc = useQueryClient();
  const league = useQuery({ queryKey: ["optLeague"], queryFn: api.optionsLeague });
  const rc = useQuery({ queryKey: ["optReportCard"], queryFn: api.optionsReportCard });
  const runBatch = useMutation({
    mutationFn: () => api.optionsReportCardRun(5),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["optReportCard"] }),
  });

  const rows = league.data?.rows || [];
  const card = rc.data;

  return (
    <div className="max-w-5xl mx-auto">
      <PageTitle
        title="Strategy League"
        subtitle="Every strategy family on one honest axis: realized return on capital at risk. Quoted yields promise; this table remembers. Strategies earn more capital here — or get retired here."
      />

      {league.error && <ErrorBox error={league.error} />}
      {league.isLoading && <Loading />}

      {rows.length > 0 && (
        <Card className="p-0 overflow-hidden mb-8">
          <div className="overflow-x-auto">
            <table className="w-full text-sm min-w-[720px]">
              <thead>
                <tr className="border-b border-line bg-bg-soft text-xs text-gray-500">
                  <th className="text-left p-2.5">Strategy</th>
                  <th className="text-left p-2.5">Status</th>
                  <th className="text-right p-2.5">Closed</th>
                  <th className="text-right p-2.5">Win rate</th>
                  <th className="text-right p-2.5">Avg on risk</th>
                  <th className="text-right p-2.5">Total P&L</th>
                  <th className="text-right p-2.5">Worst trade</th>
                  <th className="text-right p-2.5">Open now</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.key} className={cn("border-b border-line/40",
                    r.trades === 0 && r.open_count === 0 && "opacity-50")}>
                    <td className="p-2.5 font-semibold text-gray-200">{r.name}</td>
                    <td className="p-2.5">
                      <Badge className={cn("text-[10px]", STATUS_STYLE[r.status])}>
                        {r.status.toUpperCase()}
                      </Badge>
                    </td>
                    <td className="p-2.5 text-right stat-num">{r.trades || "—"}</td>
                    <td className="p-2.5 text-right stat-num">
                      {r.win_rate_pct != null ? `${r.win_rate_pct}%` : "—"}
                    </td>
                    <td className={cn("p-2.5 text-right stat-num font-semibold",
                      pnlCls(r.avg_return_on_risk_pct))}>
                      {r.avg_return_on_risk_pct != null
                        ? `${r.avg_return_on_risk_pct >= 0 ? "+" : ""}${r.avg_return_on_risk_pct}%`
                        : "—"}
                    </td>
                    <td className={cn("p-2.5 text-right stat-num", pnlCls(r.total_pnl_usd))}>
                      {r.trades ? `${r.total_pnl_usd < 0 ? "-" : ""}$${Math.abs(r.total_pnl_usd).toLocaleString()}` : "—"}
                    </td>
                    <td className="p-2.5 text-right stat-num text-gray-400">
                      {r.worst_trade_usd != null ? `$${r.worst_trade_usd.toLocaleString()}` : "—"}
                    </td>
                    <td className="p-2.5 text-right stat-num">
                      {r.open_count ? `${r.open_count} · $${r.open_capital.toLocaleString()}` : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      {/* Report Card — the Layer-2 evidence base */}
      <div className="flex items-center gap-3 mb-2 flex-wrap">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-gray-400">
          The evidence base — historical Report Card
        </h2>
        <div className="flex-1" />
        <Button variant="outline" onClick={() => runBatch.mutate()} disabled={runBatch.isPending}>
          {runBatch.isPending ? <Spinner /> : <PlayCircle className="h-4 w-4" />}
          {runBatch.isPending ? "Backtesting…" : "Extend coverage (+5 stocks)"}
        </Button>
      </div>
      <p className="text-xs text-gray-500 mb-3 max-w-2xl">
        Every S&P 500 stock gets its straddle strategy backtested on real historical
        option prices — ~20 more stocks each night at 03:30 ET. This is what past
        earnings actually paid, not a simulation.
      </p>
      {runBatch.error && <ErrorBox error={runBatch.error} />}

      {card && (
        <>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-4">
            <RCStat label="Stocks covered" value={`${card.symbols_covered}`} />
            <RCStat label="Real events priced" value={card.events_priced.toLocaleString()} />
            <RCStat label="Qualifying events" value={`${card.qualifying_events}`} />
            <RCStat
              label="Qualifying win rate"
              value={card.qualifying_win_rate_pct != null ? `${card.qualifying_win_rate_pct}%` : "building…"}
              cls={card.qualifying_win_rate_pct != null && card.qualifying_win_rate_pct >= 50 ? "text-pos" : undefined}
            />
          </div>
          {card.qualifying_avg_pnl_pct != null && (
            <p className="text-sm text-gray-300 mb-4">
              Across every qualifying historical event, the average trade returned{" "}
              <b className={pnlCls(card.qualifying_avg_pnl_pct)}>
                {card.qualifying_avg_pnl_pct >= 0 ? "+" : ""}{card.qualifying_avg_pnl_pct}%
              </b>{" "}
              on premium. Market-wide, implied moves ran{" "}
              <b className="text-gray-100">{card.avg_implied_vs_actual}×</b> the realized
              move — the overpricing the whole two-sided strategy set is built on.
            </p>
          )}

          {card.leaders.length > 0 && (
            <>
              <h3 className="text-xs font-semibold uppercase tracking-wide text-gray-500 mb-2">
                <Trophy className="h-3.5 w-3.5 inline mr-1 text-warn" />
                Best historical straddle stocks (≥2 qualifying events)
              </h3>
              <Card className="p-0 overflow-hidden">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-line bg-bg-soft text-xs text-gray-500">
                      <th className="text-left p-2">Symbol</th>
                      <th className="text-right p-2">Qualifying events</th>
                      <th className="text-right p-2">Win rate</th>
                      <th className="text-right p-2">Avg P&L</th>
                    </tr>
                  </thead>
                  <tbody>
                    {card.leaders.map((l) => (
                      <tr key={l.symbol} className="border-b border-line/40">
                        <td className="p-2 font-mono font-semibold">{l.symbol}</td>
                        <td className="p-2 text-right stat-num">{l.qualifying_events}</td>
                        <td className="p-2 text-right stat-num">{l.win_rate_pct ?? "—"}%</td>
                        <td className={cn("p-2 text-right stat-num font-semibold", pnlCls(l.avg_pnl_pct))}>
                          {l.avg_pnl_pct != null ? `${l.avg_pnl_pct >= 0 ? "+" : ""}${l.avg_pnl_pct}%` : "—"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </Card>
            </>
          )}
        </>
      )}
    </div>
  );
}

function RCStat({ label, value, cls }: { label: string; value: string; cls?: string }) {
  return (
    <Card className="py-3">
      <div className="text-[10px] uppercase text-gray-500">{label}</div>
      <div className={cn("text-xl stat-num mt-1 font-bold", cls || "text-gray-100")}>{value}</div>
    </Card>
  );
}
