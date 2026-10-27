#!/usr/bin/env python3
"""S&P 500 Sector-Isolated 1-on-1 Cointegrated Pair Discovery Pipeline.

Aggressively filters the S&P 500 universe using a two-stage mathematical gate:
1. Pearson Correlation Gate: r >= 0.90 over 252 trading days.
2. Engle-Granger Cointegration Gate: coint p-value <= 0.05 (mean-reversion proof).

Outputs verified survivor pairs to data/sp500_master_pairs.csv and data/sp500_master_pairs.json.
"""
from __future__ import annotations

import collections
import io
import itertools
import json
import logging
import os
import sys
import urllib.request
import warnings
from pathlib import Path
from typing import Any, Dict, List, Tuple

import numpy as np
import pandas as pd
from statsmodels.tsa.stattools import coint
import yfinance as yf

# Suppress noisy deprecation/formatting warnings
warnings.filterwarnings("ignore")
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("pair_discovery")

WIKI_SP500_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
MIN_CORRELATION = 0.90
MAX_COINT_PVALUE = 0.05
TRADING_DAYS = 252
MIN_HISTORY_BARS = 180


def fetch_sp500_universe() -> pd.DataFrame:
    """Step 1: Pull live S&P 500 tickers and GICS sectors dynamically from Wikipedia."""
    logger.info("Step 1: Fetching S&P 500 universe from Wikipedia...")
    try:
        tables = pd.read_html(WIKI_SP500_URL, storage_options={"User-Agent": USER_AGENT})
    except Exception as exc:
        logger.warning("Direct pd.read_html with storage_options failed (%s), trying with urllib request...", exc)
        req = urllib.request.Request(WIKI_SP500_URL, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=25) as response:
            html_content = response.read().decode("utf-8")
        tables = pd.read_html(io.StringIO(html_content))

    if not tables:
        raise RuntimeError("No tables found on Wikipedia S&P 500 page.")

    sp500_df = tables[0]

    sym_col = next((c for c in sp500_df.columns if "symbol" in str(c).lower() or "ticker" in str(c).lower()), None)
    sec_col = next((c for c in sp500_df.columns if "sector" in str(c).lower()), None)

    if not sym_col or not sec_col:
        raise KeyError(f"Could not locate Symbol and Sector columns. Found: {list(sp500_df.columns)}")

    universe_df = sp500_df[[sym_col, sec_col]].copy()
    universe_df.columns = ["symbol", "sector"]
    universe_df["symbol"] = universe_df["symbol"].astype(str).str.strip()
    universe_df["sector"] = universe_df["sector"].astype(str).str.strip()
    universe_df = universe_df.dropna().drop_duplicates(subset=["symbol"])

    logger.info("Successfully fetched %d S&P 500 companies across %d GICS sectors.",
                len(universe_df), universe_df["sector"].nunique())
    return universe_df


