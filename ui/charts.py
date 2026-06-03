"""Plotly chart builders shared across pages."""
from __future__ import annotations

from datetime import datetime

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots


def equity_with_drawdown(equity_points: list[dict], log_scale: bool = False) -> go.Figure:
    """Equity curve + underwater drawdown subplot."""
    if not equity_points:
        fig = go.Figure()
        fig.update_layout(title="No data")
        return fig

    df = pd.DataFrame(equity_points)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.sort_values("timestamp")
    eq = df["equity"]
    peak = eq.cummax()
    dd = (eq / peak - 1.0) * 100

    fig = make_subplots(
        rows=2, cols=1, shared_xaxes=True,
        row_heights=[0.7, 0.3], vertical_spacing=0.05,
        subplot_titles=("Equity", "Drawdown %"),
    )
    fig.add_trace(go.Scatter(
        x=df["timestamp"], y=eq, mode="lines", name="Equity",
        line=dict(color="#22d3ee", width=2),
    ), row=1, col=1)
    fig.add_trace(go.Scatter(
        x=df["timestamp"], y=dd, mode="lines", name="Drawdown",
        line=dict(color="#ef4444", width=1),
        fill="tozeroy", fillcolor="rgba(239,68,68,0.2)",
    ), row=2, col=1)
    fig.update_layout(
        height=540,
        margin=dict(l=40, r=20, t=40, b=30),
        showlegend=False,
        template="plotly_dark",
    )
    if log_scale:
        fig.update_yaxes(type="log", row=1, col=1)
    return fig


def monthly_heatmap(monthly_returns_dict: dict) -> go.Figure:
    if not monthly_returns_dict:
        return go.Figure()
    rows = []
    for k, v in monthly_returns_dict.items():
        try:
            year, month = k.split("-")
            rows.append({"year": int(year), "month": int(month), "ret": float(v) * 100})
        except Exception:
            continue
    if not rows:
        return go.Figure()
    df = pd.DataFrame(rows)
    pivot = df.pivot(index="year", columns="month", values="ret").sort_index(ascending=False)
    pivot = pivot.reindex(columns=range(1, 13))
    months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

    fig = go.Figure(data=go.Heatmap(
        z=pivot.values,
        x=months,
        y=pivot.index.astype(str),
        colorscale=[[0, "#dc2626"], [0.5, "#1e293b"], [1, "#16a34a"]],
        zmid=0,
        text=[[f"{v:.1f}%" if not pd.isna(v) else "" for v in row] for row in pivot.values],
        texttemplate="%{text}",
        textfont={"size": 10, "color": "white"},
        hoverongaps=False,
    ))
    fig.update_layout(
        title="Monthly Returns (%)",
        height=380,
        margin=dict(l=40, r=20, t=40, b=30),
        template="plotly_dark",
    )
    return fig


def per_symbol_bar(per_symbol: list[dict]) -> go.Figure:
    if not per_symbol:
        return go.Figure()
    df = pd.DataFrame(per_symbol).sort_values("total_pnl")
    colors = ["#16a34a" if v >= 0 else "#dc2626" for v in df["total_pnl"]]
    fig = go.Figure(go.Bar(x=df["total_pnl"], y=df["symbol"], orientation="h", marker_color=colors))
    fig.update_layout(
        title="P&L Contribution by Symbol",
        xaxis_title="Total P&L ($)",
        height=max(220, 28 * len(df) + 80),
        margin=dict(l=70, r=20, t=40, b=30),
        template="plotly_dark",
    )
    return fig


def exit_reason_pie(exit_reasons: dict) -> go.Figure:
    if not exit_reasons:
        return go.Figure()
    labels = list(exit_reasons.keys())
    values = list(exit_reasons.values())
    fig = go.Figure(go.Pie(labels=labels, values=values, hole=0.45))
    fig.update_layout(
        title="Exit Reasons",
        height=320, margin=dict(l=20, r=20, t=40, b=20),
        template="plotly_dark",
    )
    return fig


def mae_mfe_scatter(trades: list[dict]) -> go.Figure:
    if not trades:
        return go.Figure()
    df = pd.DataFrame(trades)
    if "mae" not in df.columns or "mfe" not in df.columns:
        return go.Figure()
    colors = ["#16a34a" if p > 0 else "#dc2626" for p in df["pnl"]]
    fig = go.Figure(go.Scatter(
        x=df["mae"], y=df["mfe"], mode="markers",
        marker=dict(color=colors, size=8, opacity=0.7),
        text=df["symbol"],
        hovertemplate="%{text}<br>MAE: %{x:.0f}<br>MFE: %{y:.0f}<extra></extra>",
    ))
    fig.update_layout(
        title="MAE vs MFE per Trade",
        xaxis_title="Max Adverse Excursion ($)",
        yaxis_title="Max Favorable Excursion ($)",
        height=380,
        template="plotly_dark",
    )
    return fig


def bars_held_histogram(trades: list[dict]) -> go.Figure:
    if not trades:
        return go.Figure()
    df = pd.DataFrame(trades)
    fig = go.Figure(go.Histogram(x=df["bars_held"], nbinsx=30, marker_color="#22d3ee"))
    fig.update_layout(
        title="Bars Held Distribution",
        xaxis_title="Bars in trade",
        yaxis_title="# trades",
        height=320, template="plotly_dark",
    )
    return fig


def equity_overlay(runs_data: list[dict]) -> go.Figure:
    """For comparison: overlay normalized equity curves."""
    fig = go.Figure()
    for run in runs_data:
        eq = run.get("equity") or []
        if not eq:
            continue
        df = pd.DataFrame(eq).sort_values("timestamp")
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        norm = df["equity"] / df["equity"].iloc[0] * 100
        fig.add_trace(go.Scatter(
            x=df["timestamp"], y=norm, mode="lines",
            name=run.get("name", run.get("run_id", "?"))[-30:],
        ))
    fig.update_layout(
        title="Equity Comparison (normalized to 100)",
        height=480,
        template="plotly_dark",
        margin=dict(l=40, r=20, t=40, b=30),
    )
    return fig


def rolling_12m_chart(data: dict) -> go.Figure:
    if not data:
        return go.Figure()
    pts = sorted(data.items())
    x = [datetime.strptime(k, "%Y-%m") for k, _ in pts]
    y = [v * 100 for _, v in pts]
    fig = go.Figure(go.Scatter(x=x, y=y, mode="lines", line=dict(color="#22d3ee")))
    fig.add_hline(y=0, line_dash="dash", line_color="gray")
    fig.update_layout(
        title="Rolling 12-month Return (%)",
        height=320,
        template="plotly_dark",
        margin=dict(l=40, r=20, t=40, b=30),
    )
    return fig
