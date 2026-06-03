import { useEffect, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { ChevronDown, ChevronRight, Play, Save } from "lucide-react";
import { api } from "@/lib/api";
import { Button, Card, ErrorBox, PageTitle } from "@/components/ui";
import { cn } from "@/lib/utils";

// ─── Default strategy parameters ────────────────────────────────────────────
const DEFAULTS = {
  // Momentum signal
  mom_short_len: 21, mom_med_len: 63, mom_long_len: 126,
  w_short: 0.2, w_med: 0.4, w_long: 0.4,
  // Trend filter
  fast_len: 50, slow_len: 150, slope_bars: 5,
  // Entry / breakout
  entry_threshold: 0.25, exit_threshold: 0.0, breakout_len: 20, skip_bars: 5,
  // Risk & sizing
  risk_pct: 0.005, target_vol: 0.1, max_lev_scalar: 1.5, max_gross_exp: 1.0,
  atr_len: 20, stop_atr: 3.0, trail_atr: 3.0, breakeven_rr: 1.0,
  vol_lookback: 20, annualization_factor: 252,
  // Scale-in
  enable_scale_in: true, max_adds: 2, add_atr: 0.75, add_frac: 0.5,
  // Take-profit
  enable_partial_tp: true, partial_pct: 50, take_profit_rr: 2.0,
  // Position limits
  max_bars_in_trade: 120, max_concurrent_positions: 10,
  max_portfolio_gross: 1.0, portfolio_vol_target: 0.1,
  // Costs
  commission_bps: 2.0, slippage_bps: 1.0, fractional_shares: false,
};
type Params = typeof DEFAULTS;

// ─── Parameter groups ────────────────────────────────────────────────────────
type ParamDef = {
  key: keyof Params;
  label: string;
  tip: string;
  type: "number" | "bool" | "pct";
  min?: number; max?: number; step?: number;
};
type Group = { title: string; params: ParamDef[] };

const GROUPS: Group[] = [
  {
    title: "Momentum signal",
    params: [
      { key: "mom_short_len",  label: "Short window",     tip: "Short lookback in bars (e.g. 21 = 1 month daily)",       type: "number", min: 5,  max: 60,  step: 1 },
      { key: "mom_med_len",    label: "Medium window",    tip: "Medium lookback (e.g. 63 = 1 quarter daily)",             type: "number", min: 20, max: 200, step: 1 },
      { key: "mom_long_len",   label: "Long window",      tip: "Long lookback (e.g. 126 = 6 months daily)",               type: "number", min: 40, max: 400, step: 1 },
      { key: "w_short",        label: "Short weight",     tip: "Blend weight for the short signal (0–1, sum must = 1)",   type: "pct",    min: 0,  max: 1,   step: 0.05 },
      { key: "w_med",          label: "Medium weight",    tip: "Blend weight for the medium signal",                      type: "pct",    min: 0,  max: 1,   step: 0.05 },
      { key: "w_long",         label: "Long weight",      tip: "Blend weight for the long signal",                        type: "pct",    min: 0,  max: 1,   step: 0.05 },
    ],
  },
  {
    title: "Trend filter",
    params: [
      { key: "fast_len",       label: "Fast EMA",         tip: "Fast EMA length (e.g. 50-day)",     type: "number", min: 5,  max: 200, step: 1 },
      { key: "slow_len",       label: "Slow EMA",         tip: "Slow EMA length (e.g. 150-day)",    type: "number", min: 20, max: 500, step: 1 },
      { key: "slope_bars",     label: "Slope bars",       tip: "How many bars back to measure EMA slope",  type: "number", min: 1,  max: 20,  step: 1 },
    ],
  },
  {
    title: "Entry & signal",
    params: [
      { key: "entry_threshold", label: "Entry threshold", tip: "Min composite score to enter a trade (0–1, higher = stricter filter)",  type: "number", min: 0, max: 1, step: 0.01 },
      { key: "exit_threshold",  label: "Exit threshold",  tip: "Score below which an open position is exited",                           type: "number", min: 0, max: 1, step: 0.01 },
      { key: "breakout_len",    label: "Breakout length", tip: "N-bar high breakout confirmation",                                       type: "number", min: 5, max: 60, step: 1 },
      { key: "skip_bars",       label: "Skip bars",       tip: "Bars to skip at startup (warm-up period)",                               type: "number", min: 0, max: 30, step: 1 },
    ],
  },
  {
    title: "Risk & position sizing",
    params: [
      { key: "risk_pct",        label: "Risk per trade %", tip: "Fraction of equity risked per trade (0.005 = 0.5%)",     type: "pct", min: 0.001, max: 0.05, step: 0.001 },
      { key: "target_vol",      label: "Vol target",       tip: "Annualized volatility target for position sizing",         type: "pct", min: 0.01,  max: 0.5,  step: 0.01 },
      { key: "atr_len",         label: "ATR length",       tip: "Period for Average True Range calculation",                type: "number", min: 5, max: 50, step: 1 },
      { key: "stop_atr",        label: "Stop (×ATR)",      tip: "Stop loss distance in ATR multiples (e.g. 3 = 3×ATR)",   type: "number", min: 0.5, max: 10, step: 0.25 },
      { key: "trail_atr",       label: "Trail (×ATR)",     tip: "Trailing stop distance in ATR multiples",                 type: "number", min: 0.5, max: 10, step: 0.25 },
      { key: "breakeven_rr",    label: "Breakeven R:R",    tip: "Move stop to breakeven once R:R exceeds this",            type: "number", min: 0.5, max: 5,  step: 0.25 },
      { key: "max_gross_exp",   label: "Max gross exp.",   tip: "Max gross exposure as fraction of equity (1.0 = 100%)",   type: "pct", min: 0.1, max: 2, step: 0.1 },
      { key: "max_lev_scalar",  label: "Max leverage",     tip: "Cap on leverage scalar applied by vol-targeting",         type: "number", min: 0.5, max: 5, step: 0.25 },
    ],
  },
  {
    title: "Scale-in",
    params: [
      { key: "enable_scale_in", label: "Enable scale-in", tip: "Allow adding to winning positions", type: "bool" },
      { key: "max_adds",        label: "Max adds",         tip: "Maximum number of scale-in additions",       type: "number", min: 1, max: 5, step: 1 },
      { key: "add_atr",         label: "Add gap (×ATR)",   tip: "Price must move this many ATRs before adding", type: "number", min: 0.25, max: 3, step: 0.25 },
      { key: "add_frac",        label: "Add size fraction", tip: "Size of each add as a fraction of original (0.5 = half)", type: "pct", min: 0.1, max: 1, step: 0.1 },
    ],
  },
  {
    title: "Take-profit",
    params: [
      { key: "enable_partial_tp", label: "Partial take-profit", tip: "Take partial profits at a reward:risk target", type: "bool" },
      { key: "partial_pct",       label: "Partial exit %",      tip: "% of position to exit at the TP level (50 = half)", type: "number", min: 10, max: 100, step: 10 },
      { key: "take_profit_rr",    label: "TP reward:risk",      tip: "R:R ratio to trigger partial exit (2 = 2×ATR)",      type: "number", min: 0.5, max: 10,  step: 0.5 },
    ],
  },
  {
    title: "Limits & portfolio",
    params: [
      { key: "max_bars_in_trade",      label: "Max bars held",      tip: "Force-exit a position after this many bars", type: "number", min: 10, max: 500, step: 10 },
      { key: "max_concurrent_positions", label: "Max positions",    tip: "Maximum number of open positions at once",    type: "number", min: 1,  max: 50,  step: 1 },
      { key: "portfolio_vol_target",   label: "Portfolio vol target", tip: "Portfolio-level volatility target",         type: "pct", min: 0.01, max: 0.5, step: 0.01 },
      { key: "max_portfolio_gross",    label: "Portfolio gross cap", tip: "Max gross exposure at portfolio level",      type: "pct", min: 0.1,  max: 2,   step: 0.1 },
    ],
  },
  {
    title: "Costs",
    params: [
      { key: "commission_bps",  label: "Commission (bps)", tip: "Round-trip commission in basis points (2 = 0.02%)",  type: "number", min: 0, max: 50, step: 0.5 },
      { key: "slippage_bps",    label: "Slippage (bps)",   tip: "Estimated slippage per trade in basis points",       type: "number", min: 0, max: 50, step: 0.5 },
      { key: "fractional_shares", label: "Fractional shares", tip: "Allow buying fractional shares (realistic only for crypto/some brokers)", type: "bool" },
    ],
  },
];

// ─── Page ────────────────────────────────────────────────────────────────────
export default function BacktestPage() {
  const nav = useNavigate();
  const universes = useQuery({ queryKey: ["universes"], queryFn: api.universes });
  const presets   = useQuery({ queryKey: ["params"],    queryFn: api.params });

  const today      = new Date().toISOString().slice(0, 10);
  const fiveYrsAgo = new Date(Date.now() - 5 * 365 * 24 * 3600 * 1000).toISOString().slice(0, 10);

  const [name,      setName]      = useState("");
  const [universe,  setUniverse]  = useState("");
  const [timeframe, setTimeframe] = useState("1D");
  const [capital,   setCapital]   = useState(100000);
  const [start,     setStart]     = useState(fiveYrsAgo);
  const [end,       setEnd]       = useState(today);
  const [params,    setParams]    = useState<Params>({ ...DEFAULTS });
  const [showRaw,   setShowRaw]   = useState(false);

  // Load first preset on mount
  useEffect(() => {
    if (presets.data?.length) loadPresetData(presets.data[0].params as Params);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [presets.data]);

  function loadPresetData(p: Partial<Params>) {
    setParams((prev) => ({ ...prev, ...p }));
  }

  function set<K extends keyof Params>(key: K, val: Params[K]) {
    setParams((p) => ({ ...p, [key]: val }));
  }

  const run = useMutation({
    mutationFn: () => {
      if (!start || !end) throw new Error("Start and end dates are required");
      return api.backtestRun({
        run_name:        name || undefined,
        universe:        universe || (universes.data?.[0] ?? "sp100"),
        timeframe,
        initial_capital: capital,
        start_date:      start,
        end_date:        end,
        params,
      });
    },
    onSuccess: (r) => nav(`/runs/${r.run_id}`),
  });

  return (
    <div>
      <PageTitle
        title="New Backtest"
        subtitle="Configure every parameter with labeled controls. Hover any label for a tooltip."
      />

      {/* ── Top config bar ─────────────────────────────────────────── */}
      <Card className="mb-4">
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3 items-end">
          <Field label="Run name" span={2}>
            <input className={inp} value={name} onChange={(e) => setName(e.target.value)} placeholder="My backtest" />
          </Field>
          <Field label="Universe">
            <select className={inp} value={universe} onChange={(e) => setUniverse(e.target.value)}>
              {(universes.data || []).map((u) => <option key={u} value={u}>{u}</option>)}
            </select>
          </Field>
          <Field label="Timeframe">
            <select className={inp} value={timeframe} onChange={(e) => setTimeframe(e.target.value)}>
              {["1D", "4h", "1h", "30m", "15m"].map((t) => <option key={t} value={t}>{t}</option>)}
            </select>
          </Field>
          <Field label="Start">
            <input type="date" className={inp} value={start} onChange={(e) => setStart(e.target.value)} />
          </Field>
          <Field label="End">
            <input type="date" className={inp} value={end} onChange={(e) => setEnd(e.target.value)} />
          </Field>
        </div>
        <div className="flex items-center gap-3 mt-3 pt-3 border-t border-line/50">
          <Field label="Capital ($)">
            <input type="number" className={`${inp} w-36`} value={capital} onChange={(e) => setCapital(Number(e.target.value))} />
          </Field>
          <div className="flex items-center gap-2 ml-2 mt-5">
            <span className="text-xs text-gray-500">Load preset:</span>
            {(presets.data || []).map((p) => (
              <button
                key={p.name}
                onClick={() => loadPresetData(p.params as Params)}
                className="text-xs px-2 py-1 rounded border border-line hover:border-brand/50 text-gray-300 hover:text-brand transition-colors"
              >
                {p.name}
              </button>
            ))}
          </div>
          <div className="flex-1" />
          <Button onClick={() => run.mutate()} disabled={run.isPending} className="h-9">
            <Play className="h-4 w-4" />
            {run.isPending ? "Launching…" : "Run backtest"}
          </Button>
        </div>
        {run.error && <ErrorBox error={run.error} />}
      </Card>

      {/* ── Strategy parameter groups ───────────────────────────────── */}
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-gray-400">
          Strategy parameters
        </h2>
        <button
          onClick={() => setShowRaw((v) => !v)}
          className="text-xs text-gray-500 hover:text-brand"
        >
          {showRaw ? "Show form" : "Show raw JSON"}
        </button>
      </div>

      {showRaw ? (
        <Card>
          <pre className="text-xs font-mono text-gray-300 bg-bg-soft rounded p-3 overflow-auto max-h-[60vh]">
            {JSON.stringify(params, null, 2)}
          </pre>
        </Card>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
          {GROUPS.map((g) => (
            <ParamGroup key={g.title} group={g} params={params} set={set} />
          ))}
        </div>
      )}
    </div>
  );
}

// ─── Collapsible param group card ────────────────────────────────────────────
function ParamGroup({
  group, params, set,
}: {
  group: Group;
  params: Params;
  set: <K extends keyof Params>(k: K, v: Params[K]) => void;
}) {
  const [open, setOpen] = useState(true);
  return (
    <Card className="p-0 overflow-hidden">
      <button
        onClick={() => setOpen((o) => !o)}
        className="w-full flex items-center gap-2 px-4 py-2.5 hover:bg-bg-hover/40 transition-colors border-b border-line/50"
      >
        <span className="text-sm font-semibold text-gray-100 flex-1 text-left">{group.title}</span>
        {open ? <ChevronDown className="h-4 w-4 text-gray-500" /> : <ChevronRight className="h-4 w-4 text-gray-500" />}
      </button>
      {open && (
        <div className="p-3 space-y-2">
          {group.params.map((pd) => (
            <ParamRow key={pd.key} def={pd} value={params[pd.key]} onChange={(v) => set(pd.key, v as any)} />
          ))}
        </div>
      )}
    </Card>
  );
}

// ─── Single parameter row ─────────────────────────────────────────────────────
function ParamRow({
  def, value, onChange,
}: {
  def: ParamDef;
  value: number | boolean;
  onChange: (v: number | boolean) => void;
}) {
  const displayVal = def.type === "pct"
    ? typeof value === "number" ? `${(value * 100).toFixed(1)}%` : value
    : typeof value === "number" ? value : value;

  return (
    <div className="flex items-center gap-2 group">
      <div className="flex-1 min-w-0">
        <div className="flex items-baseline gap-1">
          <span className="text-xs text-gray-300" title={def.tip}>{def.label}</span>
          <span className="text-[10px] text-gray-600 hidden group-hover:inline truncate ml-1" title={def.tip}>— {def.tip}</span>
        </div>
      </div>
      {def.type === "bool" ? (
        <button
          onClick={() => onChange(!value)}
          className={cn(
            "text-xs px-2.5 py-0.5 rounded border transition-colors shrink-0",
            value
              ? "border-brand/50 bg-brand/10 text-brand"
              : "border-line bg-bg-hover text-gray-500"
          )}
        >
          {value ? "ON" : "OFF"}
        </button>
      ) : (
        <div className="flex items-center gap-1 shrink-0">
          <button
            onClick={() => {
              const step = def.step ?? 1;
              const n = Math.max(def.min ?? -Infinity, Number(value) - step);
              onChange(Number(n.toFixed(10)));
            }}
            className="w-6 h-6 flex items-center justify-center rounded border border-line hover:border-brand/50 text-gray-400 hover:text-brand text-sm"
          >−</button>
          <input
            type="number"
            min={def.min}
            max={def.max}
            step={def.step ?? 1}
            value={value as number}
            onChange={(e) => onChange(Number(e.target.value))}
            className="w-20 bg-bg-soft border border-line rounded px-2 py-0.5 text-xs text-right stat-num focus:border-brand/50 outline-none"
          />
          <button
            onClick={() => {
              const step = def.step ?? 1;
              const n = Math.min(def.max ?? Infinity, Number(value) + step);
              onChange(Number(n.toFixed(10)));
            }}
            className="w-6 h-6 flex items-center justify-center rounded border border-line hover:border-brand/50 text-gray-400 hover:text-brand text-sm"
          >+</button>
        </div>
      )}
    </div>
  );
}

// ─── Helpers ──────────────────────────────────────────────────────────────────
const inp = "w-full bg-bg-soft border border-line rounded-lg px-3 py-2 text-sm focus:border-brand/50 outline-none";

function Field({ label, children, span }: { label: string; children: React.ReactNode; span?: number }) {
  return (
    <label className={cn("block", span === 2 && "col-span-2")}>
      <span className="text-xs uppercase text-gray-500 mb-1 block">{label}</span>
      {children}
    </label>
  );
}
