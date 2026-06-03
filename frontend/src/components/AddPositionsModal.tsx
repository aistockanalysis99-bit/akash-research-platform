import { useEffect, useRef, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { ArrowLeft, ArrowRight, Check, Loader2, X } from "lucide-react";
import { api } from "@/lib/api";
import { Button, ErrorBox, Spinner } from "@/components/ui";
import { cn, fmtUsd } from "@/lib/utils";

interface Row {
  key: number;
  symbol: string;
  name: string;
  shares: string;
  entryPrice: string;    // what the user actually paid
  livePrice: number | null; // yesterday's close — shown as reference
  entryDate: string;
  status: "" | "loading" | "ok" | "bad";
}

const SEED: { symbol: string; shares: number }[] = [
  { symbol: "MU",    shares: 100  }, { symbol: "INTC",  shares: 700  },
  { symbol: "AMD",   shares: 200  }, { symbol: "ORCL",  shares: 200  },
  { symbol: "AVGO",  shares: 150  }, { symbol: "NOW",   shares: 200  },
  { symbol: "SOXX",  shares: 100  }, { symbol: "NVDA",  shares: 350  },
  { symbol: "AAPL",  shares: 100  }, { symbol: "MSFT",  shares: 100  },
  { symbol: "PLTR",  shares: 100  }, { symbol: "WMT",   shares: 3    },
  { symbol: "AIPO",  shares: 1000 }, { symbol: "CRWV",  shares: 1    },
  { symbol: "CCJ",   shares: 100  }, { symbol: "BE",    shares: 100  },
  { symbol: "GOOGL", shares: 250  }, { symbol: "KLAR",  shares: 109  },
  { symbol: "GLD",   shares: 100  }, { symbol: "CEG",   shares: 100  },
  { symbol: "BLSH",  shares: 109  },
];

let _k = 1;
function makeRow(symbol = "", shares = ""): Row {
  return { key: _k++, symbol, name: "", shares, entryPrice: "", livePrice: null, entryDate: "", status: "" };
}

export default function AddPositionsModal({
  onClose,
  onDone,
}: {
  onClose: () => void;
  onDone: () => void;
}) {
  const [rows, setRows]     = useState<Row[]>(SEED.map((s) => makeRow(s.symbol, String(s.shares))));
  const [current, setCurrent] = useState(0);   // which row is active
  const [done, setDone]      = useState<Set<number>>(new Set());
  const [result, setResult]  = useState<null | { added: number; total: number; results: any[] }>(null);
  const priceRef = useRef<HTMLInputElement>(null);

  const row = rows[current];

  // Fetch live price whenever we land on a row with a symbol
  useEffect(() => {
    if (!row?.symbol || row.status === "ok" || row.status === "loading") return;
    fetchQuote(row.key, row.symbol);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [current]);

  function update(key: number, patch: Partial<Row>) {
    setRows((rs) => rs.map((r) => (r.key === key ? { ...r, ...patch } : r)));
  }

  async function fetchQuote(key: number, symbol: string) {
    const sym = symbol.trim().toUpperCase();
    if (!sym) return;
    update(key, { symbol: sym, status: "loading" });
    try {
      const q = await api.portfolioQuote(sym);
      setRows((rs) =>
        rs.map((r) =>
          r.key === key
            ? {
                ...r,
                name: q.name || "",
                livePrice: q.price,
                status: "ok",
                // Pre-fill entry price with live price ONLY if still blank
                entryPrice: r.entryPrice || q.price.toFixed(2),
              }
            : r
        )
      );
      // Move focus to entry price so user can immediately override
      setTimeout(() => priceRef.current?.focus(), 50);
    } catch {
      update(key, { status: "bad", name: "Not found", livePrice: null });
    }
  }

  function markDone(idx: number) {
    setDone((d) => { const s = new Set(d); s.add(idx); return s; });
  }

  function goNext() {
    markDone(current);
    if (current < rows.length - 1) setCurrent(current + 1);
  }
  function goPrev() {
    if (current > 0) setCurrent(current - 1);
  }
  function goTo(idx: number) {
    markDone(current);
    setCurrent(idx);
  }

  const validRows = rows.filter(
    (r) => r.symbol.trim() && Number(r.shares) > 0 && Number(r.entryPrice) > 0
  );
  const totalCost = validRows.reduce((a, r) => a + Number(r.shares) * Number(r.entryPrice), 0);

  const submit = useMutation({
    mutationFn: () =>
      api.portfolioImport(
        validRows.map((r) => ({
          symbol: r.symbol.trim().toUpperCase(),
          shares: Number(r.shares),
          entry_price: Number(r.entryPrice),
          entry_date: r.entryDate || undefined,
        }))
      ),
    onSuccess: (r) => setResult(r),
  });

  // Is the current row valid?
  const rowValid = row && row.symbol.trim() && Number(row.shares) > 0 && Number(row.entryPrice) > 0;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4" onClick={onClose}>
      <div className="card w-full max-w-2xl flex flex-col" style={{ maxHeight: "92vh" }}
           onClick={(e) => e.stopPropagation()}>

        {/* Header */}
        <div className="flex items-center justify-between px-5 py-3 border-b border-line">
          <div>
            <h3 className="text-lg font-bold text-white">Add positions</h3>
            <p className="text-xs text-gray-500 mt-0.5">
              {validRows.length} of {rows.length} filled · cost basis {fmtUsd(totalCost)}
            </p>
          </div>
          <button onClick={onClose} className="text-gray-500 hover:text-white">
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Results view */}
        {result ? (
          <div className="p-5 overflow-y-auto">
            <div className="text-sm text-gray-300 mb-3">
              Added <span className="text-pos font-semibold">{result.added}</span> of {result.total} positions.
            </div>
            <div className="border border-line rounded-lg overflow-hidden mb-4">
              {result.results.map((r: any, i: number) => (
                <div key={i} className="flex items-center gap-3 px-3 py-2 border-b border-line/40 last:border-0">
                  <span className="font-mono font-semibold w-16">{r.symbol}</span>
                  <span className={cn("text-xs",
                    r.status === "added" ? "text-pos" : r.status === "skipped" ? "text-warn" : "text-neg")}>
                    {r.status}
                  </span>
                  {r.price && <span className="text-xs text-gray-400 ml-auto">@ {fmtUsd(r.price, 2)}</span>}
                </div>
              ))}
            </div>
            <div className="flex justify-end">
              <Button onClick={() => { onDone(); onClose(); }}>Done</Button>
            </div>
          </div>
        ) : (
          <>
            {/* Progress dots */}
            <div className="px-5 pt-3 pb-2 flex flex-wrap gap-1.5">
              {rows.map((r, i) => {
                const isDone = done.has(i);
                const isValid = r.symbol.trim() && Number(r.shares) > 0 && Number(r.entryPrice) > 0;
                return (
                  <button
                    key={r.key}
                    onClick={() => goTo(i)}
                    title={r.symbol}
                    className={cn(
                      "w-7 h-7 rounded text-[11px] font-mono font-semibold transition-colors border",
                      i === current
                        ? "bg-brand text-bg border-brand"
                        : isValid
                        ? "bg-pos/20 text-pos border-pos/40"
                        : isDone
                        ? "bg-warn/20 text-warn border-warn/40"
                        : "bg-bg-hover text-gray-400 border-line"
                    )}
                  >
                    {r.symbol.slice(0, 2) || i + 1}
                  </button>
                );
              })}
            </div>

            {/* Current row entry */}
            {row && (
              <div className="flex-1 px-5 py-4">
                {/* Stock header */}
                <div className="flex items-center gap-3 mb-5">
                  <div className={cn(
                    "w-12 h-12 rounded-xl flex items-center justify-center text-lg font-bold font-mono",
                    row.status === "ok" ? "bg-brand/15 text-brand" :
                    row.status === "bad" ? "bg-neg/15 text-neg" :
                    "bg-bg-hover text-gray-400"
                  )}>
                    {row.symbol.slice(0, 2) || "?"}
                  </div>
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="text-xl font-bold font-mono">{row.symbol || "—"}</span>
                      {row.status === "loading" && <Spinner className="h-4 w-4" />}
                      {row.status === "ok" && row.livePrice && (
                        <span className="text-sm text-pos font-semibold">
                          {fmtUsd(row.livePrice, 2)}
                          <span className="text-xs text-gray-500 ml-1 font-normal">last close</span>
                        </span>
                      )}
                    </div>
                    <div className="text-sm text-gray-400">{row.name || (row.status === "bad" ? "Ticker not found" : "Auto-fills on lookup…")}</div>
                  </div>
                  <div className="ml-auto text-sm text-gray-500">
                    {current + 1} / {rows.length}
                  </div>
                </div>

                {/* Ticker (editable) */}
                <div className="grid grid-cols-2 gap-4 mb-4">
                  <Field label="Ticker">
                    <input
                      className={cn(inp, "font-mono uppercase text-lg font-bold",
                        row.status === "bad" && "border-neg/60")}
                      value={row.symbol}
                      onChange={(e) => update(row.key, { symbol: e.target.value.toUpperCase(), status: "", name: "", livePrice: null })}
                      onBlur={(e) => { if (e.target.value.trim()) fetchQuote(row.key, e.target.value); }}
                      onKeyDown={(e) => e.key === "Enter" && fetchQuote(row.key, row.symbol)}
                      placeholder="e.g. NVDA"
                    />
                  </Field>
                  <Field label="Shares">
                    <input
                      type="number"
                      className={cn(inp, "stat-num text-lg")}
                      value={row.shares}
                      onChange={(e) => update(row.key, { shares: e.target.value })}
                      placeholder="0"
                      min={0}
                    />
                  </Field>
                </div>

                {/* Entry price — pre-filled with live, user overrides */}
                <div className="grid grid-cols-2 gap-4 mb-2">
                  <Field
                    label={
                      row.livePrice
                        ? `Entry price (last close: ${fmtUsd(row.livePrice, 2)})`
                        : "Entry price (your cost)"
                    }
                  >
                    <input
                      ref={priceRef}
                      type="number"
                      className={cn(inp, "stat-num text-lg font-semibold")}
                      value={row.entryPrice}
                      onChange={(e) => update(row.key, { entryPrice: e.target.value })}
                      placeholder={row.livePrice ? fmtUsd(row.livePrice, 2) : "0.00"}
                      step={0.01}
                      min={0}
                    />
                    {row.livePrice && row.entryPrice && Number(row.entryPrice) !== row.livePrice && (
                      <div className="text-xs mt-1">
                        <span className={Number(row.entryPrice) < row.livePrice ? "text-pos" : "text-neg"}>
                          {Number(row.entryPrice) < row.livePrice
                            ? `You paid ${fmtUsd(row.livePrice - Number(row.entryPrice), 2)} less than current price (unrealized gain per share)`
                            : `You paid ${fmtUsd(Number(row.entryPrice) - row.livePrice, 2)} more than current price (unrealized loss per share)`}
                        </span>
                      </div>
                    )}
                  </Field>
                  <Field label="Entry date (optional)">
                    <input
                      type="date"
                      className={inp}
                      value={row.entryDate}
                      onChange={(e) => update(row.key, { entryDate: e.target.value })}
                    />
                  </Field>
                </div>

                {/* Cost summary */}
                {rowValid && (
                  <div className="rounded-lg bg-bg-soft border border-line p-3 text-sm flex items-center gap-4 mt-3">
                    <span className="text-gray-400">Cost basis this position:</span>
                    <span className="font-bold text-white stat-num">
                      {fmtUsd(Number(row.shares) * Number(row.entryPrice))}
                    </span>
                    {row.livePrice && (
                      <>
                        <span className="text-gray-600">·</span>
                        <span className="text-gray-400">Current value:</span>
                        <span className={cn("font-bold stat-num",
                          Number(row.entryPrice) > row.livePrice ? "text-neg" : "text-pos")}>
                          {fmtUsd(Number(row.shares) * row.livePrice)}
                        </span>
                      </>
                    )}
                  </div>
                )}
              </div>
            )}

            {/* Navigation footer */}
            <div className="flex items-center gap-3 px-5 py-3 border-t border-line">
              <Button variant="ghost" onClick={goPrev} disabled={current === 0}>
                <ArrowLeft className="h-4 w-4" /> Back
              </Button>
              <div className="flex-1 text-xs text-gray-500 text-center">
                {validRows.length} valid · {fmtUsd(totalCost)} total cost
              </div>
              {current < rows.length - 1 ? (
                <Button onClick={goNext}>
                  Next <ArrowRight className="h-4 w-4" />
                </Button>
              ) : (
                <Button
                  onClick={() => submit.mutate()}
                  disabled={submit.isPending || validRows.length === 0}
                >
                  {submit.isPending
                    ? <><Loader2 className="h-4 w-4 animate-spin" /> Adding…</>
                    : <><Check className="h-4 w-4" /> Add {validRows.length} positions</>}
                </Button>
              )}
            </div>
            {submit.error && (
              <div className="px-5 pb-3"><ErrorBox error={submit.error} /></div>
            )}
          </>
        )}
      </div>
    </div>
  );
}

const inp = "w-full bg-bg-soft border border-line rounded-lg px-3 py-2.5 text-sm focus:border-brand/50 outline-none";

function Field({ label, children }: { label: string | React.ReactNode; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="text-xs uppercase text-gray-500 mb-1.5 block">{label}</span>
      {children}
    </label>
  );
}
