"""Shared corporate-earnings blackout calendar for pair strategies."""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Iterable, Mapping, Sequence

import numpy as np
import pandas as pd

from engine.config import DATA_CACHE_DIR
from engine.logging_setup import get_logger

logger = get_logger("earnings_calendar")
RESEARCH_DIR_DEFAULT = DATA_CACHE_DIR / "research"


class EarningsCalendar:
    """Index corporate earnings dates for point-in-time blackout filtering."""

    def __init__(
        self,
        research_dir: Path | str | None = None,
        custom_earnings: Mapping[str, Iterable[str]] | None = None,
    ) -> None:
        self.research_dir = Path(research_dir or RESEARCH_DIR_DEFAULT)
        self.earnings_by_ticker: dict[str, set[str]] = {}
        if custom_earnings:
            for symbol, dates in custom_earnings.items():
                clean_symbol = symbol.strip().upper().replace(".", "-")
                self.earnings_by_ticker[clean_symbol] = {
                    pd.to_datetime(value).strftime("%Y-%m-%d")
                    for value in dates
                }
        else:
            self._load_from_cache()

    def _load_from_cache(self) -> None:
        if not self.research_dir.exists():
            return
        for symbol_dir in self.research_dir.iterdir():
            if not symbol_dir.is_dir():
                continue
            symbol = symbol_dir.name.strip().upper().replace(".", "-")
            for source in symbol_dir.glob("earnings_*.json"):
                try:
                    with source.open("r", encoding="utf-8") as handle:
                        payload = json.load(handle)
                    dates = {
                        str(row["date"])[:10]
                        for row in payload.get("data", [])
                        if row.get("date")
                    }
                    if dates:
                        self.earnings_by_ticker.setdefault(symbol, set()).update(dates)
                except Exception as exc:  # noqa: BLE001 — corrupt cache is skipped
                    logger.debug("Could not load earnings for %s: %s", symbol, exc)

    def is_in_blackout(
        self,
        ticker_a: str,
        ticker_b: str,
        target_date: str | pd.Timestamp | date,
        blackout_days: int = 5,
        trading_calendar: Sequence[pd.Timestamp] | None = None,
    ) -> tuple[bool, str | None]:
        """Return whether either leg reports within the symmetric date window."""
        ta = ticker_a.strip().upper().replace(".", "-")
        tb = ticker_b.strip().upper().replace(".", "-")
        target = pd.to_datetime(target_date).normalize()

        if trading_calendar:
            calendar = [stamp.normalize() for stamp in trading_calendar]
            try:
                position = calendar.index(target)
            except ValueError:
                position = int(np.searchsorted(
                    [stamp.value for stamp in calendar], target.value,
                ))
            start = max(0, position - blackout_days)
            end = min(len(calendar), position + blackout_days + 1)
            window = {
                stamp.strftime("%Y-%m-%d") for stamp in calendar[start:end]
            }
        else:
            business_days = pd.bdate_range(
                target - pd.Timedelta(days=blackout_days * 2),
                target + pd.Timedelta(days=blackout_days * 2),
            )
            position = int(np.searchsorted(
                [stamp.value for stamp in business_days], target.value,
            ))
            start = max(0, position - blackout_days)
            end = min(len(business_days), position + blackout_days + 1)
            window = {
                stamp.strftime("%Y-%m-%d")
                for stamp in business_days[start:end]
            }

        for symbol in (ta, tb):
            overlap = self.earnings_by_ticker.get(symbol, set()).intersection(window)
            if overlap:
                first_hit = sorted(overlap)[0]
                return (
                    True,
                    f"Earnings Blackout: {symbol} reports on {first_hit} "
                    f"(within ±{blackout_days} trading days of "
                    f"{target.strftime('%Y-%m-%d')})",
                )
        return False, None
