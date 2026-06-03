import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Download, RefreshCw } from "lucide-react";
import { api } from "@/lib/api";
import { Button, Card, EmptyState, Loading, PageTitle } from "@/components/ui";

export default function DataPage() {
  const qc = useQueryClient();
  const status = useQuery({ queryKey: ["dataStatus"], queryFn: api.dataStatus });
  const universes = useQuery({ queryKey: ["universes"], queryFn: api.universes });

  const [universe, setUniverse] = useState("");
  const [timeframe, setTimeframe] = useState("1D");
  const [years, setYears] = useState(5);
  const [full, setFull] = useState(false);
  const [jobId, setJobId] = useState<string | null>(null);

  const start = useMutation({
    mutationFn: () =>
      api.dataRefresh({
        universe: universe || universes.data?.[0] || "sp100",
        timeframe,
        years,
        full,
      }),
    onSuccess: (r) => setJobId(r.job_id),
  });

  // Poll the running job
  const job = useQuery({
    queryKey: ["dataRefresh", jobId],
    queryFn: () => api.dataRefreshStatus(jobId!),
    enabled: !!jobId,
    refetchInterval: (q) => {
      const s = q.state.data?.status;
      return s === "running" ? 1500 : false;
    },
  });

  // When the job finishes, refresh the status table (once).
  const jobStatus = job.data?.status;
  useEffect(() => {
    if (jobStatus && jobStatus !== "running") {
      qc.invalidateQueries({ queryKey: ["dataStatus"] });
    }
  }, [jobStatus, qc]);

  const rows = (status.data || []) as Record<string, any>[];
  const cols = rows.length ? Object.keys(rows[0]) : [];
  const j = job.data;
  const pct = j && j.total ? Math.round((j.done / j.total) * 100) : 0;

  return (
    <div>
      <PageTitle
        title="Data Cache"
        subtitle="Cached price history used by backtests. Update to pull the latest bars from FMP."
      />

      {/* Update control */}
      <Card className="mb-5">
        <div className="flex items-end gap-3 flex-wrap">
          <Field label="Universe">
            <select className={inp} value={universe} onChange={(e) => setUniverse(e.target.value)}>
              {(universes.data || []).map((u) => (
                <option key={u} value={u}>{u}</option>
              ))}
            </select>
          </Field>
          <Field label="Timeframe">
            <select className={inp} value={timeframe} onChange={(e) => setTimeframe(e.target.value)}>
              {["1D", "4h", "1h", "30m", "15m"].map((t) => (
                <option key={t} value={t}>{t}</option>
              ))}
            </select>
          </Field>
          <Field label="Years back">
            <input
              type="number"
              min={1}
              max={20}
              className={`${inp} w-24`}
              value={years}
              onChange={(e) => setYears(Number(e.target.value))}
            />
          </Field>
          <label className="flex items-center gap-2 text-sm text-gray-300 pb-2 cursor-pointer">
            <input type="checkbox" checked={full} onChange={(e) => setFull(e.target.checked)} />
            Full re-download
            <span className="text-xs text-gray-500">(off = incremental, only new bars)</span>
          </label>
          <Button
            onClick={() => start.mutate()}
            disabled={start.isPending || j?.status === "running"}
            className="ml-auto"
          >
            <Download className="h-4 w-4" />
            {j?.status === "running" ? "Updating…" : "Update data"}
          </Button>
        </div>

        {/* Progress */}
        {j && (
          <div className="mt-4">
            <div className="flex items-center justify-between text-xs mb-1">
              <span className="text-gray-400">
                {j.status === "running"
                  ? `Fetching ${j.current_symbol || "…"} (${j.label}, ${j.timeframe})`
                  : j.status === "done"
                  ? "✓ Update complete"
                  : `Failed: ${j.error || "unknown error"}`}
              </span>
              <span className="text-gray-500 font-mono">
                {j.done}/{j.total}
              </span>
            </div>
            <div className="h-2 bg-bg-hover rounded-full overflow-hidden">
              <div
                className={`h-full rounded-full transition-all ${
                  j.status === "failed" ? "bg-neg" : "bg-brand"
                }`}
                style={{ width: `${j.status === "done" ? 100 : pct}%` }}
              />
            </div>
          </div>
        )}
        {start.error && (
          <div className="mt-2 text-sm text-neg">{(start.error as Error).message}</div>
        )}
      </Card>

      {/* Status table */}
      <div className="flex items-center justify-between mb-2">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-gray-400">
          Cached Series {rows.length > 0 && `(${rows.length})`}
        </h2>
        <button
          onClick={() => qc.invalidateQueries({ queryKey: ["dataStatus"] })}
          className="text-gray-500 hover:text-brand"
          title="Reload table"
        >
          <RefreshCw className="h-4 w-4" />
        </button>
      </div>
      {status.isLoading && <Loading />}
      {status.data && rows.length === 0 && (
        <Card>
          <EmptyState title="No cached data" hint="Use Update data above to populate the cache." />
        </Card>
      )}
      {rows.length > 0 && (
        <Card className="p-0 overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-xs uppercase text-gray-500 border-b border-line">
                {cols.map((c) => (
                  <th key={c} className="text-left px-3 py-2">{c.replace(/_/g, " ")}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((r, i) => (
                <tr key={i} className="border-b border-line/50 hover:bg-bg-hover/50">
                  {cols.map((c) => (
                    <td key={c} className="px-3 py-2 text-gray-300 font-mono text-xs">
                      {String(r[c]).slice(0, 19)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
    </div>
  );
}

const inp =
  "bg-bg-soft border border-line rounded-lg px-3 py-2 text-sm focus:border-brand/50 outline-none";

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="text-xs uppercase text-gray-500 mb-1 block">{label}</span>
      {children}
    </label>
  );
}
