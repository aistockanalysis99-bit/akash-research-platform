#!/usr/bin/env python3
"""5-Year Historical Market Data Harvester & Offline Parquet Engine.

Harvests, aligns, sanitizes, and pre-caches 5 full calendar years of daily
adjusted OHLCV data for all cointegrated universe and elite pairs.

Key Guarantees:
  1. Crash Resilience: Batching, backoff, and isolated fallback handling.
  2. Zero NaNs & Mathematical Integrity: Elimination of lookahead/flatline bias.
  3. Cointegrated Pair Audit: Tracks intact pairs vs. broken pairs.
  4. High-Performance Parquet Storage: Read latency < 150ms.

Outputs:
  - data_cache/universe_5y_daily.parquet (Compressed, microsecond slicing)
  - data_cache/universe_meta.json (Schema metadata, date ranges, pair survival audit)
"""

from __future__ import annotations

import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

# Ensure project root is in sys.path for direct script execution
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import pandas as pd
import yfinance as yf

# Centralized imports from codebase
from engine.config import DATA_CACHE_DIR, PROJECT_ROOT
from engine.logging_setup import get_logger

logger = get_logger("harvest_5y_universe")

# Storage paths
CACHE_DIR = DATA_CACHE_DIR
CACHE_DIR.mkdir(parents=True, exist_ok=True)
PARQUET_FILE = CACHE_DIR / "universe_5y_daily.parquet"
META_FILE = CACHE_DIR / "universe_meta.json"

MASTER_PAIRS_FILE = PROJECT_ROOT / "data" / "sp500_master_pairs.json"
ELITE_PAIRS_FILE = PROJECT_ROOT / "data" / "elite_curated_pairs.json"

# Quality & Benchmark Thresholds
MAX_ALLOWED_MISSING_PCT = 0.05  # Maximum 5% missing bars across 5 years
MIN_REQUIRED_BARS = 1200        # Minimum trading sessions (~4.8 years)
BENCHMARK_TARGET_MS = 150.0     # Maximum allowed Parquet read latency (ms)
INTER_BATCH_SLEEP_SEC = 1.0     # Pacing between yfinance batch requests


def normalize_ticker(ticker: str) -> str:
    """Standardize ticker symbols for Yahoo Finance (e.g. BRK.B -> BRK-B)."""
    return str(ticker).strip().upper().replace(".", "-")


def load_universe_pairs_and_tickers() -> Tuple[List[str], List[Dict[str, Any]]]:
    """Extract deduplicated list of tickers and structured pairs from JSON definitions."""
    tickers: Set[str] = set()
    pairs: List[Dict[str, Any]] = []
    seen_pair_keys: Set[str] = set()

    files_to_check = [
        (MASTER_PAIRS_FILE, "master"),
        (ELITE_PAIRS_FILE, "elite"),
        (PROJECT_ROOT / "sp500_master_pairs.json", "master"),
        (PROJECT_ROOT / "elite_curated_pairs.json", "elite"),
    ]

    found_files = 0
    for path, source_type in files_to_check:
        if path.exists():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    payload = json.load(f)
                raw_pairs = payload.get("pairs", [])
                for p in raw_pairs:
                    ta = normalize_ticker(p.get("ticker_a", ""))
                    tb = normalize_ticker(p.get("ticker_b", ""))
                    if ta and tb and len(ta) <= 6 and len(tb) <= 6:
                        tickers.add(ta)
                        tickers.add(tb)
                        pair_key = f"{ta}_{tb}"
                        if pair_key not in seen_pair_keys:
                            seen_pair_keys.add(pair_key)
                            pair_copy = dict(p)
                            pair_copy["ticker_a"] = ta
                            pair_copy["ticker_b"] = tb
                            pair_copy["source"] = source_type
                            pairs.append(pair_copy)
                found_files += 1
            except Exception as e:
                logger.warning(f"Could not parse pairs from {path}: {e}")

    if not tickers:
        logger.warning("No tickers found from JSON files. Using default liquid pair tickers.")
        tickers = {"AAPL", "MS", "RF", "ADI", "KLAC", "JPM", "BAC", "NVDA", "AMD"}

    ticker_list = sorted(list(tickers))
    logger.info(
        f"Loaded {len(ticker_list)} unique universe tickers and {len(pairs)} pairs "
        f"from {found_files} pair definition files."
    )
    return ticker_list, pairs


