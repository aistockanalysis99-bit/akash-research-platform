import { useState } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ClipboardList, RefreshCw, ShieldCheck, Star } from "lucide-react";
import { api } from "@/lib/api";
import { Badge, Button, Card, EmptyState, ErrorBox, Loading, PageTitle, Spinner } from "@/components/ui";
import { cn } from "@/lib/utils";

type Board = Awaited<ReturnType<typeof api.optionsBoard>>;
type BoardCard = Board["cards"][number];

export default function StrategyBoardPage() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["optBoard"], queryFn: api.optionsBoard });
  const refresh = useMutation({
    mutationFn: () => api.optionsBoardRefresh(),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["optBoard"] }),
  });

  const cards = q.data?.cards || [];
  const straddles = cards.filter((c) => c.strategy_key === "long_straddle");
  const condors = cards.filter((c) => c.strategy_key === "iron_condor");

  return (
    <div>
      <PageTitle
        title="Strategy Board"
        subtitle="Every stock where a rulebook strategy fired today — with the complete trade, not a label. Quotes are ~15-min delayed: always verify prices in your broker before entering. Suggest-only; you decide."
        actions={
          <Button onClick={() => refresh.mutate()} disabled={refresh.isPending}>
            {refresh.isPending ? <Spinner /> : <RefreshCw className="h-4 w-4" />}
            {refresh.isPending ? "Building…" : "Rebuild board"}
          </Button>
        }
      />

      <div className="text-xs text-gray-500 mb-4">
        {q.data?.board_date ? `Board date: ${q.data.board_date}` : "No board yet"} ·
        rebuilds 17:05 ET weekdays after the scan ·
        rules on the <Link to="/options/rulebook" className="text-brand hover:underline">Rulebook</Link> page
      </div>

      {refresh.error && <ErrorBox error={refresh.error} />}
      {q.error && <ErrorBox error={q.error} />}
      {q.isLoading && <Loading />}

      {!q.isLoading && cards.length === 0 && (
        <Card>
          <EmptyState
            icon={<ClipboardList className="h-8 w-8" />}
            title="No strategy fired today"
            hint="That's the discipline working — the board only shows names whose explicit rule conditions are met. Check the Scanner's reject reasons to see what came close."
          />
        </Card>
      )}

      {condors.length > 0 && (
        <BoardSection
          title={`Iron condors — sell the overpriced move (${condors.length})`}
          hint="Defined risk: worst case is fixed at entry. Hold through the print; exit the morning after."
        >
          {condors.map((c) => <CondorCard key={c.id} c={c} />)}
        </BoardSection>
      )}

      {straddles.length > 0 && (
        <BoardSection
          title={`Straddles — buy the underpriced move (${straddles.length})`}
          hint="Exit before the print, always — the hard deadline is set when you track."
        >
          {straddles.map((c) => <StraddleCard key={c.id} c={c} />)}
        </BoardSection>
      )}
    </div>
  );
}

function BoardSection({ title, hint, children }: {
  title: string; hint: string; children: React.ReactNode;
}) {
  return (
    <div className="mb-8">
      <h2 className="text-sm font-semibold uppercase tracking-wide text-gray-400">{title}</h2>
      <p className="text-xs text-gray-500 mb-3">{hint}</p>
      <div className="space-y-3">{children}</div>
    </div>
  );
}

function RulesFired({ rules }: { rules?: string[] }) {
  if (!rules?.length) return null;
  return (
    <div className="flex items-start gap-2 text-xs text-gray-400 mb-3">
      <ShieldCheck className="h-3.5 w-3.5 text-brand shrink-0 mt-0.5" />
      <span>Fired because: {rules.join(" · ")}</span>
    </div>
  );
}

