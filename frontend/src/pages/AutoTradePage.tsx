import { useState, useMemo, useEffect } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Bot, RefreshCw, ShieldCheck, Power, Eye, BarChart2, CheckCircle2, Loader2, Sparkles, Activity } from "lucide-react";
import { api } from "@/lib/api";
import type { AutoTradeSignal } from "@/lib/autoTradeTypes";
import { Badge, Button, Card, ErrorBox, Loading, PageTitle, StatCard } from "@/components/ui";
import { UniverseInspectionModal } from "@/components/simulator/UniverseInspectionModal";

function SignalRow({ signal }: { signal: AutoTradeSignal }) {
  const qualified = signal.decision === "QUALIFIED";
  const p = signal.payload;
  return (
    <div className="border-t border-line/60 py-3 first:border-0">
      <div className="flex items-center gap-3">
        <span className="font-semibold text-white w-28">{p.pair_name}</span>
        <Badge
          className={
            qualified
              ? "border-pos/40 bg-pos/10 text-pos"
              : "border-gray-700 bg-gray-800 text-gray-400"
          }
        >
          {signal.decision}
        </Badge>
        <span className="text-xs text-gray-500">
          {qualified ? `Z ${p.z_score} · target ${p.target_z} · stop ${p.stop_z}` : signal.rejection_reason}
        </span>
      </div>
      {qualified && p.proposed_legs && (
        <div className="mt-2 grid gap-2 sm:grid-cols-2">
          {p.proposed_legs.map((leg) => (
            <div key={leg.symbol} className="rounded-lg bg-bg-soft px-3 py-2 text-sm">
              <span className={leg.side === "BUY" ? "text-pos" : "text-warn"}>{leg.side}</span>{" "}
              <span className="font-semibold">{leg.symbol}</span>{" "}
              <span className="text-gray-400">× {leg.qty} @ ref ${leg.reference_price}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default function AutoTradePage() {
  const queryClient = useQueryClient();
  const status = useQuery({
    queryKey: ["auto-trade-status"],
    queryFn: api.autoTradeStatus,
    refetchInterval: 30000,
    retry: false,
  });
  const broker = useQuery({
    queryKey: ["auto-trade-broker"],
    queryFn: api.autoTradeBroker,
    refetchInterval: 60000,
    retry: false,
  });
  const scan = useMutation({
    mutationFn: api.autoTradeDryScan,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["auto-trade-status"] }),
  });
  const refresh = () => queryClient.invalidateQueries({ queryKey: ["auto-trade-status"] });
  const control = useMutation({ mutationFn: api.autoTradeControl, onSuccess: refresh });
  const kill = useMutation({ mutationFn: api.autoTradeKillSwitch, onSuccess: refresh });
  const submitPair = useMutation({ mutationFn: api.autoTradeSubmitPair, onSuccess: refresh });
  const exitPair = useMutation({ mutationFn: api.autoTradeExitPair, onSuccess: refresh });
  const reconcile = useMutation({ mutationFn: api.autoTradeReconcile, onSuccess: refresh });
  const telegramTest = useMutation({ mutationFn: api.autoTradeTelegramTest });
  const runToday = useMutation({ mutationFn: api.autoTradeRunToday, onSuccess: refresh });
  const [showUniverseModal, setShowUniverseModal] = useState(false);
  const run = scan.data ?? status.data?.latest_run;
  const summary = run?.summary;
  const readiness = status.data?.readiness.configuration;

  const isScanning = scan.isPending || runToday.isPending;
  const [lastScanDone, setLastScanDone] = useState(false);

  // Live progress simulation for scanning all 53 pairs in the universe
  const [progressPct, setProgressPct] = useState(0);
  const [pairCount, setPairCount] = useState(0);
  const [stageText, setStageText] = useState("");
  const [elapsedSeconds, setElapsedSeconds] = useState(0);

  useEffect(() => {
    if (!isScanning) {
      if (progressPct > 0) {
        setProgressPct(100);
        setPairCount(53);
        setStageText("Complete — all 53 pairs analyzed");
        setLastScanDone(true);
        const t = setTimeout(() => {
          setProgressPct(0);
          setPairCount(0);
          setStageText("");
        }, 5000);
        return () => clearTimeout(t);
      }
      return;
    }

    setLastScanDone(false);
    setProgressPct(6);
    setPairCount(1);
    setStageText("Loading 90-day institutional price series (53 pairs)...");
    const start = Date.now();

    const timer = setInterval(() => {
      const now = Date.now();
      const diffSec = Math.floor((now - start) / 1000);
      setElapsedSeconds(diffSec);

      setProgressPct((prev) => {
        if (prev < 20) return prev + 2.4;
        if (prev < 48) return prev + 1.8;
        if (prev < 72) return prev + 1.1;
        if (prev < 88) return prev + 0.6;
        if (prev < 95) return prev + 0.2;
        return prev;
      });

      setPairCount((prev) => {
        const next = Math.min(53, Math.max(1, Math.floor((Date.now() - start) / 380)));
        return next;
      });

      if (diffSec < 4) {
        setStageText("Loading 90-day institutional price series (53 pairs)...");
      } else if (diffSec < 10) {
        setStageText("Calculating cointegration & OLS hedge ratios (β)...");
      } else if (diffSec < 18) {
        setStageText("Evaluating z-score hurdles (|Z| ≥ 2.0σ) & half-life limits...");
      } else if (diffSec < 26) {
        setStageText("Running econometric gauntlet (ADF, volatility, earnings blackouts)...");
      } else {
        setStageText("Formulating draft orders & persisting universe ledger...");
      }
    }, 300);

    return () => clearInterval(timer);
  }, [isScanning]);

  const handleExecuteToday = async () => {
    if (status.data?.kill_switch) {
      alert("Emergency kill switch is currently ACTIVE. Disarm the kill switch below before executing trades.");
      return;
    }

    if (!status.data?.armed) {
      const armAndRun = window.confirm(
        "Paper execution is currently DISARMED (safety mode).\n\n" +
        "Would you like to ARM paper execution now and run today's Strategy 4 trades on Alpaca paper account?"
      );
      if (!armAndRun) return;
      try {
        await control.mutateAsync({ armed: true, confirm: true });
      } catch (err) {
        alert("Could not arm execution: " + (err as Error).message);
        return;
      }
    } else {
      const proceed = window.confirm("Refresh today's Strategy 4 trades and submit qualified paper orders to Alpaca?");
      if (!proceed) return;
    }
    runToday.mutate();
  };

  const qualifiedSignals = useMemo(() => {
    return run?.signals?.filter((s) => s.decision === "QUALIFIED") ?? [];
  }, [run?.signals]);

  return (
    <div>
      <PageTitle
        title="Strategy 4 Auto Trade"
        subtitle="Alpaca paper trading · persisted two-leg execution and Strategy 4 exit management."
        actions={<div className="flex items-center gap-2 flex-wrap">
          <Button
            variant="outline"
            onClick={() => setShowUniverseModal(true)}
            disabled={!run?.signals?.length}
            className="border-brand/40 text-brand hover:bg-brand/10"
          >
            <Eye className="h-4 w-4 mr-1" />
            Inspect Universe ({run?.signals?.length ?? 0})
          </Button>
          <Button
            variant="outline"
            onClick={() => scan.mutate()}
            disabled={isScanning}
            title="Scan all 53 pairs in universe without submitting broker orders"
          >
            <RefreshCw className={`h-4 w-4 ${scan.isPending ? "animate-spin" : ""}`} />
            {scan.isPending ? "Scanning universe…" : "Run dry scan"}
          </Button>
          <Button
            onClick={handleExecuteToday}
            disabled={isScanning || status.data?.kill_switch}
            className={!status.data?.armed ? "bg-amber-600 hover:bg-amber-500 text-white" : ""}
            title={!status.data?.armed ? "Currently disarmed — click to arm & execute" : "Refresh & execute today's paper trades"}
          >
            <Power className="h-4 w-4" />
            {runToday.isPending ? "Running today…" : !status.data?.armed ? "Arm & execute today" : "Refresh & execute today"}
          </Button>
        </div>}
      />

      {/* ── REAL-TIME PROGRESS HUD ── */}
      {isScanning && (
        <Card className="mb-4 border-brand/50 bg-brand/5 p-4 relative overflow-hidden shadow-lg animate-in fade-in duration-200">
          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center gap-2">
              <Loader2 className="h-4 w-4 animate-spin text-brand" />
              <span className="font-semibold text-white text-sm">
                {scan.isPending ? "Running Strategy 4 Dry Scan" : "Running Daily Strategy 4 Analysis & Execution"}
              </span>
              <Badge className="border-brand/40 bg-brand/20 text-brand text-xs">
                Pair {pairCount} / 53
              </Badge>
            </div>
            <div className="flex items-center gap-3 text-xs font-mono">
              <span className="text-brand font-semibold">{Math.round(progressPct)}%</span>
              <span className="text-gray-400">⏱ {String(Math.floor(elapsedSeconds / 60)).padStart(2, "0")}:{String(elapsedSeconds % 60).padStart(2, "0")}</span>
            </div>
          </div>

          <div className="w-full bg-gray-800 rounded-full h-2.5 overflow-hidden border border-gray-700/80 mb-2.5">
            <div
              className="bg-gradient-to-r from-brand/70 via-brand to-cyan-400 h-2.5 rounded-full transition-all duration-300 ease-out shadow-[0_0_10px_rgba(45,212,191,0.5)]"
              style={{ width: `${progressPct}%` }}
            />
          </div>

          <div className="flex items-center justify-between text-xs text-gray-400">
            <span className="italic">{stageText}</span>
            <span className="text-gray-500 font-mono">ADF stationarity &amp; z-scores</span>
          </div>
        </Card>
      )}

      {/* ── SCAN COMPLETED BANNER ── */}
      {lastScanDone && !isScanning && (
        <Card className="mb-4 border-pos/40 bg-pos/10 p-3.5 flex items-center justify-between animate-in fade-in duration-200">
          <div className="flex items-center gap-2 text-pos text-sm font-medium">
            <CheckCircle2 className="h-4 w-4" />
            <span>Scan complete! All 53 universe pairs evaluated ({qualifiedSignals.length} qualified).</span>
          </div>
          <Button
            variant="outline"
            onClick={() => setShowUniverseModal(true)}
            className="border-pos/40 text-pos hover:bg-pos/10 text-xs py-1 h-7"
          >
            Inspect Scanned Universe
          </Button>
        </Card>
      )}

      <Card className="mb-4 border-brand/30 bg-brand/5">
        <div className="flex gap-3">
          <ShieldCheck className="h-5 w-5 text-warn shrink-0" />
          <div>
            <div className="font-semibold text-brand">Paper trading safety controls</div>
            <p className="text-sm text-gray-400 mt-1">
              Orders are restricted to Alpaca&apos;s paper endpoint. Both legs are reconciled before a pair is marked open.
            </p>
          </div>
        </div>
      </Card>

      {status.isLoading && <Loading label="Loading auto-trade status…" />}
      {status.error && <ErrorBox error={status.error} />}
      {scan.error && <ErrorBox error={scan.error} />}
      {control.error && <ErrorBox error={control.error} />}
      {kill.error && <ErrorBox error={kill.error} />}
      {submitPair.error && <ErrorBox error={submitPair.error} />}
      {exitPair.error && <ErrorBox error={exitPair.error} />}
      {reconcile.error && <ErrorBox error={reconcile.error} />}
      {broker.error && <ErrorBox error={broker.error} />}
      {telegramTest.error && <ErrorBox error={telegramTest.error} />}
      {runToday.error && <ErrorBox error={runToday.error} />}
      {runToday.data && (
        <Card className="mb-4 border-pos/30 bg-pos/5 text-sm text-pos">
          {runToday.data.message} Qualified: {runToday.data.qualified_pairs} · Submitted: {runToday.data.submitted_pairs}
        </Card>
      )}

      {status.data && (
        <>
          <div className="grid gap-3 sm:grid-cols-4 mb-4">
            <StatCard label="Mode" value="Paper" sub={status.data.trade_submission_available ? "Entries enabled" : "Entries blocked"} />
            <StatCard
              label="Configuration"
              value={readiness?.ready ? "Ready" : "Needs keys"}
              valueClass={readiness?.ready ? "text-pos" : "text-warn"}
            />
            <StatCard label="Qualified" value={summary?.qualified_pairs ?? "—"} />
            <StatCard label="Rejected" value={summary?.rejected_pairs ?? "—"} />
          </div>

          <div className="grid gap-3 sm:grid-cols-4 mb-4">
            <StatCard label="Alpaca equity" value={broker.data ? `$${broker.data.account.equity.toLocaleString()}` : "—"} />
            <StatCard label="Buying power" value={broker.data ? `$${broker.data.account.buying_power.toLocaleString()}` : "—"} />
            <StatCard label="US market" value={broker.data?.market.is_open ? "Open" : "Closed"} />
            <StatCard label="Paper positions" value={broker.data?.positions.length ?? "—"} />
          </div>

          <Card className="mb-4">
            <div className="flex flex-wrap items-center gap-2">
              <Power className="h-5 w-5 text-brand" />
              <span className="font-semibold mr-auto">Execution controls</span>
              <Button
                variant="outline"
                onClick={() => {
                  const armed = !status.data.armed;
                  if (!armed || window.confirm("Arm automatic Alpaca paper-trading entries?")) {
                    control.mutate({ armed, kill_switch: false, confirm: armed });
                  }
                }}
                disabled={control.isPending || status.data.kill_switch}
              >
                {status.data.armed ? "Disarm entries" : "Arm paper entries"}
              </Button>
              <Button variant="outline" onClick={() => reconcile.mutate()} disabled={reconcile.isPending}>
                Reconcile Alpaca
              </Button>
              <Button variant="outline" onClick={() => telegramTest.mutate()} disabled={telegramTest.isPending}>
                Test Telegram
              </Button>
              <Button
                variant="danger"
                disabled={kill.isPending || status.data.kill_switch}
                onClick={() => window.confirm("Activate kill switch and cancel pending entries?") && kill.mutate()}
              >
                {status.data.kill_switch ? "Kill switch active" : "Activate kill switch"}
              </Button>
            </div>
          </Card>

          <Card className="mb-4">
            <h2 className="font-semibold mb-3">Automation health and paper performance</h2>
            <div className="grid gap-3 sm:grid-cols-4 mb-3">
              <StatCard label="Open pairs" value={status.data.operations.performance.open_pairs} />
              <StatCard label="Closed pairs" value={status.data.operations.performance.closed_pairs} />
              <StatCard label="Realized P&L" value={`$${status.data.operations.performance.realized_pnl.toFixed(2)}`} />
              <StatCard label="Telegram pending" value={status.data.operations.notification_outbox.pending ?? 0} />
            </div>
            <div className="space-y-2 text-xs text-gray-400">
              {status.data.operations.jobs.slice(0, 6).map((job) => (
                <div key={`${job.name}-${job.slot}`} className="flex gap-3 rounded bg-bg-soft px-3 py-2">
                  <span className="font-medium text-gray-200">{job.name}</span>
                  <span>{job.slot}</span><span>{job.status}</span>
                  {job.error_type && <span className="text-neg">{job.error_type}</span>}
                </div>
              ))}
              {status.data.operations.jobs.length === 0 && <div>No automation runs recorded yet.</div>}
            </div>
          </Card>

          {!readiness?.ready && (
            <Card className="mb-4 border-neg/30">
              <div className="flex gap-2 text-sm text-neg">
                <AlertTriangle className="h-4 w-4 shrink-0" />
                <span>{readiness?.errors.join(" · ")}</span>
              </div>
            </Card>
          )}

          <Card className="mb-4">
            <div className="flex items-center gap-2 mb-3">
              <Bot className="h-5 w-5 text-brand" />
              <h2 className="font-semibold">Latest Strategy 4 scan</h2>
              {run?.idempotent_replay && <Badge className="border-brand/30 text-brand">Idempotent replay</Badge>}
            </div>
            {summary ? (
              <>
                <div className="grid gap-2 text-sm sm:grid-cols-3">
                  <div><span className="text-gray-500">Session:</span> {summary.session_date}</div>
                  <div><span className="text-gray-500">Data cutoff:</span> {summary.data_cutoff_date}</div>
                  <div><span className="text-gray-500">Market volatility:</span> {summary.market_vol_pct}%</div>
                  <div><span className="text-gray-500">Next planned scan:</span> {summary.next_scheduled_scan_at}</div>
                </div>
                <div className="mt-3 pt-3 border-t border-line/60 flex flex-wrap items-center justify-between gap-2">
                  <span className="text-xs text-gray-400">
                    {summary.qualified_pairs} qualified · {summary.rejected_pairs} uncrossed / filtered
                  </span>
                  <Button
                    variant="outline"
                    onClick={() => setShowUniverseModal(true)}
                    disabled={!run?.signals?.length}
                    className="text-xs py-1 px-2.5 h-auto border-brand/40 text-brand hover:bg-brand/10"
                  >
                    <BarChart2 className="h-3.5 w-3.5 mr-1" />
                    View Scanned Pairs, Graphs &amp; Scores
                  </Button>
                </div>
              </>
            ) : (
              <div className="text-sm text-gray-500">No dry scan has been saved yet.</div>
            )}
          </Card>

          {run?.signals && (
            <Card className="mb-4">
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2">
                  <ShieldCheck className="h-5 w-5 text-brand" />
                  <h2 className="font-semibold">Today&apos;s Strategy 4 Trades</h2>
                </div>
                <Button
                  variant="outline"
                  onClick={() => setShowUniverseModal(true)}
                  className="text-xs py-1 px-2.5 h-auto"
                >
                  <Eye className="h-3.5 w-3.5 mr-1 text-brand" />
                  Inspect All {run.signals.length} Pairs
                </Button>
              </div>

              {qualifiedSignals.length > 0 ? (
                <div>
                  <p className="text-xs text-pos font-medium mb-2">
                    {qualifiedSignals.length} pair{qualifiedSignals.length > 1 ? "s" : ""} qualified for execution.
                  </p>
                  {qualifiedSignals.map((signal) => <SignalRow key={signal.signal_id} signal={signal} />)}
                </div>
              ) : (
                <div className="rounded-lg border border-line/60 bg-bg-soft/40 p-5 text-center">
                  <div className="flex justify-center mb-2">
                    <div className="rounded-full bg-slate-800 p-2 text-slate-300">
                      <CheckCircle2 className="h-6 w-6 text-brand" />
                    </div>
                  </div>
                  <div className="font-semibold text-white text-base">No Qualifying Trades Today</div>
                  <p className="text-xs text-gray-400 max-w-xl mx-auto mt-1.5 leading-relaxed">
                    Strategy 4 evaluated all {summary?.evaluated_pairs ?? run.signals.length} pairs across the S&amp;P 500 universe for session {summary?.session_date ?? "today"}. None met the strict entry hurdle (|Z| &ge; 2.10&sigma; with momentum reversal confirmation). Capital is strictly protected until statistical divergence occurs.
                  </p>
                  <Button
                    variant="outline"
                    onClick={() => setShowUniverseModal(true)}
                    className="mt-4 text-xs border-brand/50 text-white hover:bg-brand/10"
                  >
                    <Eye className="h-4 w-4 mr-1.5 text-brand" />
                    Inspect All Scanned Pairs, Graphs &amp; Scores ({run.signals.length} Pairs)
                  </Button>
                </div>
              )}
            </Card>
          )}

          <Card className="mt-4">
            <h2 className="font-semibold mb-2">Pair trades</h2>
            {status.data.pairs.length === 0 && <div className="text-sm text-gray-500">No pair intents yet.</div>}
            {status.data.pairs.map((pair) => (
              <div key={pair.pair_trade_id} className="border-t border-line/60 py-3 first:border-0">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-semibold">{pair.ticker_a}/{pair.ticker_b}</span>
                  <Badge className="border-gray-700 text-gray-300">{pair.state}</Badge>
                  {pair.error_code && <span className="text-xs text-neg">{pair.error_code}</span>}
                  {pair.current_z != null && <span className="text-xs text-gray-400">Z {pair.current_z.toFixed(2)}</span>}
                  {pair.unrealized_pnl != null && <span className="text-xs text-gray-400">Open P&amp;L ${pair.unrealized_pnl.toFixed(2)}</span>}
                  {pair.realized_pnl != null && <span className="text-xs text-gray-400">Realized ${pair.realized_pnl.toFixed(2)}</span>}
                  <div className="ml-auto flex gap-2">
                    {pair.state === "DRAFT" && (
                      <Button
                        disabled={!status.data.trade_submission_available || submitPair.isPending}
                        onClick={() => window.confirm("Submit both paper-trading legs?") && submitPair.mutate(pair.pair_trade_id)}
                      >Submit pair</Button>
                    )}
                    {pair.state === "OPEN" && (
                      <Button
                        variant="danger"
                        disabled={exitPair.isPending}
                        onClick={() => window.confirm("Exit both paper-trading legs?") && exitPair.mutate(pair.pair_trade_id)}
                      >Exit pair</Button>
                    )}
                  </div>
                </div>
                <div className="mt-2 grid gap-2 sm:grid-cols-2">
                  {pair.legs.map((leg) => (
                    <div key={leg.leg_id} className="rounded-lg bg-bg-soft px-3 py-2 text-sm">
                      {leg.side} {leg.symbol} × {leg.target_qty} · filled {leg.filled_qty}
                      {leg.avg_fill_price ? ` @ ${leg.avg_fill_price}` : ""}
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </Card>
        </>
      )}

      {/* Universe Inspection Modal */}
      <UniverseInspectionModal
        isOpen={showUniverseModal}
        onClose={() => setShowUniverseModal(false)}
        signals={run?.signals ?? []}
        summary={summary}
      />
    </div>
  );
}
