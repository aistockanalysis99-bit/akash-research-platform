import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CircleDollarSign, Plus, RotateCw } from "lucide-react";
import { api } from "@/lib/api";
import { Badge, Button, Card, EmptyState, ErrorBox, Loading, PageTitle, Spinner } from "@/components/ui";
import { cn } from "@/lib/utils";

type Wheel = Awaited<ReturnType<typeof api.optionsWheels>>["wheels"][number];

const STATE_STYLE: Record<string, string> = {
  CASH: "border-brand/40 bg-brand/10 text-brand",
  CSP_OPEN: "border-warn/40 bg-warn/10 text-warn",
  HOLDING: "border-pos/40 bg-pos/10 text-pos",
  CC_OPEN: "border-warn/40 bg-warn/10 text-warn",
  COMPLETE: "border-line bg-bg-hover text-gray-300",
  ABANDONED: "border-line bg-bg-hover text-gray-500",
};
const STATE_LABEL: Record<string, string> = {
  CASH: "CASH — ready to sell a put",
  CSP_OPEN: "PUT OPEN — waiting on expiry",
  HOLDING: "HOLDING STOCK — ready to sell a call",
  CC_OPEN: "CALL OPEN — waiting on expiry",
  COMPLETE: "CYCLE COMPLETE",
  ABANDONED: "CLOSED (no exit)",
};

