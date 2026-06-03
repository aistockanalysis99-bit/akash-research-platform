"""Smoke-test all FMP /stable/ endpoints used by the Phase 2 AI pipeline.

Why this exists:
    FMP's /stable/ docs have several ambiguities and preserved typos. This script
    probes each endpoint against a known-good ticker (NVDA) and reports:
        - which exact path works
        - which param name works (symbol= vs tickers= vs symbols=)
        - which key fields are present (mktCap vs marketCap, etc.)
        - whether documented typo'd fields (fillingDate, ...) actually appear

Usage:
    python -m scripts.smoke_fmp_stable
    python -m scripts.smoke_fmp_stable --symbol AAPL
    python -m scripts.smoke_fmp_stable --emit-constants  # writes fmp_constants.py

The output of a successful run is the source of truth for endpoint paths and
field names baked into engine/live/data/fmp_constants.py.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from engine.data.fmp_client import FMPClient, FMPError


def _today() -> str:
    return date.today().isoformat()


def _days_ago(n: int) -> str:
    return (date.today() - timedelta(days=n)).isoformat()


@dataclass
class EndpointProbe:
    """A single endpoint's probe specification.

    `paths` is an ordered list of candidate paths to try; first to return data wins.
    `params_variants` is an ordered list of param dicts to try; first to return data wins.
    `expected_fields` are field names we want to verify are present (top-level of the
        first record in a list response, or top-level of a dict response).
    """

    label: str
    paths: list[str]
    params_variants: list[dict[str, Any]]
    expected_fields: list[str] = field(default_factory=list)
    typo_fields: list[str] = field(default_factory=list)
    note: str = ""


# ---------------------------------------------------------------------------
# Probes — covers all 13 endpoints needed by Fundamental + News analysts
# ---------------------------------------------------------------------------

def build_probes(symbol: str) -> list[EndpointProbe]:
    return [
        EndpointProbe(
            label="profile",
            paths=["/profile"],
            params_variants=[{"symbol": symbol}],
            expected_fields=["companyName", "sector", "industry", "ceo", "exchange"],
            typo_fields=[],
            note="check mktCap vs marketCap",
        ),
        EndpointProbe(
            label="income_q",
            paths=["/income-statement"],
            params_variants=[{"symbol": symbol, "period": "quarter", "limit": 8}],
            expected_fields=["date", "revenue", "grossProfit", "operatingIncome",
                             "netIncome", "eps", "epsDiluted", "filingDate"],
            typo_fields=[],
        ),
        EndpointProbe(
            label="balance_q",
            paths=["/balance-sheet-statement"],
            params_variants=[{"symbol": symbol, "period": "quarter", "limit": 4}],
            expected_fields=["cashAndCashEquivalents", "totalDebt",
                             "totalStockholdersEquity", "totalCurrentAssets",
                             "totalCurrentLiabilities"],
        ),
        EndpointProbe(
            label="cashflow_q",
            paths=["/cash-flow-statement"],
            params_variants=[{"symbol": symbol, "period": "quarter", "limit": 4}],
            expected_fields=["netCashProvidedByOperatingActivities",
                             "capitalExpenditure", "freeCashFlow"],
            typo_fields=[],
        ),
        EndpointProbe(
            label="ratios_annual",
            paths=["/ratios"],
            params_variants=[
                {"symbol": symbol, "period": "annual", "limit": 5},
                {"symbol": symbol, "limit": 5},  # no period — server default
            ],
            expected_fields=["priceEarningsRatio", "currentRatio", "debtEquityRatio"],
            note="Starter plan blocks period=quarter; annual works",
        ),
        EndpointProbe(
            label="ratios_ttm",
            paths=["/ratios-ttm"],
            params_variants=[{"symbol": symbol}],
            expected_fields=["peRatioTTM"],
            note="trailing-twelve-month snapshot — single row",
        ),
        EndpointProbe(
            label="key_metrics_annual",
            paths=["/key-metrics"],
            params_variants=[
                {"symbol": symbol, "period": "annual", "limit": 5},
                {"symbol": symbol, "limit": 5},
            ],
            expected_fields=["roic", "roe", "enterpriseValue"],
        ),
        EndpointProbe(
            label="key_metrics_ttm",
            paths=["/key-metrics-ttm"],
            params_variants=[{"symbol": symbol}],
            expected_fields=["roicTTM", "roeTTM"],
            note="trailing-twelve-month snapshot — best per-quarter substitute on Starter",
        ),
        EndpointProbe(
            label="earnings",
            paths=["/earnings"],
            params_variants=[{"symbol": symbol, "limit": 8}],
            expected_fields=["date", "epsActual", "epsEstimated"],
            note="single endpoint covers historical + upcoming",
        ),
        EndpointProbe(
            label="earnings_calendar",
            paths=["/earnings-calendar"],
            params_variants=[{"symbol": symbol}],
            expected_fields=["date", "symbol"],
            note="redundant with /earnings for per-ticker; useful for market-wide",
        ),
        EndpointProbe(
            label="analyst_estimates",
            paths=["/analyst-estimates", "/financial-estimates"],
            params_variants=[
                {"symbol": symbol, "period": "annual", "page": 0, "limit": 10},
            ],
            expected_fields=["date", "revenueAvg", "epsAvg", "numAnalystsEps"],
        ),
        EndpointProbe(
            label="news_stock",
            paths=["/news/stock", "/stock-news", "/news/stock-latest"],
            params_variants=[
                {"symbols": symbol, "limit": 15},
                {"tickers": symbol, "limit": 15},
            ],
            expected_fields=["publishedDate", "title", "url"],
            note="symbols= vs tickers= param ambiguity",
        ),
        EndpointProbe(
            label="grades",
            paths=["/grades"],
            params_variants=[{"symbol": symbol}],
            expected_fields=["publishedDate", "gradingCompany", "previousGrade", "newGrade"],
        ),
        EndpointProbe(
            label="sec_filings",
            paths=["/sec-filings-search/symbol"],
            params_variants=[
                {"symbol": symbol, "from": _days_ago(60), "to": _today(),
                 "page": 0, "limit": 50},
            ],
            expected_fields=["filingDate", "formType", "link"],
            note="from/to date params are REQUIRED",
        ),
        EndpointProbe(
            label="insider_trades",
            paths=["/insider-trading/search"],
            params_variants=[
                {"symbol": symbol, "page": 0, "limit": 50},
            ],
            expected_fields=["transactionDate", "transactionType",
                             "securitiesTransacted", "price", "reportingName",
                             "acquisitionOrDisposition"],
            typo_fields=[],
            note="$1M filter computed client-side: price * securitiesTransacted",
        ),
        EndpointProbe(
            label="press_releases",
            paths=["/news/press-releases"],
            params_variants=[
                {"symbols": symbol, "limit": 30},
            ],
            expected_fields=["date", "title", "text"],
            note="PREMIUM — may 402 on Starter plan; pipeline must handle absence",
        ),
    ]


# ---------------------------------------------------------------------------
# Probing logic
# ---------------------------------------------------------------------------

async def probe_endpoint(client: FMPClient, probe: EndpointProbe) -> dict[str, Any]:
    """Try each (path, params) combo until one returns a non-empty response.

    Returns a result dict with:
        ok           — bool
        path         — winning path or None
        params       — winning params or None
        rec_count    — number of records returned
        fields_found — list of expected fields actually present
        fields_missing — list of expected fields absent
        typos_found  — list of preserved-typo fields actually present
        sample       — first record (or top-level dict), truncated
        errors       — list of (path, params, error_str)
    """
    errors: list[tuple[str, dict, str]] = []
    for path in probe.paths:
        for params in probe.params_variants:
            try:
                data = await client._get(path, params)
            except FMPError as e:
                errors.append((path, params, str(e)[:150]))
                continue
            except Exception as e:  # noqa: BLE001 — broad on purpose
                errors.append((path, params, f"{type(e).__name__}: {str(e)[:120]}"))
                continue

            # Did we get anything useful back?
            if isinstance(data, list) and data:
                first = data[0] if isinstance(data[0], dict) else {}
                rec_count = len(data)
            elif isinstance(data, dict) and data:
                first = data
                rec_count = 1
            else:
                # 200 but empty — record and try next combo
                errors.append((path, params, "empty response"))
                continue

            return {
                "ok": True,
                "path": path,
                "params": {k: v for k, v in params.items() if k != "apikey"},
                "rec_count": rec_count,
                "fields_found": [f for f in probe.expected_fields if f in first],
                "fields_missing": [f for f in probe.expected_fields if f not in first],
                "typos_found": [f for f in probe.typo_fields if f in first],
                "sample_keys": sorted(first.keys())[:25],
                "errors": errors,
                "note": probe.note,
            }
    return {
        "ok": False,
        "path": None,
        "params": None,
        "rec_count": 0,
        "fields_found": [],
        "fields_missing": probe.expected_fields,
        "typos_found": [],
        "sample_keys": [],
        "errors": errors,
        "note": probe.note,
    }


# ---------------------------------------------------------------------------
# Report rendering
# ---------------------------------------------------------------------------

def render_report(symbol: str, results: dict[str, dict]) -> str:
    lines = [
        f"FMP /stable/ smoke test — symbol={symbol}",
        "=" * 72,
        "",
    ]
    for label, r in results.items():
        status = "OK " if r["ok"] else "FAIL"
        lines.append(f"[{status}] {label}")
        if r["ok"]:
            lines.append(f"      path      : {r['path']}")
            lines.append(f"      params    : {r['params']}")
            lines.append(f"      records   : {r['rec_count']}")
            lines.append(f"      fields y  : {', '.join(r['fields_found']) or '(none of expected found)'}")
            if r["fields_missing"]:
                lines.append(f"      fields n  : {', '.join(r['fields_missing'])}")
            if r["typos_found"]:
                lines.append(f"      typos     : {', '.join(r['typos_found'])} (present — keep as-is)")
            lines.append(f"      sample keys (first 25): {', '.join(r['sample_keys'])}")
        else:
            lines.append(f"      tried     : {len(r['errors'])} combinations, all failed")
            for path, params, err in r["errors"][:4]:
                p = {k: v for k, v in params.items() if k != "apikey"}
                lines.append(f"        - {path} {p} -> {err}")
            if len(r["errors"]) > 4:
                lines.append(f"        - ... and {len(r['errors']) - 4} more")
        if r["note"]:
            lines.append(f"      note      : {r['note']}")
        lines.append("")
    return "\n".join(lines)


def render_constants(results: dict[str, dict]) -> str:
    """Generate engine/live/data/fmp_constants.py from probe results."""
    lines = [
        '"""FMP /stable/ endpoint paths and field names — validated by',
        'scripts/smoke_fmp_stable.py against a live ticker. Do not hand-edit;',
        're-run the smoke test if FMP docs change.',
        '"""',
        "from __future__ import annotations",
        "",
        "# ---------------------------------------------------------------------------",
        "# Validated endpoint paths (relative to FMP_BASE_URL = .../stable)",
        "# ---------------------------------------------------------------------------",
        "",
    ]
    path_map = {}
    for label, r in results.items():
        if r["ok"] and r["path"]:
            const = f"PATH_{label.upper()}"
            path_map[const] = r["path"]

    for const, path in path_map.items():
        lines.append(f'{const} = "{path}"')

    lines += [
        "",
        "# ---------------------------------------------------------------------------",
        "# Validated param-name choices (which key works for ticker selection)",
        "# ---------------------------------------------------------------------------",
        "",
    ]
    for label, r in results.items():
        if r["ok"] and r["params"]:
            key = next((k for k in ("symbol", "symbols", "tickers") if k in r["params"]), None)
            if key:
                lines.append(f'PARAM_{label.upper()} = "{key}"')

    lines += [
        "",
        "# ---------------------------------------------------------------------------",
        "# Preserved-typo fields confirmed present in live responses.",
        "# Use these literal names — do NOT try to 'fix' them.",
        "# ---------------------------------------------------------------------------",
        "",
    ]
    all_typos: set[str] = set()
    for r in results.values():
        all_typos.update(r["typos_found"])
    for typo in sorted(all_typos):
        const_name = "FIELD_" + typo.upper().replace("OR", "_OR_").replace("BY", "_BY_")
        lines.append(f'{const_name} = "{typo}"')

    lines += ["", ""]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

