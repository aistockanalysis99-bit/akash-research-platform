import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { FileText } from "lucide-react";
import { api } from "@/lib/api";
import { Badge, Card, EmptyState, ErrorBox, Loading, PageTitle } from "@/components/ui";
import { cn, shortDate } from "@/lib/utils";

const TIER_COLOR: Record<string, string> = {
  tier_1: "border-pos/40 bg-pos/10 text-pos",
  tier_2: "border-info/40 bg-info/10 text-info",
  tier_3: "border-line bg-bg-hover text-gray-400",
};

export default function WatchlistPage() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["profiles"],
    queryFn: api.profiles,
  });

  const rows = (data || []).slice().sort((a, b) => {
    const t = { tier_1: 0, tier_2: 1, tier_3: 2 } as Record<string, number>;
    return (t[a.priority || ""] ?? 9) - (t[b.priority || ""] ?? 9) ||
      a.symbol.localeCompare(b.symbol);
  });

  return (
    <div>
      <PageTitle
        title="Watchlist"
        subtitle="Living research dossiers, one per stock — auto-built by the AI, refreshed on cadence, earnings, or a decision flip."
      />
      {isLoading && <Loading />}
      {error && <ErrorBox error={error} />}
      {data && data.length === 0 && (
        <Card>
          <EmptyState
            icon={<FileText className="h-8 w-8" />}
            title="No dossiers yet"
            hint="Run an analysis on any ticker and a profile is auto-built afterward."
          />
        </Card>
      )}
      {rows.length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
          {rows.map((p) => (
            <Link key={p.symbol} to={`/watchlist/${p.symbol}`}>
              <Card className="hover:border-brand/40 hover:shadow-glow transition-all h-full">
                <div className="flex items-center gap-2 mb-2">
                  <span className="text-lg font-bold font-mono">{p.symbol}</span>
                  {p.held && (
                    <Badge className="border-pos/40 bg-pos/10 text-pos">held</Badge>
                  )}
                  <div className="flex-1" />
                  <Badge className={cn(TIER_COLOR[p.priority || ""] || TIER_COLOR.tier_3)}>
                    {p.priority || "—"}
                  </Badge>
                </div>
                <div className="text-sm text-gray-300 truncate">{p.name || "—"}</div>
                <div className="text-xs text-gray-500 mb-3">{p.sector || "—"}</div>
                <div className="flex items-center gap-3 text-xs">
                  <span className="text-pos">🟢 {p.bull_pillar_count ?? 0}</span>
                  <span className="text-neg">🔴 {p.bear_pillar_count ?? 0}</span>
                  <span className="text-warn">⚠ {p.red_line_count ?? 0}</span>
                  <div className="flex-1" />
                  <span className="text-gray-600 font-mono">
                    {shortDate(p.last_reviewed)}
                  </span>
                </div>
              </Card>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
