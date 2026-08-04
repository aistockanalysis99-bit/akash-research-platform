import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BookMarked, RefreshCw, ShieldCheck, Target } from "lucide-react";
import { api } from "@/lib/api";
import { Badge, Button, Card, ErrorBox, Loading, PageTitle, Spinner } from "@/components/ui";
import { cn } from "@/lib/utils";

type Rulebook = Awaited<ReturnType<typeof api.optionsRulebook>>;
type Strategy = Rulebook["strategies"][number];

const STATUS_STYLE: Record<Strategy["status"], string> = {
  live: "border-pos/40 bg-pos/10 text-pos",
  paper: "border-warn/40 bg-warn/10 text-warn",
  planned: "border-line bg-bg-hover text-gray-400",
};
const STATUS_LABEL: Record<Strategy["status"], string> = {
  live: "LIVE",
  paper: "PAPER — earning its record",
  planned: "PLANNED",
};

export default function RulebookPage() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["rulebook"], queryFn: api.optionsRulebook });
  const refreshPool = useMutation({
    mutationFn: api.optionsPoolBRefresh,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["rulebook"] }),
  });

  const data = q.data;
  const league = data?.league || {};
  const poolQualified = (data?.pool_b || []).filter((p) => p.qualified);

  return (
    <div className="max-w-5xl mx-auto">
      <PageTitle
        title="Strategy Rulebook"
        subtitle="Every strategy this platform will ever suggest, defined by explicit conditions — parameters shown here are read live from settings, so this page always matches what the code actually does."
      />

      {q.isLoading && <Loading />}
      {q.error && <ErrorBox error={q.error} />}

      {/* Governance — the house rules */}
      {data && (
        <Card className="mb-6 border-brand/30 bg-brand/[0.04]">
          <div className="flex items-center gap-2 mb-3">
            <ShieldCheck className="h-5 w-5 text-brand" />
            <span className="font-bold text-white">House rules — enforced in code, not just promised</span>
          </div>
          <ul className="space-y-1.5">
            {data.governance.map((g) => (
              <li key={g.slice(0, 24)} className="flex gap-2 text-sm text-gray-300">
                <span className="text-brand mt-0.5 shrink-0">•</span> {g}
              </li>
            ))}
          </ul>
        </Card>
      )}

      {/* Strategies */}
      <div className="space-y-4 mb-10">
        {data?.strategies.map((s) => (
          <StrategyCard key={s.key} s={s} stats={league[s.key]} />
        ))}
      </div>

      {/* Pool B */}
      {data && (
        <>
          <div className="flex items-center gap-3 mb-2 flex-wrap">
            <h2 className="text-sm font-semibold uppercase tracking-wide text-gray-400">
              Pool B — the liquidity list ({poolQualified.length} qualified
              {data.pool_b.length ? ` of ${data.pool_b.length} measured` : ""})
            </h2>
            <div className="flex-1" />
            <Button variant="outline" onClick={() => refreshPool.mutate()}
                    disabled={refreshPool.isPending}>
              {refreshPool.isPending ? <Spinner /> : <RefreshCw className="h-4 w-4" />}
              Re-measure now
            </Button>
          </div>
          <p className="text-xs text-gray-500 mb-3 max-w-2xl">
            Membership is earned by measured liquidity (best paired open interest in
            the ATM neighborhood of the nearest Friday expiry), re-checked every
            Monday 08:10 ET. Short-premium strategies only trade names on this list.
          </p>
          {refreshPool.error && <ErrorBox error={refreshPool.error} />}
          {data.pool_b.length === 0 ? (
            <Card className="text-center py-8 text-gray-500 text-sm">
              Not measured yet — hit “Re-measure now” to qualify the seed list.
            </Card>
          ) : (
            <Card className="p-0 overflow-hidden">
              <div className="overflow-x-auto">
                <table className="w-full text-sm min-w-[560px]">
                  <thead>
                    <tr className="border-b border-line bg-bg-soft text-xs text-gray-500">
                      <th className="text-left p-2">Symbol</th>
                      <th className="text-right p-2">Spot</th>
                      <th className="text-left p-2 pl-4">Measured expiry</th>
                      <th className="text-right p-2">Best ATM OI</th>
                      <th className="text-left p-2 pl-4">Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.pool_b.map((p) => (
                      <tr key={p.symbol} className="border-b border-line/40">
                        <td className="p-2 font-mono font-semibold">{p.symbol}</td>
                        <td className="p-2 text-right stat-num">
                          {p.spot != null ? `$${p.spot.toFixed(2)}` : "—"}
                        </td>
                        <td className="p-2 pl-4 text-xs text-gray-400">{p.expiry ?? "—"}</td>
                        <td className="p-2 text-right stat-num">
                          {p.atm_oi != null ? p.atm_oi.toLocaleString() : "—"}
                        </td>
                        <td className="p-2 pl-4">
                          {p.qualified ? (
                            <Badge className="border-pos/40 bg-pos/10 text-pos text-[10px]">qualified</Badge>
                          ) : (
                            <span className="text-xs text-gray-500">{p.note || "not qualified"}</span>
                          )}
                        </td>
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

function StrategyCard({ s, stats }: {
  s: Strategy;
  stats?: { trades: number; win_rate_pct?: number | null; total_pnl_usd: number;
            avg_return_on_risk_pct?: number | null };
}) {
  return (
    <Card className={cn("border-l-4",
      s.status === "live" ? "border-pos/60" :
      s.status === "paper" ? "border-warn/60" : "border-line")}>
      <div className="flex items-center gap-2 flex-wrap mb-1.5">
        <BookMarked className="h-4 w-4 text-gray-500" />
        <span className="font-bold text-white">{s.name}</span>
        <Badge className={cn("text-[10px]", STATUS_STYLE[s.status])}>
          {STATUS_LABEL[s.status]}
        </Badge>
        <span className="text-xs text-gray-500">{s.phase}</span>
        <div className="flex-1" />
        <span className="text-xs text-gray-500">{s.risk_type}</span>
      </div>

      <p className="text-sm text-gray-300 mb-3 max-w-3xl">{s.plain}</p>

      <div className="grid sm:grid-cols-3 gap-3 text-sm">
        <RuleBlock title="Fires when">
          {s.entry_conditions.map((c) => <li key={c}>{c}</li>)}
        </RuleBlock>
        <RuleBlock title="The structure">
          <li>{s.structure}</li>
          <li className="text-gray-500">pools: {s.pools.join(" · ")}</li>
        </RuleBlock>
        <RuleBlock title="Exit rules">
          {s.exit_rules.map((c) => <li key={c}>{c}</li>)}
        </RuleBlock>
      </div>

      {stats && stats.trades > 0 && (
        <div className="mt-3 pt-2 border-t border-line/50 flex items-center gap-2 text-xs text-gray-400">
          <Target className="h-3.5 w-3.5 text-brand" />
          Realized record: {stats.trades} closed · win rate {stats.win_rate_pct ?? 0}% ·
          avg {stats.avg_return_on_risk_pct != null ? `${stats.avg_return_on_risk_pct >= 0 ? "+" : ""}${stats.avg_return_on_risk_pct}%` : "—"} on risk ·
          total <span className={stats.total_pnl_usd >= 0 ? "text-pos" : "text-neg"}>
            {stats.total_pnl_usd < 0 ? "-" : ""}$
            {Math.abs(stats.total_pnl_usd).toLocaleString(undefined, {
              minimumFractionDigits: 2, maximumFractionDigits: 2 })}
          </span> (paper)
        </div>
      )}
    </Card>
  );
}

function RuleBlock({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-lg bg-bg-hover/40 border border-line/50 p-3">
      <div className="text-[10px] uppercase tracking-wide text-gray-500 mb-1.5">{title}</div>
      <ul className="space-y-1 text-xs text-gray-300 list-disc list-inside marker:text-gray-600">
        {children}
      </ul>
    </div>
  );
}