async def amain(symbol: str, emit_constants: bool, dump_json: bool) -> int:
    probes = build_probes(symbol)
    results: dict[str, dict] = {}

    async with FMPClient() as client:
        # Sequential — we want clear error attribution per endpoint.
        for probe in probes:
            print(f"  probing {probe.label} ...", flush=True)
            results[probe.label] = await probe_endpoint(client, probe)

    print()
    report = render_report(symbol, results)
    print(report)
    # Persist to file too — handy regardless of console encoding.
    from engine.config import LOG_DIR
    report_path = LOG_DIR / f"fmp_smoke_{symbol}.txt"
    report_path.write_text(report, encoding="utf-8")
    print(f"\nReport saved: {report_path}")

    if dump_json:
        out = {k: {kk: vv for kk, vv in v.items() if kk != "errors"}
               for k, v in results.items()}
        print("\n--- raw JSON ---")
        print(json.dumps(out, indent=2, default=str))

    if emit_constants:
        from engine.config import PROJECT_ROOT

        out_path = PROJECT_ROOT / "engine" / "live" / "data" / "fmp_constants.py"
        out_path.write_text(render_constants(results), encoding="utf-8")
        print(f"\nWrote: {out_path}")

    n_ok = sum(1 for r in results.values() if r["ok"])
    n_fail = len(results) - n_ok
    print(f"\nSummary: {n_ok} ok, {n_fail} fail")
    return 0 if n_fail == 0 else 1


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", default="NVDA")
    ap.add_argument("--emit-constants", action="store_true",
                    help="Write engine/live/data/fmp_constants.py from results")
    ap.add_argument("--json", action="store_true",
                    help="Also print raw JSON of results")
    args = ap.parse_args()
    sys.exit(asyncio.run(amain(args.symbol, args.emit_constants, args.json)))


if __name__ == "__main__":
    main()
