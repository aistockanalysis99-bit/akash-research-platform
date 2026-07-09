import { useState } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BarChart3, ChevronDown, ChevronRight, Crosshair, RefreshCw, Star } from "lucide-react";
import { api } from "@/lib/api";
import { Badge, Button, Card, EmptyState, ErrorBox, Loading, PageTitle, Spinner } from "@/components/ui";
import { cn } from "@/lib/utils";

type Candidate = Awaited<ReturnType<typeof api.optionsCandidates>>[number];

function cheapCls(c?: number): string {
  if (c == null) return "text-gray-400";
  if (c <= 0.8) return "text-pos";
  if (c <= 1.0) return "text-warn";
  return "text-neg";
}

export default function OptionsScannerPage() {
  const qc = useQueryClient();
  const cands = useQuery({ queryKey: ["optCands"], queryFn: api.optionsCandidates });
  const settings = useQuery({ queryKey: ["settings"], queryFn: api.getSettings });

  const scan = useMutation({
    mutationFn: () => api.optionsScan(false),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["optCands"] }),
  });

  const opts = (settings.data as any)?.options || {};
  const rows = cands.data || [];
  const qualified = rows.filter((r) => r.qualified);
  const rejected = rows.filter((r) => !r.qualified);
  const scanDate = rows[0]?.scan_date;

  return (
    <div>
      <PageTitle
        title="Earnings Straddle Scanner"
        subtitle="Finds stocks whose upcoming earnings move is UNDERPRICED by the options market — buy the straddle, ride the anticipation, exit before the print. Suggest-only; nothing trades automatically."
        actions={
          <Button onClick={() => scan.mutate()} disabled={scan.isPending}>
            {scan.isPending ? <Spinner /> : <RefreshCw className="h-4 w-4" />}
            {scan.isPending ? "Scanning…" : "Scan now"}
          </Button>
        }
      />

      <div className="text-xs text-gray-500 mb-4">
        {scanDate ? `Last scan: ${scanDate}` : "No scan yet"} · auto-scan 16:45 ET weekdays ·
        rules: {opts.entry_min_days?.value ?? 3}–{opts.entry_max_days?.value ?? 14} days out ·
        cheapness ≤ {opts.cheapness_max?.value ?? 0.8} · OI ≥ {opts.min_oi?.value ?? 500}
      </div>

      {scan.error && <ErrorBox error={scan.error} />}
      {cands.isLoading && <Loading />}

      {!cands.isLoading && rows.length === 0 && (
        <Card>
          <EmptyState
            icon={<Crosshair className="h-8 w-8" />}
            title="No candidates yet"
            hint="Hit Scan now — the scanner checks every watchlist + held stock for earnings 3–14 days out and prices the ATM straddle."
          />
        </Card>
      )}

      {qualified.length > 0 && (
        <>
          <h2 className="text-sm font-semibold uppercase tracking-wide text-gray-400 mb-2">
            Qualified candidates ({qualified.length})
          </h2>
          <div className="space-y-3 mb-6">
            {qualified.map((c) => (
              <CandidateCard key={c.id} c={c} />
            ))}
          </div>
        </>
      )}

      {rejected.length > 0 && <RejectedList rows={rejected} />}
    </div>
  );
}