def download_batch_yfinance(
    batch: List[str],
    period: str = "5y",
    max_retries: int = 3,
) -> Optional[pd.DataFrame]:
    """Download OHLCV data for a batch of tickers using yfinance with retry backoff."""
    for attempt in range(1, max_retries + 1):
        try:
            df = yf.download(
                tickers=batch,
                period=period,
                auto_adjust=False,
                progress=False,
                threads=True,
                timeout=15,
            )
            if df is not None and not df.empty:
                return df
        except Exception as e:
            logger.warning(
                f"Batch download attempt {attempt}/{max_retries} failed for {len(batch)} tickers ({e})."
            )
            time.sleep(1.5 * attempt)

    # Fallback: Download symbol by symbol with isolated exception handling
    logger.info(f"Executing symbol-by-symbol fallback for batch of {len(batch)} tickers...")
    individual_dfs: List[pd.DataFrame] = []
    for sym in batch:
        for sym_attempt in range(1, 3):
            try:
                sdf = yf.download(
                    tickers=sym,
                    period=period,
                    auto_adjust=False,
                    progress=False,
                    threads=False,
                    timeout=10,
                )
                if sdf is not None and not sdf.empty:
                    if not isinstance(sdf.columns, pd.MultiIndex):
                        sdf.columns = pd.MultiIndex.from_product([sdf.columns, [sym]])
                    individual_dfs.append(sdf)
                    break
            except Exception as sym_err:
                logger.debug(f"Attempt {sym_attempt} failed for {sym}: {sym_err}")
                time.sleep(0.5)

    if individual_dfs:
        try:
            return pd.concat(individual_dfs, axis=1)
        except Exception as concat_err:
            logger.error(f"Failed to concatenate fallback ticker frames: {concat_err}")

    return None