def download_historical_prices(universe_df: pd.DataFrame) -> Tuple[pd.DataFrame, Dict[str, str]]:
    """Step 2: Download daily adjusted closing prices for past 252 trading days."""
    logger.info("Step 2: Downloading 1-year historical prices (252 trading days) via yfinance...")

    ticker_map = {}  # yf_symbol -> original_symbol
    yf_tickers = []
    symbol_to_sector = {}

    for _, row in universe_df.iterrows():
        orig_sym = row["symbol"]
        sector = row["sector"]
        yf_sym = orig_sym.replace(".", "-")
        ticker_map[yf_sym] = orig_sym
        yf_tickers.append(yf_sym)
        symbol_to_sector[orig_sym] = sector

    prices_dict = {}
    try:
        from engine.detect_setups import get_fmp_api_key, fetch_fmp_historical_prices
        fmp_key = get_fmp_api_key()
    except Exception:
        fmp_key = ""

    if fmp_key:
        logger.info("Downloading historical prices for %d tickers via FMP (Primary)...", len(yf_tickers))
        try:
            fmp_series = fetch_fmp_historical_prices(yf_tickers, period="5y")
            for yf_s in yf_tickers:
                orig_s = ticker_map.get(yf_s, yf_s)
                if yf_s in fmp_series and not fmp_series[yf_s].dropna().empty:
                    prices_dict[orig_s] = fmp_series[yf_s]
                elif orig_s in fmp_series and not fmp_series[orig_s].dropna().empty:
                    prices_dict[orig_s] = fmp_series[orig_s]
        except Exception as e:
            logger.warning("FMP universe download error: %s. Using secondary provider.", e)

    missing_tickers = [ticker_map.get(s, s) for s in yf_tickers if ticker_map.get(s, s) not in prices_dict]
    if missing_tickers:
        missing_yf = [s for s in yf_tickers if ticker_map.get(s, s) in missing_tickers]
        if not fmp_key:
            logger.info("FMP API key not configured locally. Downloading historical prices for %d tickers via secondary provider...", len(missing_yf))
        try:
            raw_data = yf.download(
                missing_yf,
                period="5y",
                interval="1d",
                auto_adjust=True,
                progress=False,
                threads=True,
            )
            if not raw_data.empty:
                if isinstance(raw_data.columns, pd.MultiIndex):
                    level_0 = [str(c).lower() for c in raw_data.columns.levels[0]]
                    if "close" in level_0:
                        sec_df = raw_data["Close"].copy()
                    elif "adj close" in level_0:
                        sec_df = raw_data["Adj Close"].copy()
                    else:
                        sec_df = raw_data.xs(raw_data.columns.levels[0][0], axis=1).copy()
                else:
                    sec_df = raw_data.copy()

                for col in sec_df.columns:
                    orig_s = ticker_map.get(col, col)
                    if orig_s not in prices_dict and not sec_df[col].dropna().empty:
                        prices_dict[orig_s] = sec_df[col]
        except Exception as exc:
            logger.warning("Secondary batch download encountered an error: %s", exc)

    if not prices_dict:
        raise RuntimeError("No historical data returned from primary (FMP) or secondary providers.")

    prices_df = pd.DataFrame(prices_dict)
    if len(prices_df) > TRADING_DAYS:
        prices_df = prices_df.iloc[-TRADING_DAYS:]

    valid_columns = []
    dropped_count = 0
    for col in prices_df.columns:
        valid_bars = prices_df[col].dropna().count()
        if valid_bars >= MIN_HISTORY_BARS:
            valid_columns.append(col)
        else:
            dropped_count += 1

    prices_df = prices_df[valid_columns]
    logger.info("Dropped %d symbols due to insufficient history or delisting.", dropped_count)

    # Impute missing values robustly
    prices_df = prices_df.ffill().bfill()
    prices_df = prices_df.dropna(axis=1)

    logger.info("Final clean price matrix shape: %s (%d trading days, %d tickers)",
                prices_df.shape, len(prices_df), prices_df.shape[1])
    return prices_df, symbol_to_sector


def compute_cointegrated_pairs(
    prices_df: pd.DataFrame,
    symbol_to_sector: Dict[str, str],
    min_corr: float = MIN_CORRELATION,
    max_pvalue: float = MAX_COINT_PVALUE,
) -> List[Dict[str, Any]]:
    """Steps 3 & 4: Strict 1-on-1 Sector-Isolated Pairing with Correlation + Cointegration Gates."""
    logger.info("Step 3: Calculating strict 1-v-1 pairs within exact same GICS sectors...")
    logger.info("Gate 1: Pearson Correlation >= %.2f | Gate 2: Engle-Granger Cointegration p-value <= %.2f",
                min_corr, max_pvalue)

    sector_groups: Dict[str, List[str]] = collections.defaultdict(list)
    for symbol in prices_df.columns:
        sec = symbol_to_sector.get(symbol)
        if sec:
            sector_groups[sec].append(symbol)

    survivor_pairs: List[Dict[str, Any]] = []
    total_evaluated = 0
    passed_corr = 0
    passed_coint = 0

    for sector, tickers in sorted(sector_groups.items()):
        if len(tickers) < 2:
            continue

        sec_prices = prices_df[tickers]
        corr_matrix = sec_prices.corr(method="pearson")

        sector_evaluated = 0
        sector_survivors = 0

        for ticker_a, ticker_b in itertools.combinations(sorted(tickers), 2):
            total_evaluated += 1
            sector_evaluated += 1

            corr = corr_matrix.loc[ticker_a, ticker_b]
            if pd.isna(corr) or np.isinf(corr):
                continue

            # Gate 1: Pearson Correlation check (r >= 0.90)
            if corr < min_corr:
                continue

            passed_corr += 1

            # Gate 2: Engle-Granger Cointegration test (coint p-value <= 0.05)
            s_a = sec_prices[ticker_a]
            s_b = sec_prices[ticker_b]

            try:
                # Test Engle-Granger cointegration
                _, p_val, _ = coint(s_a, s_b)
            except Exception as test_err:
                logger.warning("Error running coint on %s-%s: %s", ticker_a, ticker_b, test_err)
                continue

            if pd.isna(p_val) or np.isinf(p_val):
                continue

            if p_val <= max_pvalue:
                passed_coint += 1
                sector_survivors += 1
                survivor_pairs.append({
                    "ticker_a": ticker_a,
                    "ticker_b": ticker_b,
                    "sector": sector,
                    "correlation": round(float(corr), 4),
                    "cointegration_pvalue": round(float(p_val), 4),
                })

        logger.info("Sector '%s': %d evaluated -> %d passed correlation >= %.2f -> %d proven cointegrated (p <= %.2f)",
                    sector, sector_evaluated, sum(1 for p in survivor_pairs if p["sector"] == sector), min_corr, sector_survivors, max_pvalue)

    logger.info("Summary: %d pairs evaluated -> %d passed corr >= %.2f -> %d survived cointegration gate (p <= %.2f)",
                total_evaluated, passed_corr, min_corr, len(survivor_pairs), max_pvalue)

    # Sort survivor pairs by correlation descending (secondary sort by p-value ascending)
    survivor_pairs.sort(key=lambda item: (-item["correlation"], item["cointegration_pvalue"]))
    return survivor_pairs


