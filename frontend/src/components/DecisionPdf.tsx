import {
  Document,
  Page,
  View,
  Text,
  StyleSheet,
  Svg,
  Polyline,
  Line,
  Rect,
} from "@react-pdf/renderer";

// ── Data contract ─────────────────────────────────────────────────────────────
export interface DecisionPdfData {
  symbol: string;
  date: string;
  name?: string;
  sector?: string;
  decision?: string; // BUY / WATCH / AVOID / APPROVE / RESIZE / REJECT
  conviction?: number;
  currentPrice?: number;
  target?: number;
  targetUpsidePct?: number;
  stop?: number;
  stopPct?: number;
  scores: { label: string; value: number | string | null; kind: "high" | "low" | "text" }[];
  stockView?: string;
  portFit?: string;
  bull?: { conv?: number | string | null; summary?: string };
  bear?: { conv?: number | string | null; summary?: string };
  judge?: { winner?: string; summary?: string };
  risk?: { verdict?: string; summary?: string };
  pm?: { summary?: string };
  bars: { date: string; close: number }[];
  generatedAt: string;
}

// ── Palette ─────────────────────────────────────────────────────────────────
const C = {
  ink: "#111827",
  body: "#374151",
  muted: "#6b7280",
  faint: "#9ca3af",
  line: "#e5e7eb",
  soft: "#f9fafb",
  brand: "#0d9488",
  pos: "#16a34a",
  neg: "#dc2626",
  warn: "#d97706",
  white: "#ffffff",
};

function verdictStyle(d?: string): { bg: string; fg: string } {
  const v = (d || "").toUpperCase();
  if (["BUY", "APPROVE"].includes(v)) return { bg: "#dcfce7", fg: "#166534" };
  if (["WATCH", "RESIZE", "HOLD"].includes(v)) return { bg: "#fef3c7", fg: "#92400e" };
  if (["AVOID", "REJECT", "BLOCK"].includes(v)) return { bg: "#fee2e2", fg: "#991b1b" };
  return { bg: "#f3f4f6", fg: "#374151" };
}

function scoreColor(value: number | string | null, kind: "high" | "low" | "text"): string {
  if (typeof value !== "number") return C.ink;
  const p = value / 10;
  if (kind === "high") return p >= 0.7 ? C.pos : p >= 0.4 ? C.warn : C.neg;
  if (kind === "low") return p <= 0.3 ? C.pos : p <= 0.6 ? C.warn : C.neg;
  return C.ink;
}

const fmtMoney = (n?: number) =>
  n == null ? "—" : `$${n.toLocaleString("en-US", { maximumFractionDigits: 2 })}`;