def download_universe_data(
    tickers: List[str],
    period: str = "5y",
    batch_size: int = 30,
) -> pd.DataFrame:
    """Download complete 5-year OHLCV dataset across all universe tickers with pacing."""
    logger.info(f"Starting 5-year data harvest for {len(tickers)} tickers (batch size: {batch_size})...")
    batch_results: List[pd.DataFrame] = []
    total_batches = (len(tickers) + batch_size - 1) // batch_size

    for i in range(0, len(tickers), batch_size):
        batch = tickers[i : i + batch_size]
        batch_idx = (i // batch_size) + 1
        logger.info(f"Downloading batch {batch_idx}/{total_batches} ({len(batch)} tickers: {batch[0]}..{batch[-1]})...")
        b_df = download_batch_yfinance(batch, period=period)
        if b_df is not None and not b_df.empty:
            batch_results.append(b_df)
        else:
            logger.warning(f"Batch {batch_idx} produced no data. Continuing with next batch.")
        
        # Pacing between batches to protect against Yahoo Finance HTTP 429 throttling
        if i + batch_size < len(tickers):
            time.sleep(INTER_BATCH_SLEEP_SEC)

    if not batch_results:
        raise RuntimeError("Fatal: Failed to retrieve market data for all universe tickers.")

    # Combine all batches horizontally
    logger.info("Assembling multi-batch DataFrame...")
    full_df = pd.concat(batch_results, axis=1)

    # Deduplicate columns if any symbol was fetched twice
    full_df = full_df.loc[:, ~full_df.columns.duplicated()]
    logger.info(f"Assembled raw universe shape: {full_df.shape} (bars: {len(full_df)})")
    return full_df


def sanitize_and_align_universe(
    df: pd.DataFrame,
    all_requested_tickers: List[str],
    max_missing_pct: float = MAX_ALLOWED_MISSING_PCT,
    min_required_bars: int = MIN_REQUIRED_BARS,
) -> Tuple[pd.DataFrame, List[str], List[str]]:
    """Strictly sanitize market data:
    1. Align all series to chronological daily trading timestamps.
    2. Exclude incomplete intraday current-day bars during market hours.
    3. Drop tickers with late inception / IPO dates to eliminate flatline bfill bias.
    4. Apply bounded forward fill (max 5 days) for minor exchange gaps.
    5. Invariant checking: Price positivity, High >= Low, and zero NaNs across ALL fields.
    """
    logger.info("Starting rigorous data sanitization & calendar alignment...")

    # Ensure index is timezone-naive DatetimeIndex sorted chronologically
    df.index = pd.to_datetime(df.index)
    if df.index.tz is not None:
        df.index = df.index.tz_localize(None)
    df = df.sort_index()

    # Drop incomplete intraday bar if harvester is run during market trading hours
    today_date = pd.Timestamp.now().floor("D")
    if len(df) > 0 and df.index[-1] == today_date:
        logger.info(f"Trimming partial intraday bar from today ({today_date.date()}).")
        df = df.iloc[:-1]

    # Available fields
    available_fields = df.columns.get_level_values(0).unique().tolist()
    primary_close_col = "Adj Close" if "Adj Close" in available_fields else "Close"
    logger.info(f"Primary closing price metric for pairs: '{primary_close_col}'")

    close_matrix = df[primary_close_col]
    total_bars = len(df)
    dataset_start_date = df.index[0]

    valid_tickers: List[str] = []
    dropped_tickers: List[str] = []

    for sym in all_requested_tickers:
        if sym not in close_matrix.columns:
            dropped_tickers.append(sym)
            logger.warning(f"Ticker '{sym}' was not returned by provider (dropped).")
            continue

        series = close_matrix[sym]
        first_valid = series.first_valid_index()

        # Check 1: Late Inception / IPO Check
        # Reject tickers that began trading > 14 days after dataset start
        if first_valid is None or (first_valid - dataset_start_date).days > 14:
            dropped_tickers.append(sym)
            first_valid_str = first_valid.date() if first_valid is not None else "None"
            logger.warning(
                f"Ticker '{sym}' inception late ({first_valid_str} vs start {dataset_start_date.date()}). "
                "Dropped to prevent flatline bfill lookahead bias."
            )
            continue

        valid_count = series.dropna().count()
        missing_count = total_bars - valid_count
        missing_pct = missing_count / max(1, total_bars)

        # Check 2: Minimum history & max missing threshold
        if missing_pct > max_missing_pct or valid_count < min_required_bars:
            dropped_tickers.append(sym)
            logger.warning(
                f"Ticker '{sym}' has structurally insufficient bars "
                f"({valid_count}/{total_bars} bars, {missing_pct*100:.1f}% missing). Dropped."
            )
        else:
            valid_tickers.append(sym)

    logger.info(
        f"Sanitization Audit: {len(valid_tickers)} valid tickers retained, "
        f"{len(dropped_tickers)} tickers dropped."
    )

    if not valid_tickers:
        raise RuntimeError("No tickers passed the quality sanitization threshold.")

    # Slice DataFrame to keep only valid tickers
    sanitized_df = df.loc[:, (slice(None), valid_tickers)].copy()

    # Bounded filling to prevent synthetic data fabrication:
    # 1. Forward-fill up to 5 days (covers multi-day bank holidays or minor exchange delays)
    # 2. Backward-fill up to 2 days maximum ONLY for initial calendar offset
    # 3. Fill remaining Volume NaNs with 0
    clean_field_dfs = {}
    for field in available_fields:
        field_slice = sanitized_df[field].copy()
        if field == "Volume":
            field_slice = field_slice.ffill(limit=5).fillna(0)
        else:
            field_slice = field_slice.ffill(limit=5).bfill(limit=2)
        clean_field_dfs[field] = field_slice

    sanitized_df = pd.concat(clean_field_dfs, axis=1)

    # Re-verify and drop any tickers that still contain ANY NaNs after bounded filling
    residual_nans_by_col = sanitized_df.isna().sum()
    tickers_with_nans = set()
    for (col_field, col_ticker), count in residual_nans_by_col.items():
        if count > 0:
            tickers_with_nans.add(col_ticker)

    if tickers_with_nans:
        logger.warning(f"Dropping {len(tickers_with_nans)} tickers with residual unfillable gaps: {tickers_with_nans}")
        valid_tickers = [t for t in valid_tickers if t not in tickers_with_nans]
        dropped_tickers.extend(sorted(list(tickers_with_nans)))
        sanitized_df = sanitized_df.loc[:, (slice(None), valid_tickers)].copy()

    # Constraint 2 Verification: Zero NaNs across ALL OHLCV fields
    total_nan_count = sanitized_df.isna().sum().sum()
    if total_nan_count > 0:
        raise ValueError(f"Constraint Violation: Found {total_nan_count} residual NaN values across universe dataset.")

    # Invariant Verification: Price Positivity & High >= Low
    for p_col in ["Adj Close", "Close", "High", "Low", "Open"]:
        if p_col in available_fields:
            if (sanitized_df[p_col] <= 0).any().any():
                raise ValueError(f"Constraint Violation: Non-positive price detected in '{p_col}'.")

    if "High" in available_fields and "Low" in available_fields:
        hl_diff = sanitized_df["High"] - sanitized_df["Low"]
        if (hl_diff < -1e-4).any().any():
            raise ValueError("Constraint Violation: High price is less than Low price in market data.")

    logger.info(
        f"Quality Gate PASSED: 0 NaNs across all {sanitized_df.shape[1]} columns. "
        f"Price invariants fully verified for {len(valid_tickers)} tickers."
    )
    return sanitized_df, valid_tickers, dropped_tickers


def audit_pair_integrity(
    pairs: List[Dict[str, Any]],
    valid_tickers: List[str],
    dropped_tickers: List[str],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Audit cointegrated pairs against retained tickers to detect broken pairs."""
    valid_set = set(valid_tickers)
    intact_pairs: List[Dict[str, Any]] = []
    broken_pairs: List[Dict[str, Any]] = []

    for p in pairs:
        ta = p["ticker_a"]
        tb = p["ticker_b"]
        pair_name = f"{ta}/{tb}"
        pair_record = dict(p)
        pair_record["pair_name"] = pair_name

        if ta in valid_set and tb in valid_set:
            intact_pairs.append(pair_record)
        else:
            reasons = []
            if ta not in valid_set:
                reasons.append(f"{ta} dropped")
            if tb not in valid_set:
                reasons.append(f"{tb} dropped")
            pair_record["broken_reason"] = ", ".join(reasons)
            broken_pairs.append(pair_record)

    logger.info(
        f"Pair Survival Audit: {len(intact_pairs)} intact pairs available for simulation; "
        f"{len(broken_pairs)} broken pairs excluded."
    )
    return intact_pairs, broken_pairs


def save_parquet_and_metadata(
    df: pd.DataFrame,
    valid_tickers: List[str],
    dropped_tickers: List[str],
    intact_pairs: List[Dict[str, Any]],
    broken_pairs: List[Dict[str, Any]],
) -> Tuple[Path, Path, float]:
    """Persist sanitized DataFrame to Parquet and output quality metadata JSON."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Save optimized Parquet file with Snappy compression
    logger.info(f"Saving Parquet cache to: {PARQUET_FILE}")
    df.to_parquet(PARQUET_FILE, engine="pyarrow", compression="snappy")
    file_size_bytes = PARQUET_FILE.stat().st_size
    file_size_mb = file_size_bytes / (1024 * 1024)
    logger.info(f"Parquet file written successfully ({file_size_mb:.2f} MB, {file_size_bytes:,} bytes).")

    # 2. Benchmark loading speed (Constraint 3)
    t0 = time.perf_counter()
    _ = pd.read_parquet(PARQUET_FILE)
    load_duration_ms = (time.perf_counter() - t0) * 1000.0

    benchmark_passed = load_duration_ms < BENCHMARK_TARGET_MS
    logger.info(
        f"[BENCHMARK] Loaded universe parquet into pandas in {load_duration_ms:.2f} ms "
        f"(Target: < {BENCHMARK_TARGET_MS} ms -> {'PASSED' if benchmark_passed else 'FAILED'})"
    )

    # 3. Create metadata header with pair audit and storage metrics
    start_date = df.index[0].strftime("%Y-%m-%d")
    end_date = df.index[-1].strftime("%Y-%m-%d")
    relative_parquet = PARQUET_FILE.relative_to(PROJECT_ROOT).as_posix()

    metadata: Dict[str, Any] = {
        "dataset_name": "5-Year Daily OHLCV Universe Dataset",
        "description": "Sanitized historical market data for cointegrated statistical arbitrage pairs.",
        "harvested_at": datetime.now(timezone.utc).isoformat(),
        "date_range": {
            "start_date": start_date,
            "end_date": end_date,
            "trading_days": len(df),
        },
        "ticker_metrics": {
            "total_requested": len(valid_tickers) + len(dropped_tickers),
            "retained_valid_tickers": len(valid_tickers),
            "dropped_incomplete_tickers": len(dropped_tickers),
            "valid_tickers": valid_tickers,
            "dropped_tickers": dropped_tickers,
        },
        "pair_metrics": {
            "total_pairs_defined": len(intact_pairs) + len(broken_pairs),
            "intact_pairs_count": len(intact_pairs),
            "broken_pairs_count": len(broken_pairs),
            "intact_pairs": [p["pair_name"] for p in intact_pairs],
            "broken_pairs": [
                {"pair": p["pair_name"], "reason": p.get("broken_reason", "incomplete legs")}
                for p in broken_pairs
            ],
        },
        "storage": {
            "parquet_path": relative_parquet,
            "file_size_bytes": file_size_bytes,
            "file_size_mb": round(file_size_mb, 2),
            "compression": "snappy",
            "load_time_ms": round(load_duration_ms, 2),
            "benchmark_target_ms": BENCHMARK_TARGET_MS,
            "benchmark_passed": benchmark_passed,
        },
        "schema": {
            "fields": df.columns.levels[0].tolist(),
            "total_columns": len(df.columns),
            "nan_count_total": int(df.isna().sum().sum()),
            "nan_count_adj_close": int(df["Adj Close"].isna().sum().sum()) if "Adj Close" in df.columns else 0,
        },
    }

    with open(META_FILE, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)
    logger.info(f"Metadata written to: {META_FILE}")

    return PARQUET_FILE, META_FILE, load_duration_ms


def harvest_5y_universe() -> Dict[str, Any]:
    """Execute complete end-to-end 5-year data harvesting pipeline."""
    start_time = time.time()
    logger.info("================================================================================")
    logger.info("Starting Phase 1: 5-Year Pair Universe Data Harvesting & Parquet Caching")
    logger.info("================================================================================")

    # Step 1: Extract all universe tickers and pairs
    tickers, pairs = load_universe_pairs_and_tickers()

    # Step 2: Download 5-year OHLCV market data
    raw_df = download_universe_data(tickers, period="5y", batch_size=30)

    # Step 3: Sanitize and align to trading calendar with bounded filling
    sanitized_df, valid_tickers, dropped_tickers = sanitize_and_align_universe(raw_df, tickers)

    # Step 4: Audit pair integrity
    intact_pairs, broken_pairs = audit_pair_integrity(pairs, valid_tickers, dropped_tickers)

    # Step 5: Persist Parquet and generate metadata
    parquet_path, meta_path, load_ms = save_parquet_and_metadata(
        sanitized_df, valid_tickers, dropped_tickers, intact_pairs, broken_pairs
    )

    total_duration = time.time() - start_time
    logger.info("================================================================================")
    logger.info(f"Phase 1 Harvesting COMPLETE in {total_duration:.1f}s.")
    logger.info(f"Valid Tickers: {len(valid_tickers)} | Dropped: {len(dropped_tickers)}")
    logger.info(f"Intact Pairs: {len(intact_pairs)} | Broken: {len(broken_pairs)}")
    logger.info(f"Date Range: {sanitized_df.index[0].date()} to {sanitized_df.index[-1].date()} ({len(sanitized_df)} days)")
    logger.info(f"Parquet File: {parquet_path} ({parquet_path.stat().st_size / (1024*1024):.2f} MB)")
    logger.info(f"Pandas Load Latency: {load_ms:.2f} ms")
    logger.info("================================================================================")

    return {
        "status": "success",
        "parquet_file": str(parquet_path),
        "metadata_file": str(meta_path),
        "valid_tickers": len(valid_tickers),
        "dropped_tickers": len(dropped_tickers),
        "intact_pairs": len(intact_pairs),
        "broken_pairs": len(broken_pairs),
        "trading_days": len(sanitized_df),
        "load_time_ms": load_ms,
    }


if __name__ == "__main__":
    try:
        harvest_5y_universe()
        sys.exit(0)
    except Exception as exc:
        logger.exception(f"Harvest pipeline failed: {exc}")
        sys.exit(1)
