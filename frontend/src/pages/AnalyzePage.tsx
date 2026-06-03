import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { Play, Loader2 } from "lucide-react";
import { api } from "@/lib/api";
import { Badge, Button, Card, ErrorBox, Loading, PageTitle } from "@/components/ui";
import { cn, decisionColor, shortDate } from "@/lib/utils";
import type { AIJob } from "@/lib/types";

const STAGE_LABELS: Record<string, string> = {
  init: "Initializing",
  prefetch: "Fetching data",
  analysts: "6 analysts",
  debate: "Bull vs Bear",
  judge: "Debate judge",
  risk_manager: "Risk manager",
  pm: "Portfolio manager",
  summary: "Summary",
  profile_build: "Profile build",
  notify: "Telegram",
  done: "Complete",
};
const STAGE_SEQUENCE = Object.keys(STAGE_LABELS);

export default function AnalyzePage() {
  const qc = useQueryClient();
  const [symbol, setSymbol] = useState("");

  const jobs = useQuery({
    queryKey: ["aiJobs"],
    queryFn: api.aiJobs,
    refetchInterval: 4000, // live polling
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
            {analyze.isPending ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Play className="h-4 w-4" />
            )}
            Run analysis
          </Button>
          {analyze.error && (
            <span className="text-sm text-neg">
              {(analyze.error as Error).message}
            </span>
          )}
        </form>
      </Card>

      <h2 className="text-sm font-semibold uppercase tracking-wide text-gray-400 mb-3">
        Recent analyses
      </h2>
      {jobs.isLoading && <Loading />}
      {jobs.error && <ErrorBox error={jobs.error} />}
      <div className="space-y-3">
        {sorted.slice(0, 25).map((j) => (
          <JobCard key={j.job_id} job={j} />
        ))}
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

function JobCard({ job }: { job: AIJob }) {
  const seen = new Set((job.stages || []).map((s) => s.stage));
  const running = job.status === "running" || job.status === "queued";

  return (
    <Card>
      <div className="flex items-center gap-3 flex-wrap">
        <span className="text-lg font-bold font-mono w-20">{job.symbol}</span>
        <span className="text-xs text-gray-500 font-mono">
          #{job.job_id.slice(0, 7)}
        </span>
        <span className="text-xs text-gray-500">{shortDate(job.started_at)}</span>
        <div className="flex-1" />
        {running ? (
          <span className="flex items-center gap-2 text-sm text-brand">
            <Loader2 className="h-4 w-4 animate-spin" />
            {STAGE_LABELS[job.current_stage || ""] || job.current_stage}
          </span>
        ) : job.status === "complete" ? (
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

      {/* Stage progress dots */}
      <div className="flex items-center gap-1 mt-3 flex-wrap">
        {STAGE_SEQUENCE.map((st) => {
          const done = seen.has(st) || job.status === "complete";
          const isCurrent = st === job.current_stage && running;
          return (
            <div key={st} className="flex items-center gap-1" title={STAGE_LABELS[st]}>
              <div
                className={cn(
                  "h-1.5 w-1.5 rounded-full",
                  isCurrent
                    ? "bg-brand animate-pulse"
                    : done
                    ? "bg-pos"
                    : "bg-line"
                )}
              />
            </div>
          );
        })}
        <span className="text-[10px] text-gray-600 ml-2">
          {STAGE_SEQUENCE.filter((s) => seen.has(s)).length}/{STAGE_SEQUENCE.length}
        </span>
      </div>

      {job.status === "failed" && job.error && (
        <div className="mt-2 text-xs text-neg font-mono bg-neg/5 rounded p-2 max-h-24 overflow-auto">
          {job.error.slice(0, 400)}
        </div>
      )}
    </Card>
  );
}
