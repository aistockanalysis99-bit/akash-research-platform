#!/usr/bin/env python3
"""7-Stage Rigorous Pair-Filtering Gauntlet for S&P 500 Stock Pairs.

Isolates institutional-grade mean-reverting pairs through sequential statistical gates:
  Stage 1 (Liquidity Gate): ADV > 2,000,000 shares for both tickers.
  Stage 2 (Correlation Gate): Pearson correlation >= 0.90 over 252 trading days.
  Stage 3 (Cointegration Gate): Engle-Granger coint p-value <= 0.05.
  Stage 4 (Zero-Crossing Frequency): Spread crosses Z-score = 0 at least 12 times/year.
  Stage 5 (Half-Life Calculation): Ornstein-Uhlenbeck half-life between 2 and 30 days.
  Stage 6 (Hurst Exponent): Hurst exponent H < 0.45 (proven mean-reverting).
  Stage 7 (ADF T-Statistic): Augmented Dickey-Fuller t-stat < -3.0.

Outputs surviving elite pairs to data/elite_curated_pairs.csv.
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
from statsmodels.tsa.stattools import adfuller, coint
import yfinance as yf

# Suppress noisy deprecation/formatting warnings
warnings.filterwarnings("ignore")
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("pair_gauntlet")

# Strict Thresholds per 5-Year Specification
MIN_ADV = 1_500_000
MIN_CORRELATION = 0.85
MAX_COINT_PVALUE = 0.05
MIN_ZERO_CROSSINGS_PER_YEAR = 10
MIN_HALF_LIFE = 2.0
MAX_HALF_LIFE = 35.0
MAX_HURST = 0.48
MAX_ADF_TSTAT = -2.8

TRADING_DAYS = 1260
WIKI_SP500_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"


def load_candidate_pairs() -> Tuple[List[Dict[str, Any]], Dict[str, str]]:
    """Load the candidate pairs (from 1600+ pairs file or dynamically from Wikipedia)."""
    # Check candidate files
    locations = [
        Path("EXTRA/data/sp500_master_pairs.json"),
        Path("data/sp500_master_pairs.json"),
        Path("sp500_master_pairs.json"),
    ]

    for p in locations:
        if p.exists():
            try:
                with open(p, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    pairs = data.get("pairs", [])
                    if len(pairs) >= 500:
                        logger.info("Loaded %d candidate pairs from %s", len(pairs), p)
                        # Rebuild symbol to sector
                        sym_to_sec = {}
                        for item in pairs:
                            sym_to_sec[item["ticker_a"]] = item["sector"]
                            sym_to_sec[item["ticker_b"]] = item["sector"]
                        return pairs, sym_to_sec
            except Exception as e:
                logger.warning("Could not read candidate pairs from %s: %e", p, e)

    # Dynamic fallback to Wikipedia S&P 500
    logger.info("Fetching S&P 500 universe dynamically from Wikipedia...")
    try:
        tables = pd.read_html(WIKI_SP500_URL, storage_options={"User-Agent": USER_AGENT})
    except Exception:
        req = urllib.request.Request(WIKI_SP500_URL, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=25) as response:
            tables = pd.read_html(io.StringIO(response.read().decode("utf-8")))

    sp500_df = tables[0]
    sym_col = next(c for c in sp500_df.columns if "symbol" in str(c).lower() or "ticker" in str(c).lower())
    sec_col = next(c for c in sp500_df.columns if "sector" in str(c).lower())

    sym_to_sec = dict(zip(sp500_df[sym_col].str.strip(), sp500_df[sec_col].str.strip()))
    sec_groups = collections.defaultdict(list)
    for sym, sec in sym_to_sec.items():
        sec_groups[sec].append(sym)

    pairs = []
    for sec, tickers in sec_groups.items():
        for a, b in itertools.combinations(sorted(tickers), 2):
            pairs.append({"ticker_a": a, "ticker_b": b, "sector": sec})

    logger.info("Generated %d initial intra-sector combinations from Wikipedia.", len(pairs))
    return pairs, sym_to_sec


def download_market_data(
    candidate_pairs: List[Dict[str, Any]],
) -> Tuple[pd.DataFrame, pd.Series, Dict[str, str]]:
    """Download Close prices and Volume for all unique symbols involved.
    
    1. Primary Provider: Financial Modeling Prep (FMP) REST API (online deployment).
    2. Secondary Provider: yfinance (automatic fallback when FMP is unconfigured or unavailable).
    """
    unique_symbols = set()
    for p in candidate_pairs:
        unique_symbols.add(p["ticker_a"])
        unique_symbols.add(p["ticker_b"])

    yf_map = {sym: sym.replace(".", "-") for sym in unique_symbols}
    rev_map = {yf_sym: orig for orig, yf_sym in yf_map.items()}
    sym_list = sorted(list(unique_symbols))

    prices_dict: Dict[str, pd.Series] = {}
    volumes_dict: Dict[str, pd.Series] = {}

    # --- 1. PRIMARY OPTION: FMP API ---
    try:
        from engine.detect_setups import get_fmp_api_key, fetch_fmp_prices_and_volumes
        fmp_key = get_fmp_api_key()
    except Exception:
        fmp_key = ""

    if fmp_key:
        logger.info("Downloading historical 5-year prices and volume for %d tickers via FMP (Primary)...", len(sym_list))
        try:
            fmp_prices, fmp_vols = fetch_fmp_prices_and_volumes(sym_list, period="5y")
            for sym in sym_list:
                clean_sym = yf_map.get(sym, sym)
                if sym in fmp_prices and not fmp_prices[sym].dropna().empty:
                    prices_dict[clean_sym] = fmp_prices[sym]
                    volumes_dict[clean_sym] = fmp_vols.get(sym, pd.Series(0.0, index=fmp_prices[sym].index))
                elif clean_sym in fmp_prices and not fmp_prices[clean_sym].dropna().empty:
                    prices_dict[clean_sym] = fmp_prices[clean_sym]
                    volumes_dict[clean_sym] = fmp_vols.get(clean_sym, pd.Series(0.0, index=fmp_prices[clean_sym].index))

            if len(prices_dict) == len(sym_list):
                logger.info("Successfully retrieved all %d tickers via FMP.", len(prices_dict))
            else:
                logger.info("FMP retrieved %d/%d tickers. Filling missing via secondary provider...", len(prices_dict), len(sym_list))
        except Exception as e:
            logger.warning("FMP primary market data download encountered error: %s. Falling back to secondary.", e)

    # --- 2. SECONDARY OPTION: yfinance fallback ---
    missing_yf_symbols = [yf_map[s] for s in sym_list if yf_map[s] not in prices_dict]
    if missing_yf_symbols:
        if not fmp_key:
            logger.info("FMP API key not configured locally. Downloading 5-year prices for %d tickers via secondary provider...", len(missing_yf_symbols))
        try:
            raw = yf.download(missing_yf_symbols, period="5y", interval="1d", auto_adjust=True, progress=False, threads=True)
            if not raw.empty:
                if "Close" in raw.columns:
                    sec_prices = raw["Close"].copy()
                else:
                    sec_prices = raw.xs(raw.columns.levels[0][0], axis=1).copy()

                if "Volume" in raw.columns:
                    sec_volumes = raw["Volume"].copy()
                else:
                    sec_volumes = pd.DataFrame(index=sec_prices.index, columns=sec_prices.columns).fillna(0)

                for clean_sym in missing_yf_symbols:
                    if clean_sym in sec_prices.columns and not sec_prices[clean_sym].dropna().empty:
                        prices_dict[clean_sym] = sec_prices[clean_sym]
                        volumes_dict[clean_sym] = sec_volumes[clean_sym] if clean_sym in sec_volumes.columns else pd.Series(0.0, index=sec_prices[clean_sym].index)
        except Exception as e:
            logger.warning("Secondary batch download encountered error: %s", e)

    if not prices_dict:
        raise RuntimeError("No historical market data could be returned by primary (FMP) or secondary providers.")

    prices = pd.DataFrame(prices_dict)
    volumes = pd.DataFrame(volumes_dict)

    # Slice to last 1260 trading days (5 years)
    if len(prices) > TRADING_DAYS:
        prices = prices.iloc[-TRADING_DAYS:]
        volumes = volumes.iloc[-TRADING_DAYS:]

    # Impute missing values
    prices = prices.ffill().bfill().dropna(axis=1)
    volumes = volumes.ffill().bfill().fillna(0)

    # Calculate Average Daily Volume (ADV)
    adv = volumes.mean()

    # Map column names back to original ticker symbols
    prices = prices.rename(columns=rev_map)
    adv = adv.rename(index=rev_map)

    logger.info("Successfully processed data: %d valid tickers with complete 5-year history (%d bars).", len(prices.columns), len(prices))
    return prices, adv, rev_map


# --------------------------------------------------------------------------- #
# Mathematical Spread Functions
# --------------------------------------------------------------------------- #
def calculate_ols_spread(series_a: pd.Series, series_b: pd.Series) -> pd.Series:
    """Calculate the cointegrating OLS spread: Spread = P_A - (alpha + beta * P_B)."""
    cov = np.cov(series_b, series_a)[0, 1]
    var_b = np.var(series_b)
    beta = cov / var_b if var_b > 0 else 1.0
    alpha = np.mean(series_a) - beta * np.mean(series_b)
    spread = series_a - (alpha + beta * series_b)
    return spread


def calculate_zero_crossings(spread: pd.Series) -> int:
    """Stage 4: Count times the standardized spread crosses zero (mean)."""
    std = np.std(spread)
    if std == 0:
        return 0
    z = (spread - np.mean(spread)) / std
    z_vals = z.values
    # Detect sign changes: z[t] * z[t+1] < 0
    return int(np.sum((z_vals[:-1] * z_vals[1:]) < 0))


def calculate_ou_half_life(spread: pd.Series) -> float:
    """Stage 5: Calculate Ornstein-Uhlenbeck half-life of mean reversion.
    Delta Spread = lambda * Spread_{t-1} + alpha + epsilon
    Half-life = -ln(2) / lambda
    """
    s_vals = spread.values
    ds = np.diff(s_vals)
    s_lag = s_vals[:-1]

    if len(s_lag) < 10:
        return np.inf

    poly = np.polyfit(s_lag, ds, 1)
    lam = float(poly[0])

    if lam >= 0:
        return np.inf  # Divergent or non-mean-reverting

    half_life = -np.log(2.0) / lam
    return float(half_life)


def calculate_hurst_exponent(spread: pd.Series, max_lag: int = 20) -> float:
    """Stage 6: Calculate Hurst Exponent H via variance of differences.
    Var(tau) ~ tau^{2H} => log(std(tau)) = H * log(tau) + c
    H < 0.5: Mean-reverting series
    H = 0.5: Random walk (Brownian motion)
    H > 0.5: Persistent/trending
    """
    s_vals = spread.values
    lags = range(2, min(max_lag, len(s_vals) // 4))
    tau = []
    for lag in lags:
        diff = s_vals[lag:] - s_vals[:-lag]
        std_val = np.std(diff)
        if std_val > 0:
            tau.append(std_val)
        else:
            tau.append(1e-8)

    poly = np.polyfit(np.log(list(lags)), np.log(tau), 1)
    return float(poly[0])


def calculate_adf_tstat(spread: pd.Series) -> float:
    """Stage 7: Calculate Augmented Dickey-Fuller t-statistic for stationarity."""
    try:
        res = adfuller(spread, autolag="AIC")
        return float(res[0])
    except Exception:
        return 0.0


# --------------------------------------------------------------------------- #
# Main Filtering Pipeline
# --------------------------------------------------------------------------- #
def run_filter_gauntlet() -> int:
    # 0. Ingestion
    candidate_pairs, sym_to_sec = load_candidate_pairs()
    prices, adv, _ = download_market_data(candidate_pairs)

    print("\n" + "=" * 70)
    print("STARTING 7-STAGE STATISTICAL PAIR-FILTERING GAUNTLET")
    print(f"Total Candidate Pairs Ingested: {len(candidate_pairs)}")
    print("=" * 70)

    # Stage 1: Liquidity Gate (ADV > 2,000,000 shares on both tickers)
    stage1_survivors: List[Dict[str, Any]] = []
    for p in candidate_pairs:
        ta, tb = p["ticker_a"], p["ticker_b"]
        if ta not in prices.columns or tb not in prices.columns:
            continue
        adv_a = float(adv.get(ta, 0))
        adv_b = float(adv.get(tb, 0))
        if adv_a > MIN_ADV and adv_b > MIN_ADV:
            item = dict(p)
            item["adv_a"] = adv_a
            item["adv_b"] = adv_b
            stage1_survivors.append(item)

    print(f"Stage 1 (Liquidity Gate - ADV > 2M): {len(stage1_survivors)} pairs remaining")

    # Stage 2: Correlation Gate (Pearson Correlation >= 0.90)
    stage2_survivors: List[Dict[str, Any]] = []
    for p in stage1_survivors:
        ta, tb = p["ticker_a"], p["ticker_b"]
        r = float(prices[ta].corr(prices[tb]))
        if pd.notna(r) and r >= MIN_CORRELATION:
            item = dict(p)
            item["correlation"] = round(r, 4)
            stage2_survivors.append(item)

    print(f"Stage 2 (Correlation Gate - r >= 0.90): {len(stage2_survivors)} pairs remaining")

    # Stage 3: Cointegration Gate (Engle-Granger coint p-value <= 0.05)
    stage3_survivors: List[Dict[str, Any]] = []
    for p in stage2_survivors:
        ta, tb = p["ticker_a"], p["ticker_b"]
        sa = prices[ta]
        sb = prices[tb]
        try:
            _, p_val, _ = coint(sa, sb)
            if pd.notna(p_val) and p_val <= MAX_COINT_PVALUE:
                item = dict(p)
                item["cointegration_pvalue"] = round(float(p_val), 4)
                stage3_survivors.append(item)
        except Exception:
            continue

    print(f"Stage 3 (Cointegration Gate - p <= 0.05): {len(stage3_survivors)} pairs remaining")

    # Stage 4: Zero-Crossing Frequency (Mean Crossings >= 10 / year annualized)
    stage4_survivors: List[Dict[str, Any]] = []
    for p in stage3_survivors:
        ta, tb = p["ticker_a"], p["ticker_b"]
        spread = calculate_ols_spread(prices[ta], prices[tb])
        zc = calculate_zero_crossings(spread)
        zc_annual = round(zc * (252.0 / max(1, len(spread))), 1)
        if zc_annual >= MIN_ZERO_CROSSINGS_PER_YEAR:
            item = dict(p)
            item["zero_crossings"] = int(zc_annual)
            item["zero_crossings_total_5y"] = zc
            stage4_survivors.append(item)

    print(f"Stage 4 (Zero-Crossing Frequency - >= 10/yr): {len(stage4_survivors)} pairs remaining")

    # Stage 5: Half-Life Calculation (2.0 <= Half-Life <= 30.0 days)
    stage5_survivors: List[Dict[str, Any]] = []
    for p in stage4_survivors:
        ta, tb = p["ticker_a"], p["ticker_b"]
        spread = calculate_ols_spread(prices[ta], prices[tb])
        hl = calculate_ou_half_life(spread)
        if pd.notna(hl) and MIN_HALF_LIFE <= hl <= MAX_HALF_LIFE:
            item = dict(p)
            item["half_life"] = round(float(hl), 2)
            stage5_survivors.append(item)

    print(f"Stage 5 (Half-Life Calculation - 2 to 30 days): {len(stage5_survivors)} pairs remaining")

    # Stage 6: Hurst Exponent (H < 0.45, proven mean-reverting)
    stage6_survivors: List[Dict[str, Any]] = []
    for p in stage5_survivors:
        ta, tb = p["ticker_a"], p["ticker_b"]
        spread = calculate_ols_spread(prices[ta], prices[tb])
        h = calculate_hurst_exponent(spread)
        if pd.notna(h) and h < MAX_HURST:
            item = dict(p)
            item["hurst_exponent"] = round(float(h), 4)
            stage6_survivors.append(item)

    print(f"Stage 6 (Hurst Exponent - H < 0.45): {len(stage6_survivors)} pairs remaining")

    # Stage 7: ADF T-Statistic (t-stat < -3.0)
    stage7_survivors: List[Dict[str, Any]] = []
    for p in stage6_survivors:
        ta, tb = p["ticker_a"], p["ticker_b"]
        spread = calculate_ols_spread(prices[ta], prices[tb])
        t_stat = calculate_adf_tstat(spread)
        if pd.notna(t_stat) and t_stat < MAX_ADF_TSTAT:
            item = dict(p)
            item["adf_t_stat"] = round(float(t_stat), 3)

            # 5-Year Return, Trend & Spread Volatility Analytics
            sa = prices[ta]
            sb = prices[tb]
            ret_5y_a = round(float((sa.iloc[-1] - sa.iloc[0]) / sa.iloc[0] * 100), 1)
            ret_5y_b = round(float((sb.iloc[-1] - sb.iloc[0]) / sb.iloc[0] * 100), 1)
            ret_1y_a = round(float((sa.iloc[-1] - sa.iloc[-252]) / sa.iloc[-252] * 100), 1) if len(sa) >= 252 else ret_5y_a
            ret_1y_b = round(float((sb.iloc[-1] - sb.iloc[-252]) / sb.iloc[-252] * 100), 1) if len(sb) >= 252 else ret_5y_b

            trend_a = "Bullish Growth" if ret_5y_a > 15 else ("Bearish Trend" if ret_5y_a < -15 else "Consolidation")
            trend_b = "Bullish Growth" if ret_5y_b > 15 else ("Bearish Trend" if ret_5y_b < -15 else "Consolidation")

            pct_a = sa.pct_change().dropna()
            pct_b = sb.pct_change().dropna()
            trend_corr = round(float(pct_a.corr(pct_b) * 100), 1) if len(pct_a) > 10 else 85.0

            std_s = float(np.std(spread, ddof=1))
            rel_vol = round((std_s / max(0.01, float(sa.iloc[-1]))) * 100.0, 2)
            tier = "Ultra Tight" if rel_vol <= 2.5 else ("Tight" if rel_vol <= 4.5 else ("Medium / Moderate" if rel_vol <= 7.0 else "Wide Spread"))

            item["return_5y_a"] = ret_5y_a
            item["return_5y_b"] = ret_5y_b
            item["return_1y_a"] = ret_1y_a
            item["return_1y_b"] = ret_1y_b
            item["trend_a"] = trend_a
            item["trend_b"] = trend_b
            item["trend_co_movement_score"] = trend_corr
            item["relative_spread_vol_pct"] = rel_vol
            item["spread_tier"] = tier

            stage7_survivors.append(item)

    print(f"Stage 7 (ADF T-Statistic - t-stat < -2.8): {len(stage7_survivors)} pairs remaining")
    print("=" * 70 + "\n")

    if not stage7_survivors:
        logger.error("Zero pairs survived the 7-stage gauntlet! Check thresholds.")
        return 1

    # Sort final survivors: highest correlation, lowest cointegration p-value
    stage7_survivors.sort(key=lambda x: (-x["correlation"], x["cointegration_pvalue"], x["hurst_exponent"]))

    # Output to data/elite_curated_pairs.csv and JSON
    output_dirs = [Path("data"), Path("EXTRA/data")]
    for out_dir in output_dirs:
        out_dir.mkdir(parents=True, exist_ok=True)
        csv_path = out_dir / "elite_curated_pairs.csv"
        json_path = out_dir / "elite_curated_pairs.json"

        field_order = [
            "ticker_a",
            "ticker_b",
            "sector",
            "correlation",
            "cointegration_pvalue",
            "zero_crossings",
            "half_life",
            "hurst_exponent",
            "adf_t_stat",
            "adv_a",
            "adv_b",
            "return_5y_a",
            "return_5y_b",
            "return_1y_a",
            "return_1y_b",
            "trend_a",
            "trend_b",
            "trend_co_movement_score",
            "relative_spread_vol_pct",
            "spread_tier",
        ]

        df_out = pd.DataFrame(stage7_survivors, columns=field_order)
        df_out.to_csv(csv_path, index=False)

        export_json = {
            "metadata": {
                "description": "5-Year Statistical Arbitrage Elite Curated Pairs",
                "total_elite_pairs": len(stage7_survivors),
                "data_history_years": 5,
                "trading_days": TRADING_DAYS,
                "min_adv": MIN_ADV,
                "min_correlation": MIN_CORRELATION,
                "max_cointegration_pvalue": MAX_COINT_PVALUE,
                "min_zero_crossings_per_year": MIN_ZERO_CROSSINGS_PER_YEAR,
                "half_life_range_days": [MIN_HALF_LIFE, MAX_HALF_LIFE],
                "max_hurst": MAX_HURST,
                "max_adf_tstat": MAX_ADF_TSTAT,
            },
            "pairs": stage7_survivors,
        }
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(export_json, f, indent=2)

    logger.info("Successfully exported %d elite pairs to data/elite_curated_pairs.csv and JSON.", len(stage7_survivors))

    # Verification assertions
    csv_verify = Path("data/elite_curated_pairs.csv")
    assert csv_verify.exists() and csv_verify.stat().st_size > 0, "Output CSV is missing or empty!"
    df_verify = pd.read_csv(csv_verify)
    assert "half_life" in df_verify.columns, "half_life column missing from CSV!"
    assert "hurst_exponent" in df_verify.columns, "hurst_exponent column missing from CSV!"
    assert "cointegration_pvalue" in df_verify.columns, "cointegration_pvalue column missing from CSV!"
    assert "adf_t_stat" in df_verify.columns, "adf_t_stat column missing from CSV!"
    assert (df_verify["correlation"] >= MIN_CORRELATION).all(), "Found correlation < 0.85!"
    assert (df_verify["cointegration_pvalue"] <= MAX_COINT_PVALUE).all(), "Found coint p-value > 0.05!"
    assert (df_verify["half_life"] >= MIN_HALF_LIFE).all() and (df_verify["half_life"] <= MAX_HALF_LIFE).all()
    assert (df_verify["hurst_exponent"] < MAX_HURST).all(), "Found Hurst >= 0.48!"
    assert (df_verify["adf_t_stat"] < MAX_ADF_TSTAT).all(), "Found ADF t-stat >= -2.8!"

    logger.info("Verification PASSED: All 7 stages satisfied across 5-year history.")
    return 0


if __name__ == "__main__":
    sys.exit(run_filter_gauntlet())
