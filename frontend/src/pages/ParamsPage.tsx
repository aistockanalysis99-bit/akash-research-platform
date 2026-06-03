import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { Card, EmptyState, Loading, PageTitle } from "@/components/ui";
import { cn } from "@/lib/utils";

export default function ParamsPage() {
  const { data, isLoading } = useQuery({ queryKey: ["params"], queryFn: api.params });
  const [sel, setSel] = useState<string | null>(null);

  const chosen = (data || []).find((p) => p.name === sel) || (data || [])[0];

  return (
    <div>
      <PageTitle title="Parameters" subtitle="Saved strategy parameter presets." />
      {isLoading && <Loading />}
      {data && data.length === 0 && (
        <Card>
          <EmptyState title="No saved presets" hint="Save a parameter set from the Backtest tab." />
        </Card>
      )}
      {data && data.length > 0 && (
        <div className="grid grid-cols-[220px_1fr] gap-5">
          <div className="space-y-1">
            {data.map((p) => (
              <button
                key={p.name}
                onClick={() => setSel(p.name)}
                className={cn(
                  "w-full text-left px-3 py-2 rounded-lg text-sm transition-colors",
                  (sel ?? data[0].name) === p.name
                    ? "bg-brand/15 text-brand"
                    : "text-gray-400 hover:bg-bg-hover"
                )}
              >
                {p.name}
              </button>
            ))}
          </div>
          <Card>
            {chosen && (
              <>
                <h3 className="text-sm font-semibold text-brand-glow mb-3">{chosen.name}</h3>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-1.5 text-sm">
                  {Object.entries(chosen.params).map(([k, v]) => (
                    <div key={k} className="flex justify-between border-b border-line/40 py-1">
                      <span className="text-gray-400">{k}</span>
                      <span className="stat-num text-gray-200">{String(v)}</span>
                    </div>
                  ))}
                </div>
              </>
            )}
          </Card>
        </div>
      )}
    </div>
  );
}
