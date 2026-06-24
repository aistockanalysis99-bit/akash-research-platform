import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { FlaskConical, Play, Search, Check } from "lucide-react";
import { api } from "@/lib/api";
import { Badge, Button, Card, ErrorBox, PageTitle, Spinner } from "@/components/ui";
import { cn } from "@/lib/utils";

function verdictCls(v?: string): string {
  const u = (v || "").toUpperCase();
  if (u.includes("BUY") || u.includes("APPROVE")) return "border-pos/40 bg-pos/10 text-pos";
  if (u.includes("WATCH") || u.includes("HOLD")) return "border-warn/40 bg-warn/10 text-warn";
  if (u.includes("AVOID") || u.includes("SELL")) return "border-neg/40 bg-neg/10 text-neg";
  return "border-line bg-bg-hover text-gray-300";
}

export default function ModelLabPage() {
  const models = useQuery({ queryKey: ["compareModels"], queryFn: api.compareModels });
  const [ticker, setTicker] = useState("");
  const [picked, setPicked] = useState<Record<string, boolean>>({});

  // default: all models selected once loaded
  const allKeys = (models.data || []).map((m) => m.key);
  const selected = allKeys.filter((k) => picked[k] !== false);

  const run = useMutation({
    mutationFn: () => api.compareRun(ticker.trim().toUpperCase(), selected),
  });

  const data = run.data;
  const cols = data?.results?.length || 1;

  return (
    <div>
      <PageTitle
        title="Model Lab — Compare Mode"
        subtitle="Run the same stock through several AI models, side by side. Test whether open models (DeepSeek, GLM, Qwen) match Claude — before buying any hardware."
      />

      {/* Controls */}
      <Card className="mb-5">
        <div className="flex items-center gap-2 flex-wrap mb-3">
          <div className="relative flex-1 min-w-[200px]">
            <Search className="h-4 w-4 text-gray-500 absolute left-3 top-1/2 -translate-y-1/2" />
            <input
              value={ticker}
              onChange={(e) => setTicker(e.target.value.toUpperCase())}
              onKeyDown={(e) => e.key === "Enter" && ticker.trim() && selected.length && run.mutate()}
              placeholder="Ticker, e.g. NVDA"
              autoComplete="off"
              spellCheck={false}
              className="w-full bg-bg-soft border border-line rounded-lg pl-9 pr-3 py-2 text-sm font-mono uppercase placeholder:font-sans placeholder:normal-case focus:border-brand/50 outline-none"
            />
          </div>
          <Button
            onClick={() => run.mutate()}
            disabled={!ticker.trim() || selected.length === 0 || run.isPending}
          >
            {run.isPending ? <Spinner /> : <Play className="h-4 w-4" />}
            {run.isPending ? "Running…" : "Compare"}
          </Button>
        </div>

        {/* Model picker */}
        <div className="flex flex-wrap gap-2">
          {(models.data || []).map((m) => {
            const on = picked[m.key] !== false;
            return (
              <button
                key={m.key}
                onClick={() => setPicked((p) => ({ ...p, [m.key]: !on }))}
                className={cn(
                  "inline-flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-xs transition-colors",
                  on ? "border-brand/50 bg-brand/10 text-brand" : "border-line text-gray-500 hover:text-gray-300"
                )}
                title={m.tagline}
              >
                <span className={cn("h-3.5 w-3.5 rounded-sm border flex items-center justify-center",
                  on ? "border-brand bg-brand/20" : "border-gray-600")}>
                  {on && <Check className="h-3 w-3" />}
                </span>
                {m.name}
              </button>
            );
          })}
        </div>
        {run.isPending && (
          <div className="text-xs text-gray-500 mt-3 animate-pulse">
            Running {selected.length} models on {ticker.toUpperCase()} — reasoning models can take 30–90s each…
          </div>
        )}
      </Card>

      {run.error && <ErrorBox error={run.error} />}

      {data && (
        <>
          {/* Header / context */}
          <div className="flex items-baseline gap-3 mb-3 flex-wrap">
            <h2 className="text-lg font-bold text-white font-mono">{data.symbol}</h2>
            <span className="text-sm text-gray-400">{data.company}</span>
            <div className="flex-1" />
            <span className="text-xs text-gray-500">
              run cost: <span className="text-gray-300 font-mono">${data.total_cost_usd?.toFixed(4)}</span>
            </span>
          </div>

          {/* Disagreement banner */}
          <Verdicts results={data.results} />

          {/* Side-by-side cards */}
          <div
            className="grid gap-3 mt-3"
            style={{ gridTemplateColumns: `repeat(${Math.min(cols, 4)}, minmax(0, 1fr))` }}
          >
            {data.results.map((r) => (
              <Card key={r.key} className="flex flex-col">
                <div className="mb-2">
                  <div className="font-bold text-white text-sm">{r.model}</div>
                  <div className="text-[11px] text-gray-500">{r.tagline}</div>
                </div>

                {r.ok ? (
                  <>
                    <div className="flex items-center gap-2 mb-2 flex-wrap">
                      <Badge className={cn("text-sm px-2.5 py-0.5 font-bold", verdictCls(r.verdict))}>
                        {r.verdict || "—"}
                      </Badge>
                      <Badge className="border-line bg-bg-hover text-gray-300">
                        {r.conviction ?? "—"}/10
                      </Badge>
                    </div>
                    <div className="grid grid-cols-2 gap-2 mb-2 text-xs">
                      <div className="rounded bg-bg-hover/50 p-1.5">
                        <div className="text-gray-500">Target</div>
                        <div className="text-pos font-mono font-semibold">
                          {r.target_price != null ? `$${r.target_price}` : "—"}
                        </div>
                      </div>
                      <div className="rounded bg-bg-hover/50 p-1.5">
                        <div className="text-gray-500">Stop</div>
                        <div className="text-neg font-mono font-semibold">
                          {r.stop_price != null ? `$${r.stop_price}` : "—"}
                        </div>
                      </div>
                    </div>
                    <p className="text-xs text-gray-300 leading-relaxed mb-2">{r.summary}</p>
                    {!!r.bull_points?.length && (
                      <Points label="Bull" cls="text-pos" items={r.bull_points} />
                    )}
                    {!!r.bear_points?.length && (
                      <Points label="Bear" cls="text-neg" items={r.bear_points} />
                    )}
                    {r.key_risk && (
                      <div className="text-[11px] text-gray-400 mt-1 border-t border-line/50 pt-1.5">
                        <span className="text-warn font-semibold">Key risk: </span>{r.key_risk}
                      </div>
                    )}
                  </>
                ) : (
                  <div className="text-xs text-neg">
                    Failed: {r.error || "no valid output"}
                    {r.raw_text && (
                      <pre className="text-[10px] text-gray-500 whitespace-pre-wrap mt-1">{r.raw_text}</pre>
                    )}
                  </div>
                )}

                <div className="flex items-center gap-3 text-[10px] text-gray-600 mt-auto pt-2 border-t border-line/50">
                  <span>${(r.cost_usd ?? 0).toFixed(4)}</span>
                  <span>{r.latency_s}s</span>
                  <span className={r.valid_json ? "text-pos" : "text-neg"}>
                    {r.valid_json ? "valid JSON" : "bad format"}
                  </span>
                </div>
              </Card>
            ))}
          </div>
        </>
      )}

      {!data && !run.isPending && (
        <Card className="text-center py-12 text-gray-500">
          <FlaskConical className="h-8 w-8 mx-auto mb-2 text-gray-600" />
          <div className="text-gray-300 font-medium">Enter a ticker and hit Compare</div>
          <div className="text-sm mt-1">
            Each model gets the identical data bundle, so you're comparing the model — not the inputs.
          </div>
        </Card>
      )}
    </div>
  );
}

