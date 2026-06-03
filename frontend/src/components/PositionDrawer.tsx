import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { X } from "lucide-react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { api } from "@/lib/api";
import { Badge, Button, ErrorBox, Loading } from "@/components/ui";
import { cn, decisionColor, fmtPct, fmtUsd, fmtUsdSigned, pnlColor } from "@/lib/utils";

export default function PositionDrawer({
  positionId,
  onClose,
  onChanged,
}: {
  positionId: number;
  onClose: () => void;
  onChanged: () => void;
}) {
  const qc = useQueryClient();
  const detail = useQuery({
    queryKey: ["positionDetail", positionId],
    queryFn: () => api.positionDetail(positionId),
  });
  const [addAmt, setAddAmt] = useState(50000);

  const refetchAll = () => {
    qc.invalidateQueries({ queryKey: ["positionDetail", positionId] });
    onChanged();
  };
  const add = useMutation({
    mutationFn: () => api.positionAdd(positionId, addAmt),
    onSuccess: refetchAll,
  });
  const trim = useMutation({
    mutationFn: (fraction: number) => api.positionTrim(positionId, fraction),
    onSuccess: refetchAll,
  });

  const d = detail.data;
  const p = d?.position;
  const ai = d?.ai;
  const last = p?.current_price ?? 0;
  const target = ai?.target_6m_usd ?? null;
  const entry = p?.entry_price ?? 0;

  // Progress toward AI target (entry → target, where's price now)
  let targetProgress: number | null = null;
  if (target && entry && target !== entry) {
    targetProgress = Math.max(0, Math.min(100, ((last - entry) / (target - entry)) * 100));
  }
  const stop = p?.trailing_stop ?? p?.initial_stop;
  const distToStop = stop && last ? ((last - stop) / last) * 100 : null;

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-black/60" onClick={onClose}>
      <div
        className="h-full w-full max-w-2xl bg-bg-soft border-l border-line overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="sticky top-0 bg-bg-soft/95 backdrop-blur border-b border-line px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <span className="text-2xl font-extrabold font-mono">{p?.symbol}</span>
            {p?.decision_verdict && (
              <Badge className={decisionColor(p.decision_verdict)}>
                {p.decision_verdict === "MANUAL" ? "Manual" : `AI ${p.decision_verdict}`}
              </Badge>
            )}
          </div>
          <button onClick={onClose} className="text-gray-500 hover:text-white">
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="p-6">
          {detail.isLoading && <Loading />}
          {detail.error && <ErrorBox error={detail.error} />}

          {p && (
            <>
              {/* Key numbers */}
              <div className="grid grid-cols-3 gap-3 mb-5">
                <Mini label="Last" value={fmtUsd(last, 2)} />
                <Mini label="Day" value={p.day_change_pct != null ? fmtPct(p.day_change_pct) : "—"} cls={pnlColor(p.day_change_pct)} />
                <Mini label="Avg Cost" value={fmtUsd(entry, 2)} />
                <Mini label="Shares" value={p.units?.toFixed(2) ?? "—"} />
                <Mini label="Market Value" value={fmtUsd((p.units || 0) * last)} />
                <Mini
                  label="Total P&L"
                  value={`${fmtUsdSigned(p.current_pnl_usd)} (${fmtPct(p.current_pnl_pct)})`}
                  cls={pnlColor(p.current_pnl_usd)}
                />
              </div>

              {/* Price chart with entry / stop / target lines */}
              {d?.bars && d.bars.length > 1 && (
                <div className="card p-3 mb-5">
                  <div className="text-xs uppercase text-gray-500 mb-2">Price · last {d.bars.length}d</div>
                  <ResponsiveContainer width="100%" height={220}>
                    <AreaChart data={d.bars} margin={{ top: 5, right: 8, bottom: 0, left: 0 }}>
                      <defs>
                        <linearGradient id="pd" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="0%" stopColor="#2dd4bf" stopOpacity={0.3} />
                          <stop offset="100%" stopColor="#2dd4bf" stopOpacity={0} />
                        </linearGradient>
                      </defs>
                      <CartesianGrid stroke="#1e2a3d" strokeDasharray="3 3" />
                      <XAxis dataKey="date" tick={{ fill: "#64748b", fontSize: 10 }} minTickGap={40} />
                      <YAxis tick={{ fill: "#64748b", fontSize: 10 }} width={50} domain={["auto", "auto"]}
                        tickFormatter={(v) => `$${v.toFixed(0)}`} />
                      <Tooltip
                        contentStyle={{ background: "#111824", border: "1px solid #1e2a3d", borderRadius: 8, fontSize: 12 }}
                        formatter={(v: number) => [fmtUsd(v, 2), "Close"]}
                      />
                      <Area type="monotone" dataKey="close" stroke="#2dd4bf" strokeWidth={2} fill="url(#pd)" />
                      <ReferenceLine y={entry} stroke="#94a3b8" strokeDasharray="4 4"
                        label={{ value: "entry", fill: "#94a3b8", fontSize: 10, position: "insideTopLeft" }} />
                      {stop && <ReferenceLine y={stop} stroke="#f87171" strokeDasharray="4 4"
                        label={{ value: "stop", fill: "#f87171", fontSize: 10, position: "insideBottomLeft" }} />}
                      {target && <ReferenceLine y={target} stroke="#34d399" strokeDasharray="4 4"
                        label={{ value: "target", fill: "#34d399", fontSize: 10, position: "insideTopLeft" }} />}
                    </AreaChart>
                  </ResponsiveContainer>
                </div>
              )}

              {/* Risk row: distance to stop + progress to target */}
              <div className="grid grid-cols-2 gap-3 mb-5">
                <div className="card p-3">
                  <div className="text-xs uppercase text-gray-500 mb-1">Distance to stop</div>
                  <div className="text-lg font-bold stat-num text-warn">
                    {distToStop != null ? `${distToStop.toFixed(1)}%` : "—"}
                  </div>
                  <div className="text-xs text-gray-500">stop {fmtUsd(stop, 2)}</div>
                </div>
                <div className="card p-3">
                  <div className="text-xs uppercase text-gray-500 mb-1">Progress to AI target</div>
                  {target ? (
                    <>
                      <div className="flex items-center justify-between text-sm">
                        <span className="stat-num text-gray-300">{fmtUsd(target, 0)}</span>
                        <span className="text-xs text-gray-500">{ai?.upside_pct ? `${ai.upside_pct}% upside` : ""}</span>
                      </div>
                      <div className="h-2 bg-bg-hover rounded mt-1.5 overflow-hidden">
                        <div className="h-full bg-pos rounded" style={{ width: `${targetProgress ?? 0}%` }} />
                      </div>
                    </>
                  ) : (
                    <div className="text-sm text-gray-500">no AI target</div>
                  )}
                </div>
              </div>

              {/* Why I own this */}
              {ai && (ai.why_now || ai.exit_thesis) && (
                <div className="card p-4 mb-5">
                  <div className="text-sm font-semibold text-brand-glow mb-2">Why I own this</div>
                  {ai.conviction != null && (
                    <p className="text-xs text-gray-500 mb-2">
                      AI conviction at entry: {ai.conviction}/10 ·{" "}
                      {ai.decision_date && (
                        <Link to={`/decisions/${p.symbol}/${ai.decision_date}`} className="text-brand hover:text-brand-glow">
                          full dossier →
                        </Link>
                      )}
                    </p>
                  )}
                  {ai.why_now && <p className="text-sm text-gray-300 leading-relaxed mb-2">{ai.why_now}</p>}
                  {ai.exit_thesis && (
                    <p className="text-xs text-gray-400">
                      <span className="text-gray-500 uppercase">Exit when: </span>
                      {ai.exit_thesis}
                    </p>
                  )}
                </div>
              )}

              {/* Add / trim actions */}
              <div className="card p-4">
                <div className="text-sm font-semibold text-gray-200 mb-3">Manage position</div>
                <div className="flex items-center gap-2 mb-3">
                  <input
                    type="number"
                    value={addAmt}
                    step={5000}
                    onChange={(e) => setAddAmt(Number(e.target.value))}
                    className="bg-bg-soft border border-line rounded-lg px-3 py-1.5 text-sm w-32 stat-num focus:border-brand/50 outline-none"
                  />
                  <Button onClick={() => add.mutate()} disabled={add.isPending}>
                    {add.isPending ? "Buying…" : "Buy more"}
                  </Button>
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-xs text-gray-500 mr-1">Trim:</span>
                  {[0.25, 0.5, 0.75].map((f) => (
                    <Button key={f} variant="outline" onClick={() => trim.mutate(f)} disabled={trim.isPending}>
                      {f * 100}%
                    </Button>
                  ))}
                  <Button variant="danger" onClick={() => confirm(`Sell all of ${p.symbol}?`) && trim.mutate(1)} disabled={trim.isPending}>
                    Sell all
                  </Button>
                </div>
                {(add.error || trim.error) && (
                  <div className="mt-2"><ErrorBox error={add.error || trim.error} /></div>
                )}
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

function Mini({ label, value, cls }: { label: string; value: string; cls?: string }) {
  return (
    <div className="card p-3">
      <div className="text-xs uppercase text-gray-500">{label}</div>
      <div className={cn("text-base font-bold stat-num mt-0.5", cls)}>{value}</div>
    </div>
  );
}
