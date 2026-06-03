import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate, useParams } from "react-router-dom";
import { ArrowLeft, Save, Trash2 } from "lucide-react";
import { api } from "@/lib/api";
import { Badge, Button, Card, ErrorBox, Loading, PageTitle } from "@/components/ui";
import Markdown from "@/components/Markdown";
import { cn } from "@/lib/utils";

type Any = Record<string, any>;

export default function ProfileDetailPage() {
  const { symbol = "" } = useParams();
  const profile = useQuery({
    queryKey: ["profile", symbol],
    queryFn: () => api.profile(symbol) as Promise<Any>,
  });
  const raw = useQuery({
    queryKey: ["profileRaw", symbol],
    queryFn: () => api.profileRaw(symbol),
  });
  const [showRaw, setShowRaw] = useState(false);
  const [draft, setDraft] = useState("");
  const qc = useQueryClient();
  const nav = useNavigate();

  useEffect(() => {
    if (raw.data?.content) setDraft(raw.data.content);
  }, [raw.data]);

  const save = useMutation({
    mutationFn: () => api.profileSaveRaw(symbol, draft),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["profile", symbol] });
      qc.invalidateQueries({ queryKey: ["profileRaw", symbol] });
      qc.invalidateQueries({ queryKey: ["profiles"] });
    },
  });
  const del = useMutation({
    mutationFn: () => api.profileDelete(symbol),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["profiles"] });
      nav("/watchlist");
    },
  });

  const p = profile.data;

  return (
    <div>
      <Link
        to="/watchlist"
        className="inline-flex items-center gap-1 text-sm text-gray-400 hover:text-brand mb-3"
      >
        <ArrowLeft className="h-4 w-4" /> All dossiers
      </Link>
      <PageTitle
        title={symbol}
        subtitle={p?.name as string}
        actions={
          <button
            onClick={() => setShowRaw((v) => !v)}
            className="text-xs text-gray-400 hover:text-brand"
          >
            {showRaw ? "Show structured" : "Show raw markdown"}
          </button>
        }
      />

      {profile.isLoading && <Loading />}
      {profile.error && <ErrorBox error={profile.error} />}

      {showRaw && raw.data && (
        <Card>
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs text-gray-500">
              Edit the dossier (YAML frontmatter + markdown). Saving re-validates the profile.
            </span>
            <div className="flex items-center gap-2">
              <Button
                variant="primary"
                onClick={() => save.mutate()}
                disabled={save.isPending || draft === raw.data.content}
              >
                <Save className="h-4 w-4" />
                {save.isPending ? "Saving…" : save.isSuccess && draft === raw.data.content ? "Saved" : "Save"}
              </Button>
              <Button
                variant="danger"
                onClick={() => {
                  if (confirm(`Delete the ${symbol} dossier? This cannot be undone.`)) del.mutate();
                }}
                disabled={del.isPending}
              >
                <Trash2 className="h-4 w-4" /> Delete
              </Button>
            </div>
          </div>
          {save.error && <ErrorBox error={save.error} />}
          <textarea
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            spellCheck={false}
            className="w-full h-[600px] bg-bg-soft border border-line rounded-lg p-3 text-xs font-mono text-gray-300 focus:border-brand/50 outline-none resize-none"
          />
        </Card>
      )}

      {!showRaw && p && (
        <div className="space-y-4">
          {/* Meta row */}
          <Card className="flex flex-wrap items-center gap-x-6 gap-y-2 text-sm">
            <Meta label="Sector" value={p.sector} />
            <Meta label="Industry" value={p.industry} />
            <Meta label="Tier" value={p.priority} />
            <Meta label="Intent" value={p.position_intent} />
            <Meta label="Held" value={p.held ? "yes" : "no"} />
            <Meta label="Reviewed" value={p.last_reviewed} />
            <Meta label="Auto-built" value={p.auto_built ? "yes" : "no"} />
          </Card>

          {p.business_model && (
            <Section title="Business Model">
              <p className="text-sm text-gray-300 leading-relaxed">{p.business_model}</p>
            </Section>
          )}

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            {arr(p.revenue_segments).length > 0 && (
              <Section title="Revenue by Segment">
                <PctList
                  rows={arr(p.revenue_segments).map((s: Any) => ({
                    name: s.name,
                    pct: s.pct_of_revenue,
                    note: s.description,
                  }))}
                />
              </Section>
            )}
            {arr(p.geographic_revenue).length > 0 && (
              <Section title="Revenue by Geography">
                <PctList
                  rows={arr(p.geographic_revenue).map((s: Any) => ({
                    name: s.region,
                    pct: s.pct_of_revenue,
                  }))}
                />
              </Section>
            )}
          </div>

          {arr(p.key_kpis).length > 0 && (
            <Section title="Key KPIs">
              <ul className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-1 text-sm text-gray-300 list-disc pl-5">
                {arr(p.key_kpis).map((k, i: number) => (
                  <li key={i}>{String(k)}</li>
                ))}
              </ul>
            </Section>
          )}

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            {arr(p.bull_thesis_pillars).length > 0 && (
              <Section title="🟢 Bull Pillars">
                <Pillars rows={arr(p.bull_thesis_pillars)} tone="pos" />
              </Section>
            )}
            {arr(p.bear_thesis_pillars).length > 0 && (
              <Section title="🔴 Bear Pillars">
                <Pillars rows={arr(p.bear_thesis_pillars)} tone="neg" />
              </Section>
            )}
          </div>

          {arr(p.red_lines).length > 0 && (
            <Section title="⚠ Red Lines (exit triggers)">
              <div className="space-y-2">
                {arr(p.red_lines).map((r: Any, i: number) => (
                  <div key={i} className="text-sm border-l-2 border-warn/50 pl-3">
                    <div className="text-gray-200">{r.condition}</div>
                    {r.rationale && (
                      <div className="text-xs text-gray-500 mt-0.5">{r.rationale}</div>
                    )}
                  </div>
                ))}
              </div>
            </Section>
          )}

          {arr(p.preferred_peers).length > 0 && (
            <Section title="Preferred Peers">
              <div className="flex flex-wrap gap-2">
                {arr(p.preferred_peers).map((pe, i: number) => (
                  <Badge key={i} className="border-line bg-bg-hover text-gray-300 font-mono">
                    {String(pe)}
                  </Badge>
                ))}
              </div>
            </Section>
          )}

          {p.correlation_notes && (
            <Section title="Correlation Notes">
              <p className="text-sm text-gray-300 leading-relaxed">{p.correlation_notes}</p>
            </Section>
          )}

          {p.pm_notes && (
            <Section title="PM Notes">
              <p className="text-sm text-gray-300 leading-relaxed">{p.pm_notes}</p>
            </Section>
          )}

          {arr(p.historical_lessons).length > 0 && (
            <Section title="Historical Lessons">
              <ul className="text-sm text-gray-300 list-disc pl-5 space-y-1">
                {arr(p.historical_lessons).map((l, i: number) => (
                  <li key={i}>{String(l)}</li>
                ))}
              </ul>
            </Section>
          )}

          {p.long_form_notes && (
            <Section title="Long-form Notes">
              <Markdown>{p.long_form_notes as string}</Markdown>
            </Section>
          )}
        </div>
      )}
    </div>
  );
}

