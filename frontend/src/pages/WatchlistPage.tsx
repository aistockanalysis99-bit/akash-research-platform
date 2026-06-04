import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { Plus, Trash2, Eye, EyeOff, FileText, Play, Search } from "lucide-react";
import { api } from "@/lib/api";
import type { ProfileRow, WatchlistItem } from "@/lib/types";
import { Badge, Button, Card, ErrorBox, Loading, PageTitle, Spinner } from "@/components/ui";
import { cn, shortDate } from "@/lib/utils";

const TIER_COLOR: Record<string, string> = {
  tier_1: "border-pos/40 bg-pos/10 text-pos",
  tier_2: "border-info/40 bg-info/10 text-info",
  tier_3: "border-line bg-bg-hover text-gray-400",
};

export default function WatchlistPage() {
  const qc = useQueryClient();
  const wl = useQuery({ queryKey: ["watchlist"], queryFn: api.watchlist });
  const profiles = useQuery({ queryKey: ["profiles"], queryFn: api.profiles });

  const invalidate = () => qc.invalidateQueries({ queryKey: ["watchlist"] });

  const profileBySymbol: Record<string, ProfileRow> = {};
  (profiles.data || []).forEach((p) => (profileBySymbol[p.symbol.toUpperCase()] = p));

  const watchSymbols = new Set((wl.data || []).map((w) => w.symbol.toUpperCase()));
  // Dossiers that exist but are NOT on the watchlist (e.g. from quant signals)
  const orphanDossiers = (profiles.data || []).filter(
    (p) => !watchSymbols.has(p.symbol.toUpperCase())
  );

  const sorted = (wl.data || [])
    .slice()
    .sort((a, b) => Number(b.enabled) - Number(a.enabled) || a.symbol.localeCompare(b.symbol));

  return (
    <div>
      <PageTitle
        title="Watchlist"
        subtitle="The stocks the AI researches automatically every evening (4:30 PM ET). Add or remove any stock here — enabled stocks get a full 11-analyst report each night."
      />

      <AddBox onAdded={invalidate} existing={watchSymbols} />

      {(wl.isLoading || profiles.isLoading) && <Loading />}
      {wl.error && <ErrorBox error={wl.error} />}

      {wl.data && wl.data.length === 0 && (
        <Card className="text-center py-10 text-gray-400">
          <Search className="h-7 w-7 mx-auto mb-2 text-gray-600" />
          <div className="font-medium text-gray-300">Your watchlist is empty</div>
          <div className="text-sm text-gray-500 mt-1">
            Add a stock above to start getting nightly AI research on it.
          </div>
        </Card>
      )}

      {sorted.length > 0 && (
        <>
          <div className="text-xs text-gray-500 mb-2">
            {sorted.length} stocks · {sorted.filter((w) => w.enabled).length} enabled for nightly research
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
            {sorted.map((w) => (
              <WatchRow
                key={w.symbol}
                item={w}
                profile={profileBySymbol[w.symbol.toUpperCase()]}
                onChange={invalidate}
              />
            ))}
          </div>
        </>
      )}

      {/* Orphan dossiers — researched but not on the watchlist */}
      {orphanDossiers.length > 0 && (
        <div className="mt-8">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-gray-400 mb-1">
            Other research dossiers
          </h2>
          <p className="text-xs text-gray-500 mb-3">
            These stocks were analyzed from quant signals but aren't on your watchlist. View the
            research or add them to your nightly watchlist.
          </p>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
            {orphanDossiers.map((p) => (
              <OrphanCard key={p.symbol} profile={p} onAdded={invalidate} />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ── Add box ─────────────────────────────────────────────────────────────────
function AddBox({ onAdded, existing }: { onAdded: () => void; existing: Set<string> }) {
  const [ticker, setTicker] = useState("");
  const add = useMutation({
    mutationFn: (sym: string) => api.watchlistAdd(sym, "manual add"),
    onSuccess: () => {
      setTicker("");
      onAdded();
    },
  });

  const sym = ticker.trim().toUpperCase();
  const already = sym && existing.has(sym);

  const submit = () => {
    if (sym && !already) add.mutate(sym);
  };

  return (
    <Card className="mb-5">
      <div className="flex items-center gap-2 flex-wrap">
        <div className="relative flex-1 min-w-[200px]">
          <Search className="h-4 w-4 text-gray-500 absolute left-3 top-1/2 -translate-y-1/2" />
          <input
            value={ticker}
            onChange={(e) => setTicker(e.target.value.toUpperCase())}
            onKeyDown={(e) => e.key === "Enter" && submit()}
            placeholder="Add a ticker, e.g. TSLA"
            autoComplete="off"
            spellCheck={false}
            className="w-full bg-bg-soft border border-line rounded-lg pl-9 pr-3 py-2 text-sm font-mono uppercase placeholder:font-sans placeholder:normal-case focus:border-brand/50 outline-none"
          />
        </div>
        <Button onClick={submit} disabled={!sym || !!already || add.isPending}>
          {add.isPending ? <Spinner /> : <Plus className="h-4 w-4" />}
          Add to watchlist
        </Button>
      </div>
      {already && (
        <div className="text-xs text-warn mt-2">{sym} is already on your watchlist.</div>
      )}
      {add.isError && (
        <div className="text-xs text-neg mt-2">
          Couldn't add {sym}: {(add.error as Error)?.message?.slice(0, 120)}
        </div>
      )}
    </Card>
  );
}

// ── A watchlist row ───────────────────────────────────────────────────────────
function WatchRow({
  item,
  profile,
  onChange,
}: {
  item: WatchlistItem;
  profile?: ProfileRow;
  onChange: () => void;
}) {
  const enabled = !!item.enabled;
  const sym = item.symbol.toUpperCase();

  const toggle = useMutation({
    mutationFn: () => api.watchlistToggle(sym, !enabled),
    onSuccess: onChange,
  });
  const remove = useMutation({
    mutationFn: () => api.watchlistRemove(sym),
    onSuccess: onChange,
  });
  const analyze = useMutation({ mutationFn: () => api.aiAnalyze(sym) });

  return (
    <Card className={cn("h-full flex flex-col", !enabled && "opacity-60")}>
      <div className="flex items-center gap-2 mb-2">
        <span className="text-lg font-bold font-mono">{sym}</span>
        {profile?.held && <Badge className="border-pos/40 bg-pos/10 text-pos">held</Badge>}
        <div className="flex-1" />
        {profile?.priority && (
          <Badge className={cn(TIER_COLOR[profile.priority] || TIER_COLOR.tier_3)}>
            {profile.priority}
          </Badge>
        )}
      </div>

      <div className="text-sm text-gray-300 truncate">{profile?.name || sym}</div>
      <div className="text-xs text-gray-500 mb-3">{profile?.sector || "—"}</div>

      {/* Research status */}
      {profile ? (
        <Link
          to={`/watchlist/${sym}`}
          className="flex items-center gap-3 text-xs mb-3 hover:text-brand transition-colors"
        >
          <span className="text-pos">🟢 {profile.bull_pillar_count ?? 0}</span>
          <span className="text-neg">🔴 {profile.bear_pillar_count ?? 0}</span>
          <span className="text-warn">⚠ {profile.red_line_count ?? 0}</span>
          <div className="flex-1" />
          <span className="text-gray-600 font-mono">{shortDate(profile.last_reviewed)}</span>
        </Link>
      ) : (
        <div className="text-xs text-gray-500 mb-3 italic">
          No research yet — a dossier builds after its first analysis.
        </div>
      )}

      {/* Actions */}
      <div className="flex items-center gap-2 mt-auto pt-2 border-t border-line/50">
        <button
          onClick={() => toggle.mutate()}
          disabled={toggle.isPending}
          title={enabled ? "Disable nightly research" : "Enable nightly research"}
          className={cn(
            "inline-flex items-center gap-1 text-xs px-2 py-1 rounded-md transition-colors",
            enabled
              ? "text-pos hover:bg-pos/10"
              : "text-gray-500 hover:bg-bg-hover"
          )}
        >
          {enabled ? <Eye className="h-3.5 w-3.5" /> : <EyeOff className="h-3.5 w-3.5" />}
          {enabled ? "Enabled" : "Disabled"}
        </button>

        {profile && (
          <Link
            to={`/watchlist/${sym}`}
            className="inline-flex items-center gap-1 text-xs px-2 py-1 rounded-md text-gray-400 hover:text-white hover:bg-bg-hover transition-colors"
          >
            <FileText className="h-3.5 w-3.5" /> Dossier
          </Link>
        )}

        <button
          onClick={() => analyze.mutate()}
          disabled={analyze.isPending || analyze.isSuccess}
          title="Run a full AI analysis now"
          className="inline-flex items-center gap-1 text-xs px-2 py-1 rounded-md text-gray-400 hover:text-white hover:bg-bg-hover transition-colors disabled:opacity-60"
        >
          <Play className="h-3.5 w-3.5" />
          {analyze.isSuccess ? "Queued ✓" : analyze.isPending ? "…" : "Analyze"}
        </button>

        <div className="flex-1" />
        <button
          onClick={() => remove.mutate()}
          disabled={remove.isPending}
          title="Remove from watchlist"
          className="inline-flex items-center text-xs px-2 py-1 rounded-md text-gray-500 hover:text-neg hover:bg-neg/10 transition-colors"
        >
          <Trash2 className="h-3.5 w-3.5" />
        </button>
      </div>
    </Card>
  );
}

// ── Orphan dossier card (researched, not on watchlist) ───────────────────────
function OrphanCard({ profile, onAdded }: { profile: ProfileRow; onAdded: () => void }) {
  const sym = profile.symbol.toUpperCase();
  const add = useMutation({
    mutationFn: () => api.watchlistAdd(sym, "added from dossier"),
    onSuccess: onAdded,
  });

  return (
    <Card className="h-full flex flex-col border-line/60">
      <div className="flex items-center gap-2 mb-2">
        <Link to={`/watchlist/${sym}`} className="text-lg font-bold font-mono hover:text-brand">
          {sym}
        </Link>
        <div className="flex-1" />
        {profile.priority && (
          <Badge className={cn(TIER_COLOR[profile.priority] || TIER_COLOR.tier_3)}>
            {profile.priority}
          </Badge>
        )}
      </div>
      <div className="text-sm text-gray-300 truncate">{profile.name || sym}</div>
      <div className="text-xs text-gray-500 mb-3">{profile.sector || "—"}</div>
      <div className="flex items-center gap-3 text-xs mb-3">
        <span className="text-pos">🟢 {profile.bull_pillar_count ?? 0}</span>
        <span className="text-neg">🔴 {profile.bear_pillar_count ?? 0}</span>
        <span className="text-warn">⚠ {profile.red_line_count ?? 0}</span>
        <div className="flex-1" />
        <span className="text-gray-600 font-mono">{shortDate(profile.last_reviewed)}</span>
      </div>
      <div className="flex items-center gap-2 mt-auto pt-2 border-t border-line/50">
        <Link
          to={`/watchlist/${sym}`}
          className="inline-flex items-center gap-1 text-xs px-2 py-1 rounded-md text-gray-400 hover:text-white hover:bg-bg-hover"
        >
          <FileText className="h-3.5 w-3.5" /> View dossier
        </Link>
        <div className="flex-1" />
        <Button variant="outline" onClick={() => add.mutate()} disabled={add.isPending || add.isSuccess}>
          {add.isSuccess ? "Added ✓" : <><Plus className="h-3.5 w-3.5" /> Add</>}
        </Button>
      </div>
    </Card>
  );
}