def export_survivor_pairs(pairs: List[Dict[str, Any]]) -> Tuple[Path, Path]:
    """Step 5: Export survivor pairs to CSV and JSON formats."""
    logger.info("Step 4: Exporting curated cointegrated pairs...")

    script_path = Path(__file__).resolve()
    # Support running from repo root or inside EXTRA/
    base_dirs = [
        script_path.parent.parent,
        Path.cwd(),
    ]

    target_paths = []
    for base_dir in set(base_dirs):
        data_dir = base_dir / "data"
        data_dir.mkdir(parents=True, exist_ok=True)

        csv_path = data_dir / "sp500_master_pairs.csv"
        json_path = data_dir / "sp500_master_pairs.json"

        # Export CSV strictly containing: ticker_a, ticker_b, sector, correlation, cointegration_pvalue
        field_order = ["ticker_a", "ticker_b", "sector", "correlation", "cointegration_pvalue"]
        df_export = pd.DataFrame(pairs, columns=field_order)
        df_export.to_csv(csv_path, index=False)

        # Export JSON
        export_payload = {
            "metadata": {
                "description": "S&P 500 Sector-Isolated Mathematically Proven Cointegrated Pairs",
                "min_correlation": MIN_CORRELATION,
                "max_cointegration_pvalue": MAX_COINT_PVALUE,
                "trading_days": TRADING_DAYS,
                "total_pairs": len(pairs),
            },
            "pairs": pairs,
        }
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(export_payload, f, indent=2)

        # Also sync to root files if writing to base_dir
        root_csv = base_dir / "sp500_master_pairs.csv"
        root_json = base_dir / "sp500_master_pairs.json"
        df_export.to_csv(root_csv, index=False)
        with open(root_json, "w", encoding="utf-8") as f:
            json.dump(export_payload, f, indent=2)

        target_paths.append((csv_path, json_path))
        logger.info("Exported files to %s and %s", csv_path, json_path)

    primary_csv, primary_json = target_paths[0]
    return primary_csv, primary_json


def main() -> int:
    try:
        # 1. Fetch Universe
        universe_df = fetch_sp500_universe()

        # 2. Download Historical Data
        prices_df, symbol_to_sector = download_historical_prices(universe_df)

        # 3. Strict 1-on-1 Sector-Isolated Pairing & Mathematical Cointegration Gate
        survivor_pairs = compute_cointegrated_pairs(
            prices_df,
            symbol_to_sector,
            min_corr=MIN_CORRELATION,
            max_pvalue=MAX_COINT_PVALUE,
        )

        if not survivor_pairs:
            logger.error("Zero pairs survived the correlation and cointegration gates!")
            return 1

        # 4. Export
        csv_path, json_path = export_survivor_pairs(survivor_pairs)

        # 5. Verification Constraints
        assert csv_path.exists() and csv_path.stat().st_size > 0, "CSV export file is missing or empty"
        assert json_path.exists() and json_path.stat().st_size > 0, "JSON export file is missing or empty"

        df_check = pd.read_csv(csv_path)
        assert "cointegration_pvalue" in df_check.columns, "cointegration_pvalue column is missing from CSV!"
        assert (df_check["correlation"] >= MIN_CORRELATION).all(), f"Found pair with correlation < {MIN_CORRELATION}"
        assert (df_check["cointegration_pvalue"] <= MAX_COINT_PVALUE).all(), (
            f"Found pair with cointegration_pvalue > {MAX_COINT_PVALUE}"
        )

        # Sector invariant check
        for p in survivor_pairs:
            assert symbol_to_sector[p["ticker_a"]] == symbol_to_sector[p["ticker_b"]], (
                f"Sector mismatch: {p['ticker_a']} ({symbol_to_sector[p['ticker_a']]}) != "
                f"{p['ticker_b']} ({symbol_to_sector[p['ticker_b']]})"
            )

        logger.info("Verification PASSED: %d elite cointegrated pairs generated.", len(survivor_pairs))
        logger.info("Sample Top Survivor Pairs:")
        for top_pair in survivor_pairs[:10]:
            logger.info("  %s - %s (%s): r=%.4f, p-value=%.4f",
                        top_pair["ticker_a"], top_pair["ticker_b"], top_pair["sector"],
                        top_pair["correlation"], top_pair["cointegration_pvalue"])

        return 0

    except Exception as exc:
        logger.exception("Fatal error in cointegrated pair discovery pipeline: %s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
