import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Layers, Play, Search } from "lucide-react";
import { api } from "@/lib/api";
import { Badge, Button, Card, ErrorBox, PageTitle, Spinner } from "@/components/ui";
import { cn } from "@/lib/utils";

const AGENTS: { key: string; label: string }[] = [
  { key: "fundamental", label: "Fundamental" },
  { key: "news", label: "News" },
  { key: "technical", label: "Technical" },
  { key: "institutional_flow", label: "Institutional Flow" },
  { key: "options_structure", label: "Options Structure" },
  { key: "macro_regime", label: "Macro Regime" },
  { key: "bull", label: "Bull" },
  { key: "bear", label: "Bear" },
  { key: "judge", label: "Judge" },
  { key: "risk", label: "Risk Manager" },
  { key: "pm", label: "Portfolio Manager" },
];

function verdictCls(v?: string): string {
  const u = (v || "").toUpperCase();
  if (u.includes("APPROVE") || u.includes("BUY")) return "border-pos/40 bg-pos/10 text-pos";
  if (u.includes("RESIZE") || u.includes("WATCH")) return "border-warn/40 bg-warn/10 text-warn";
  if (u.includes("REJECT") || u.includes("AVOID")) return "border-neg/40 bg-neg/10 text-neg";
  return "border-line bg-bg-hover text-gray-300";
}

