import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Play, Power, Send } from "lucide-react";
import { api } from "@/lib/api";
import { Badge, Button, Card, Loading, PageTitle } from "@/components/ui";
import { cn, shortDate } from "@/lib/utils";

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
  const runMorning = useMutation({ mutationFn: api.schedulerRunMorning });
  const runEvening = useMutation({ mutationFn: api.schedulerRunEvening });
  const runWeekly = useMutation({ mutationFn: api.schedulerRunWeekly });
  const tgTest = useMutation({
    mutationFn: () => api.telegramTest("Test from Akash dashboard"),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["tgLog"] }),
  });

  const running = !!status.data?.running;
  const jobs = status.data?.jobs || [];

  return (
    <div>
      <PageTitle
        title="Automation"
        subtitle="Scheduler for the morning / evening / weekly cycles, plus Telegram delivery log."
      />

      {status.isLoading && <Loading />}
      {status.data && (
        <Card className="mb-4">
          <div className="flex items-center gap-3 flex-wrap">
            <span
              className={cn(
                "h-2.5 w-2.5 rounded-full",
                running ? "bg-pos animate-pulse" : "bg-gray-600"
              )}
            />
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
              {jobs.map((j) => (
                <div
                  key={j.id}
                  className="flex items-center justify-between text-sm border-t border-line/50 pt-1.5"
                >
                  <span className="text-gray-300">{j.id}</span>
                  <span className="text-xs text-gray-500 font-mono">
                    {j.trigger || ""} · next {shortDate(j.next_run) || "—"}
                  </span>
                </div>
              ))}
            </div>
          )}
        </Card>
      )}

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 mb-6">
        <RunCard label="Run Morning" m={runMorning} />
        <RunCard label="Run Evening" m={runEvening} />
        <RunCard label="Run Weekly" m={runWeekly} />
        <Card className="flex items-center justify-center">
          <Button variant="outline" onClick={() => tgTest.mutate()} disabled={tgTest.isPending}>
            <Send className="h-4 w-4" /> Test Telegram
          </Button>
        </Card>
      </div>

      <h2 className="text-sm font-semibold uppercase tracking-wide text-gray-400 mb-2">
        Telegram Delivery Log
      </h2>
      {log.isLoading && <Loading />}
      {log.data && (
        <Card className="p-0 overflow-hidden divide-y divide-line/50">
          {log.data.map((r, i) => (
            <TelegramRow key={r.id ?? i} row={r} />
          ))}
          {log.data.length === 0 && (
            <div className="py-8 text-center text-gray-500 text-sm">No messages sent yet.</div>
          )}
        </Card>
      )}
    </div>
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
        {hasText && <span className="text-xs text-gray-600">{open ? "hide" : "view"}</span>}
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

function RunCard({ label, m }: { label: string; m: { mutate: () => void; isPending: boolean; isSuccess: boolean } }) {
  return (
    <Card className="flex items-center justify-center">
      <Button variant="outline" onClick={() => m.mutate()} disabled={m.isPending}>
        <Play className="h-4 w-4" />
        {m.isPending ? "Running…" : m.isSuccess ? "Queued ✓" : label}
      </Button>
    </Card>
  );
}
