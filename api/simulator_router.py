from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter, Query
from fastapi.responses import Response

logger = logging.getLogger("simulator_router")
router = APIRouter()

ROOT_DIR = Path(__file__).resolve().parent.parent

# In-memory raw bytes cache for sub-5ms 1Y backtest response
_cached_1y_json_bytes: Optional[bytes] = None
_cached_1y_lock = threading.Lock()


@router.get("/backtest-1y")
def get_backtest_1y(
    refresh: bool = Query(False, description="Force re-computation of 1-year walkforward backtest"),
) -> Response:
    """Retrieve full 1-year historical walkforward backtest results, trade list, and 10/10 metrics."""
    global _cached_1y_json_bytes

    with _cached_1y_lock:
        if not refresh and _cached_1y_json_bytes is not None:
            return Response(content=_cached_1y_json_bytes, media_type="application/json")

        cache_file = ROOT_DIR / "data" / "backtest_1y_results.json"
        if cache_file.exists():
            try:
                _cached_1y_json_bytes = cache_file.read_bytes()
                return Response(content=_cached_1y_json_bytes, media_type="application/json")
            except Exception as e:
                logger.warning(f"Failed to load cached 1-year backtest bytes: {e}")

        # Fallback: run script if available
        try:
            from scripts.run_1y_backtest import run_1y_walkforward_backtest

            result = run_1y_walkforward_backtest()
            _cached_1y_json_bytes = json.dumps(result).encode("utf-8")
            return Response(content=_cached_1y_json_bytes, media_type="application/json")
        except Exception as e:
            logger.error(f"Failed to compute 1-year backtest: {e}")
            return Response(
                content=json.dumps({"error": "1-year backtest data not available"}).encode("utf-8"),
                status_code=500,
                media_type="application/json",
            )