// ── Styles ────────────────────────────────────────────────────────────────────
const s = StyleSheet.create({
  page: { paddingTop: 34, paddingBottom: 44, paddingHorizontal: 36, fontFamily: "Helvetica", color: C.body, fontSize: 9.5 },
  // header
  headRow: { flexDirection: "row", justifyContent: "space-between", alignItems: "flex-start" },
  brandTag: { fontSize: 7.5, letterSpacing: 1.5, color: C.faint, fontFamily: "Helvetica-Bold" },
  symbol: { fontSize: 26, fontFamily: "Helvetica-Bold", color: C.ink, marginTop: 2 },
  name: { fontSize: 10, color: C.body, marginTop: 1 },
  sector: { fontSize: 8.5, color: C.muted },
  verdictPill: { borderRadius: 6, paddingVertical: 6, paddingHorizontal: 12, alignItems: "center", minWidth: 96 },
  verdictText: { fontSize: 15, fontFamily: "Helvetica-Bold" },
  convText: { fontSize: 8, marginTop: 2 },
  divider: { borderBottomWidth: 1, borderBottomColor: C.line, marginVertical: 12 },
  // key levels
  levelsRow: { flexDirection: "row", marginBottom: 4 },
  levelBox: { flex: 1, backgroundColor: C.soft, borderRadius: 6, borderWidth: 1, borderColor: C.line, padding: 8, marginRight: 8 },
  levelLabel: { fontSize: 7.5, letterSpacing: 0.5, color: C.muted, textTransform: "uppercase" },
  levelValue: { fontSize: 15, fontFamily: "Helvetica-Bold", color: C.ink, marginTop: 3 },
  levelSub: { fontSize: 8, marginTop: 1 },
  // section
  sectionTitle: { fontSize: 8.5, letterSpacing: 1, color: C.muted, textTransform: "uppercase", fontFamily: "Helvetica-Bold", marginBottom: 5, marginTop: 14 },
  // scores
  scoreRow: { flexDirection: "row" },
  scoreBox: { flex: 1, marginRight: 5, backgroundColor: C.soft, borderRadius: 5, borderWidth: 1, borderColor: C.line, paddingVertical: 6, paddingHorizontal: 2, alignItems: "center" },
  scoreLabel: { fontSize: 6.5, color: C.muted, textTransform: "uppercase" },
  scoreValue: { fontSize: 13, fontFamily: "Helvetica-Bold", marginTop: 2 },
  // prose
  prose: { fontSize: 9.5, color: C.body, lineHeight: 1.5 },
  // cards
  card: { borderWidth: 1, borderColor: C.line, borderRadius: 6, padding: 9, marginBottom: 8 },
  cardHead: { flexDirection: "row", alignItems: "center", marginBottom: 4 },
  cardTitle: { fontSize: 10, fontFamily: "Helvetica-Bold", color: C.ink },
  cardBadge: { marginLeft: "auto", fontSize: 8, fontFamily: "Helvetica-Bold", paddingVertical: 2, paddingHorizontal: 6, borderRadius: 4 },
  twoCol: { flexDirection: "row" },
  footer: { position: "absolute", bottom: 20, left: 36, right: 36, flexDirection: "row", justifyContent: "space-between", borderTopWidth: 1, borderTopColor: C.line, paddingTop: 6 },
  footerText: { fontSize: 7, color: C.faint },
});

// ── Price chart (vector) ──────────────────────────────────────────────────────
function PriceChart({ bars, target, stop, current }: {
  bars: { date: string; close: number }[];
  target?: number; stop?: number; current?: number;
}) {
  const W = 523, H = 150, pad = 6;
  if (!bars || bars.length < 2) {
    return (
      <View style={{ height: 60, justifyContent: "center", alignItems: "center", backgroundColor: C.soft, borderRadius: 6, borderWidth: 1, borderColor: C.line }}>
        <Text style={{ fontSize: 8.5, color: C.muted }}>Price history unavailable</Text>
      </View>
    );
  }
  const closes = bars.map((b) => b.close);
  const domainVals = [...closes];
  if (target) domainVals.push(target);
  if (stop) domainVals.push(stop);
  const min = Math.min(...domainVals);
  const max = Math.max(...domainVals);
  const span = max - min || 1;

  const x = (i: number) => pad + (i * (W - 2 * pad)) / (bars.length - 1);
  const y = (v: number) => H - pad - ((v - min) / span) * (H - 2 * pad);

  const points = bars.map((b, i) => `${x(i).toFixed(1)},${y(b.close).toFixed(1)}`).join(" ");
  const first = bars[0].close;
  const last = closes[closes.length - 1];
  const up = last >= first;
  const lineColor = up ? C.pos : C.neg;

  return (
    <View>
      <Svg width={W} height={H} style={{ borderWidth: 1, borderColor: C.line, borderRadius: 6, backgroundColor: C.white }}>
        <Rect x={0} y={0} width={W} height={H} fill={C.white} />
        {/* baseline grid: top + bottom */}
        <Line x1={pad} y1={y(max)} x2={W - pad} y2={y(max)} strokeWidth={0.5} stroke={C.line} />
        <Line x1={pad} y1={y(min)} x2={W - pad} y2={y(min)} strokeWidth={0.5} stroke={C.line} />
        {/* target line */}
        {target != null && (
          <Line x1={pad} y1={y(target)} x2={W - pad} y2={y(target)} strokeWidth={1} stroke={C.pos} strokeDasharray="3 3" />
        )}
        {/* stop line */}
        {stop != null && (
          <Line x1={pad} y1={y(stop)} x2={W - pad} y2={y(stop)} strokeWidth={1} stroke={C.neg} strokeDasharray="3 3" />
        )}
        {/* price polyline */}
        <Polyline points={points} fill="none" stroke={lineColor} strokeWidth={1.4} />
      </Svg>
      {/* labels */}
      <View style={{ flexDirection: "row", justifyContent: "space-between", marginTop: 3 }}>
        <Text style={{ fontSize: 7, color: C.muted }}>{bars[0].date}  ·  low {fmtMoney(min)}</Text>
        <Text style={{ fontSize: 7, color: C.muted }}>
          last {fmtMoney(last)}{target != null ? `   · target ${fmtMoney(target)}` : ""}{stop != null ? `   · stop ${fmtMoney(stop)}` : ""}
        </Text>
      </View>
    </View>
  );
}

