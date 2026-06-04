import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import { ArrowLeft, ChevronDown, ChevronRight, Download } from "lucide-react";
import { api } from "@/lib/api";
import { Badge, Button, Card, ErrorBox, Loading, Spinner } from "@/components/ui";
import Markdown from "@/components/Markdown";
import { cn, decisionColor } from "@/lib/utils";
import type { DecisionPdfData } from "@/components/DecisionPdf";

// Strip emoji / symbols Helvetica can't render, and normalize the unicode
// minus so the PDF text stays clean.
function cleanForPdf(s?: string): string {
  return (s || "")
    .replace(
      /[\u{1F000}-\u{1FAFF}\u{2600}-\u{27BF}\u{2190}-\u{21FF}\u{2B00}-\u{2BFF}\u{FE00}-\u{FE0F}\u{20E3}]/gu,
      ""
    )
    .replace(/−/g, "-") // unicode minus → hyphen
    .replace(/^[ \t]+/gm, "") // drop leading space left by a removed emoji
    .trim();
}

// Pull the client-facing verdict (BUY / WATCH / AVOID …) from the first line
// of the PM message, e.g. "🟢 MRVL — BUY" → "BUY".
function parseVerdict(msg?: string): string | undefined {
  const first = (msg || "").split("\n")[0];
  const m = first.match(/[—–-]\s*([A-Za-z]+)/);
  return m ? m[1].toUpperCase() : undefined;
}

// Best-effort parse of price levels from the plain-English PM message.
function parseLevels(text: string, fallbackCurrent?: number) {
  const t = text || "";
  const num = (x?: string) => (x == null ? undefined : parseFloat(x.replace(/[,$\s]/g, "")));
  const grab = (re: RegExp) => {
    const m = t.match(re);
    return m ? num(m[1]) : undefined;
  };
  const current =
    fallbackCurrent ??
    grab(/current price[^$\d]*\$?([\d,.]+)/i) ??
    grab(/buy(?:\s+around|\s+at|\s+near)?[^$\d]*\$?([\d,.]+)/i);
  const target = grab(/(?:6-?month\s+)?(?:upside\s+)?target[^$\d]*\$?([\d,.]+)/i);
  const stop = grab(
    /(?:cut losses(?:\s+at)?|sell to cut losses(?:\s+at)?|stop(?:\s+loss)?(?:\s+at)?)[^$\d]*\$?([\d,.]+)/i
  );
  const targetUpsidePct =
    target && current && current > 0 ? ((target - current) / current) * 100 : undefined;
  const stopPct =
    stop && current && current > 0 ? ((stop - current) / current) * 100 : undefined;
  return { current, target, targetUpsidePct, stop, stopPct };
}

// ─── Stage file ordering for full reports ────────────────────────────────────
const REPORT_STAGES: { key: string; label: string; emoji: string }[] = [
  { key: "fundamental",       label: "Fundamental Analyst",   emoji: "📊" },
  { key: "news",              label: "News Analyst",           emoji: "📰" },
  { key: "technical",         label: "Technical Analyst",      emoji: "📈" },
  { key: "institutional_flow",label: "Institutional Flow",     emoji: "🏦" },
  { key: "options_structure", label: "Options Structure",      emoji: "📉" },
  { key: "macro_regime",      label: "Macro Regime",           emoji: "🌐" },
  { key: "bull",              label: "Bull Researcher",        emoji: "🟢" },
  { key: "bear",              label: "Bear Researcher",        emoji: "🔴" },
  { key: "judge",             label: "Debate Judge",           emoji: "⚖️" },
  { key: "risk_manager",      label: "Risk Manager",           emoji: "🛡️" },
  { key: "pm",                label: "Portfolio Manager",      emoji: "👔" },
  { key: "summary",           label: "Executive Summary",      emoji: "📝" },
];

