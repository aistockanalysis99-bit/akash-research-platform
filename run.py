"""Launcher: starts the FastAPI backend, which also serves the React SPA.

The frontend is the React app in frontend/dist (built with `npm run build`).
FastAPI serves both the JSON API and the SPA on a single port — NiceGUI has
been retired.

Usage:
    python run.py                # start server, open browser
    python run.py --no-browser   # start server only
    python run.py --dev          # reminder: run the Vite dev server separately
"""
from __future__ import annotations

import argparse
import sys
import threading
import time
import webbrowser
from pathlib import Path

# Bootstrap path
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engine.config import API_HOST, API_PORT  # noqa: E402
from engine.db.schema import init_db  # noqa: E402


def serve_api() -> None:
    import uvicorn
    uvicorn.run("api.main:app", host=API_HOST, port=API_PORT, log_level="info", reload=False)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-browser", action="store_true", help="Don't auto-open browser")
    parser.add_argument(
        "--dev",
        action="store_true",
        help="Print a reminder to run the Vite dev server for hot-reload development",
    )
    args = parser.parse_args()

    init_db()

    dist = PROJECT_ROOT / "frontend" / "dist" / "index.html"
    url = f"http://{API_HOST}:{API_PORT}"

    if args.dev:
        print("\n  DEV MODE")
        print("  1. Backend:  python run.py --no-browser   (this serves the API)")
        print("  2. Frontend: cd frontend && npm run dev    (Vite hot-reload on :5173)")
        print("  Open http://localhost:5173 — it proxies /api to the backend.\n")

    if not dist.exists():
        print("\n  ⚠ frontend/dist not found.")
        print("  Build the React app first:  cd frontend && npm run build")
        print("  (Or develop with hot-reload: cd frontend && npm run dev)\n")

    print(f"\n  Akash Research Platform running at {url}\n")

    if not args.no_browser and dist.exists():
        threading.Thread(
            target=lambda: (time.sleep(2.0), webbrowser.open(url)), daemon=True
        ).start()

    try:
        serve_api()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
