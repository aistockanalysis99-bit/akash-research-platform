import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { Play, Loader2, Check, Circle } from "lucide-react";
import { api } from "@/lib/api";
import { Badge, Button, Card, ErrorBox, Loading, PageTitle } from "@/components/ui";
import { cn, decisionColor, shortDate } from "@/lib/utils";
import type { AIJob, StageEvent } from "@/lib/types";

// Ordered pipeline stages with friendly labels + the model that runs them.
const STAGE_META: { key: string; label: string; model?: string }[] = [
  { key: "init", label: "Initializing" },
  { key: "prefetch", label: "Fetching data (FMP + Unusual Whales + portfolio)" },
  { key: "analysts", label: "6 analysts in parallel", model: "Gemini Flash" },
  { key: "debate", label: "Bull vs Bear debate", model: "Claude Sonnet" },
  { key: "judge", label: "Debate judge", model: "Claude Sonnet" },
  { key: "risk_manager", label: "Risk manager", model: "Claude Sonnet" },
  { key: "pm", label: "Portfolio Manager verdict", model: "Claude Opus" },
  { key: "summary", label: "Executive summary", model: "Gemini Flash" },
  { key: "profile_build", label: "Profile build / refresh", model: "Claude Opus" },
  { key: "notify", label: "Telegram delivery" },
  { key: "done", label: "Complete" },
];
const ORDER = STAGE_META.map((s) => s.key);

const SCORE_LABELS: Record<string, string> = {
  fundamental: "📊 Fundamental",
  news_risk: "📰 News risk",
  technical: "📈 Technical",
  smart_money: "🏦 Smart money",
  dealer_positioning: "📉 Dealer",
  macro_risk: "🌐 Macro risk",
};

function useTicker(active: boolean): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!active) return;
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, [active]);
  return now;
}

function fmtElapsed(ms: number): string {
  if (ms < 0) ms = 0;
  const s = Math.floor(ms / 1000);
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

export default function AnalyzePage() {
  const qc = useQueryClient();
  const [symbol, setSymbol] = useState("");

  const jobs = useQuery({
    queryKey: ["aiJobs"],
    queryFn: api.aiJobs,
    // Poll fast while something is running, slow otherwise.
    refetchInterval: (q) => {
      const data = q.state.data as AIJob[] | undefined;
      const anyRunning = (data || []).some(
        (j) => j.status === "running" || j.status === "queued"
      );
      return anyRunning ? 1500 : 8000;
    },
  });

  const analyze = useMutation({
    mutationFn: (s: string) => api.aiAnalyze(s),
    onSuccess: () => {
      setSymbol("");
      qc.invalidateQueries({ queryKey: ["aiJobs"] });
    },
  });

  const sorted = (jobs.data || [])
    .slice()
    .sort((a, b) => (b.started_at || "").localeCompare(a.started_at || ""));
  const anyRunning = sorted.some((j) => j.status === "running" || j.status === "queued");
  const now = useTicker(anyRunning);

  return (
    <div>
      <PageTitle
        title="Analyze a Ticker"
        subtitle="Runs the full 11-agent pipeline. ~5 minutes. Delivers two Telegram messages and a full dossier."
      />

      <Card className="mb-6">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            const s = symbol.trim().toUpperCase();
            if (s) analyze.mutate(s);
          }}
          className="flex items-center gap-3"
        >
          <input
            value={symbol}
            onChange={(e) => setSymbol(e.target.value)}
            placeholder="Ticker e.g. NVDA"
            className="bg-bg-soft border border-line rounded-lg px-4 py-2 text-sm w-48 font-mono uppercase focus:border-brand/50 outline-none"
          />
          <Button type="submit" disabled={analyze.isPending || !symbol.trim()}>
            {analyze.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
            Run analysis
          </Button>
          {analyze.error && <span className="text-sm text-neg">{(analyze.error as Error).message}</span>}
        </form>
      </Card>

      <h2 className="text-sm font-semibold uppercase tracking-wide text-gray-400 mb-3">
        Recent analyses
      </h2>
      {jobs.isLoading && <Loading />}
      {jobs.error && <ErrorBox error={jobs.error} />}
      <div className="space-y-3">
        {sorted.slice(0, 25).map((j) => {
          const running = j.status === "running" || j.status === "queued";
          return running ? (
            <LiveJobPanel key={j.job_id} job={j} now={now} />
          ) : (
            <CompactJob key={j.job_id} job={j} />
          );
        })}
        {sorted.length === 0 && !jobs.isLoading && (
          <Card>
            <div className="py-10 text-center text-gray-500 text-sm">
              No analyses yet. Enter a ticker above to run one.
            </div>
          </Card>
        )}
      </div>
    </div>
  );
}

// ---- Live (running) view --------------------------------------------------

function stageStatus(stageKey: string, job: AIJob): "done" | "active" | "pending" {
  const curIdx = ORDER.indexOf(job.current_stage || "");
  const i = ORDER.indexOf(stageKey);
  if (i < 0) return "pending";
  if (i < curIdx) return "done";
  if (i === curIdx) return "active";
  return "pending";
}