// ─── Main page ────────────────────────────────────────────────────────────────
export default function DecisionDetailPage() {
  const { symbol = "", date = "" } = useParams();

  const files = useQuery({
    queryKey: ["decisionFiles", symbol, date],
    queryFn:  () => api.aiDecisionFiles(symbol, date),
  });
  const scorecards = useQuery({
    queryKey: ["scorecards", symbol, date],
    queryFn:  () => api.aiScorecards(symbol, date),
  });
  const [building, setBuilding] = useState(false);

  if (files.isLoading || scorecards.isLoading) return <Loading />;
  if (files.error) return <ErrorBox error={files.error} />;

  const sc   = Object.fromEntries((scorecards.data || []).map((c) => [c.name, c]));
  const f    = files.data || {};

  // Telegram messages come from the PM scorecard (extended fields).
  const pmCard        = (scorecards.data || []).find((c) => c.name === "pm");
  const stockViewMsg  = pmCard?.telegram_message || "";
  const portFitMsg    = pmCard?.telegram_portfolio_message || "";

  // Pull fields directly from scorecards / raw files
  const pm         = sc["pm"];
  const bull       = sc["bull"];
  const bear       = sc["bear"];
  const judge      = sc["judge"];
  const risk       = sc["risk"];
  const fund       = sc["fundamental"];
  const news       = sc["news"];
  const tech       = sc["technical"];
  const instFlow   = sc["institutional_flow"];
  const macro      = sc["macro_regime"];
  const opts       = sc["options_structure"];

  const decision   = pm?.score_value as string | undefined;
  const conviction = bull ? (bull.score_value as number) : undefined;

  async function downloadPdf() {
    setBuilding(true);
    try {
      // Code-split: only pull the heavy PDF lib + doc when the user asks for it.
      const [{ pdf }, { default: DecisionPdf }] = await Promise.all([
        import("@react-pdf/renderer"),
        import("@/components/DecisionPdf"),
      ]);
      const [bars, quote] = await Promise.all([
        api.quoteBars(symbol, 130).catch(() => []),
        api.portfolioQuote(symbol).catch(() => null),
      ]);
      const levels = parseLevels(stockViewMsg, quote?.price);

      const data: DecisionPdfData = {
        symbol,
        date,
        name: quote?.name,
        sector: quote?.sector,
        decision: parseVerdict(stockViewMsg) || decision,
        conviction,
        currentPrice: levels.current,
        target: levels.target,
        targetUpsidePct: levels.targetUpsidePct,
        stop: levels.stop,
        stopPct: levels.stopPct,
        scores: [
          { label: "Fundamental", value: fund?.score_value ?? null, kind: "high" },
          { label: "News risk", value: news?.score_value ?? null, kind: "low" },
          { label: "Technical", value: tech?.score_value ?? null, kind: "high" },
          { label: "Smart money", value: instFlow?.score_value ?? null, kind: "high" },
          { label: "Macro risk", value: macro?.score_value ?? null, kind: "low" },
          { label: "Dealer", value: opts?.score_value ?? null, kind: "text" },
        ],
        stockView: cleanForPdf(stockViewMsg),
        portFit: cleanForPdf(portFitMsg),
        bull: { conv: bull?.score_value, summary: bull?.summary },
        bear: { conv: bear?.score_value, summary: bear?.summary },
        judge: { winner: judge?.score_value ? String(judge.score_value) : undefined, summary: judge?.summary },
        risk: { verdict: risk?.score_value ? String(risk.score_value) : undefined, summary: risk?.summary },
        pm: { summary: pm?.summary },
        bars,
        generatedAt: new Date().toLocaleString("en-US", { dateStyle: "medium", timeStyle: "short" }),
      };

      const blob = await pdf(<DecisionPdf data={data} />).toBlob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${symbol}_${date}_research.pdf`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (e) {
      console.error("PDF generation failed", e);
      alert("Could not generate the PDF. Please try again.");
    } finally {
      setBuilding(false);
    }
  }

  return (
    <div className="max-w-5xl mx-auto">
      {/* Back nav + PDF download */}
      <div className="flex items-center justify-between mb-4">
        <Link
          to="/decisions"
          className="inline-flex items-center gap-1 text-sm text-gray-400 hover:text-brand"
        >
          <ArrowLeft className="h-4 w-4" /> All decisions
        </Link>
        <Button variant="outline" onClick={downloadPdf} disabled={building}>
          {building ? <Spinner /> : <Download className="h-4 w-4" />}
          {building ? "Building PDF…" : "Download PDF"}
        </Button>
      </div>

      {/* ── ZONE 1: Verdict hero ─────────────────────────────────────── */}
      <div className="flex items-start gap-4 mb-5">
        <div>
          <h1 className="text-3xl font-extrabold font-mono">{symbol}</h1>
          <div className="text-sm text-gray-500 mt-0.5">{date}</div>
        </div>
        <div className="flex items-center gap-3 mt-1 flex-wrap">
          {decision && (
            <Badge className={cn("text-base px-3 py-1 font-bold", decisionColor(decision))}>
              {decision}
            </Badge>
          )}
          {conviction != null && (
            <Badge className="border-line bg-bg-hover text-gray-300 text-sm px-3 py-1">
              Conviction {conviction}/10
            </Badge>
          )}
          {pm?.score_label && pm.score_value && (
            <Badge className="border-line bg-bg-hover text-gray-400 text-sm">
              {pm.score_label}: {String(pm.score_value)}
            </Badge>
          )}
        </div>
      </div>

      {/* Telegram messages — always shown in full */}
      {(stockViewMsg || portFitMsg) && (
        <TelegramMessages stockView={stockViewMsg} portFit={portFitMsg} />
      )}

      {/* ── ZONE 2: Signal strip ────────────────────────────────────── */}
      <div className="grid grid-cols-3 sm:grid-cols-6 gap-2 mb-6">
        <Signal label="Fundamental" value={fund?.score_value} max={10} good="high" />
        <Signal label="News risk"   value={news?.score_value}  max={10} good="low" />
        <Signal label="Technical"   value={tech?.score_value}  max={10} good="high" />
        <Signal label="Smart money" value={instFlow?.score_value} max={10} good="high" />
        <Signal label="Macro risk"  value={macro?.score_value} max={10} good="low" />
        <Signal label="Dealer"      value={opts?.score_value}  isText />
      </div>

      {/* ── ZONE 3: Analysis cards ──────────────────────────────────── */}
      {/* 3a — 4 analyst mini-cards */}
      <SectionLabel>Analyst signals</SectionLabel>
      <div className="grid grid-cols-2 gap-3 mb-4">
        <MiniCard emoji="📊" label="Fundamental" scoreLabel="Score" score={fund?.score_value} summary={fund?.summary} />
        <MiniCard emoji="📰" label="News"         scoreLabel="Risk"  score={news?.score_value} summary={news?.summary} />
        <MiniCard emoji="🏦" label="Institutional Flow" scoreLabel="Smart $" score={instFlow?.score_value} summary={instFlow?.summary} />
        <MiniCard emoji="🌐" label="Macro Regime" scoreLabel="Risk"  score={macro?.score_value} summary={macro?.summary} />
      </div>

      {/* 3b — Bull vs Bear side-by-side */}
      <SectionLabel>Bull vs Bear</SectionLabel>
      <div className="grid grid-cols-2 gap-3 mb-4">
        <DebateCard side="bull" emoji="🟢" label="Bull Researcher" conviction={bull?.score_value} summary={bull?.summary} />
        <DebateCard side="bear" emoji="🔴" label="Bear Researcher"  conviction={bear?.score_value} summary={bear?.summary} />
      </div>

      {/* 3c — Judge verdict */}
      {judge && (
        <>
          <SectionLabel>Debate Judge</SectionLabel>
          <Card className="mb-4">
            <div className="flex items-center gap-3 mb-2">
              <span className="text-xl">⚖️</span>
              <span className="font-semibold text-gray-100">
                Winner:{" "}
                <span className={judge.score_value === "bull" ? "text-pos" : "text-neg"}>
                  {String(judge.score_value || "—").toUpperCase()}
                </span>
              </span>
            </div>
            <p className="text-sm text-gray-300 leading-relaxed">{judge.summary}</p>
          </Card>
        </>
      )}

      {/* 3d — Risk + PM chain */}
      <SectionLabel>Decision chain</SectionLabel>
      <div className="grid grid-cols-2 gap-3 mb-6">
        <Card>
          <div className="flex items-center gap-2 mb-2">
            <span className="text-xl">🛡️</span>
            <span className="font-semibold text-gray-100">Risk Manager</span>
            {risk?.score_value && (
              <Badge className={cn("ml-auto", riskColor(String(risk.score_value)))}>
                {risk.score_value}
              </Badge>
            )}
          </div>
          <p className="text-xs text-gray-400 leading-relaxed">{risk?.summary}</p>
        </Card>
        <Card>
          <div className="flex items-center gap-2 mb-2">
            <span className="text-xl">👔</span>
            <span className="font-semibold text-gray-100">Portfolio Manager</span>
            {decision && (
              <Badge className={cn("ml-auto", decisionColor(decision))}>
                {decision}
              </Badge>
            )}
          </div>
          <p className="text-xs text-gray-400 leading-relaxed">{pm?.summary}</p>
        </Card>
      </div>

      {/* ── ZONE 4: Full reports (collapsed) ────────────────────────── */}
      <SectionLabel>Full agent reports</SectionLabel>
      <div className="space-y-2">
        {REPORT_STAGES.filter((s) => f[s.key]).map((s) => (
          <CollapsibleReport
            key={s.key}
            emoji={s.emoji}
            label={s.label}
            content={f[s.key]}
            defaultOpen={false}
          />
        ))}
      </div>
    </div>
  );
}

// ─── Telegram messages block ─────────────────────────────────────────────────
function TelegramMessages({ stockView, portFit }: { stockView: string; portFit: string }) {
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mb-6">
      {stockView && (
        <Card className="border-l-4 border-brand/60">
          <div className="text-xs uppercase tracking-wide text-brand/70 mb-2 font-semibold">
            📈 Stock view
          </div>
          <pre className="text-sm text-gray-200 whitespace-pre-wrap leading-relaxed font-sans">
            {stockView}
          </pre>
        </Card>
      )}
      {portFit && (
        <Card className="border-l-4 border-gray-600">
          <div className="text-xs uppercase tracking-wide text-gray-500 mb-2 font-semibold">
            📂 Portfolio fit
          </div>
          <pre className="text-sm text-gray-300 whitespace-pre-wrap leading-relaxed font-sans">
            {portFit}
          </pre>
        </Card>
      )}
    </div>
  );
}

// ─── Signal strip chip ────────────────────────────────────────────────────────
function Signal({
  label, value, max, good, isText,
}: {
  label: string;
  value?: number | string | null;
  max?: number;
  good?: "high" | "low";
  isText?: boolean;
}) {
  const v = value;
  let color = "text-gray-300";
  if (!isText && typeof v === "number" && max) {
    const pct = v / max;
    if (good === "high") color = pct >= 0.7 ? "text-pos" : pct >= 0.4 ? "text-warn" : "text-neg";
    if (good === "low")  color = pct <= 0.3 ? "text-pos" : pct <= 0.6 ? "text-warn" : "text-neg";
  }
  return (
    <div className="card p-2 text-center">
      <div className="text-[10px] uppercase text-gray-500 truncate">{label}</div>
      <div className={cn("text-lg font-bold stat-num mt-0.5", color)}>
        {v == null ? "—" : isText ? String(v).replace("_", " ") : `${v}${max ? `/${max}` : ""}`}
      </div>
    </div>
  );
}

// ─── Analyst mini-card ────────────────────────────────────────────────────────
function MiniCard({ emoji, label, scoreLabel, score, summary }: {
  emoji: string; label: string; scoreLabel: string;
  score?: number | string | null; summary?: string;
}) {
  return (
    <Card>
      <div className="flex items-center gap-2 mb-1.5">
        <span className="text-lg">{emoji}</span>
        <span className="text-sm font-semibold text-gray-100 flex-1">{label}</span>
        {score != null && (
          <Badge className="border-line bg-bg-hover text-gray-300 shrink-0">
            {scoreLabel}: {String(score)}{typeof score === "number" ? "/10" : ""}
          </Badge>
        )}
      </div>
      <p className="text-xs text-gray-400 leading-relaxed">{summary || "—"}</p>
    </Card>
  );
}

// ─── Bull / Bear card ─────────────────────────────────────────────────────────
function DebateCard({ side, emoji, label, conviction, summary }: {
  side: "bull" | "bear"; emoji: string; label: string;
  conviction?: number | string | null; summary?: string;
}) {
  const border = side === "bull" ? "border-l-4 border-pos/50" : "border-l-4 border-neg/50";
  return (
    <Card className={border}>
      <div className="flex items-center gap-2 mb-1.5">
        <span className="text-lg">{emoji}</span>
        <span className="text-sm font-semibold text-gray-100 flex-1">{label}</span>
        {conviction != null && (
          <Badge className={cn("shrink-0", side === "bull" ? "border-pos/40 bg-pos/10 text-pos" : "border-neg/40 bg-neg/10 text-neg")}>
            {conviction}/10
          </Badge>
        )}
      </div>
      <p className="text-xs text-gray-400 leading-relaxed">{summary || "—"}</p>
    </Card>
  );
}

// ─── Collapsible report ───────────────────────────────────────────────────────
function CollapsibleReport({ emoji, label, content, defaultOpen }: {
  emoji: string; label: string; content: string; defaultOpen: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <Card className="p-0 overflow-hidden">
      <button
        onClick={() => setOpen((o) => !o)}
        className="w-full flex items-center gap-2 px-4 py-3 hover:bg-bg-hover/50 transition-colors"
      >
        <span className="text-base">{emoji}</span>
        <span className="text-sm font-semibold text-gray-100 flex-1 text-left">{label}</span>
        {open
          ? <ChevronDown className="h-4 w-4 text-gray-500" />
          : <ChevronRight className="h-4 w-4 text-gray-500" />}
      </button>
      {open && (
        <div className="px-4 pb-4 border-t border-line/50">
          <div className="pt-3">
            <Markdown>{content}</Markdown>
          </div>
        </div>
      )}
    </Card>
  );
}

// ─── Helpers ──────────────────────────────────────────────────────────────────
function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <div className="text-xs font-semibold uppercase tracking-wider text-gray-500 mb-2 mt-2">
      {children}
    </div>
  );
}

function riskColor(verdict: string): string {
  const v = verdict.toUpperCase();
  if (v === "CLEAR" || v === "APPROVE") return "border-pos/40 bg-pos/10 text-pos";
  if (v === "BLOCK" || v === "REJECT")  return "border-neg/40 bg-neg/10 text-neg";
  return "border-warn/40 bg-warn/10 text-warn";
}
