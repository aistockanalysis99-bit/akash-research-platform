import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { Search } from "lucide-react";
import { api } from "@/lib/api";
import { Badge, Card, ErrorBox, Loading, PageTitle } from "@/components/ui";
import { cn, decisionColor, shortDate } from "@/lib/utils";

export default function DecisionsPage() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["decisions"],
    queryFn: api.aiDecisions,
  });
  const [q, setQ] = useState("");

  const rows = useMemo(() => {
    const r = (data || []).slice();
    r.sort((a, b) => (b.date + b.symbol).localeCompare(a.date + a.symbol));
    if (!q) return r;
    const needle = q.toUpperCase();
    return r.filter(
      (d) =>
        d.symbol.toUpperCase().includes(needle) ||
        (d.decision || "").toUpperCase().includes(needle)
    );
  }, [data, q]);

  return (
    <div>
      <PageTitle
        title="Decisions"
        subtitle="Every analysis the AI has produced. Click any row for the full 11-agent report."
        actions={
          <div className="relative">
            <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-500" />
            <input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Filter symbol / verdict…"
              className="bg-bg-card border border-line rounded-lg pl-8 pr-3 py-1.5 text-sm w-56 focus:border-brand/50 outline-none"
            />
          </div>
        }
      />

      {isLoading && <Loading />}
      {error && <ErrorBox error={error} />}

      {data && (
        <Card className="p-0 overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-xs uppercase text-gray-500 border-b border-line">
                <th className="text-left px-3 py-2 font-medium">Symbol</th>
                <th className="text-left px-3 py-2 font-medium">Date</th>
                <th className="text-left px-3 py-2 font-medium">Decision</th>
                <th className="text-right px-3 py-2 font-medium">Conviction</th>
                <th className="text-right px-3 py-2 font-medium">Size</th>
                <th className="text-left px-3 py-2 font-medium">Status</th>
                <th className="px-3 py-2"></th>
              </tr>
            </thead>
            <tbody>
              {rows.map((d) => (
                <tr
                  key={`${d.symbol}-${d.date}`}
                  className="border-b border-line/50 hover:bg-bg-hover/50"
                >
                  <td className="px-3 py-2.5 font-bold font-mono">{d.symbol}</td>
                  <td className="px-3 py-2.5 text-gray-400 font-mono text-xs">
                    {shortDate(d.date)}
                  </td>
                  <td className="px-3 py-2.5">
                    <Badge className={decisionColor(d.decision)}>
                      {d.decision || "—"}
                    </Badge>
                  </td>
                  <td className="px-3 py-2.5 text-right stat-num">
                    {d.conviction != null ? `${d.conviction}/10` : "—"}
                  </td>
                  <td className="px-3 py-2.5 text-right stat-num">
                    {d.size_pct != null ? `${d.size_pct}%` : "—"}
                  </td>
                  <td className="px-3 py-2.5">
                    <span
                      className={cn(
                        "text-xs",
                        d.status === "complete" ? "text-pos" : "text-warn"
                      )}
                    >
                      {d.status}
                    </span>
                  </td>
                  <td className="px-3 py-2.5 text-right">
                    <Link
                      to={`/decisions/${d.symbol}/${d.date}`}
                      className="text-brand text-xs hover:text-brand-glow"
                    >
                      Open →
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {rows.length === 0 && (
            <div className="py-12 text-center text-gray-500 text-sm">
              No decisions match “{q}”.
            </div>
          )}
        </Card>
      )}
    </div>
  );
}
