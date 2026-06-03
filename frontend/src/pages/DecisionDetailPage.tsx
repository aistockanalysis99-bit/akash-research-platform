import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import { ArrowLeft, ChevronDown, ChevronRight } from "lucide-react";
import { api } from "@/lib/api";
import { Badge, Card, ErrorBox, Loading, PageTitle } from "@/components/ui";
import Markdown from "@/components/Markdown";
import { cn } from "@/lib/utils";
import type { Scorecard } from "@/lib/types";

// Logical order + friendly labels for the stage markdown files.
const STAGE_ORDER: { key: string; label: string; emoji: string }[] = [
  { key: "signal", label: "Signal", emoji: "📍" },
  { key: "fundamental", label: "Fundamental Analyst", emoji: "📊" },
  { key: "news", label: "News Analyst", emoji: "📰" },
  { key: "technical", label: "Technical Analyst", emoji: "📈" },
  { key: "institutional_flow", label: "Institutional Flow", emoji: "🏦" },
  { key: "options_structure", label: "Options Structure", emoji: "📉" },
  { key: "macro_regime", label: "Macro Regime", emoji: "🌐" },
  { key: "bull", label: "Bull Researcher", emoji: "🟢" },
  { key: "bear", label: "Bear Researcher", emoji: "🔴" },
  { key: "judge", label: "Debate Judge", emoji: "⚖️" },
  { key: "risk_manager", label: "Risk Manager", emoji: "🛡️" },
  { key: "macro_context", label: "Macro Context", emoji: "🧭" },
  { key: "pm", label: "Portfolio Manager", emoji: "👔" },
  { key: "summary", label: "Executive Summary", emoji: "📝" },
];

export default function DecisionDetailPage() {
  const { symbol = "", date = "" } = useParams();
  const files = useQuery({
    queryKey: ["decisionFiles", symbol, date],
    queryFn: () => api.aiDecisionFiles(symbol, date),
  });
  const scorecards = useQuery({
    queryKey: ["scorecards", symbol, date],
    queryFn: () => api.aiScorecards(symbol, date),
  });

  return (
    <div>
      <Link
        to="/decisions"
        className="inline-flex items-center gap-1 text-sm text-gray-400 hover:text-brand mb-3"
      >
        <ArrowLeft className="h-4 w-4" /> All decisions
      </Link>

      <PageTitle title={`${symbol}`} subtitle={`Full research dossier · ${date}`} />

      {/* Scorecards */}
      {scorecards.isLoading && <Loading label="Loading scorecards…" />}
      {scorecards.data && scorecards.data.length > 0 && (
        <div className="columns-1 sm:columns-2 lg:columns-3 gap-3 mb-8 [&>*]:mb-3">
          {scorecards.data.map((c) => (
            <ScorecardTile key={c.name} c={c} />
          ))}
        </div>
      )}

      {/* Full reports */}
      <h2 className="text-sm font-semibold uppercase tracking-wide text-gray-400 mb-3">
        Full agent reports
      </h2>
      {files.isLoading && <Loading label="Loading reports…" />}
      {files.error && <ErrorBox error={files.error} />}
      {files.data && (
        <div className="space-y-3">
          {STAGE_ORDER.filter((s) => files.data![s.key]).map((s) => (
            <ReportSection
              key={s.key}
              emoji={s.emoji}
              label={s.label}
              content={files.data![s.key]}
              defaultOpen={["pm", "summary", "bull", "bear"].includes(s.key)}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function ScorecardTile({ c }: { c: Scorecard }) {
  const score =
    c.score_value === null || c.score_value === ""
      ? "—"
      : typeof c.score_value === "number"
      ? `${c.score_value}/10`
      : String(c.score_value);
  return (
    <Card className="hover:border-brand/30 transition-colors break-inside-avoid">
      <div className="flex items-center gap-2 mb-1.5">
        <span className="text-lg">{c.emoji}</span>
        <span className="text-sm font-semibold text-gray-100 flex-1">{c.label}</span>
        <Badge className="border-brand/40 bg-brand/10 text-brand-glow whitespace-nowrap">
          {c.score_label}: {score}
        </Badge>
      </div>
      <p className="text-xs text-gray-400 leading-relaxed whitespace-pre-line">
        {c.summary}
      </p>
    </Card>
  );
}

function ReportSection({
  emoji,
  label,
  content,
  defaultOpen,
}: {
  emoji: string;
  label: string;
  content: string;
  defaultOpen?: boolean;
}) {
  const [open, setOpen] = useState(!!defaultOpen);
  return (
    <Card className="p-0 overflow-hidden">
      <button
        onClick={() => setOpen((o) => !o)}
        className="w-full flex items-center gap-2 px-4 py-3 hover:bg-bg-hover/50 transition-colors"
      >
        <span className="text-base">{emoji}</span>
        <span className="text-sm font-semibold text-gray-100 flex-1 text-left">
          {label}
        </span>
        {open ? (
          <ChevronDown className="h-4 w-4 text-gray-500" />
        ) : (
          <ChevronRight className="h-4 w-4 text-gray-500" />
        )}
      </button>
      <div className={cn("px-4 pb-4 border-t border-line/50", !open && "hidden")}>
        <div className="pt-3">
          <Markdown>{content}</Markdown>
        </div>
      </div>
    </Card>
  );
}
