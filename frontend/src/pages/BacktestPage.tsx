import { useEffect, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { Play } from "lucide-react";
import { api } from "@/lib/api";
import { Button, Card, ErrorBox, PageTitle } from "@/components/ui";

export default function BacktestPage() {
  const nav = useNavigate();
  const universes = useQuery({ queryKey: ["universes"], queryFn: api.universes });
  const presets = useQuery({ queryKey: ["params"], queryFn: api.params });

  // Defaults: required by the API. Daily bars, ~5y window ending today.
  const today = new Date().toISOString().slice(0, 10);
  const fiveYrsAgo = new Date(Date.now() - 5 * 365 * 24 * 3600 * 1000)
    .toISOString()
    .slice(0, 10);

  const [name, setName] = useState("");
  const [universe, setUniverse] = useState("");
  const [timeframe, setTimeframe] = useState("1D");
  const [capital, setCapital] = useState(100000);
  const [start, setStart] = useState(fiveYrsAgo);
  const [end, setEnd] = useState(today);
  const [paramsText, setParamsText] = useState("{}");

  // Pre-fill the params editor with the first saved preset so it's never blank.
  useEffect(() => {
    if (presets.data && presets.data.length && paramsText === "{}") {
      setParamsText(JSON.stringify(presets.data[0].params, null, 2));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [presets.data]);

  const run = useMutation({
    mutationFn: () => {
      if (!start || !end) throw new Error("Start and end dates are required");
      let params: unknown = {};
      try {
        params = JSON.parse(paramsText || "{}");
      } catch {
        throw new Error("Parameters must be valid JSON");
      }
      return api.backtestRun({
        run_name: name || undefined,
        universe: universe || (universes.data?.[0] ?? "sp100"),
        timeframe,
        initial_capital: capital,
        start_date: start,
        end_date: end,
        params,
      });
    },
    onSuccess: (r) => nav(`/runs/${r.run_id}`),
  });

  function loadPreset(n: string) {
    if (!n) return;
    api.paramGet(n).then((p) => setParamsText(JSON.stringify(p.params, null, 2)));
  }

  return (
    <div>
      <PageTitle title="New Backtest" subtitle="Launch a strategy backtest. Load a saved preset or hand-edit the parameters." />
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <Card className="space-y-3">
          <Field label="Run name">
            <input className={inp} value={name} onChange={(e) => setName(e.target.value)} placeholder="My backtest" />
          </Field>
          <Field label="Universe">
            <select className={inp} value={universe} onChange={(e) => setUniverse(e.target.value)}>
              {(universes.data || []).map((u) => (
                <option key={u} value={u}>{u}</option>
              ))}
            </select>
          </Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Timeframe">
              <select className={inp} value={timeframe} onChange={(e) => setTimeframe(e.target.value)}>
                {["1D", "4h", "1h", "30m", "15m"].map((t) => (
                  <option key={t} value={t}>{t}</option>
                ))}
              </select>
            </Field>
            <Field label="Initial capital">
              <input
                type="number"
                className={inp}
                value={capital}
                onChange={(e) => setCapital(Number(e.target.value))}
              />
            </Field>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Start date">
              <input type="date" className={inp} value={start} onChange={(e) => setStart(e.target.value)} />
            </Field>
            <Field label="End date">
              <input type="date" className={inp} value={end} onChange={(e) => setEnd(e.target.value)} />
            </Field>
          </div>
          <Button onClick={() => run.mutate()} disabled={run.isPending} className="w-full justify-center">
            <Play className="h-4 w-4" /> {run.isPending ? "Launching…" : "Run backtest"}
          </Button>
          {run.error && <ErrorBox error={run.error} />}
        </Card>

        <Card className="space-y-3">
          <Field label="Load preset">
            <select className={inp} onChange={(e) => loadPreset(e.target.value)} defaultValue="">
              <option value="">— pick a saved preset —</option>
              {(presets.data || []).map((p) => (
                <option key={p.name} value={p.name}>{p.name}</option>
              ))}
            </select>
          </Field>
          <Field label="Strategy parameters (JSON)">
            <textarea
              className={`${inp} font-mono text-xs h-[340px] resize-none`}
              value={paramsText}
              onChange={(e) => setParamsText(e.target.value)}
              spellCheck={false}
            />
          </Field>
        </Card>
      </div>
    </div>
  );
}

const inp =
  "w-full bg-bg-soft border border-line rounded-lg px-3 py-2 text-sm focus:border-brand/50 outline-none";

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="text-xs uppercase text-gray-500 mb-1 block">{label}</span>
      {children}
    </label>
  );
}