function arr(v: unknown): Any[] {
  return Array.isArray(v) ? (v as Any[]) : [];
}

function Meta({ label, value }: { label: string; value: unknown }) {
  return (
    <div>
      <span className="text-xs uppercase text-gray-500 mr-2">{label}</span>
      <span className="text-gray-200">{value ? String(value) : "—"}</span>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <Card>
      <h3 className="text-sm font-semibold text-brand-glow mb-3">{title}</h3>
      {children}
    </Card>
  );
}

function PctList({ rows }: { rows: { name: string; pct?: number; note?: string }[] }) {
  return (
    <div className="space-y-2">
      {rows.map((r, i) => {
        const pct = typeof r.pct === "number" ? r.pct * 100 : null;
        return (
          <div key={i}>
            <div className="flex items-center justify-between text-sm">
              <span className="text-gray-200">{r.name}</span>
              <span className="font-mono text-gray-400">
                {pct != null ? `${pct.toFixed(1)}%` : "—"}
              </span>
            </div>
            {pct != null && (
              <div className="h-1.5 bg-bg-hover rounded mt-1 overflow-hidden">
                <div
                  className="h-full bg-brand/70 rounded"
                  style={{ width: `${Math.min(100, pct)}%` }}
                />
              </div>
            )}
            {r.note && <div className="text-xs text-gray-500 mt-0.5">{r.note}</div>}
          </div>
        );
      })}
    </div>
  );
}

function Pillars({ rows, tone }: { rows: Any[]; tone: "pos" | "neg" }) {
  return (
    <div className="space-y-2">
      {rows.map((r, i) => (
        <div
          key={i}
          className={cn(
            "text-sm border-l-2 pl-3",
            tone === "pos" ? "border-pos/50" : "border-neg/50"
          )}
        >
          <div className="text-gray-200">{r.text || r}</div>
          {r.confidence && (
            <div className="text-xs text-gray-500 mt-0.5">confidence: {r.confidence}</div>
          )}
        </div>
      ))}
    </div>
  );
}
