import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, RefreshCw, TrendingUp, Upload, X } from "lucide-react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { api } from "@/lib/api";
import PositionDrawer from "@/components/PositionDrawer";
import AddPositionsModal from "@/components/AddPositionsModal";
import { Badge, Button, Card, EmptyState, ErrorBox, Loading, PageTitle } from "@/components/ui";
import {
  cn,
  decisionColor,
  fmtPct,
  fmtUsd,
  fmtUsdSigned,
  pnlColor,
  shortDate,
} from "@/lib/utils";
import type { Position } from "@/lib/types";

const ALLOC_COLORS = ["#2dd4bf", "#60a5fa", "#a78bfa", "#f472b6", "#fbbf24", "#34d399", "#fb923c", "#22d3ee"];

export default function PortfolioPage() {
  const qc = useQueryClient();
  const snap = useQuery({ queryKey: ["snap"], queryFn: api.portfolioSnapshot });
  const open = useQuery({ queryKey: ["open"], queryFn: api.portfolioOpen });
  const closed = useQuery({ queryKey: ["closed"], queryFn: () => api.portfolioClosed(50) });
  const history = useQuery({ queryKey: ["pfHistory"], queryFn: api.portfolioHistory });

  const [buyOpen, setBuyOpen] = useState(false);
  const [importOpen, setImportOpen] = useState(false);
  const [resetOpen, setResetOpen] = useState(false);
  const [detailId, setDetailId] = useState<number | null>(null);

  const invalidate = () => {
    ["snap", "open", "closed", "pfHistory"].forEach((k) =>
      qc.invalidateQueries({ queryKey: [k] })
    );
  };
  const refresh = useMutation({ mutationFn: api.portfolioRefresh, onSuccess: invalidate });
  const closeOne = useMutation({
    mutationFn: (id: number) => api.portfolioClose(id, "manual"),
    onSuccess: invalidate,
  });
  const closeAll = useMutation({ mutationFn: api.portfolioCloseAll, onSuccess: invalidate });

  const s = snap.data;
  const positions = open.data || [];
  const totalMV = positions.reduce((a, p) => a + (p.market_value ?? (p.units || 0) * (p.current_price || 0)), 0);

  // Day change across the book: Σ (current - prev_close) * units
  const dayChangeUsd = positions.reduce((a, p) => {
    if (p.prev_close && p.current_price && p.units)
      return a + (p.current_price - p.prev_close) * p.units;
    return a;
  }, 0);
  const prevMV = totalMV - dayChangeUsd;
  const dayChangePct = prevMV > 0 ? (dayChangeUsd / prevMV) * 100 : 0;

  const totalPnl = s ? s.realized_pnl + s.unrealized_pnl : 0;
  const totalPct = s && s.initial_capital ? (totalPnl / s.initial_capital) * 100 : 0;

  return (
    <div>
      <PageTitle
        title="Portfolio"
        subtitle="Your paper brokerage account. Buy and sell holdings, track daily moves and total return."
        actions={
          <div className="flex items-center gap-2">
            <Button onClick={() => setImportOpen(true)}>
              <Plus className="h-4 w-4" /> Add positions
            </Button>
            <Button variant="outline" onClick={() => refresh.mutate()} disabled={refresh.isPending}>
              <RefreshCw className={cn("h-4 w-4", refresh.isPending && "animate-spin")} />
              {refresh.isPending ? "Updating…" : "Update prices"}
            </Button>
            <button
              onClick={() => setResetOpen(true)}
              className="text-xs text-gray-600 hover:text-neg ml-1"
              title="Reset the paper account"
            >
              Reset
            </button>
          </div>
        }
      />

      {snap.isLoading && <Loading />}
      {snap.error && <ErrorBox error={snap.error} />}

      {/* HERO: total value + day change + total return */}
      {s && (
        <Card className="mb-5">
          <div className="flex flex-wrap items-end gap-x-10 gap-y-4">
            <div>
              <div className="text-xs uppercase tracking-wide text-gray-500">Total Value</div>
              <div className="text-4xl font-extrabold text-white stat-num mt-1">
                {fmtUsd(s.equity)}
              </div>
            </div>
            <div>
              <div className="text-xs uppercase tracking-wide text-gray-500">Today</div>
              <div className={cn("text-2xl font-bold stat-num mt-1", pnlColor(dayChangeUsd))}>
                {fmtUsdSigned(dayChangeUsd)}
                <span className="text-base ml-1">({fmtPct(dayChangePct)})</span>
              </div>
            </div>
            <div>
              <div className="text-xs uppercase tracking-wide text-gray-500">Total Return</div>
              <div className={cn("text-2xl font-bold stat-num mt-1", pnlColor(totalPnl))}>
                {fmtUsdSigned(totalPnl)}
                <span className="text-base ml-1">({fmtPct(totalPct)})</span>
              </div>
            </div>
            <div className="ml-auto text-right">
              <div className="text-xs uppercase tracking-wide text-gray-500">Cash · Holdings</div>
              <div className="text-sm text-gray-300 mt-2 stat-num">
                {fmtUsd(Math.max(0, s.cash))} · {fmtUsd(totalMV)}
              </div>
              <div className="text-xs text-gray-500 mt-0.5">
                {s.open_positions} positions · {s.gross_exposure_pct.toFixed(0)}% invested
              </div>
            </div>
          </div>
        </Card>
      )}

      {/* Portfolio value chart */}
      <Card className="mb-5">
        <div className="text-xs uppercase tracking-wide text-gray-500 mb-2">Portfolio Value</div>
        {history.isLoading && <Loading />}
        {history.data && history.data.length > 1 ? (
          <ResponsiveContainer width="100%" height={240}>
            <AreaChart data={history.data} margin={{ top: 5, right: 8, bottom: 0, left: 0 }}>
              <defs>
                <linearGradient id="pv" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#2dd4bf" stopOpacity={0.35} />
                  <stop offset="100%" stopColor="#2dd4bf" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid stroke="#1e2a3d" strokeDasharray="3 3" />
              <XAxis dataKey="snapshot_date" tick={{ fill: "#64748b", fontSize: 11 }} minTickGap={40} />
              <YAxis
                tick={{ fill: "#64748b", fontSize: 11 }}
                tickFormatter={(v) => `$${(v / 1e6).toFixed(2)}M`}
                width={62}
                domain={["auto", "auto"]}
              />
              <Tooltip
                contentStyle={{ background: "#111824", border: "1px solid #1e2a3d", borderRadius: 8, fontSize: 12 }}
                labelStyle={{ color: "#94a3b8" }}
                formatter={(v: number) => [fmtUsd(v), "Value"]}
              />
              <Area type="monotone" dataKey="equity" stroke="#2dd4bf" strokeWidth={2} fill="url(#pv)" />
            </AreaChart>
          </ResponsiveContainer>
        ) : (
          !history.isLoading && (
            <div className="py-10 text-center text-gray-500 text-sm">
              Building history — the value chart fills in as you update prices each day.
            </div>
          )
        )}
      </Card>

      {/* Holdings */}
      <div className="flex items-center justify-between mb-2">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-gray-400">Holdings</h2>
        {positions.length > 0 && (
          <button
            onClick={() => confirm("Sell ALL holdings at current price?") && closeAll.mutate()}
            className="text-xs text-gray-500 hover:text-neg"
          >
            Sell all
          </button>
        )}
      </div>
      {open.isLoading && <Loading />}
      {positions.length === 0 && !open.isLoading && (
        <Card>
          <EmptyState
            icon={<TrendingUp className="h-8 w-8" />}
            title="No holdings yet"
            hint="Buy a stock above, or let an approved AI verdict open a position automatically."
          />
        </Card>
      )}
      {positions.length > 0 && (
        <Card className="p-0 overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-xs uppercase text-gray-500 border-b border-line">
                <Th>Symbol</Th>
                <Th right>Shares</Th>
                <Th right>Avg Cost</Th>
                <Th right>Last</Th>
                <Th right>Day</Th>
                <Th right>Mkt Value</Th>
                <Th right>Total P&L</Th>
                <Th right>Weight</Th>
                <Th>Source</Th>
                <Th right></Th>
              </tr>
            </thead>
            <tbody>
              {positions.map((p, i) => {
                const mv = p.market_value ?? (p.units || 0) * (p.current_price || 0);
                const weight = totalMV > 0 ? (mv / totalMV) * 100 : 0;
                return (
                  <tr
                    key={p.id}
                    onClick={() => setDetailId(p.id)}
                    className="border-b border-line/50 hover:bg-bg-hover/50 cursor-pointer"
                  >
                    <Td>
                      <div className="flex items-center gap-2">
                        <span className="h-2 w-2 rounded-sm" style={{ background: ALLOC_COLORS[i % ALLOC_COLORS.length] }} />
                        <span className="font-bold font-mono">{p.symbol}</span>
                      </div>
                      <span className="text-xs text-gray-500 ml-4">{p.sector || ""}</span>
                    </Td>
                    <Td right className="text-gray-300">{p.units?.toFixed(2)}</Td>
                    <Td right className="text-gray-400">{fmtUsd(p.entry_price, 2)}</Td>
                    <Td right>{fmtUsd(p.current_price, 2)}</Td>
                    <Td right className={pnlColor(p.day_change_pct)}>
                      {p.day_change_pct != null ? fmtPct(p.day_change_pct) : "—"}
                    </Td>
                    <Td right className="text-white">{fmtUsd(mv)}</Td>
                    <Td right className={pnlColor(p.current_pnl_usd)}>
                      {fmtUsdSigned(p.current_pnl_usd)}
                      <span className="text-xs ml-1">({fmtPct(p.current_pnl_pct)})</span>
                    </Td>
                    <Td right className="text-gray-400">{weight.toFixed(1)}%</Td>
                    <Td>
                      <Badge className={decisionColor(p.decision_verdict)}>
                        {p.decision_verdict === "MANUAL"
                          ? "Manual"
                          : p.decision_verdict === "IMPORTED"
                          ? "Imported"
                          : `AI ${p.decision_verdict || ""}`}
                      </Badge>
                    </Td>
                    <Td right>
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          if (confirm(`Sell ${p.symbol} at current price?`)) closeOne.mutate(p.id);
                        }}
                        disabled={closeOne.isPending}
                        className="text-xs text-gray-500 hover:text-neg disabled:opacity-40"
                      >
                        Sell
                      </button>
                    </Td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </Card>
      )}

      {/* Closed trades */}
      {closed.data && closed.data.length > 0 && (
        <>
          <h2 className="text-sm font-semibold uppercase tracking-wide text-gray-400 mb-2 mt-8">
            Trade History
          </h2>
          <Card className="p-0 overflow-hidden">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-xs uppercase text-gray-500 border-b border-line">
                  <Th>Symbol</Th><Th right>Entry</Th><Th right>Exit</Th>
                  <Th right>P&L</Th><Th>Closed</Th><Th>Reason</Th>
                </tr>
              </thead>
              <tbody>
                {closed.data.map((p: Position) => (
                  <tr key={p.id} className="border-b border-line/50 hover:bg-bg-hover/50">
                    <Td className="font-bold font-mono">{p.symbol}</Td>
                    <Td right>{fmtUsd(p.entry_price, 2)}</Td>
                    <Td right>{fmtUsd(p.exit_price, 2)}</Td>
                    <Td right className={pnlColor(p.final_pnl_usd)}>
                      {fmtUsdSigned(p.final_pnl_usd)}
                      <span className="text-xs ml-1">({fmtPct(p.final_pnl_pct)})</span>
                    </Td>
                    <Td className="text-gray-400 text-xs">{shortDate(p.exit_date)}</Td>
                    <Td className="text-gray-400 text-xs">{p.exit_reason || "—"}</Td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>
        </>
      )}

      {buyOpen && <BuyModal onClose={() => setBuyOpen(false)} onDone={invalidate} />}
      {importOpen && <AddPositionsModal onClose={() => setImportOpen(false)} onDone={invalidate} />}
      {resetOpen && (
        <ResetModal
          currentCapital={s?.initial_capital ?? 2000000}
          onClose={() => setResetOpen(false)}
          onDone={invalidate}
        />
      )}
      {detailId != null && (
        <PositionDrawer positionId={detailId} onClose={() => setDetailId(null)} onChanged={invalidate} />
      )}
    </div>
  );
}

function BuyModal({ onClose, onDone }: { onClose: () => void; onDone: () => void }) {
  const [symbol, setSymbol] = useState("");
  const [amount, setAmount] = useState(100000);
  const buy = useMutation({
    mutationFn: () => api.portfolioBuy(symbol.trim().toUpperCase(), amount),
    onSuccess: () => {
      onDone();
      onClose();
    },
  });
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60" onClick={onClose}>
      <div className="card p-6 w-[420px]" onClick={(e) => e.stopPropagation()}>
        <h3 className="text-lg font-bold text-white mb-1">Buy a stock</h3>
        <p className="text-xs text-gray-500 mb-4">
          Market buy at the latest price. Shares = amount ÷ price.
        </p>
        <label className="block mb-3">
          <span className="text-xs uppercase text-gray-500 mb-1 block">Ticker</span>
          <input
            value={symbol}
            onChange={(e) => setSymbol(e.target.value)}
            placeholder="e.g. AAPL"
            className="w-full bg-bg-soft border border-line rounded-lg px-3 py-2 text-sm font-mono uppercase focus:border-brand/50 outline-none"
          />
        </label>
        <label className="block mb-4">
          <span className="text-xs uppercase text-gray-500 mb-1 block">Amount (USD)</span>
          <input
            type="number"
            value={amount}
            min={1000}
            step={1000}
            onChange={(e) => setAmount(Number(e.target.value))}
            className="w-full bg-bg-soft border border-line rounded-lg px-3 py-2 text-sm stat-num focus:border-brand/50 outline-none"
          />
        </label>
        {buy.error && <div className="text-sm text-neg mb-3">{(buy.error as Error).message}</div>}
        <div className="flex items-center justify-end gap-2">
          <Button variant="ghost" onClick={onClose}>Cancel</Button>
          <Button onClick={() => buy.mutate()} disabled={buy.isPending || !symbol.trim() || amount <= 0}>
            {buy.isPending ? "Buying…" : `Buy ${fmtUsd(amount)}`}
          </Button>
        </div>
        <button onClick={onClose} className="absolute" style={{ display: "none" }}><X /></button>
      </div>
    </div>
  );
}

function ResetModal({
  currentCapital,
  onClose,
  onDone,
}: {
  currentCapital: number;
  onClose: () => void;
  onDone: () => void;
}) {
  const [capital, setCapital] = useState(currentCapital);
  const [confirm, setConfirm] = useState("");
  const reset = useMutation({
    mutationFn: () => api.portfolioReset(capital),
    onSuccess: () => {
      onDone();
      onClose();
    },
  });
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60" onClick={onClose}>
      <div className="card p-6 w-[440px]" onClick={(e) => e.stopPropagation()}>
        <h3 className="text-lg font-bold text-neg mb-1">Reset paper account</h3>
        <p className="text-xs text-gray-400 mb-4">
          Permanently clears <b>all</b> positions (open + closed) and the value history,
          then sets your starting capital. Use this before importing your real
          holdings for a clean slate. This cannot be undone.
        </p>
        <label className="block mb-3">
          <span className="text-xs uppercase text-gray-500 mb-1 block">Starting capital (USD)</span>
          <input
            type="number"
            value={capital}
            step={10000}
            onChange={(e) => setCapital(Number(e.target.value))}
            className="w-full bg-bg-soft border border-line rounded-lg px-3 py-2 text-sm stat-num focus:border-brand/50 outline-none"
          />
        </label>
        <label className="block mb-4">
          <span className="text-xs uppercase text-gray-500 mb-1 block">
            Type RESET to confirm
          </span>
          <input
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
            placeholder="RESET"
            className="w-full bg-bg-soft border border-line rounded-lg px-3 py-2 text-sm font-mono focus:border-neg/50 outline-none"
          />
        </label>
        {reset.error && <div className="text-sm text-neg mb-3">{(reset.error as Error).message}</div>}
        <div className="flex items-center justify-end gap-2">
          <Button variant="ghost" onClick={onClose}>Cancel</Button>
          <Button
            variant="danger"
            onClick={() => reset.mutate()}
            disabled={reset.isPending || confirm.trim().toUpperCase() !== "RESET" || capital <= 0}
          >
            {reset.isPending ? "Resetting…" : "Wipe & reset"}
          </Button>
        </div>
      </div>
    </div>
  );
}

function Th({ children, right }: { children?: React.ReactNode; right?: boolean }) {
  return <th className={cn("px-3 py-2 font-medium", right ? "text-right" : "text-left")}>{children}</th>;
}
function Td({ children, right, className }: { children: React.ReactNode; right?: boolean; className?: string }) {
  return <td className={cn("px-3 py-2.5 align-top", right ? "text-right" : "text-left", className)}>{children}</td>;
}
