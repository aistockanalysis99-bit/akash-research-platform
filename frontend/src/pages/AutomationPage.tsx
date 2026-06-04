import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Play, Power, RefreshCw, Send, TrendingUp, Zap } from "lucide-react";
import { api } from "@/lib/api";
import { Badge, Button, Card, Loading, PageTitle } from "@/components/ui";
import { cn, fmtUsd, shortDate } from "@/lib/utils";

export default function AutomationPage() {
  const qc = useQueryClient();
  const status = useQuery({
    queryKey: ["scheduler"],
    queryFn: api.schedulerStatus,
    refetchInterval: 10000,
  });
  const log = useQuery({ queryKey: ["tgLog"], queryFn: () => api.telegramLog(40) });

  const invalidate = () => qc.invalidateQueries({ queryKey: ["scheduler"] });
  const startStop = useMutation({
    mutationFn: (on: boolean) => (on ? api.schedulerStart() : api.schedulerStop()),
    onSuccess: invalidate,
  });
  const runMorning  = useMutation({ mutationFn: api.schedulerRunMorning });
  const runEvening  = useMutation({ mutationFn: api.schedulerRunEvening });
  const runWeekly   = useMutation({ mutationFn: api.schedulerRunWeekly });
  const tgTest      = useMutation({
    mutationFn: () => api.telegramTest("Test from Akash dashboard"),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["tgLog"] }),
  });

  const running = !!status.data?.running;
  const jobs    = status.data?.jobs || [];

  return (
    <div>
      <PageTitle
        title="Automation"
        subtitle="Scheduler · quant signals · Telegram delivery log."
      />

      {/* ── Quant Signals panel ───────────────────────────────── */}
      <QuantSignalsPanel />

      {/* ── Scheduler status ─────────────────────────────────── */}
      {status.isLoading && <Loading />}
      {status.data && (
        <Card className="mb-4">
          <div className="flex items-center gap-3 flex-wrap">
            <span className={cn(
              "h-2.5 w-2.5 rounded-full",
              running ? "bg-pos animate-pulse" : "bg-gray-600"
            )} />
            <span className="text-sm font-semibold">
              Scheduler {running ? "running" : "stopped"}
            </span>
            <div className="flex-1" />
            <Button
              variant={running ? "danger" : "primary"}
              onClick={() => startStop.mutate(!running)}
              disabled={startStop.isPending}
            >
              <Power className="h-4 w-4" />
              {running ? "Stop" : "Start"}
            </Button>
          </div>

          {jobs.length > 0 && (
            <div className="mt-4 space-y-1.5">
              {jobs.map((j: any) => (
                <div
                  key={j.id}
                  className="flex items-center justify-between text-sm border-t border-line/50 pt-1.5"
                >
                  <span className="text-gray-300">{j.id}</span>
                  <span className="text-xs text-gray-500 font-mono">
                    {j.trigger?.replace("cron[", "cron(")?.replace("]", ")") || ""}
                    {j.next_run ? ` · next ${j.next_run.slice(0, 16)}` : ""}
                  </span>
                </div>
              ))}
            </div>
          )}
        </Card>
      )}

      {/* ── Manual triggers ──────────────────────────────────── */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-6">
        <TriggerCard label="Run Morning"  m={runMorning} />
        <TriggerCard label="Run Evening"  m={runEvening} />
        <TriggerCard label="Run Weekly"   m={runWeekly} />
        <Card className="flex items-center justify-center">
          <Button variant="outline" onClick={() => tgTest.mutate()} disabled={tgTest.isPending}>
            <Send className="h-4 w-4" /> Test Telegram
          </Button>
        </Card>
      </div>

      {/* ── Telegram log ─────────────────────────────────────── */}
      <h2 className="text-sm font-semibold uppercase tracking-wide text-gray-400 mb-2">
        Telegram Delivery Log
      </h2>
      {log.isLoading && <Loading />}
      {log.data && (
        <Card className="p-0 overflow-hidden divide-y divide-line/50">
          {log.data.map((r, i) => (
            <TelegramRow key={(r as any).id ?? i} row={r} />
          ))}
          {log.data.length === 0 && (
            <div className="py-8 text-center text-gray-500 text-sm">No messages sent yet.</div>
          )}
        </Card>
      )}
    </div>
  );
}

