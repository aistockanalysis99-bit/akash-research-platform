import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { Plus, Trash2, X } from "lucide-react";
import { api } from "@/lib/api";
import { Button, ErrorBox } from "@/components/ui";
import { cn, fmtUsd } from "@/lib/utils";

interface Row {
  key: number;
  symbol: string;
  name: string;
  shares: string;
  entryPrice: string;
  entryDate: string;
  live: number | null;
  status: "" | "loading" | "ok" | "bad";
}

// Pre-seed with the user's actual stock holdings (share counts known;
// entry price + date to be filled in). Edit/remove freely.
const SEED: { symbol: string; shares: number }[] = [
  { symbol: "MU", shares: 100 }, { symbol: "INTC", shares: 700 },
  { symbol: "AMD", shares: 200 }, { symbol: "ORCL", shares: 200 },
  { symbol: "AVGO", shares: 150 }, { symbol: "NOW", shares: 200 },
  { symbol: "SOXX", shares: 100 }, { symbol: "NVDA", shares: 350 },
  { symbol: "AAPL", shares: 100 }, { symbol: "MSFT", shares: 100 },
  { symbol: "PLTR", shares: 100 }, { symbol: "WMT", shares: 3 },
  { symbol: "AIPO", shares: 1000 }, { symbol: "CRWV", shares: 1 },
  { symbol: "CCJ", shares: 100 }, { symbol: "BE", shares: 100 },
  { symbol: "GOOGL", shares: 250 }, { symbol: "KLAR", shares: 109 },
  { symbol: "GLD", shares: 100 }, { symbol: "CEG", shares: 100 },
  { symbol: "BLSH", shares: 109 },
];

let _k = 1;
function blankRow(symbol = "", shares = ""): Row {
  return { key: _k++, symbol, name: "", shares, entryPrice: "", entryDate: "", live: null, status: "" };
}