export default function WheelPage() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["optWheels"], queryFn: api.optionsWheels });
  const [newSym, setNewSym] = useState("");
  const start = useMutation({
    mutationFn: () => api.optionsWheelStart(newSym.trim().toUpperCase(), 1),
    onSuccess: () => { setNewSym(""); qc.invalidateQueries({ queryKey: ["optWheels"] }); },
  });

  const wheels = q.data?.wheels || [];
  const active = wheels.filter((w) => !["COMPLETE", "ABANDONED"].includes(w.state));
  const done = wheels.filter((w) => ["COMPLETE", "ABANDONED"].includes(w.state));

  return (
    <div className="max-w-4xl mx-auto">
      <PageTitle
        title="The Wheel"
        subtitle="One capital commitment cycling: get paid to wait → own at a discount → rent it out → get called away. You confirm every outcome from your broker — the platform tracks the true cost basis and books the full-cycle return."
        actions={
          <div className="flex items-center gap-2">
            <input
              value={newSym} onChange={(e) => setNewSym(e.target.value)}
              placeholder="Symbol…" maxLength={6}
              className="w-24 bg-bg-soft border border-line rounded-lg px-2 py-1.5 text-sm font-mono uppercase focus:border-brand/50 outline-none"
            />
            <Button onClick={() => start.mutate()} disabled={!newSym.trim() || start.isPending}>
              {start.isPending ? <Spinner /> : <Plus className="h-4 w-4" />} Start wheel
            </Button>
          </div>
        }
      />
      {start.error && <ErrorBox error={start.error} />}
      {q.error && <ErrorBox error={q.error} />}
      {q.isLoading && <Loading />}

      {!q.isLoading && wheels.length === 0 && (
        <Card>
          <EmptyState
            icon={<RotateCw className="h-8 w-8" />}
            title="No wheels yet"
            hint="Start one on a stock the AI would own (Pool C) — the suggestion engine picks the strike from the AI's own levels."
          />
        </Card>
      )}

      {active.length > 0 && (
        <div className="space-y-4 mb-8">
          {active.map((w) => <WheelCard key={w.id} w={w} />)}
        </div>
      )}

      {done.length > 0 && (
        <>
          <h2 className="text-sm font-semibold uppercase tracking-wide text-gray-400 mb-2">
            Completed cycles ({done.length})
          </h2>
          <Card className="p-0 overflow-hidden">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-line bg-bg-soft text-xs text-gray-500">
                  <th className="text-left p-2">Symbol</th>
                  <th className="text-left p-2">State</th>
                  <th className="text-right p-2">Premiums</th>
                  <th className="text-right p-2">Cycle ROI</th>
                  <th className="text-left p-2 pl-4">Started → Done</th>
                </tr>
              </thead>
              <tbody>
                {done.map((w) => (
                  <tr key={w.id} className="border-b border-line/40">
                    <td className="p-2 font-mono font-semibold">{w.symbol}</td>
                    <td className="p-2 text-xs text-gray-400">{w.state}</td>
                    <td className="p-2 text-right stat-num">${((w.premiums_net || 0) * 100 * (w.qty || 1)).toFixed(0)}</td>
                    <td className={cn("p-2 text-right stat-num font-semibold",
                      (w.cycle_roi_pct ?? 0) >= 0 ? "text-pos" : "text-neg")}>
                      {w.cycle_roi_pct != null ? `${w.cycle_roi_pct >= 0 ? "+" : ""}${w.cycle_roi_pct}%` : "—"}
                    </td>
                    <td className="p-2 pl-4 text-xs text-gray-500">
                      {(w.started_at || "").slice(0, 10)} → {(w.completed_at || "").slice(0, 10)}
                    </td>
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

function WheelCard({ w }: { w: Wheel }) {
  const qc = useQueryClient();
  const invalidate = () => qc.invalidateQueries({ queryKey: ["optWheels"] });
  const openLeg = w.legs.find((l) => !l.outcome);
  const resting = w.state === "CASH" || w.state === "HOLDING";

  return (
    <Card className="border-l-4 border-brand/50">
      <div className="flex items-center gap-2 flex-wrap mb-2">
        <CircleDollarSign className="h-4 w-4 text-brand" />
        <span className="text-lg font-bold font-mono">{w.symbol}</span>
        <Badge className={cn("text-[10px]", STATE_STYLE[w.state])}>
          {STATE_LABEL[w.state] || w.state}
        </Badge>
        <div className="flex-1" />
        <span className="text-xs text-gray-500">wheel #{w.id} · {w.qty} contract(s)</span>
      </div>

      <div className="flex items-baseline gap-4 flex-wrap text-sm mb-3">
        <span className="text-gray-400">
          premiums banked <b className="text-pos">${((w.premiums_net || 0) * 100 * (w.qty || 1)).toFixed(0)}</b>
        </span>
        {w.assigned_price != null && (
          <span className="text-gray-400">
            assigned at <b className="text-gray-200">${w.assigned_price}</b> ·
            true basis <b className="text-brand">${w.effective_basis}</b>
          </span>
        )}
        {w.capital_per_share != null && (
          <span className="text-gray-500">capital ${(w.capital_per_share * 100 * (w.qty || 1)).toLocaleString()}</span>
        )}
      </div>

      {w.legs.length > 0 && (
        <div className="overflow-x-auto mb-3">
          <table className="text-xs min-w-[460px]">
            <tbody>
              {w.legs.map((l) => (
                <tr key={l.id} className="text-gray-300">
                  <td className="pr-3 py-0.5 text-gray-500">#{l.seq}</td>
                  <td className="pr-3 font-semibold">{l.kind.toUpperCase()}</td>
                  <td className="pr-3 font-mono">${l.strike} · {l.expiry}</td>
                  <td className="pr-3 stat-num text-pos">+${(l.premium * 100).toFixed(0)}</td>
                  <td className="pr-3">
                    {l.outcome
                      ? <span className="text-gray-500">{l.outcome}{l.close_price != null ? ` @ $${l.close_price}` : ""}</span>
                      : <ResolveButtons wheelId={w.id} leg={l} onDone={invalidate} />}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {resting && <NextAction w={w} onDone={invalidate} />}
    </Card>
  );
}

function ResolveButtons({ wheelId, leg, onDone }: {
  wheelId: number; leg: Wheel["legs"][number]; onDone: () => void;
}) {
  const [buyback, setBuyback] = useState("");
  const resolve = useMutation({
    mutationFn: (p: { outcome: string; close_price?: number }) =>
      api.optionsWheelResolve(wheelId, leg.id, p.outcome, p.close_price),
    onSuccess: onDone,
  });
  const final = leg.kind === "csp"
    ? { label: "Assigned", outcome: "assigned" }
    : { label: "Called away", outcome: "called_away" };
  return (
    <span className="inline-flex items-center gap-1.5 flex-wrap">
      <button className="text-brand hover:underline" disabled={resolve.isPending}
        onClick={() => resolve.mutate({ outcome: "expired" })}>Expired</button>
      <button className="text-warn hover:underline" disabled={resolve.isPending}
        onClick={() => resolve.mutate({ outcome: final.outcome })}>{final.label}</button>
      <input value={buyback} onChange={(e) => setBuyback(e.target.value)}
        placeholder="buyback $" className="w-16 bg-bg-soft border border-line rounded px-1 py-0.5 text-[11px] stat-num outline-none" />
      <button className="text-gray-400 hover:underline" disabled={resolve.isPending || !buyback}
        onClick={() => resolve.mutate({ outcome: "closed_early", close_price: Number(buyback) })}>
        Closed early
      </button>
      {resolve.error && <span className="text-neg">{(resolve.error as Error).message.slice(0, 60)}</span>}
    </span>
  );
}

function NextAction({ w, onDone }: { w: Wheel; onDone: () => void }) {
  const [sug, setSug] = useState<Awaited<ReturnType<typeof api.optionsWheelSuggest>> | null>(null);
  const suggest = useMutation({
    mutationFn: () => api.optionsWheelSuggest(w.id),
    onSuccess: (d) => setSug(d),
  });
  const record = useMutation({
    mutationFn: () => {
      const s = sug?.suggestion;
      if (!s?.ok) throw new Error("no suggestion");
      return api.optionsWheelLeg(w.id, sug!.kind!, s.strike!, s.expiry!, s.premium!);
    },
    onSuccess: () => { setSug(null); onDone(); },
  });

  return (
    <div className="border-t border-line/50 pt-2">
      {!sug && (
        <Button variant="outline" onClick={() => suggest.mutate()} disabled={suggest.isPending}>
          {suggest.isPending ? <Spinner /> : <RotateCw className="h-4 w-4" />}
          Suggest next {w.state === "CASH" ? "put" : "call"} (AI levels)
        </Button>
      )}
      {suggest.error && <ErrorBox error={suggest.error} />}
      {sug && (
        <div className="text-sm text-gray-300">
          {sug.suggestion?.ok ? (
            <>
              Sell the <b className="font-mono">${sug.suggestion.strike} {sug.kind === "csp" ? "put" : "call"}</b>{" "}
              exp {sug.suggestion.expiry} → collect ≈
              <b className="text-pos"> ${sug.suggestion.premium_usd_per_contract?.toLocaleString()}</b>/contract
              {sug.suggestion.annualized_pct != null && <> · {sug.suggestion.annualized_pct}% annualized</>}
              <span className="text-gray-500"> · verify in broker, then</span>{" "}
              <button className="text-brand hover:underline" disabled={record.isPending}
                onClick={() => record.mutate()}>
                record it on the wheel
              </button>
              {record.error && <span className="text-neg text-xs ml-2">{(record.error as Error).message.slice(0, 60)}</span>}
            </>
          ) : (
            <span className="text-gray-500">No trade suggested: {sug.suggestion?.reason || sug.note}</span>
          )}
        </div>
      )}
    </div>
  );
}