function CandidateCard({ c }: { c: Candidate }) {
  const qc = useQueryClient();
  const [contracts, setContracts] = useState(1);
  const track = useMutation({
    mutationFn: () => api.optionsTrack(c.id, contracts),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["optPositions"] }),
  });
  const cost = (c.straddle_cost || 0) * 100;

  return (
    <Card className="border-l-4 border-pos/50">
      <div className="flex items-center gap-2 flex-wrap mb-2">
        <span className="text-lg font-bold font-mono">{c.symbol}</span>
        <span className="text-sm text-gray-400">
          earnings {c.earnings_date} · {c.days_to_earnings} days out
        </span>
        {!!c.dual_signal && (
          <Badge className="border-brand/40 bg-brand/10 text-brand">
            <Star className="h-3 w-3 mr-1" /> DUAL SIGNAL — 7+ AI pick
          </Badge>
        )}
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 mb-3">
        <Stat label="Implied move" value={`±${c.implied_move_pct ?? "—"}%`} />
        <Stat label={`Historical (${c.hist_events}q)`} value={`±${c.hist_median_move_pct ?? "—"}%`} />
        <Stat label="Cheapness" value={c.cheapness ?? "—"} cls={cheapCls(c.cheapness)} bold />
        <Stat label="Min OI" value={c.min_oi?.toLocaleString() ?? "—"} />
      </div>

      <div className="text-sm text-gray-300 mb-3">
        <span className="text-gray-500">The trade: </span>
        Buy ${c.strike} call + ${c.strike} put · exp {c.expiry} · cost ≈{" "}
        <b className="text-gray-100">${cost.toLocaleString(undefined, { maximumFractionDigits: 0 })}/contract</b>
        <span className="text-gray-500"> · exit before {c.earnings_date} (deadline set on track)</span>
      </div>

      <div className="flex items-center gap-2">
        <label className="text-xs text-gray-500">Contracts</label>
        <input
          type="number" min={1} max={100} value={contracts}
          onChange={(e) => setContracts(Math.max(1, Number(e.target.value)))}
          className="w-16 bg-bg-soft border border-line rounded-lg px-2 py-1 text-sm stat-num focus:border-brand/50 outline-none"
        />
        <Button onClick={() => track.mutate()} disabled={track.isPending || track.isSuccess}>
          {track.isSuccess ? "Tracking ✓" : track.isPending ? <Spinner /> : "▶ Track it (paper)"}
        </Button>
        <Link
          to={`/options/backtest/${c.symbol}`}
          className="inline-flex items-center gap-1 text-xs text-gray-400 hover:text-brand transition-colors"
        >
          <BarChart3 className="h-3.5 w-3.5" /> Track record
        </Link>
        {track.error && (
          <span className="text-xs text-neg">{(track.error as Error).message.slice(0, 80)}</span>
        )}
      </div>
    </Card>
  );
}

function Stat({ label, value, cls, bold }: {
  label: string; value: React.ReactNode; cls?: string; bold?: boolean;
}) {
  return (
    <div className="rounded-lg bg-bg-hover/50 px-2.5 py-1.5">
      <div className="text-[10px] uppercase text-gray-500">{label}</div>
      <div className={cn("text-sm stat-num", bold && "font-bold", cls || "text-gray-200")}>{value}</div>
    </div>
  );
}

function RejectedList({ rows }: { rows: Candidate[] }) {
  const [open, setOpen] = useState(false);
  return (
    <Card className="p-0 overflow-hidden">
      <button
        onClick={() => setOpen((o) => !o)}
        className="w-full flex items-center gap-2 px-4 py-3 hover:bg-bg-hover/50 transition-colors"
      >
        {open ? <ChevronDown className="h-4 w-4 text-gray-500" /> : <ChevronRight className="h-4 w-4 text-gray-500" />}
        <span className="text-sm font-semibold text-gray-300">
          Scanned but rejected ({rows.length}) — why
        </span>
      </button>
      {open && (
        <div className="border-t border-line/50 divide-y divide-line/40">
          {rows.map((c) => (
            <div key={c.id} className="flex items-baseline gap-3 px-4 py-2 text-sm">
              <span className="font-mono font-semibold w-14">{c.symbol}</span>
              <span className="text-xs text-gray-500 w-40 shrink-0">
                earnings {c.earnings_date} ({c.days_to_earnings}d)
              </span>
              <span className="text-xs text-gray-400 flex-1">{c.reject_reason}</span>
              {c.cheapness != null && (
                <span className={cn("text-xs font-mono", cheapCls(c.cheapness))}>{c.cheapness}</span>
              )}
              <Link
                to={`/options/backtest/${c.symbol}`}
                className="text-xs text-gray-500 hover:text-brand transition-colors shrink-0"
              >
                track record
              </Link>
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}
