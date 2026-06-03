"""Hard-coded ticker universes. Single source of truth.

S&P 100 list verified 2026-04-30 against major index providers.
If membership changes materially, regenerate this list.
"""
from __future__ import annotations

# S&P 100 tickers (alphabetical), verified 2026-04-30
SP100: list[str] = [
    "AAPL", "ABBV", "ABT", "ACN", "ADBE", "AIG", "AMD", "AMGN", "AMT", "AMZN",
    "AVGO", "AXP", "BA", "BAC", "BK", "BKNG", "BLK", "BMY", "BRK.B", "C",
    "CAT", "CHTR", "CL", "CMCSA", "COF", "COP", "COST", "CRM", "CSCO", "CVS",
    "CVX", "DE", "DHR", "DIS", "DUK", "EMR", "F", "FDX", "GD", "GE",
    "GILD", "GM", "GOOG", "GOOGL", "GS", "HD", "HON", "IBM", "INTC", "INTU",
    "ISRG", "JNJ", "JPM", "KHC", "KO", "LIN", "LLY", "LMT", "LOW", "MA",
    "MCD", "MDLZ", "MDT", "MET", "META", "MMM", "MO", "MRK", "MS", "MSFT",
    "NEE", "NFLX", "NKE", "NVDA", "ORCL", "PEP", "PFE", "PG", "PM", "PYPL",
    "QCOM", "RTX", "SBUX", "SCHW", "SO", "SPG", "T", "TGT", "TMO", "TMUS",
    "TSLA", "TXN", "UNH", "UNP", "UPS", "USB", "V", "VZ", "WFC", "WMT",
]

# Smoke test universe — small but diverse
SMOKE_TEST: list[str] = ["SPY", "AAPL", "MSFT", "GOOGL", "NVDA"]


def get_universe(name: str = "sp100") -> list[str]:
    """Return ticker list for a named universe."""
    name = name.lower()
    if name == "sp100":
        return list(SP100)
    if name == "smoke":
        return list(SMOKE_TEST)
    raise ValueError(f"Unknown universe: {name}. Available: sp100, smoke.")


def list_universes() -> list[str]:
    return ["sp100", "smoke"]
