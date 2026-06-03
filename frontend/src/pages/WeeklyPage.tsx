import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { Card, EmptyState, Loading, PageTitle } from "@/components/ui";
import Markdown from "@/components/Markdown";
import { cn } from "@/lib/utils";

export default function WeeklyPage() {
  const dates = useQuery({ queryKey: ["weeklyList"], queryFn: api.weeklyList });
  const [sel, setSel] = useState<string | null>(null);

  useEffect(() => {
    if (!sel && dates.data && dates.data.length) setSel(dates.data[0]);
  }, [dates.data, sel]);

  const files = useQuery({
    queryKey: ["weeklyGet", sel],
    queryFn: () => api.weeklyGet(sel!),
    enabled: !!sel,
  });

  return (
    <div>
      <PageTitle
        title="Weekly Review"
        subtitle="The Friday portfolio review: performance, lessons, positioning for the week ahead."
      />
      {dates.isLoading && <Loading />}
      {dates.data && dates.data.length === 0 && (
        <Card>
          <EmptyState title="No weekly reviews yet" hint="The scheduler runs this Fridays at 17:00 ET." />
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
              Object.entries(files.data).map(([k, v]) => (
                <Card key={k}>
                  <Markdown>{v}</Markdown>
                </Card>
              ))}
          </div>
        </div>
      )}
    </div>
  );
}
