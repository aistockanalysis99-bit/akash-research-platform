import { useEffect, useRef, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { Check, Loader2, Search, X } from "lucide-react";
import { api } from "@/lib/api";
import { Button, ErrorBox } from "@/components/ui";
import { cn, fmtUsd } from "@/lib/utils";

// ── Popular tickers for autocomplete suggestions ─────────────────────────────
const POPULAR = [
  "AAPL","MSFT","NVDA","GOOGL","AMZN","META","TSLA","AMD","INTC","AVGO",
  "MU","ORCL","NOW","PLTR","CRWV","WMT","CCJ","GLD","CEG","SOXX",
  "KLAR","AIPO","BLSH","BE","SPY","QQQ","MRVL","ASML","NFLX","CRM",
];

const SEED: { symbol: string; shares: number }[] = [
  { symbol:"MU",    shares:100  }, { symbol:"INTC",  shares:700  },
  { symbol:"AMD",   shares:200  }, { symbol:"ORCL",  shares:200  },
  { symbol:"AVGO",  shares:150  }, { symbol:"NOW",   shares:200  },
  { symbol:"SOXX",  shares:100  }, { symbol:"NVDA",  shares:350  },
  { symbol:"AAPL",  shares:100  }, { symbol:"MSFT",  shares:100  },
  { symbol:"PLTR",  shares:100  }, { symbol:"WMT",   shares:3    },
  { symbol:"AIPO",  shares:1000 }, { symbol:"CRWV",  shares:1    },
  { symbol:"CCJ",   shares:100  }, { symbol:"BE",    shares:100  },
  { symbol:"GOOGL", shares:250  }, { symbol:"KLAR",  shares:109  },
  { symbol:"GLD",   shares:100  }, { symbol:"CEG",   shares:100  },
  { symbol:"BLSH",  shares:109  },
];

interface Row {
  key: number; symbol: string; name: string;
  shares: string; entryPrice: string; entryDate: string;
  livePrice: number | null; fetching: boolean;
}

let _k = 0;
function makeRow(symbol = "", shares = ""): Row {
  const today = new Date().toISOString().slice(0, 10);
  return { key: ++_k, symbol, name: "", shares, entryPrice: "", entryDate: today, livePrice: null, fetching: false };
}

export default function AddPositionsModal({ onClose, onDone }: { onClose: () => void; onDone: () => void }) {
  const [rows, setRows]       = useState<Row[]>([makeRow()]);
  const [idx, setIdx]         = useState(0);
  const [result, setResult]   = useState<null | { added: number; total: number; results: any[] }>(null);
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const symbolRef = useRef<HTMLInputElement>(null);

  const row = rows[idx];

  // Auto-fetch price when landing on a row that has a symbol but no price yet
  useEffect(() => {
    if (row?.symbol && !row.livePrice && !row.fetching) fetchPrice(row.key, row.symbol);
    symbolRef.current?.select();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [idx]);

  function upd(key: number, patch: Partial<Row>) {
    setRows(rs => rs.map(r => r.key === key ? { ...r, ...patch } : r));
  }

  async function fetchPrice(key: number, symbol: string) {
    if (!symbol.trim()) return;
    upd(key, { fetching: true });
    try {
      const q = await api.portfolioQuote(symbol.trim().toUpperCase());
      setRows(rs => rs.map(r => r.key === key ? {
        ...r, name: q.name || "",
        livePrice: q.price, fetching: false,
        entryPrice: r.entryPrice || q.price.toFixed(2),
      } : r));
    } catch {
      upd(key, { fetching: false, name: "" });
    }
  }

  function handleSymbolChange(val: string) {
    const v = val.toUpperCase();
    upd(row.key, { symbol: v, livePrice: null, name: "", entryPrice: "" });
    setSuggestions(v.length > 0 ? POPULAR.filter(p => p.startsWith(v) && p !== v).slice(0, 6) : []);
  }

  function pickSuggestion(s: string) {
    setSuggestions([]);
    upd(row.key, { symbol: s, livePrice: null, name: "", entryPrice: "" });
    fetchPrice(row.key, s);
  }

  function handleSymbolBlur() {
    setTimeout(() => setSuggestions([]), 150);
    if (row.symbol && !row.livePrice && !row.fetching) fetchPrice(row.key, row.symbol);
  }

  const valid = rows.filter(r => r.symbol.trim() && Number(r.shares) > 0 && Number(r.entryPrice) > 0);
  const totalCost = valid.reduce((a, r) => a + Number(r.shares) * Number(r.entryPrice), 0);

  const submit = useMutation({
    mutationFn: () => api.portfolioImport(valid.map(r => ({
      symbol: r.symbol.trim().toUpperCase(),
      shares: Number(r.shares),
      entry_price: Number(r.entryPrice),
      entry_date: r.entryDate || undefined,
    }))),
    onSuccess: r => setResult(r),
  });

  const rowValid = row && row.symbol.trim() && Number(row.shares) > 0 && Number(row.entryPrice) > 0;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4" onClick={onClose}>
      <div
        className="bg-bg-card border border-line rounded-2xl w-full max-w-lg shadow-2xl flex flex-col"
        style={{ maxHeight: "90vh" }}
        onClick={e => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-6 pt-5 pb-4">
          <div>
            <h2 className="text-xl font-bold text-white">Add to portfolio</h2>
            <p className="text-xs text-gray-500 mt-0.5">
              Enter one stock at a time
            </p>
          </div>
          <button onClick={onClose} className="text-gray-500 hover:text-white p-1">
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="border-t border-line" />

        {/* Result view */}
        {result ? (
          <div className="p-6 overflow-y-auto">
            <p className="text-sm text-gray-300 mb-3">
              Added <span className="text-pos font-semibold">{result.added}</span> of {result.total} positions.
            </p>
            <div className="space-y-1 mb-5">
              {result.results.map((r: any, i: number) => (
                <div key={i} className="flex items-center gap-3 text-sm">
                  <span className="font-mono w-14">{r.symbol}</span>
                  <span className={r.status === "added" ? "text-pos" : r.status === "skipped" ? "text-warn" : "text-neg"}>
                    {r.status}
                  </span>
                  {r.price && <span className="text-gray-500 ml-auto">@ {fmtUsd(r.price, 2)}</span>}
                </div>
              ))}
            </div>
            <Button onClick={() => { onDone(); onClose(); }} className="w-full justify-center">Done</Button>
          </div>
        ) : row ? (
          <>
            <div className="px-6 py-5 flex-1 overflow-y-auto">

              {/* Ticker field with suggestions */}
              <div className="mb-5 relative">
                <label className="text-xs font-semibold uppercase tracking-wide text-gray-400 mb-2 flex items-center gap-1.5">
                  <Search className="h-3.5 w-3.5" /> Ticker
                </label>
                <input
                  ref={symbolRef}
                  value={row.symbol}
                  onChange={e => handleSymbolChange(e.target.value)}
                  onBlur={handleSymbolBlur}
                  onKeyDown={e => {
                    if (e.key === "Enter" && row.symbol) fetchPrice(row.key, row.symbol);
                    if (e.key === "Tab" && suggestions.length) { e.preventDefault(); pickSuggestion(suggestions[0]); }
                  }}
                  placeholder="e.g. NVDA"
                  className={cn(
                    "w-full bg-bg-soft border rounded-xl px-4 py-3 text-2xl font-bold font-mono uppercase",
                    "focus:border-brand/60 outline-none transition-colors",
                    row.symbol && !row.livePrice && !row.fetching ? "border-line" : "border-line",
                  )}
                />
                {/* Suggestions dropdown */}
                {suggestions.length > 0 && (
                  <div className="absolute top-full mt-1 left-0 right-0 bg-bg-card border border-line rounded-xl overflow-hidden z-10 shadow-xl">
                    {suggestions.map(s => (
                      <button
                        key={s}
                        onMouseDown={() => pickSuggestion(s)}
                        className="w-full text-left px-4 py-2.5 text-sm font-mono font-semibold hover:bg-bg-hover transition-colors flex items-center gap-2"
                      >
                        <span className="text-brand">{row.symbol}</span>
                        <span className="text-gray-200">{s.slice(row.symbol.length)}</span>
                      </button>
                    ))}
                  </div>
                )}
                {/* Company name + price badge */}
                <div className="flex items-center gap-2 mt-2 min-h-[20px]">
                  {row.fetching ? (
                    <span className="text-xs text-gray-500 flex items-center gap-1">
                      <Loader2 className="h-3 w-3 animate-spin" /> Fetching price…
                    </span>
                  ) : row.name ? (
                    <>
                      <span className="text-sm text-gray-300">{row.name}</span>
                      {row.livePrice && (
                        <span className="ml-auto text-sm font-semibold text-brand">
                          {fmtUsd(row.livePrice, 2)}
                          <span className="text-xs text-gray-500 font-normal ml-1">last close</span>
                        </span>
                      )}
                    </>
                  ) : null}
                </div>
              </div>

              {/* Three fields in a row */}
              <div className="grid grid-cols-3 gap-3 mb-5">
                <div>
                  <label className="text-xs font-semibold uppercase tracking-wide text-gray-400 mb-2 block">
                    Shares
                  </label>
                  <input
                    type="number"
                    value={row.shares}
                    onChange={e => upd(row.key, { shares: e.target.value })}
                    placeholder="0"
                    min={0}
                    className="w-full bg-bg-soft border border-line rounded-xl px-3 py-3 text-lg font-bold stat-num text-center focus:border-brand/60 outline-none"
                  />
                </div>
                <div>
                  <label className="text-xs font-semibold uppercase tracking-wide text-gray-400 mb-2 block">
                    Entry price
                    {row.livePrice && (
                      <span className="normal-case font-normal text-gray-500 ml-1">
                        (last: {fmtUsd(row.livePrice, 0)})
                      </span>
                    )}
                  </label>
                  <input
                    type="number"
                    value={row.entryPrice}
                    onChange={e => upd(row.key, { entryPrice: e.target.value })}
                    placeholder={row.livePrice ? fmtUsd(row.livePrice, 2) : "0.00"}
                    step={0.01}
                    min={0}
                    className="w-full bg-bg-soft border border-line rounded-xl px-3 py-3 text-lg font-bold stat-num text-center focus:border-brand/60 outline-none"
                  />
                </div>
                <div>
                  <label className="text-xs font-semibold uppercase tracking-wide text-gray-400 mb-2 block">
                    Entry date
                  </label>
                  <input
                    type="date"
                    value={row.entryDate}
                    onChange={e => upd(row.key, { entryDate: e.target.value })}
                    className="w-full bg-bg-soft border border-line rounded-xl px-3 py-3 text-sm focus:border-brand/60 outline-none"
                  />
                </div>
              </div>

              {/* Summary card — only shown when row is valid */}
              {rowValid && (
                <div className="rounded-xl bg-bg-soft border border-line px-4 py-3 flex items-center justify-between">
                  <div>
                    <div className="text-xs text-gray-500">Cost basis</div>
                    <div className="text-lg font-bold stat-num text-white">
                      {fmtUsd(Number(row.shares) * Number(row.entryPrice))}
                    </div>
                  </div>
                  {row.livePrice && (
                    <div className="text-right">
                      <div className="text-xs text-gray-500">Current value</div>
                      <div className={cn("text-lg font-bold stat-num",
                        Number(row.entryPrice) <= row.livePrice ? "text-pos" : "text-neg")}>
                        {fmtUsd(Number(row.shares) * row.livePrice)}
                      </div>
                    </div>
                  )}
                  {row.livePrice && Number(row.entryPrice) > 0 && (
                    <div className="text-right">
                      <div className="text-xs text-gray-500">Unrealized P&L</div>
                      <div className={cn("text-lg font-bold stat-num",
                        Number(row.entryPrice) <= row.livePrice ? "text-pos" : "text-neg")}>
                        {Number(row.entryPrice) < row.livePrice ? "+" : ""}
                        {fmtUsd((row.livePrice - Number(row.entryPrice)) * Number(row.shares))}
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>

            {/* Footer */}
            <div className="border-t border-line px-6 py-4 flex items-center justify-between gap-3">
              <button onClick={onClose} className="text-sm text-gray-400 hover:text-white">
                Cancel
              </button>
              <button
                onClick={() => submit.mutate()}
                disabled={submit.isPending || valid.length === 0}
                className="flex items-center gap-2 px-6 py-2.5 bg-brand text-bg rounded-xl font-semibold text-sm hover:bg-brand-glow disabled:opacity-50 transition-colors"
              >
                {submit.isPending
                  ? <><Loader2 className="h-4 w-4 animate-spin" />Adding…</>
                  : <><Check className="h-4 w-4" />Add to portfolio</>}
              </button>
            </div>
            {submit.error && <div className="px-6 pb-4"><ErrorBox error={submit.error} /></div>}
          </>
        ) : null}
      </div>
    </div>
  );
}