function LiveJobPanel({ job, now }: { job: AIJob; now: number }) {
  const events = job.stages || [];
  const latest = events[events.length - 1];
  const curMeta = STAGE_META.find((s) => s.key === job.current_stage);
  const startedMs = job.started_at ? Date.parse(job.started_at + "Z") : now;
  const elapsed = fmtElapsed(now - startedMs);
  const doneCount = ORDER.filter((k) => stageStatus(k, job) === "done").length;
  const pct = Math.round((doneCount / (ORDER.length - 1)) * 100);

  // Pull the most recent metrics event (the analyst scores).
  const metrics = [...events].reverse().find((e) => e.metrics && Object.keys(e.metrics).length)?.metrics;

  return (
    <Card className="border-l-4 border-brand/60">
      {/* Header */}
      <div className="flex items-center gap-3 flex-wrap mb-3">
        <span className="text-lg font-bold font-mono">{job.symbol}</span>
        <span className="text-xs text-gray-500 font-mono">#{job.job_id.slice(0, 7)}</span>
        <div className="flex-1" />
        <span className="font-mono text-sm text-brand tabular-nums">{elapsed}</span>
      </div>

      {/* Current-step banner */}
      <div className="flex items-center gap-3 bg-bg-soft rounded-lg p-3 mb-3">
        <Loader2 className="h-5 w-5 animate-spin text-brand shrink-0" />
        <div className="flex-1 min-w-0">
          <div className="text-sm font-semibold text-white flex items-center gap-2">
            {curMeta?.label || job.current_stage || "Working…"}
            {curMeta?.model && (
              <Badge className="border-line bg-bg-hover text-gray-400">{curMeta.model}</Badge>
            )}
          </div>
          {latest?.msg && (
            <div className="text-xs text-gray-400 truncate mt-0.5">{latest.msg}</div>
          )}
        </div>
      </div>

      {/* Progress bar */}
      <div className="h-1.5 bg-bg-hover rounded-full overflow-hidden mb-4">
        <div className="h-full bg-brand transition-all duration-500" style={{ width: `${pct}%` }} />
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Stage stepper */}
        <div className="space-y-1.5">
          {STAGE_META.filter((s) => s.key !== "init").map((s) => {
            const st = stageStatus(s.key, job);
            return (
              <div key={s.key} className="flex items-center gap-2 text-sm">
                {st === "done" ? (
                  <Check className="h-4 w-4 text-pos shrink-0" />
                ) : st === "active" ? (
                  <Loader2 className="h-4 w-4 text-brand animate-spin shrink-0" />
                ) : (
                  <Circle className="h-4 w-4 text-line shrink-0" />
                )}
                <span className={cn(
                  st === "active" ? "text-white font-medium"
                    : st === "done" ? "text-gray-400" : "text-gray-600"
                )}>
                  {s.label}
                </span>
                {s.model && st !== "pending" && (
                  <span className="text-[10px] text-gray-600 ml-auto">{s.model}</span>
                )}
              </div>
            );
          })}
        </div>

        {/* Scores ticking in + activity feed */}
        <div>
          {metrics && (
            <div className="flex flex-wrap gap-1.5 mb-3">
              {Object.entries(metrics).map(([k, v]) =>
                v != null && SCORE_LABELS[k] ? (
                  <Badge key={k} className="border-brand/30 bg-brand/10 text-brand-glow">
                    {SCORE_LABELS[k]}: {String(v)}
                  </Badge>
                ) : null
              )}
            </div>
          )}
          <div className="text-[11px] uppercase text-gray-600 mb-1">Activity</div>
          <div className="space-y-1 max-h-44 overflow-y-auto pr-1">
            {[...events].reverse().slice(0, 30).map((e, i) => (
              <FeedLine key={i} ev={e} />
            ))}
          </div>
        </div>
      </div>
    </Card>
  );
}

function FeedLine({ ev }: { ev: StageEvent }) {
  const t = ev.at ? ev.at.slice(11, 19) : "";
  return (
    <div className="flex gap-2 text-xs leading-snug">
      <span className="text-gray-600 font-mono shrink-0">{t}</span>
      <span className="text-gray-400">
        {ev.agent && <span className="text-brand-glow">[{ev.agent}] </span>}
        {ev.msg}
      </span>
    </div>
  );
}

// ---- Compact (finished) view ----------------------------------------------

function CompactJob({ job }: { job: AIJob }) {
  const seen = new Set((job.stages || []).map((s) => s.stage));
  return (
    <Card>
      <div className="flex items-center gap-3 flex-wrap">
        <span className="text-lg font-bold font-mono w-20">{job.symbol}</span>
        <span className="text-xs text-gray-500 font-mono">#{job.job_id.slice(0, 7)}</span>
        <span className="text-xs text-gray-500">{shortDate(job.started_at)}</span>
        <div className="flex-1" />
        {job.status === "complete" ? (
          <div className="flex items-center gap-2">
            <Badge className={decisionColor(job.verdict?.decision)}>
              {job.verdict?.decision || "—"}{" "}
              {job.verdict?.conviction != null ? `${job.verdict.conviction}/10` : ""}
            </Badge>
            {job.signal_date && (
              <Link
                to={`/decisions/${job.symbol}/${job.signal_date}`}
                className="text-brand text-xs hover:text-brand-glow"
              >
                Open dossier →
              </Link>
            )}
          </div>
        ) : (
          <Badge className="border-neg/40 bg-neg/10 text-neg">FAILED</Badge>
        )}
      </div>
      <div className="flex items-center gap-1 mt-3 flex-wrap">
        {ORDER.map((st) => (
          <div
            key={st}
            title={STAGE_META.find((m) => m.key === st)?.label}
            className={cn(
              "h-1.5 w-1.5 rounded-full",
              seen.has(st) || job.status === "complete" ? "bg-pos" : "bg-line"
            )}
          />
        ))}
      </div>
      {job.status === "failed" && job.error && (
        <div className="mt-2 text-xs text-neg font-mono bg-neg/5 rounded p-2 max-h-24 overflow-auto">
          {job.error.slice(0, 400)}
        </div>
      )}
    </Card>
  );
}