// ── Document ──────────────────────────────────────────────────────────────────
export default function DecisionPdf({ data }: { data: DecisionPdfData }) {
  const vs = verdictStyle(data.decision);
  const levels: { label: string; value: string; sub?: string; subColor?: string }[] = [];
  if (data.currentPrice != null)
    levels.push({ label: "Current price", value: fmtMoney(data.currentPrice) });
  if (data.target != null)
    levels.push({
      label: "6-month target",
      value: fmtMoney(data.target),
      sub: data.targetUpsidePct != null ? `+${data.targetUpsidePct.toFixed(0)}% upside` : undefined,
      subColor: C.pos,
    });
  if (data.stop != null)
    levels.push({
      label: "Cut losses at",
      value: fmtMoney(data.stop),
      sub: data.stopPct != null ? `-${Math.abs(data.stopPct).toFixed(0)}% stop` : undefined,
      subColor: C.neg,
    });

  return (
    <Document title={`${data.symbol} research — ${data.date}`} author="Akash Research Platform">
      <Page size="LETTER" style={s.page} wrap>
        {/* Header */}
        <View style={s.headRow}>
          <View style={{ flex: 1 }}>
            <Text style={s.brandTag}>AKASH RESEARCH PLATFORM</Text>
            <Text style={s.symbol}>{data.symbol}</Text>
            {data.name ? <Text style={s.name}>{data.name}</Text> : null}
            <Text style={s.sector}>
              {(data.sector || "").toString()}{data.sector ? "  ·  " : ""}Analysis {data.date}
            </Text>
          </View>
          <View style={[s.verdictPill, { backgroundColor: vs.bg }]}>
            <Text style={[s.verdictText, { color: vs.fg }]}>{(data.decision || "—").toUpperCase()}</Text>
            {data.conviction != null && (
              <Text style={[s.convText, { color: vs.fg }]}>Conviction {data.conviction}/10</Text>
            )}
          </View>
        </View>

        <View style={s.divider} />

        {/* Key levels */}
        {levels.length > 0 && (
          <View style={s.levelsRow}>
            {levels.map((lv, i) => (
              <View key={i} style={[s.levelBox, i === levels.length - 1 ? { marginRight: 0 } : {}]}>
                <Text style={s.levelLabel}>{lv.label}</Text>
                <Text style={s.levelValue}>{lv.value}</Text>
                {lv.sub ? <Text style={[s.levelSub, { color: lv.subColor || C.muted }]}>{lv.sub}</Text> : null}
              </View>
            ))}
          </View>
        )}

        {/* Price chart */}
        <Text style={s.sectionTitle}>Price — recent history</Text>
        <PriceChart bars={data.bars} target={data.target} stop={data.stop} current={data.currentPrice} />

        {/* Signal scores */}
        <Text style={s.sectionTitle}>Signal scorecard</Text>
        <View style={s.scoreRow}>
          {data.scores.map((sc, i) => (
            <View key={i} style={[s.scoreBox, i === data.scores.length - 1 ? { marginRight: 0 } : {}]}>
              <Text style={s.scoreLabel}>{sc.label}</Text>
              <Text style={[s.scoreValue, { color: scoreColor(sc.value, sc.kind) }]}>
                {sc.value == null ? "—" : sc.kind === "text" ? String(sc.value).replace(/_/g, " ") : `${sc.value}/10`}
              </Text>
            </View>
          ))}
        </View>

        {/* Plain-English verdict */}
        {data.stockView ? (
          <>
            <Text style={s.sectionTitle}>What the AI concluded</Text>
            <Text style={s.prose}>{data.stockView}</Text>
          </>
        ) : null}

        {/* Portfolio fit */}
        {data.portFit ? (
          <>
            <Text style={s.sectionTitle}>How it fits your portfolio</Text>
            <Text style={s.prose}>{data.portFit}</Text>
          </>
        ) : null}

        {/* Debate */}
        {(data.bull?.summary || data.bear?.summary) && (
          <>
            <Text style={s.sectionTitle} break={false}>The debate</Text>
            <View style={s.twoCol}>
              <View style={[s.card, { flex: 1, marginRight: 8, borderLeftWidth: 3, borderLeftColor: C.pos }]}>
                <View style={s.cardHead}>
                  <Text style={s.cardTitle}>Bull case</Text>
                  {data.bull?.conv != null && (
                    <Text style={[s.cardBadge, { backgroundColor: "#dcfce7", color: "#166534" }]}>{data.bull.conv}/10</Text>
                  )}
                </View>
                <Text style={s.prose}>{data.bull?.summary || "—"}</Text>
              </View>
              <View style={[s.card, { flex: 1, borderLeftWidth: 3, borderLeftColor: C.neg }]}>
                <View style={s.cardHead}>
                  <Text style={s.cardTitle}>Bear case</Text>
                  {data.bear?.conv != null && (
                    <Text style={[s.cardBadge, { backgroundColor: "#fee2e2", color: "#991b1b" }]}>{data.bear.conv}/10</Text>
                  )}
                </View>
                <Text style={s.prose}>{data.bear?.summary || "—"}</Text>
              </View>
            </View>
          </>
        )}

        {/* Decision chain */}
        {(data.judge?.summary || data.risk?.summary || data.pm?.summary) && (
          <>
            <Text style={s.sectionTitle}>Decision chain</Text>
            {data.judge?.summary ? (
              <View style={s.card}>
                <View style={s.cardHead}>
                  <Text style={s.cardTitle}>Debate judge</Text>
                  {data.judge.winner ? (
                    <Text style={[s.cardBadge, { backgroundColor: C.soft, color: C.ink }]}>
                      Winner: {data.judge.winner.toUpperCase()}
                    </Text>
                  ) : null}
                </View>
                <Text style={s.prose}>{data.judge.summary}</Text>
              </View>
            ) : null}
            {data.risk?.summary ? (
              <View style={s.card}>
                <View style={s.cardHead}>
                  <Text style={s.cardTitle}>Risk manager</Text>
                  {data.risk.verdict ? (
                    <Text style={[s.cardBadge, { backgroundColor: C.soft, color: C.ink }]}>{data.risk.verdict}</Text>
                  ) : null}
                </View>
                <Text style={s.prose}>{data.risk.summary}</Text>
              </View>
            ) : null}
            {data.pm?.summary ? (
              <View style={s.card}>
                <View style={s.cardHead}>
                  <Text style={s.cardTitle}>Portfolio manager</Text>
                  <Text style={[s.cardBadge, { backgroundColor: vs.bg, color: vs.fg }]}>{(data.decision || "—").toUpperCase()}</Text>
                </View>
                <Text style={s.prose}>{data.pm.summary}</Text>
              </View>
            ) : null}
          </>
        )}

        {/* Footer */}
        <View style={s.footer} fixed>
          <Text style={s.footerText}>
            Generated {data.generatedAt} · Akash Research Platform
          </Text>
          <Text
            style={s.footerText}
            render={({ pageNumber, totalPages }) => `${pageNumber} / ${totalPages}  ·  Informational only — not financial advice`}
          />
        </View>
      </Page>
    </Document>
  );
}