export default function AddPositionsModal({
  onClose,
  onDone,
  seed = true,
}: {
  onClose: () => void;
  onDone: () => void;
  seed?: boolean;
}) {
  const [rows, setRows] = useState<Row[]>(
    seed ? SEED.map((s) => blankRow(s.symbol, String(s.shares))) : [blankRow(), blankRow(), blankRow()]
  );

  const update = (key: number, patch: Partial<Row>) =>
    setRows((rs) => rs.map((r) => (r.key === key ? { ...r, ...patch } : r)));

  async function lookup(key: number, symbol: string) {
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
                live: q.price,
                status: "ok",
                // prefill entry price with live price only if user left it blank
                entryPrice: r.entryPrice || q.price.toFixed(2),
              }
            : r
        )
      );
    } catch {
      update(key, { status: "bad", name: "", live: null });
    }
  }

  const valid = rows.filter(
    (r) => r.symbol.trim() && Number(r.shares) > 0 && Number(r.entryPrice) > 0
  );
  const totalCost = valid.reduce((a, r) => a + Number(r.shares) * Number(r.entryPrice), 0);

  const submit = useMutation({
    mutationFn: () =>
      api.portfolioImport(
        valid.map((r) => ({
          symbol: r.symbol.trim().toUpperCase(),
          shares: Number(r.shares),
          entry_price: Number(r.entryPrice),
          entry_date: r.entryDate || undefined,
        }))
      ),
    onSuccess: () => onDone(),
  });
  const result = submit.data;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4" onClick={onClose}>
      <div
        className="card p-0 w-full max-w-5xl max-h-[92vh] flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-3 border-b border-line">
          <div>
            <h3 className="text-lg font-bold text-white">Add positions</h3>
            <p className="text-xs text-gray-500">
              Enter each holding. Type a ticker to auto-fetch its live price — then set the
              price you actually paid and your entry date.
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
              Imported <span className="text-pos font-semibold">{result.added}</span> of {result.total}.
            </div>
            <div className="border border-line rounded-lg overflow-hidden">
              <table className="w-full text-sm">
                <tbody>
                  {result.results.map((r, i) => (
                    <tr key={i} className="border-b border-line/40">
                      <td className="px-3 py-1.5 font-mono font-semibold">{r.symbol}</td>
                      <td className="px-3 py-1.5">
                        <span className={cn("text-xs",
                          r.status === "added" ? "text-pos" : r.status === "skipped" ? "text-warn" : "text-neg")}>
                          {r.status}
                        </span>
                        {r.detail && <span className="text-xs text-gray-500 ml-2">{r.detail}</span>}
                      </td>
                      <td className="px-3 py-1.5 text-right text-xs text-gray-400">
                        {r.price ? `@ ${fmtUsd(r.price, 2)}` : ""}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="flex justify-end mt-4">
              <Button onClick={onClose}>Done</Button>
            </div>
          </div>
        ) : (
          <>
            {/* Grid */}
            <div className="overflow-auto flex-1 px-2">
              <table className="w-full text-sm">
                <thead className="sticky top-0 bg-bg-card z-10">
                  <tr className="text-xs uppercase text-gray-500 border-b border-line">
                    <th className="text-left px-2 py-2 w-32">Ticker</th>
                    <th className="text-left px-2 py-2">Company</th>
                    <th className="text-right px-2 py-2 w-24">Shares</th>
                    <th className="text-right px-2 py-2 w-28">Entry $</th>
                    <th className="text-left px-2 py-2 w-40">Entry date</th>
                    <th className="text-right px-2 py-2 w-24">Last</th>
                    <th className="text-right px-2 py-2 w-28">Cost</th>
                    <th className="w-8"></th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r) => {
                    const cost = Number(r.shares) * Number(r.entryPrice);
                    return (
                      <tr key={r.key} className="border-b border-line/40">
                        <td className="px-2 py-1.5">
                          <input
                            value={r.symbol}
                            onChange={(e) => update(r.key, { symbol: e.target.value.toUpperCase(), status: "" })}
                            onBlur={(e) => lookup(r.key, e.target.value)}
                            className={cn(inp, "font-mono font-semibold w-full",
                              r.status === "bad" && "border-neg/60")}
                            placeholder="AAPL"
                          />
                        </td>
                        <td className="px-2 py-1.5 text-xs text-gray-400 max-w-[200px] truncate">
                          {r.status === "loading" ? "…" : r.status === "bad" ? <span className="text-neg">not found</span> : r.name}
                        </td>
                        <td className="px-2 py-1.5">
                          <input type="number" value={r.shares}
                            onChange={(e) => update(r.key, { shares: e.target.value })}
                            className={cn(inp, "text-right w-full stat-num")} placeholder="0" />
                        </td>
                        <td className="px-2 py-1.5">
                          <input type="number" value={r.entryPrice}
                            onChange={(e) => update(r.key, { entryPrice: e.target.value })}
                            className={cn(inp, "text-right w-full stat-num")} placeholder="0.00" />
                        </td>
                        <td className="px-2 py-1.5">
                          <input type="date" value={r.entryDate}
                            onChange={(e) => update(r.key, { entryDate: e.target.value })}
                            className={cn(inp, "w-full text-xs")} />
                        </td>
                        <td className="px-2 py-1.5 text-right stat-num text-gray-400">
                          {r.live != null ? fmtUsd(r.live, 2) : "—"}
                        </td>
                        <td className="px-2 py-1.5 text-right stat-num text-gray-300">
                          {cost > 0 ? fmtUsd(cost) : "—"}
                        </td>
                        <td className="px-2 py-1.5 text-center">
                          <button onClick={() => setRows((rs) => rs.filter((x) => x.key !== r.key))}
                            className="text-gray-600 hover:text-neg">
                            <Trash2 className="h-4 w-4" />
                          </button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

            {/* Footer */}
            <div className="flex items-center justify-between px-5 py-3 border-t border-line">
              <div className="flex items-center gap-4">
                <button
                  onClick={() => setRows((rs) => [...rs, blankRow()])}
                  className="inline-flex items-center gap-1 text-sm text-brand hover:text-brand-glow"
                >
                  <Plus className="h-4 w-4" /> Add row
                </button>
                <span className="text-xs text-gray-500">
                  {valid.length} valid · cost basis {fmtUsd(totalCost)}
                </span>
              </div>
              <div className="flex items-center gap-2">
                {submit.error && <span className="text-xs text-neg">{(submit.error as Error).message}</span>}
                <Button variant="ghost" onClick={onClose}>Cancel</Button>
                <Button onClick={() => submit.mutate()} disabled={submit.isPending || valid.length === 0}>
                  {submit.isPending ? "Adding…" : `Add ${valid.length} positions`}
                </Button>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

const inp =
  "bg-bg-soft border border-line rounded px-2 py-1 text-sm focus:border-brand/50 outline-none";
