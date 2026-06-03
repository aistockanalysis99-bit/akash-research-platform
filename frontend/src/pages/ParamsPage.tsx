import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { Trash2 } from "lucide-react";
import { api } from "@/lib/api";
import { Card, EmptyState, Loading, PageTitle } from "@/components/ui";
import { cn } from "@/lib/utils";

export default function ParamsPage() {
  const qc = useQueryClient();
  const { data, isLoading } = useQuery({ queryKey: ["params"], queryFn: api.params });
  const [sel, setSel] = useState<string | null>(null);

  const del = useMutation({
    mutationFn: (name: string) => api.paramDelete(name),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["params"] });
      setSel(null);
    },
  });

  const chosen =
    (data || []).find((p) => p.name === sel) ||
    (data && data.length ? data[0] : null);

  if (!sel && chosen) setSel(chosen.name);

  const params = chosen ? Object.entries(chosen.params) : [];

  // Group params visually (same groups as backtest page)
  const GROUP_KEYS: Record<string, string[]> = {
    "Momentum signal":    ["mom_short_len","mom_med_len","mom_long_len","w_short","w_med","w_long"],
    "Trend filter":       ["fast_len","slow_len","slope_bars"],
    "Entry & signal":     ["entry_threshold","exit_threshold","breakout_len","skip_bars"],
    "Risk & sizing":      ["risk_pct","target_vol","atr_len","stop_atr","trail_atr","breakeven_rr","max_gross_exp","max_lev_scalar"],
    "Scale-in":           ["enable_scale_in","max_adds","add_atr","add_frac"],
    "Take-profit":        ["enable_partial_tp","partial_pct","take_profit_rr"],
    "Limits & portfolio": ["max_bars_in_trade","max_concurrent_positions","portfolio_vol_target","max_portfolio_gross"],
    "Costs":              ["commission_bps","slippage_bps","fractional_shares","annualization_factor","vol_lookback"],
  };
  const allGrouped = Object.values(GROUP_KEYS).flat();
  const ungrouped = params.filter(([k]) => !allGrouped.includes(k));

  return (
    <div>
      <PageTitle
        title="Parameter Presets"
        subtitle="Saved strategy configurations. Load any preset from the Backtest tab."
        actions={
          <Link
            to="/backtest"
            className="text-sm text-brand hover:text-brand-glow"
          >
            ← Go to Backtest to create / run
          </Link>
        }
      />

      {isLoading && <Loading />}

      {data && data.length === 0 && (
        <Card>
          <EmptyState
            title="No saved presets yet"
            hint="Go to Backtest → configure parameters → click 'Save preset' to save a set here."
          />
        </Card>
      )}

      {data && data.length > 0 && (
        <div className="grid grid-cols-[220px_1fr] gap-5">
          {/* Preset list */}
          <div className="space-y-1">
            {data.map((p) => (
              <div
                key={p.name}
                className={cn(
                  "flex items-center gap-1 group rounded-lg px-3 py-2 cursor-pointer transition-colors",
                  sel === p.name ? "bg-brand/15" : "hover:bg-bg-hover"
                )}
                onClick={() => setSel(p.name)}
              >
                <span className={cn("text-sm flex-1 truncate", sel === p.name ? "text-brand font-medium" : "text-gray-300")}>
                  {p.name}
                </span>
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    if (confirm(`Delete preset "${p.name}"?`)) del.mutate(p.name);
                  }}
                  className="opacity-0 group-hover:opacity-100 text-gray-600 hover:text-neg transition-opacity"
                  title="Delete preset"
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </button>
              </div>
            ))}
          </div>

          {/* Preset detail */}
          {chosen && (
            <Card>
              <div className="flex items-center justify-between mb-4">
                <h3 className="font-semibold text-white">{chosen.name}</h3>
                <Link
                  to="/backtest"
                  className="text-xs text-brand hover:text-brand-glow"
                >
                  Open in Backtest →
                </Link>
              </div>

              <div className="space-y-4">
                {Object.entries(GROUP_KEYS).map(([group, keys]) => {
                  const rows = keys
                    .map((k) => params.find(([pk]) => pk === k))
                    .filter(Boolean) as [string, unknown][];
                  if (!rows.length) return null;
                  return (
                    <div key={group}>
                      <div className="text-[10px] uppercase tracking-wider text-gray-500 mb-1.5">
                        {group}
                      </div>
                      <div className="grid grid-cols-2 sm:grid-cols-3 gap-x-6 gap-y-1">
                        {rows.map(([k, v]) => (
                          <div key={k} className="flex items-center justify-between border-b border-line/30 py-0.5">
                            <span className="text-[11px] text-gray-400 truncate pr-2">
                              {k.replace(/_/g, " ")}
                            </span>
                            <span className={cn(
                              "text-[11px] stat-num shrink-0 font-medium",
                              v === true ? "text-pos" : v === false ? "text-neg" : "text-gray-200"
                            )}>
                              {v === true ? "ON" : v === false ? "OFF" : String(v)}
                            </span>
                          </div>
                        ))}
                      </div>
                    </div>
                  );
                })}
                {ungrouped.length > 0 && (
                  <div>
                    <div className="text-[10px] uppercase tracking-wider text-gray-500 mb-1.5">Other</div>
                    <div className="grid grid-cols-2 sm:grid-cols-3 gap-x-6 gap-y-1">
                      {ungrouped.map(([k, v]) => (
                        <div key={k} className="flex justify-between border-b border-line/30 py-0.5">
                          <span className="text-[11px] text-gray-400 truncate pr-2">{k.replace(/_/g, " ")}</span>
                          <span className="text-[11px] stat-num text-gray-200">{String(v)}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </Card>
          )}
        </div>
      )}
    </div>
  );
}