// ── Quant Signals Panel ────────────────────────────────────────────────────
function QuantSignalsPanel() {
  const [scanned, setScanned] = useState(false);
  const scan = useMutation({
    mutationFn: api.schedulerQuantScan,
    onSuccess: () => setScanned(true),
  });
  const signals = scan.data || [];

  return (
    <Card className="mb-4">
      <div className="flex items-center gap-3 mb-3">
        <Zap className="h-5 w-5 text-warn shrink-0" />
        <div className="flex-1">
          <div className="text-sm font-semibold text-white">Today's Quant Signals</div>
          <div className="text-xs text-gray-500 mt-0.5">
            Momentum strategy scan of S&amp;P 100 — these are the stocks the strategy
            wants the AI to research tonight at 16:30 ET.
          </div>
        </div>
        <Button
          variant="outline"
          onClick={() => scan.mutate()}
          disabled={scan.isPending}
          className="shrink-0"
        >
          {scan.isPending ? (
            <><RefreshCw className="h-4 w-4 animate-spin" /> Scanning…</>
          ) : (
            <><TrendingUp className="h-4 w-4" /> {scanned ? "Rescan" : "Scan now"}</>
          )}
        </Button>
      </div>

      {!scanned && !scan.isPending && (
        <div className="text-xs text-gray-500 italic">
          Click "Scan now" to run the momentum scanner and see today's top signals before the evening cycle fires.
        </div>
      )}

      {scan.isPending && (
        <div className="text-xs text-gray-500 animate-pulse">
          Scanning S&amp;P 100 momentum signals… (fetching ~30d of price data per symbol)
        </div>
      )}

      {signals.length > 0 && (
        <>
          <div className="text-xs text-gray-500 mb-2 mt-1">
            {signals.length} stocks cleared threshold · sorted by score · only these go to AI tonight
          </div>
          <div className="space-y-1.5">
            {signals.map((s) => (
              <SignalRow key={s.symbol} s={s} />
            ))}
          </div>
        </>
      )}

      {scanned && signals.length === 0 && !scan.isPending && (
        <div className="text-xs text-warn mt-1">
          No stocks cleared the momentum threshold today — evening cycle will run watchlist only.
        </div>
      )}
    </Card>
  );
}

function SignalRow({ s }: {
  s: {
    symbol: string; score: number; rank: number;
    trend_ok: boolean; breakout_ok: boolean;
    current_price: number; atr: number;
  };
}) {
  const isBreakout = s.breakout_ok;
  const stopDist   = s.current_price > 0 ? (s.atr * 3 / s.current_price * 100) : 0;

  return (
    <div className={cn(
      "flex items-center gap-3 rounded-lg px-3 py-2 text-sm",
      isBreakout ? "bg-pos/8 border border-pos/20" : "bg-bg-hover border border-line/50"
    )}>
      {/* Rank */}
      <span className="text-xs font-mono text-gray-500 w-6">#{s.rank}</span>

      {/* Symbol */}
      <span className="font-bold font-mono w-14">{s.symbol}</span>

      {/* Score bar */}
      <div className="flex-1 max-w-[140px]">
        <div className="flex items-center gap-1.5">
          <div className="h-1.5 flex-1 bg-bg-soft rounded-full overflow-hidden">
            <div
              className={cn("h-full rounded-full", isBreakout ? "bg-pos" : "bg-brand")}
              style={{ width: `${Math.min(100, (s.score / 2) * 100)}%` }}
            />
          </div>
          <span className="text-xs font-mono text-gray-300 w-10 text-right">
            {s.score.toFixed(3)}
          </span>
        </div>
      </div>

      {/* Badges */}
      <div className="flex items-center gap-1.5">
        {isBreakout && (
          <Badge className="border-pos/40 bg-pos/10 text-pos text-[10px] px-1.5 py-0">
            BREAKOUT
          </Badge>
        )}
        <Badge className={cn(
          "text-[10px] px-1.5 py-0",
          s.trend_ok ? "border-brand/40 bg-brand/10 text-brand" : "border-line bg-bg-hover text-gray-500"
        )}>
          TREND {s.trend_ok ? "✓" : "—"}
        </Badge>
      </div>

      {/* Price + stop */}
      <div className="text-right ml-auto">
        <div className="text-xs font-mono text-gray-200">{fmtUsd(s.current_price, 2)}</div>
        <div className="text-[10px] text-gray-500">stop ~{stopDist.toFixed(1)}%</div>
      </div>
    </div>
  );
}

// ── Helper components ──────────────────────────────────────────────────────
function TriggerCard({ label, m }: {
  label: string;
  m: { mutate: () => void; isPending: boolean; isSuccess: boolean };
}) {
  return (
    <Card className="flex items-center justify-center py-3">
      <Button variant="outline" onClick={() => m.mutate()} disabled={m.isPending}>
        <Play className="h-4 w-4" />
        {m.isPending ? "Running…" : m.isSuccess ? "Queued ✓" : label}
      </Button>
    </Card>
  );
}

function TelegramRow({ row }: { row: import("@/lib/types").TelegramLogRow }) {
  const [open, setOpen] = useState(false);
  const hasText = !!row.text;
  return (
    <div>
      <button
        onClick={() => hasText && setOpen((o) => !o)}
        className={cn(
          "w-full flex items-center gap-3 px-3 py-2 text-sm text-left",
          hasText && "hover:bg-bg-hover/50"
        )}
      >
        <span className="font-mono text-xs text-gray-500 w-36 shrink-0">
          {(row.sent_at || "").slice(0, 19).replace("T", " ")}
        </span>
        <span className="font-mono font-semibold w-16 shrink-0">{row.symbol || "—"}</span>
        <span className="text-gray-400 flex-1">{row.kind || "—"}</span>
        {hasText && (
          <span className="text-xs text-gray-600">{open ? "hide" : "view"}</span>
        )}
      </button>
      {open && row.text && (
        <div className="px-3 pb-3 -mt-1">
          <pre className="text-xs whitespace-pre-wrap bg-bg-soft border border-line rounded-lg p-3 text-gray-300">
            {row.text}
          </pre>
        </div>
      )}
    </div>
  );
}
