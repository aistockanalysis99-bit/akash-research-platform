"""Macro context loader — derives a small snapshot from today's morning regime.

This lets the evening PM prompt see "regime is BULL_TRENDING, throttle=full"
without paying for a separate LLM call. If the morning cycle didn't run today,
returns None and the PM proceeds without macro overlay.
"""
from __future__ import annotations

import json
import logging
from datetime import date
from typing import Optional

from .file_store import FileStore
from .schemas import MacroContextSnapshot, MarketRegime

log = logging.getLogger(__name__)


def load_macro_context_for_today() -> Optional[MacroContextSnapshot]:
    """Read today's morning cycle artifacts and build a MacroContextSnapshot.

    Returns None if:
    - morning cycle didn't run today, OR
    - the regime field is missing/malformed
    """
    today = date.today().isoformat()
    fs = FileStore()
    raw_path = fs.morning_folder(today) / "_raw.json"
    if not raw_path.exists():
        log.info("macro_context: no morning cycle today (%s)", today)
        return None

    try:
        raw = json.loads(raw_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        log.warning("macro_context: corrupt morning raw json: %s", e)
        return None

    regime_data = raw.get("regime")
    if not regime_data:
        return None

    try:
        regime = MarketRegime.model_validate(regime_data)
    except Exception as e:  # noqa: BLE001
        log.warning("macro_context: regime didn't validate: %s", e)
        return None

    # Sector tailwinds = top 3 by 20d return; headwinds = bottom 3.
    market = raw.get("market_data") or {}
    sectors_ranked = market.get("sectors_ranked") or []
    tailwinds = [s.get("symbol", "") for s in sectors_ranked[:3] if s.get("symbol")]
    headwinds = [s.get("symbol", "") for s in sectors_ranked[-3:] if s.get("symbol")]

    return MacroContextSnapshot(
        as_of_date=today,
        regime=regime.regime,
        confidence=regime.regime_confidence,
        new_entries_throttle=regime.new_entries_throttle,
        sector_tailwinds=tailwinds,
        sector_headwinds=headwinds,
        summary=regime.key_observation,
    )
