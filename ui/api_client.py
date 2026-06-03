"""HTTP client used by the UI to talk to the FastAPI backend."""
from __future__ import annotations

from typing import Any, Optional

import httpx

from engine.config import API_HOST, API_PORT

API_BASE = f"http://{API_HOST}:{API_PORT}"


class APIClient:
    def __init__(self, base: str = API_BASE) -> None:
        self.base = base.rstrip("/")
        self._client = httpx.Client(timeout=60.0)

    def _get(self, path: str, **params) -> Any:
        r = self._client.get(f"{self.base}{path}", params=params)
        r.raise_for_status()
        return r.json()

    def _post(self, path: str, json: Any = None) -> Any:
        r = self._client.post(f"{self.base}{path}", json=json)
        r.raise_for_status()
        return r.json()

    def _delete(self, path: str) -> Any:
        r = self._client.delete(f"{self.base}{path}")
        r.raise_for_status()
        return r.json()

    # Health
    def health(self) -> dict:
        try:
            return self._get("/health")
        except Exception:
            return {"status": "unreachable"}

    # Universe
    def list_universes(self) -> list[str]:
        return self._get("/universes")

    def get_universe(self, name: str) -> dict:
        return self._get(f"/universe/{name}")

    # Data
    def refresh_data(self, universe: Optional[str], symbols: Optional[list[str]],
                     timeframe: str, years: int, full: bool) -> dict:
        return self._post("/data/refresh", json={
            "universe": universe,
            "symbols": symbols,
            "timeframe": timeframe,
            "years": years,
            "full": full,
        })

    def refresh_status(self, job_id: str) -> dict:
        return self._get(f"/data/refresh/{job_id}")

    def data_status(self) -> list[dict]:
        return self._get("/data/status")

    # Backtest
    def run_backtest(self, payload: dict) -> dict:
        return self._post("/backtest/run", json=payload)

    def get_run(self, run_id: str) -> dict:
        return self._get(f"/backtest/{run_id}")

    def get_progress(self, run_id: str) -> dict:
        return self._get(f"/backtest/{run_id}/progress")

    def get_equity(self, run_id: str) -> list[dict]:
        return self._get(f"/backtest/{run_id}/equity")

    def get_trades(self, run_id: str, **filters) -> list[dict]:
        return self._get(f"/backtest/{run_id}/trades", **filters)

    def get_per_symbol(self, run_id: str) -> list[dict]:
        return self._get(f"/backtest/{run_id}/per-symbol")

    def list_runs(self, limit: int = 200) -> list[dict]:
        return self._get("/runs", limit=limit)

    def delete_run(self, run_id: str) -> dict:
        return self._delete(f"/runs/{run_id}")

    # Params
    def list_params(self) -> list[dict]:
        return self._get("/params")

    def save_params(self, name: str, params: dict) -> dict:
        return self._post("/params/save", json={"name": name, "params": params})

    def get_params(self, name: str) -> dict:
        return self._get(f"/params/{name}")

    def delete_params(self, name: str) -> dict:
        return self._delete(f"/params/{name}")

    # Compare
    def compare(self, run_ids: list[str]) -> dict:
        return self._post("/compare", json={"run_ids": run_ids})

    def trades_csv_url(self, run_id: str) -> str:
        return f"{self.base}/backtest/{run_id}/trades.csv"

    # AI Pipeline
    def ai_analyze(self, symbol: str, source: str = "manual",
                    notes: Optional[str] = None) -> dict:
        return self._post("/ai/analyze", json={
            "symbol": symbol, "source": source, "notes": notes,
        })

    def ai_get_job(self, job_id: str) -> dict:
        return self._get(f"/ai/analyze/{job_id}")

    def ai_list_jobs(self) -> list[dict]:
        return self._get("/ai/jobs")

    def ai_list_decisions(self) -> list[dict]:
        return self._get("/ai/decisions")

    def ai_get_decision(self, symbol: str, date_iso: str) -> dict:
        return self._get(f"/ai/decisions/{symbol}/{date_iso}")

    def ai_get_scorecards(self, symbol: str, date_iso: str) -> list[dict]:
        return self._get(f"/ai/decisions/{symbol}/{date_iso}/scorecards")

    # Morning cycle
    def ai_morning_run(self) -> dict:
        return self._post("/ai/morning/run")

    def ai_morning_jobs(self) -> list[dict]:
        return self._get("/ai/morning/jobs")

    def ai_morning_job(self, job_id: str) -> dict:
        return self._get(f"/ai/morning/jobs/{job_id}")

    def ai_morning_dates(self) -> list[str]:
        return self._get("/ai/morning/dates")

    def ai_morning_files(self, date_iso: str) -> dict:
        return self._get(f"/ai/morning/{date_iso}")

    # Virtual Portfolio
    def portfolio_snapshot(self) -> dict:
        return self._get("/portfolio/snapshot")

    def portfolio_open(self) -> list[dict]:
        return self._get("/portfolio/open")

    def portfolio_closed(self, limit: int = 200) -> list[dict]:
        return self._get("/portfolio/closed", limit=limit)

    def portfolio_today(self) -> list[dict]:
        return self._get("/portfolio/today")

    def portfolio_refresh(self) -> dict:
        return self._post("/portfolio/refresh")

    def portfolio_close(self, position_id: int, reason: str = "manual") -> dict:
        return self._post(f"/portfolio/close/{position_id}", json={"reason": reason})

    def portfolio_close_all(self) -> dict:
        return self._post("/portfolio/close-all")

    # Watchlist (Phase 4)
    def watchlist_list(self) -> list[dict]:
        return self._get("/watchlist")

    def watchlist_add(self, symbol: str, notes: Optional[str] = None) -> dict:
        return self._post("/watchlist", json={"symbol": symbol, "notes": notes})

    def watchlist_remove(self, symbol: str) -> dict:
        return self._delete(f"/watchlist/{symbol}")

    def watchlist_toggle(self, symbol: str, enabled: bool) -> dict:
        return self._post(f"/watchlist/{symbol}/toggle", json={"enabled": enabled})

    # Scheduler (Phase 4)
    def scheduler_status(self) -> dict:
        return self._get("/scheduler/status")

    def scheduler_start(self) -> dict:
        return self._post("/scheduler/start")

    def scheduler_stop(self) -> dict:
        return self._post("/scheduler/stop")

    def scheduler_restart(self) -> dict:
        return self._post("/scheduler/restart")

    def scheduler_run_morning(self) -> dict:
        return self._post("/scheduler/run/morning")

    def scheduler_run_evening(self) -> dict:
        return self._post("/scheduler/run/evening")

    def scheduler_run_weekly(self) -> dict:
        return self._post("/scheduler/run/weekly")

    def scheduler_quant_scan(self) -> list[dict]:
        return self._post("/scheduler/quant-scan")

    # Memory (Phase 4)
    def memory_lessons(self, limit: int = 100) -> list[dict]:
        return self._get("/memory/lessons", limit=limit)

    def memory_pending(self) -> list[dict]:
        return self._get("/memory/pending")

    def memory_reflect(self) -> dict:
        return self._post("/memory/reflect")

    # Weekly (Phase 4)
    def ai_weekly_list(self) -> list[str]:
        return self._get("/ai/weekly")

    def ai_weekly_get(self, date_iso: str) -> dict:
        return self._get(f"/ai/weekly/{date_iso}")

    # Per-stock profiles (M17)
    def profiles_list(self) -> list[dict]:
        return self._get("/profiles")

    def profile_get(self, symbol: str) -> dict:
        return self._get(f"/profiles/{symbol}")

    def profile_get_raw(self, symbol: str) -> dict:
        return self._get(f"/profiles/{symbol}/raw")

    def profile_put_raw(self, symbol: str, content: str) -> dict:
        r = self._client.put(f"{self.base}/profiles/{symbol}/raw",
                              json={"content": content})
        r.raise_for_status()
        return r.json()

    def profile_delete(self, symbol: str) -> dict:
        return self._delete(f"/profiles/{symbol}")

    # Live settings (Phase 4)
    def settings_get(self) -> dict:
        return self._get("/settings")

    def settings_update(self, payload: dict) -> dict:
        return self._post("/settings", json=payload)

    # Telegram (Phase 4)
    def telegram_test(self, text: Optional[str] = None) -> dict:
        return self._post("/telegram/test", json={"text": text} if text else {})

    def telegram_log(self, limit: int = 50) -> list[dict]:
        return self._get("/telegram/log", limit=limit)


api = APIClient()
