import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Play } from "lucide-react";
import { api } from "@/lib/api";
import { Button, Card, EmptyState, Loading, PageTitle } from "@/components/ui";
import Markdown from "@/components/Markdown";
import { cn } from "@/lib/utils";

const ORDER = [
  "regime",
  "position_monitor",
  "exit_confirmer",
  "morning_briefing",
];
const LABELS: Record<string, string> = {
  regime: "🧭 Market Regime",
  position_monitor: "📋 Position Monitor",
  exit_confirmer: "🚪 Exit Confirmer",
  morning_briefing: "🌅 Morning Briefing",
};

export default function MorningPage() {
  const qc = useQueryClient();
  const dates = useQuery({ queryKey: ["morningDates"], queryFn: api.morningDates });
  const [sel, setSel] = useState<string | null>(null);

  useEffect(() => {
    if (!sel && dates.data && dates.data.length) setSel(dates.data[0]);
  }, [dates.data, sel]);

  const files = useQuery({
    queryKey: ["morningFiles", sel],
    queryFn: () => api.morningFiles(sel!),
    enabled: !!sel,
  });

  const run = useMutation({
    mutationFn: api.morningRun,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["morningDates"] }),
  });

  return (
    <div>
      <PageTitle
        title="Morning Cycle"
        subtitle="Daily pre-market briefing: market regime, position monitor, exit checks."
        actions={
          <Button variant="outline" onClick={() => run.mutate()} disabled={run.isPending}>
            <Play className="h-4 w-4" /> Run now
          </Button>
        }
      />
      {dates.isLoading && <Loading />}
      {dates.data && dates.data.length === 0 && (
        <Card>
          <EmptyState title="No morning briefings yet" hint="Run one with the button above, or let the scheduler fire it at 08:00 ET." />
        </Card>
      )}
      {dates.data && dates.data.length > 0 && (
        <div className="grid grid-cols-[180px_1fr] gap-5">
          <div className="space-y-1">
            {dates.data.map((d) => (
              <button
                key={d}
                onClick={() => setSel(d)}
                className={cn(
                  "w-full text-left px-3 py-2 rounded-lg text-sm font-mono transition-colors",
                  d === sel ? "bg-brand/15 text-brand" : "text-gray-400 hover:bg-bg-hover"
                )}
              >
                {d}
              </button>
            ))}
          </div>
          <div className="space-y-3">
            {files.isLoading && <Loading />}
            {files.data &&
              ORDER.filter((k) => files.data![k]).map((k) => (
                <Card key={k}>
                  <h3 className="text-sm font-semibold text-brand-glow mb-2">
                    {LABELS[k] || k}
                  </h3>
                  <Markdown>{files.data![k]}</Markdown>
                </Card>
              ))}
            {files.data && Object.keys(files.data).length === 0 && (
              <Card>
                <EmptyState title="No files for this date" />
              </Card>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