export default function PipelineBakeoffPage() {
  const qc = useQueryClient();
  const [ticker, setTicker] = useState("");
  const [jobId, setJobId] = useState<string | null>(null);

  const stacksQ = useQuery({ queryKey: ["bakeoffStacks"], queryFn: api.compareStacks });
  const availStacks = stacksQ.data || [];
  const [picked, setPicked] = useState<Record<string, boolean>>({});
  const isOn = (s: { key: string; default: boolean }) => picked[s.key] ?? s.default;
  const selected = availStacks.filter(isOn).map((s) => s.key);

  const start = useMutation({
    mutationFn: () => api.compareFullStart(ticker.trim().toUpperCase(), selected),
    onSuccess: (r) => setJobId(r.job_id),
  });

  const job = useQuery({
    queryKey: ["bakeoff", jobId],
    queryFn: () => api.compareFullStatus(jobId as string),
    enabled: !!jobId,
    refetchInterval: (q) => {
      const s = q.state.data?.status;
      return s === "complete" || s === "failed" ? false : 5000;
    },
  });

  const history = useQuery({ queryKey: ["bakeoffHistory"], queryFn: api.compareHistory });
  const scorecard = useQuery({ queryKey: ["bakeoffScorecard"], queryFn: api.compareScorecard });

  const data = job.data;

  // When a run finishes, refresh the accumulated scorecard + history.
  useEffect(() => {
    if (data?.status === "complete") {
      qc.invalidateQueries({ queryKey: ["bakeoffHistory"] });
      qc.invalidateQueries({ queryKey: ["bakeoffScorecard"] });
    }
  }, [data?.status, qc]);
  const running = !!jobId && data?.status !== "complete" && data?.status !== "failed";
  const stacks = data?.stacks || [];

  return (
    <div>
      <PageTitle
        title="Full-Pipeline Bake-off"
        subtitle="Run the ENTIRE 11-agent pipeline end-to-end on each model — Production (Gemini+Claude) vs DeepSeek-R1, GLM-5.2, Qwen — and compare agent-by-agent. The real test before buying a DGX."
      />

      <Card className="mb-5">
        <div className="flex items-center gap-2 flex-wrap">
          <div className="relative flex-1 min-w-[200px]">
            <Search className="h-4 w-4 text-gray-500 absolute left-3 top-1/2 -translate-y-1/2" />
            <input
              value={ticker}
              onChange={(e) => setTicker(e.target.value.toUpperCase())}
              onKeyDown={(e) => e.key === "Enter" && ticker.trim() && !running && start.mutate()}
              placeholder="Ticker, e.g. NVDA"
              autoComplete="off"
              spellCheck={false}
              className="w-full bg-bg-soft border border-line rounded-lg pl-9 pr-3 py-2 text-sm font-mono uppercase placeholder:font-sans placeholder:normal-case focus:border-brand/50 outline-none"
            />
          </div>
          <Button onClick={() => start.mutate()} disabled={!ticker.trim() || running || start.isPending || selected.length === 0}>
            {running || start.isPending ? <Spinner /> : <Play className="h-4 w-4" />}
            {running ? "Running…" : "Run bake-off"}
          </Button>
        </div>

        {/* Model picker — choose which stacks to run */}
        <div className="flex flex-wrap gap-2 mt-3">
          {availStacks.map((s) => {
            const on = isOn(s);
            const costly = s.key === "fugu-ultra";
            return (
              <button
                key={s.key}
                onClick={() => setPicked((p) => ({ ...p, [s.key]: !on }))}
                disabled={running}
                className={cn(
                  "inline-flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-xs transition-colors disabled:opacity-50",
                  on ? "border-brand/50 bg-brand/10 text-brand" : "border-line text-gray-500 hover:text-gray-300"
                )}
                title={costly ? "Premium + slow — most expensive stack" : undefined}
              >
                <span className={cn("h-3.5 w-3.5 rounded-sm border flex items-center justify-center",
                  on ? "border-brand bg-brand/20" : "border-gray-600")}>
                  {on && "✓"}
                </span>
                {s.name.split(" (")[0]}
                {costly && <span className="text-[10px] text-warn">$$</span>}
              </button>
            );
          })}
        </div>
        {selected.length === 0 && (
          <div className="text-xs text-warn mt-2">Select at least one model.</div>
        )}
        {running && (
          <div className="text-xs text-gray-500 mt-3 animate-pulse">
            Running the full 11-agent pipeline on 4 model stacks for {data?.symbol}… this takes
            ~5–15 min (DeepSeek is slow). They run in parallel — leave this open.
          </div>
        )}
        {start.error && <div className="mt-2"><ErrorBox error={start.error} /></div>}
      </Card>

      {data?.status === "failed" && (
        <ErrorBox error={new Error(data.error || "bake-off failed")} />
      )}

      {data?.status === "complete" && stacks.length > 0 && (
        <>
          {/* Verdict summary cards */}
          <div className="flex items-baseline gap-3 mb-2 flex-wrap">
            <h2 className="text-lg font-bold text-white font-mono">{data.symbol}</h2>
            <span className="text-xs text-gray-500">
              total cost <span className="font-mono text-gray-300">${data.total_cost_usd?.toFixed(3)}</span>
            </span>
          </div>
          <div className="grid gap-3 mb-6" style={{ gridTemplateColumns: `repeat(${stacks.length}, minmax(0,1fr))` }}>
            {stacks.map((s) => (
              <Card key={s.name} className={cn(s.model === "production" && "border-brand/40")}>
                <div className="text-sm font-bold text-white">{s.name}</div>
                {!s.ok ? (
                  <div className="text-xs text-neg mt-2">Failed: {s.error || "no verdict"}</div>
                ) : (
                  <>
                    <div className="flex items-center gap-2 mt-2 mb-2 flex-wrap">
                      <Badge className={cn("font-bold", verdictCls(s.decision))}>{s.decision || "—"}</Badge>
                      <Badge className="border-line bg-bg-hover text-gray-300">{s.conviction ?? "—"}/10</Badge>
                    </div>
                    <div className="text-xs text-gray-400 space-y-0.5">
                      <div>Size: <span className="text-gray-200">{s.position_pct_of_fund != null ? `${s.position_pct_of_fund}% of fund` : "—"}</span></div>
                      <div>Stop: <span className="text-neg">{s.stop_price != null ? `$${s.stop_price}` : "—"}{s.stop_pct != null ? ` (−${s.stop_pct}%)` : ""}</span></div>
                    </div>
                  </>
                )}
                <div className="flex items-center gap-3 text-[10px] text-gray-600 mt-2 pt-2 border-t border-line/50">
                  <span>{s.cost_usd != null && s.cost_usd > 0 ? `$${s.cost_usd.toFixed(3)}` : "—"}</span>
                  <span>{s.secs}s</span>
                </div>
              </Card>
            ))}
          </div>

          {/* Agent-by-agent comparison */}
          <h2 className="text-sm font-semibold uppercase tracking-wide text-gray-400 mb-2">
            Agent-by-agent
          </h2>
          <div className="overflow-x-auto rounded-lg border border-line">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-line bg-bg-soft">
                  <th className="text-left p-2 text-gray-400 font-semibold w-32">Agent</th>
                  {stacks.map((s) => (
                    <th key={s.name} className="text-left p-2 text-gray-300 font-semibold">
                      {s.name.split(" ")[0]}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {AGENTS.map((a, i) => (
                  <tr key={a.key} className={cn("border-b border-line/40 align-top", i % 2 && "bg-bg-soft/30")}>
                    <td className="p-2 text-gray-400 font-medium">{a.label}</td>
                    {stacks.map((s) => {
                      const cell = s.agents?.[a.key];
                      return (
                        <td key={s.name} className="p-2 text-gray-300">
                          {cell ? (
                            <>
                              {cell.score != null && (
                                <span className="font-mono text-brand mr-1">[{String(cell.score)}]</span>
                              )}
                              <span className="text-gray-400">{cell.summary || "—"}</span>
                            </>
                          ) : (
                            <span className="text-gray-600">—</span>
                          )}
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Final messages */}
          <h2 className="text-sm font-semibold uppercase tracking-wide text-gray-400 mb-2 mt-6">
            Final client message (per model)
          </h2>
          <div className="grid gap-3" style={{ gridTemplateColumns: `repeat(${Math.min(stacks.length, 2)}, minmax(0,1fr))` }}>
            {stacks.map((s) => (
              <Card key={s.name}>
                <div className="text-xs font-bold text-white mb-1">{s.name}</div>
                <pre className="text-xs text-gray-300 whitespace-pre-wrap font-sans leading-relaxed">
                  {s.telegram_message || "(none)"}
                </pre>
              </Card>
            ))}
          </div>
        </>
      )}

      {!jobId && !start.isPending && (history.data?.length ?? 0) === 0 && (
        <Card className="text-center py-12 text-gray-500">
          <Layers className="h-8 w-8 mx-auto mb-2 text-gray-600" />
          <div className="text-gray-300 font-medium">Enter a ticker and run the bake-off</div>
          <div className="text-sm mt-1">
            Each model runs your complete 11-agent pipeline. You'll see every agent's output side by side.
          </div>
        </Card>
      )}

      {/* ── Scorecard (accumulated across all runs) ─────────── */}
      {(scorecard.data?.runs_total ?? 0) > 0 && (
        <div className="mt-8">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-gray-400 mb-1">
            Scorecard — across {scorecard.data!.runs_total} run(s)
          </h2>
          <p className="text-xs text-gray-500 mb-2">
            How each model compares to Production over every stock you've tested.
          </p>
          <div className="overflow-x-auto rounded-lg border border-line">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-line bg-bg-soft text-gray-400">
                  <th className="text-left p-2 font-semibold">Model</th>
                  <th className="text-center p-2 font-semibold">Runs</th>
                  <th className="text-center p-2 font-semibold">Agree w/ Prod</th>
                  <th className="text-center p-2 font-semibold">Avg conviction</th>
                  <th className="text-center p-2 font-semibold">Valid output</th>
                  <th className="text-center p-2 font-semibold">Avg cost</th>
                  <th className="text-center p-2 font-semibold">Avg time</th>
                </tr>
              </thead>
              <tbody>
                {scorecard.data!.rows.map((r) => (
                  <tr key={r.model} className={cn("border-b border-line/40",
                    r.model === "Production" && "bg-brand/5")}>
                    <td className="p-2 font-medium text-gray-200">{r.model}</td>
                    <td className="p-2 text-center text-gray-400">{r.runs}</td>
                    <td className={cn("p-2 text-center font-semibold",
                      r.agreement_pct == null ? "text-gray-600"
                        : r.agreement_pct >= 80 ? "text-pos"
                        : r.agreement_pct >= 60 ? "text-warn" : "text-neg")}>
                      {r.model === "Production" ? "—" : r.agreement_pct == null ? "—" : `${r.agreement_pct}%`}
                    </td>
                    <td className="p-2 text-center text-gray-300">{r.avg_conviction ?? "—"}</td>
                    <td className={cn("p-2 text-center",
                      (r.valid_pct ?? 0) >= 100 ? "text-pos" : "text-warn")}>
                      {r.valid_pct == null ? "—" : `${r.valid_pct}%`}</td>
                    <td className="p-2 text-center font-mono text-gray-400">
                      {r.avg_cost ? `$${r.avg_cost.toFixed(3)}` : "—"}</td>
                    <td className="p-2 text-center text-gray-400">{r.avg_secs ? `${r.avg_secs}s` : "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* ── History ─────────────────────────────────────────── */}
      {(history.data?.length ?? 0) > 0 && (
        <div className="mt-6">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-gray-400 mb-2">
            History — click to reopen
          </h2>
          <Card className="p-0 overflow-hidden divide-y divide-line/50">
            {history.data!.map((h) => (
              <button
                key={h.job_id}
                onClick={() => setJobId(h.job_id)}
                className={cn("w-full flex items-center gap-3 px-3 py-2 text-left text-sm hover:bg-bg-hover/50",
                  jobId === h.job_id && "bg-bg-hover/40")}
              >
                <span className="font-mono font-bold w-16">{h.symbol}</span>
                <span className="text-xs text-gray-500 w-28">{(h.created_at || "").slice(0, 16).replace("T", " ")}</span>
                <span className="flex-1 text-xs text-gray-400 truncate">
                  {h.verdicts.map((v) => `${v.name.split(" ")[0]}:${v.decision || "?"}`).join("  ·  ")}
                </span>
                <span className="text-xs font-mono text-gray-600">
                  {h.total_cost_usd != null ? `$${h.total_cost_usd.toFixed(2)}` : ""}
                </span>
              </button>
            ))}
          </Card>
        </div>
      )}
    </div>
  );
}
