import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Clock, Layers, RefreshCw, TrendingUp } from "lucide-react";
import { api } from "@/lib/api";
import type { OptionPosition, StructurePosition } from "@/lib/types";
import { Badge, Button, Card, EmptyState, Loading, PageTitle, Spinner } from "@/components/ui";
import { cn } from "@/lib/utils";

function pnlCls(v?: number | null): string {
  if (v == null) return "text-gray-300";
  return v >= 0 ? "text-pos" : "text-neg";
}

export default function OptionsPositionsPage() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["optPositions"], queryFn: api.optionsPositions });
  const refresh = useMutation({
    mutationFn: api.optionsRefresh,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["optPositions"] }),
  });
  const closeOne = useMutation({
    mutationFn: (id: number) => api.optionsClose(id, "manual"),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["optPositions"] }),
  });

  const open = q.data?.open || [];
  const closed = q.data?.closed || [];
  const stats = q.data?.stats;
  const sleeve = q.data?.sleeve;

  return (
    <div>
      <PageTitle
        title="Straddle Positions"
        subtitle="Paper positions from the scanner. Values refresh each morning (09:15 ET); exit alerts fire on deadline day. Completely separate from the equity portfolio."
        actions={
          <Button variant="outline" onClick={() => refresh.mutate()} disabled={refresh.isPending}>
            {refresh.isPending ? <Spinner /> : <RefreshCw className="h-4 w-4" />}
            Update values
          </Button>
        }
      />

      {((stats && stats.trades > 0) || (sleeve && sleeve.count > 0)) && (
        <div className="mb-4 space-y-1">
          {stats && stats.trades > 0 && (
            <div className="text-sm text-gray-400">
              📈 {stats.trades} closed · win rate {stats.win_rate_pct ?? 0}% ·
              avg win {stats.avg_win_pct != null ? `+${stats.avg_win_pct}%` : "—"} ·
              avg loss {stats.avg_loss_pct != null ? `${stats.avg_loss_pct}%` : "—"} ·
              total <span className={pnlCls(stats.total_pnl_usd)}>
                ${stats.total_pnl_usd.toLocaleString()}
              </span> (paper)
            </div>
          )}
          {sleeve && sleeve.count > 0 && (
            <div className="text-xs text-gray-500">
              Sleeve in use: {sleeve.count} open · ${sleeve.capital.toLocaleString()} capital
              deployed (paper — fully separate from equity cash)
            </div>
          )}
        </div>
      )}

      {q.isLoading && <Loading />}

      <h2 className="text-sm font-semibold uppercase tracking-wide text-gray-400 mb-2">
        Open ({open.length})
      </h2>
      {open.length === 0 && !q.isLoading && (
        <Card className="mb-6">
          <EmptyState
            icon={<TrendingUp className="h-8 w-8" />}
            title="No open straddles"
            hint="Track a qualified candidate from the Scanner to start a paper position."
          />
        </Card>
      )}
      <div className="space-y-3 mb-8">
        {open.map((p) => (
          <OpenCard key={p.id} p={p} onClose={() => {
            if (confirm(`Close the ${p.symbol} straddle at current value?`)) closeOne.mutate(p.id);
          }} closing={closeOne.isPending} />
        ))}
      </div>

      <StructuresSection />

      {closed.length > 0 && (
        <>
          <h2 className="text-sm font-semibold uppercase tracking-wide text-gray-400 mb-2">
            History — straddles ({closed.length})
          </h2>
          <Card className="p-0 overflow-hidden">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-line bg-bg-soft text-xs text-gray-500">
                  <th className="text-left p-2">Symbol</th>
                  <th className="text-left p-2">Entry → Exit</th>
                  <th className="text-right p-2">Contracts</th>
                  <th className="text-right p-2">P&L $</th>
                  <th className="text-right p-2">P&L %</th>
                  <th className="text-left p-2 pl-4">Reason</th>
                </tr>
              </thead>
              <tbody>
                {closed.map((p) => (
                  <tr key={p.id} className="border-b border-line/40">
                    <td className="p-2 font-mono font-semibold">{p.symbol}</td>
                    <td className="p-2 text-xs text-gray-400">
                      {p.entry_date} → {p.exit_date}
                    </td>
                    <td className="p-2 text-right stat-num">{p.contracts}</td>
                    <td className={cn("p-2 text-right stat-num", pnlCls(p.final_pnl_usd))}>
                      {p.final_pnl_usd != null ? `${p.final_pnl_usd >= 0 ? "+" : ""}$${p.final_pnl_usd.toLocaleString()}` : "—"}
                    </td>
                    <td className={cn("p-2 text-right stat-num", pnlCls(p.final_pnl_pct))}>
                      {p.final_pnl_pct != null ? `${p.final_pnl_pct >= 0 ? "+" : ""}${p.final_pnl_pct}%` : "—"}
                    </td>
                    <td className="p-2 pl-4 text-xs text-gray-500">{p.exit_reason}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>
        </>
      )}
    </div>
  );
}

function OpenCard({ p, onClose, closing }: {
  p: OptionPosition; onClose: () => void; closing: boolean;
}) {
  const invested = (p.entry_cost || 0) * 100 * (p.contracts || 1);
  const deadline = p.exit_deadline ? p.exit_deadline.slice(0, 16).replace("T", " ") : "—";
  const daysLeft = p.exit_deadline
    ? Math.max(0, Math.ceil((new Date(p.exit_deadline).getTime() - Date.now()) / 86400000))
    : null;

  return (
    <Card className={cn("border-l-4", (p.pnl_usd ?? 0) >= 0 ? "border-pos/50" : "border-neg/50")}>
      <div className="flex items-center gap-2 flex-wrap mb-2">
        <span className="text-lg font-bold font-mono">{p.symbol}</span>
        <span className="text-sm text-gray-400">
          ${p.strike} straddle · {p.contracts} contract(s) · in for ${invested.toLocaleString(undefined, { maximumFractionDigits: 0 })}
        </span>
        <div className="flex-1" />
        {!!p.profit_alerted && (
          <Badge className="border-pos/40 bg-pos/10 text-pos">💰 take-profit suggested</Badge>
        )}
        {!!p.stop_alerted && (
          <Badge className="border-neg/40 bg-neg/10 text-neg">stop level hit</Badge>
        )}
        <Badge className="border-warn/40 bg-warn/10 text-warn">
          <Clock className="h-3 w-3 mr-1" />
          {daysLeft != null ? `exit in ${daysLeft}d` : "exit —"}
        </Badge>
      </div>

      <div className="flex items-baseline gap-3 mb-1">
        <span className="text-xl font-bold stat-num">
          {p.current_value != null ? `$${p.current_value.toFixed(2)}` : "—"}
        </span>
        <span className={cn("text-lg font-semibold stat-num", pnlCls(p.pnl_usd))}>
          {p.pnl_usd != null ? `${p.pnl_usd >= 0 ? "+" : ""}$${p.pnl_usd.toLocaleString()} (${(p.pnl_pct ?? 0) >= 0 ? "+" : ""}${p.pnl_pct}%)` : "not marked yet"}
        </span>
      </div>

      {(p.vega_pnl != null || p.theta_pnl != null) && (
        <div className="text-xs text-gray-400 mb-2">
          Why: IV run-up <span className={pnlCls(p.vega_pnl)}>{fmtD(p.vega_pnl)}</span> 💨 ·
          movement <span className={pnlCls(p.move_pnl)}>{fmtD(p.move_pnl)}</span> 🎢 ·
          time decay <span className={pnlCls(p.theta_pnl)}>{fmtD(p.theta_pnl)}</span> ⏳
          <span className="text-gray-600"> (estimates)</span>
        </div>
      )}

      <div className="flex items-center gap-3 text-xs text-gray-500 border-t border-line/50 pt-2">
        <span>earnings {p.earnings_date}</span>
        <span className="text-warn font-semibold">HARD EXIT {deadline} ET</span>
        <span>{p.notes}</span>
        <div className="flex-1" />
        <Button variant="danger" onClick={onClose} disabled={closing}>
          Close position
        </Button>
      </div>
    </Card>
  );
}

function fmtD(v?: number | null): string {
  if (v == null) return "—";
  return `${v >= 0 ? "+" : ""}$${Math.abs(v) >= 100 ? v.toFixed(0) : v.toFixed(2)}`;
}

// ── Multi-leg structures (condors, spreads — from the Strategy Board) ──────

function legsSummary(p: StructurePosition): string {
  return p.legs
    .map((l) => `${l.side > 0 ? "+" : "-"}${l.qty > 1 ? l.qty : ""}${l.contract_type === "call" ? "C" : "P"}${l.strike}`)
    .join(" / ");
}

function StructuresSection() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["optStructures"], queryFn: api.optionsStructures });
  const refresh = useMutation({
    mutationFn: api.optionsStructuresRefresh,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["optStructures"] }),
  });
  const closeOne = useMutation({
    mutationFn: (id: number) => api.optionsStructureClose(id, "manual"),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["optStructures"] }),
  });

  const open = q.data?.open || [];
  const closed = q.data?.closed || [];
  if (q.isLoading || (open.length === 0 && closed.length === 0)) return null;

  return (
    <div className="mb-8">
      <div className="flex items-center gap-3 mb-2 flex-wrap">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-gray-400">
          Multi-leg structures ({open.length} open)
        </h2>
        <div className="flex-1" />
        <Button variant="outline" onClick={() => refresh.mutate()} disabled={refresh.isPending}>
          {refresh.isPending ? <Spinner /> : <RefreshCw className="h-4 w-4" />}
          Update values
        </Button>
      </div>
      <div className="space-y-3">
        {open.map((p) => (
          <Card key={p.id} className={cn("border-l-4",
            (p.pnl_usd ?? 0) >= 0 ? "border-pos/50" : "border-neg/50")}>
            <div className="flex items-center gap-2 flex-wrap mb-1.5">
              <Layers className="h-4 w-4 text-gray-500" />
              <span className="text-lg font-bold font-mono">{p.symbol}</span>
              <span className="text-sm text-gray-400">
                {p.strategy_key.replace(/_/g, " ")} · {legsSummary(p)} · exp {p.legs[0]?.expiry}
              </span>
              <div className="flex-1" />
              {p.exit_deadline && (
                <Badge className="border-warn/40 bg-warn/10 text-warn">
                  <Clock className="h-3 w-3 mr-1" />
                  exit {p.exit_deadline.slice(0, 16).replace("T", " ")} ET
                </Badge>
              )}
            </div>
            <div className="flex items-baseline gap-3 flex-wrap text-sm">
              <span>
                {(p.entry_value ?? 0) < 0
                  ? <>collected <b className="text-pos">${(Math.abs(p.entry_value!) * 100).toFixed(0)}</b>/set</>
                  : <>paid <b className="text-gray-200">${((p.entry_value ?? 0) * 100).toFixed(0)}</b>/set</>}
              </span>
              <span className="text-gray-500">
                worst case ${((p.capital_at_risk ?? 0) * 100).toFixed(0)}
              </span>
              {p.pop_est != null && <span className="text-gray-500">odds ≈{p.pop_est}%</span>}
              <span className={cn("font-semibold stat-num", pnlCls(p.pnl_usd))}>
                {p.pnl_usd != null
                  ? `${p.pnl_usd >= 0 ? "+" : ""}$${p.pnl_usd.toLocaleString()} (${(p.pnl_pct_on_risk ?? 0) >= 0 ? "+" : ""}${p.pnl_pct_on_risk ?? 0}% on risk)`
                  : "not marked yet"}
              </span>
              <div className="flex-1" />
              <Button variant="danger" disabled={closeOne.isPending} onClick={() => {
                if (confirm(`Close the ${p.symbol} ${p.strategy_key.replace(/_/g, " ")} at current value?`)) closeOne.mutate(p.id);
              }}>
                Close position
              </Button>
            </div>
          </Card>
        ))}
      </div>

      {closed.length > 0 && (
        <>
          <h3 className="text-xs font-semibold uppercase tracking-wide text-gray-500 mt-4 mb-2">
            History — structures ({closed.length})
          </h3>
          <Card className="p-0 overflow-hidden">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-line bg-bg-soft text-xs text-gray-500">
                  <th className="text-left p-2">Symbol</th>
                  <th className="text-left p-2">Strategy</th>
                  <th className="text-left p-2">Entry → Exit</th>
                  <th className="text-right p-2">P&L $</th>
                  <th className="text-right p-2">On risk</th>
                  <th className="text-left p-2 pl-4">Reason</th>
                </tr>
              </thead>
              <tbody>
                {closed.map((p) => (
                  <tr key={p.id} className="border-b border-line/40">
                    <td className="p-2 font-mono font-semibold">{p.symbol}</td>
                    <td className="p-2 text-xs text-gray-400">{p.strategy_key.replace(/_/g, " ")}</td>
                    <td className="p-2 text-xs text-gray-400">{p.entry_date} → {p.exit_date}</td>
                    <td className={cn("p-2 text-right stat-num", pnlCls(p.final_pnl_usd))}>
                      {p.final_pnl_usd != null
                        ? `${p.final_pnl_usd >= 0 ? "+" : ""}$${p.final_pnl_usd.toLocaleString()}`
                        : "unpriced"}
                    </td>
                    <td className={cn("p-2 text-right stat-num", pnlCls(p.final_pnl_pct_on_risk))}>
                      {p.final_pnl_pct_on_risk != null
                        ? `${p.final_pnl_pct_on_risk >= 0 ? "+" : ""}${p.final_pnl_pct_on_risk}%`
                        : "—"}
                    </td>
                    <td className="p-2 pl-4 text-xs text-gray-500">{p.exit_reason}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>
        </>
      )}
    </div>
  );
}