function TrackControl({ boardId, invalidate }: { boardId: number; invalidate: string[] }) {
  const qc = useQueryClient();
  const [contracts, setContracts] = useState(1);
  const track = useMutation({
    mutationFn: () => api.optionsBoardTrack(boardId, contracts),
    onSuccess: () => invalidate.forEach((k) => qc.invalidateQueries({ queryKey: [k] })),
  });
  return (
    <div className="flex items-center gap-2 flex-wrap">
      <label className="text-xs text-gray-500">Contracts</label>
      <input
        type="number" min={1} max={100} value={contracts}
        onChange={(e) => setContracts(Math.max(1, Number(e.target.value)))}
        className="w-16 bg-bg-soft border border-line rounded-lg px-2 py-1 text-sm stat-num focus:border-brand/50 outline-none"
      />
      <Button onClick={() => track.mutate()} disabled={track.isPending || track.isSuccess}>
        {track.isSuccess ? "Tracking ✓" : track.isPending ? <Spinner /> : "▶ Track it (paper)"}
      </Button>
      <span className="text-[11px] text-gray-500">verify prices in your broker first</span>
      {track.error && (
        <span className="text-xs text-neg">{(track.error as Error).message.slice(0, 90)}</span>
      )}
    </div>
  );
}

function Stat({ label, value, cls }: { label: string; value: React.ReactNode; cls?: string }) {
  return (
    <div className="rounded-lg bg-bg-hover/50 px-2.5 py-1.5">
      <div className="text-[10px] uppercase text-gray-500">{label}</div>
      <div className={cn("text-sm stat-num font-semibold", cls || "text-gray-200")}>{value}</div>
    </div>
  );
}

