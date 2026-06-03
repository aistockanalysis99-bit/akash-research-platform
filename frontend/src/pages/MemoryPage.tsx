import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Brain, RefreshCw } from "lucide-react";
import { api } from "@/lib/api";
import { Button, Card, EmptyState, ErrorBox, Loading, PageTitle } from "@/components/ui";
import { shortDate } from "@/lib/utils";

export default function MemoryPage() {
  const qc = useQueryClient();
  const lessons = useQuery({ queryKey: ["lessons"], queryFn: () => api.lessons(200) });
  const reflect = useMutation({
    mutationFn: api.memoryReflect,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["lessons"] }),
  });

  return (
    <div>
      <PageTitle
        title="Memory"
        subtitle="Lessons the system has distilled from closed trades — fed back into future analysis prompts."
        actions={
          <Button variant="outline" onClick={() => reflect.mutate()} disabled={reflect.isPending}>
            <RefreshCw className={reflect.isPending ? "h-4 w-4 animate-spin" : "h-4 w-4"} />
            Reflect now
          </Button>
        }
      />
      {lessons.isLoading && <Loading />}
      {lessons.error && <ErrorBox error={lessons.error} />}
      {lessons.data && lessons.data.length === 0 && (
        <Card>
          <EmptyState
            icon={<Brain className="h-8 w-8" />}
            title="No lessons yet"
            hint="Lessons accumulate as paper positions close and the system reflects on outcomes."
          />
        </Card>
      )}
      {lessons.data && lessons.data.length > 0 && (
        <div className="space-y-2">
          {lessons.data.map((l, i) => (
            <Card key={l.id ?? i} className="py-3">
              <div className="flex items-center gap-2 mb-1">
                {l.symbol && (
                  <span className="font-mono font-bold text-sm text-brand">{l.symbol}</span>
                )}
                {l.category && (
                  <span className="text-xs text-gray-500 uppercase">{l.category}</span>
                )}
                <div className="flex-1" />
                <span className="text-xs text-gray-600 font-mono">
                  {shortDate(l.created_at)}
                </span>
              </div>
              <p className="text-sm text-gray-300">{l.lesson || JSON.stringify(l)}</p>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