function Points({ label, cls, items }: { label: string; cls: string; items: string[] }) {
  return (
    <div className="mb-1.5">
      <div className={cn("text-[10px] uppercase font-semibold mb-0.5", cls)}>{label}</div>
      <ul className="space-y-0.5">
        {items.slice(0, 4).map((it, i) => (
          <li key={i} className="text-[11px] text-gray-400 leading-snug flex gap-1">
            <span className={cls}>·</span> {it}
          </li>
        ))}
      </ul>
    </div>
  );
}

// Quick agreement read across models
function Verdicts({ results }: { results: { model: string; verdict?: string; ok: boolean }[] }) {
  const ok = results.filter((r) => r.ok && r.verdict);
  if (ok.length < 2) return null;
  const verdicts = ok.map((r) => (r.verdict || "").toUpperCase().split(" ")[0]);
  const unique = Array.from(new Set(verdicts));
  const agree = unique.length === 1;
  return (
    <div
      className={cn(
        "rounded-lg border px-3 py-2 text-sm",
        agree ? "border-pos/30 bg-pos/5 text-pos" : "border-warn/30 bg-warn/5 text-warn"
      )}
    >
      {agree
        ? `✓ All ${ok.length} models agree: ${unique[0]}`
        : `⚠ Models disagree — ${ok.map((r) => `${r.model.split(" ")[0]}: ${(r.verdict || "").split(" ")[0]}`).join(" · ")}`}
    </div>
  );
}
