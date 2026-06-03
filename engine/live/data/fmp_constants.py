"""FMP /stable/ endpoint paths and field names — validated by
scripts/smoke_fmp_stable.py against a live ticker. Do not hand-edit;
re-run the smoke test if FMP docs change.
"""
from __future__ import annotations

# ---------------------------------------------------------------------------
# Validated endpoint paths (relative to FMP_BASE_URL = .../stable)
# ---------------------------------------------------------------------------

PATH_PROFILE = "/profile"
PATH_INCOME_Q = "/income-statement"
PATH_BALANCE_Q = "/balance-sheet-statement"
PATH_CASHFLOW_Q = "/cash-flow-statement"
PATH_RATIOS_ANNUAL = "/ratios"
PATH_RATIOS_TTM = "/ratios-ttm"
PATH_KEY_METRICS_ANNUAL = "/key-metrics"
PATH_KEY_METRICS_TTM = "/key-metrics-ttm"
PATH_EARNINGS = "/earnings"
PATH_EARNINGS_CALENDAR = "/earnings-calendar"
PATH_ANALYST_ESTIMATES = "/analyst-estimates"
PATH_NEWS_STOCK = "/news/stock"
PATH_GRADES = "/grades"
PATH_SEC_FILINGS = "/sec-filings-search/symbol"
PATH_INSIDER_TRADES = "/insider-trading/search"

# ---------------------------------------------------------------------------
# Validated param-name choices (which key works for ticker selection)
# ---------------------------------------------------------------------------

PARAM_PROFILE = "symbol"
PARAM_INCOME_Q = "symbol"
PARAM_BALANCE_Q = "symbol"
PARAM_CASHFLOW_Q = "symbol"
PARAM_RATIOS_ANNUAL = "symbol"
PARAM_RATIOS_TTM = "symbol"
PARAM_KEY_METRICS_ANNUAL = "symbol"
PARAM_KEY_METRICS_TTM = "symbol"
PARAM_EARNINGS = "symbol"
PARAM_EARNINGS_CALENDAR = "symbol"
PARAM_ANALYST_ESTIMATES = "symbol"
PARAM_NEWS_STOCK = "symbols"
PARAM_GRADES = "symbol"
PARAM_SEC_FILINGS = "symbol"
PARAM_INSIDER_TRADES = "symbol"

# ---------------------------------------------------------------------------
# Preserved-typo fields confirmed present in live responses.
# (None as of NVDA 2026-05-24 — /stable/ has cleaned up the v3-era typos.)
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Plan-tier limitations (FMP Starter — known restrictions)
# ---------------------------------------------------------------------------

# period=quarter is REJECTED (402) on /ratios and /key-metrics under Starter.
# Workaround: use annual + TTM endpoints (-ttm) for the latest snapshot.
RATIOS_PERIOD_FALLBACK = "annual"
KEY_METRICS_PERIOD_FALLBACK = "annual"

# /news/press-releases returns 402 under Starter. Pipeline must handle
# absence — the News Analyst degrades gracefully when this slot is missing.
PATH_PRESS_RELEASES = "/news/press-releases"  # premium-only
PARAM_PRESS_RELEASES = "symbols"
PRESS_RELEASES_AVAILABLE = True   # FMP premium plan unlocks press releases

# /sec-filings-search/symbol REQUIRES from/to date params (not optional).
# Pass ISO YYYY-MM-DD; default window is 60 days back.
SEC_FILINGS_DATE_REQUIRED = True

# ---------------------------------------------------------------------------
# Field-name conventions confirmed by live response
# ---------------------------------------------------------------------------

# Grades: uses 'date' (NOT 'publishedDate' as some docs suggest)
FIELD_GRADES_DATE = "date"

# Insider trading: 'acquisitionOrDisposition' is the CORRECT spelling
# (the v3-era typo 'acquistion' was fixed in /stable/).
FIELD_INSIDER_ACQ_OR_DISP = "acquisitionOrDisposition"

# Income statement: 'filingDate' (single L) — also cleaned up vs v3.
FIELD_INCOME_FILING_DATE = "filingDate"

# TTM endpoints suffix every field with 'TTM': peRatioTTM, roicTTM, etc.
TTM_FIELD_SUFFIX = "TTM"

# ---------------------------------------------------------------------------
# Tier 1 endpoints added in M17 — to verify empirically on this plan
# (revenue segments, earnings call transcripts, analyst price targets,
# institutional ownership).
# ---------------------------------------------------------------------------

PATH_REVENUE_SEGMENT_PRODUCT = "/revenue-product-segmentation"
PATH_REVENUE_SEGMENT_GEO     = "/revenue-geographic-segmentation"
PATH_EARNINGS_TRANSCRIPT     = "/earning-call-transcript"
PATH_PRICE_TARGET_SUMMARY    = "/price-target-summary"
PATH_PRICE_TARGET_NEWS       = "/price-target-news"
PATH_INSTITUTIONAL_HOLDERS   = "/institutional-ownership/positions"