function CondorCard({ c }: { c: BoardCard }) {
  const credit = (c.credit || 0) * 100;
  const maxLoss = Math.abs(c.max_loss || 0) * 100;
  return (
    <Card className="border-l-4 border-brand/50">
      <div className="flex items-center gap-2 flex-wrap mb-2">
        <span className="text-lg font-bold font-mono">{c.symbol}</span>
        <span className="text-sm text-gray-400">
          earnings {c.earnings_date} · {c.days_to_earnings}d out · exp {c.expiry}
        </span>
        <Badge className="border-brand/40 bg-brand/10 text-brand">defined risk</Badge>
      </div>

      <RulesFired rules={c.rules_fired} />

      <div className="grid grid-cols-2 sm:grid-cols-5 gap-2 mb-3">
        <Stat label="Collect (credit)" value={`$${credit.toLocaleString(undefined, { maximumFractionDigits: 0 })}/set`} cls="text-pos" />
        <Stat label="Worst case" value={`-$${maxLoss.toLocaleString(undefined, { maximumFractionDigits: 0 })}`} cls="text-neg" />
        <Stat label="Odds (est.)" value={c.pop_est != null ? `≈${c.pop_est}%` : "—"} />
        <Stat label="Return on risk" value={c.return_on_risk_pct != null ? `${c.return_on_risk_pct}%` : "—"} />
        <Stat label="Profit range" value={c.breakevens?.length === 2 ? `$${c.breakevens[0]}–$${c.breakevens[1]}` : "—"} />
      </div>

      {c.legs && (
        <div className="overflow-x-auto mb-3">
          <table className="text-xs min-w-[420px]">
            <tbody>
              {c.legs.map((l, i) => (
                <tr key={i} className="text-gray-300">
                  <td className={cn("pr-3 py-0.5 font-semibold", l.side > 0 ? "text-pos" : "text-neg")}>
                    {l.side > 0 ? "BUY" : "SELL"}
                  </td>
                  <td className="pr-3 font-mono">${l.strike} {l.contract_type}</td>
                  <td className="pr-3 stat-num">${l.price}</td>
                  <td className="pr-3 text-gray-500">Δ {l.delta != null ? l.delta.toFixed(2) : "—"}</td>
                  <td className="text-gray-500">OI {l.oi?.toLocaleString?.() ?? l.oi}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div className="text-xs text-gray-500 mb-3">
        Implied ±{c.implied_move_pct}% vs normal ±{c.hist_median_move_pct}% ·
        {" "}{c.exit_rule}
      </div>

      <CondorHistory symbol={c.symbol} />

      <TrackControl boardId={c.id} invalidate={["optBoard", "optStructures"]} />
    </Card>
  );
}

/** Layer 2 on demand: what this exact rule did on this stock's real past
 * earnings. Loaded only when asked — a condor backtest costs API budget. */
function CondorHistory({ symbol }: { symbol: string }) {
  const [wanted, setWanted] = useState(false);
  const q = useQuery({
    queryKey: ["condorBt", symbol],
    queryFn: () => api.optionsCondorBacktest(symbol),
    enabled: wanted,
    staleTime: 24 * 3600 * 1000,
  });

  if (!wanted) {
    return (
      <button
        onClick={() => setWanted(true)}
        className="text-xs text-gray-400 hover:text-brand transition-colors mb-3 block"
      >
        📜 Load this rule's history on {symbol} (real past option prices)
      </button>
    );
  }
  if (q.isLoading) return <div className="text-xs text-gray-500 mb-3">Backtesting {symbol} on real historical option prices…</div>;
  const s = q.data?.summary;
  if (q.error || q.data?.error || !s) {
    return <div className="text-xs text-gray-500 mb-3">History unavailable: {q.data?.error || (q.error as Error)?.message?.slice(0, 60) || "no data"}</div>;
  }
  return (
    <div className="text-xs text-gray-300 mb-3 rounded-lg bg-bg-hover/40 border border-line/50 px-3 py-2">
      This rule on {symbol}, last {s.events_priced} priced events:{" "}
      {s.rule_fired_events > 0 ? (
        <>
          fired {s.rule_fired_events}×, won{" "}
          <b className={s.fired_win_rate_pct != null && s.fired_win_rate_pct >= 50 ? "text-pos" : "text-neg"}>
            {s.fired_win_rate_pct ?? "—"}%
          </b>
          , avg{" "}
          <b className={(s.fired_avg_return_on_risk_pct ?? 0) >= 0 ? "text-pos" : "text-neg"}>
            {(s.fired_avg_return_on_risk_pct ?? 0) >= 0 ? "+" : ""}
            {s.fired_avg_return_on_risk_pct ?? "—"}%
          </b>{" "}
          on risk
        </>
      ) : (
        <>the rule never fired historically on this name — today's setup is its first</>
      )}
      <span className="text-gray-500"> · real expired-contract prices, no simulation</span>
    </div>
  );
}

function StraddleCard({ c }: { c: BoardCard }) {
  const cost = (c.straddle_cost || 0) * 100;
  return (
    <Card className="border-l-4 border-pos/50">
      <div className="flex items-center gap-2 flex-wrap mb-2">
        <span className="text-lg font-bold font-mono">{c.symbol}</span>
        <span className="text-sm text-gray-400">
          earnings {c.earnings_date} · {c.days_to_earnings}d out
        </span>
        {!!c.dual_signal && (
          <Badge className="border-brand/40 bg-brand/10 text-brand">
            <Star className="h-3 w-3 mr-1" /> DUAL SIGNAL — 7+ AI pick
          </Badge>
        )}
      </div>
      <RulesFired rules={c.rules_fired} />
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 mb-3">
        <Stat label="Implied move" value={`±${c.implied_move_pct ?? "—"}%`} />
        <Stat label="Historical" value={`±${c.hist_median_move_pct ?? "—"}%`} />
        <Stat label="Cheapness" value={c.cheapness ?? "—"} cls="text-pos" />
        <Stat label="Cost / contract" value={`$${cost.toLocaleString(undefined, { maximumFractionDigits: 0 })}`} />
      </div>
      <div className="text-xs text-gray-500 mb-3">
        Buy ${c.strike} call + ${c.strike} put · exp {c.expiry} · {c.exit_rule}
      </div>
      <TrackControl boardId={c.id} invalidate={["optBoard", "optPositions"]} />
    </Card>
  );
}
