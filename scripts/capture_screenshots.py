"""Capture screenshots of all UI pages for documentation.

Assumes the server is running at http://127.0.0.1:8080.
"""
from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

SCREENSHOTS_DIR = PROJECT_ROOT / "docs" / "screenshots"
SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)


async def capture() -> None:
    from playwright.async_api import async_playwright

    # Get the latest run ID for the run-detail screenshot
    import sqlite3
    conn = sqlite3.connect(PROJECT_ROOT / "runs.sqlite")
    row = conn.execute(
        "SELECT id FROM runs WHERE status='done' ORDER BY started_at DESC LIMIT 1"
    ).fetchone()
    conn.close()
    latest_run = row[0] if row else None

    pages = [
        ("01_new_backtest", "/"),
        ("02_runs_list", "/runs"),
        ("03_data_cache", "/data"),
        ("04_params", "/params"),
    ]
    if latest_run:
        pages.append((f"05_run_detail", f"/runs/{latest_run}"))

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1600, "height": 1000})
        page = await context.new_page()

        for name, url_path in pages:
            full_url = f"http://127.0.0.1:8080{url_path}"
            print(f"  Capturing {name}: {full_url}")
            try:
                await page.goto(full_url, wait_until="networkidle", timeout=30000)
                await page.wait_for_timeout(2500)  # let charts render
                out = SCREENSHOTS_DIR / f"{name}.png"
                await page.screenshot(path=str(out), full_page=True)
                print(f"    -> {out.name} ({out.stat().st_size} bytes)")
            except Exception as e:
                print(f"    FAILED: {e}")

        # Extra: tab-by-tab screenshots of run detail
        if latest_run:
            tab_url = f"http://127.0.0.1:8080/runs/{latest_run}"
            await page.goto(tab_url, wait_until="networkidle", timeout=30000)
            await page.wait_for_timeout(3000)
            for tab_name, tab_label in [
                ("06_run_equity", "Equity & Drawdown"),
                ("07_run_returns", "Returns"),
                ("08_run_trades", "Trades"),
                ("09_run_per_symbol", "Per-Symbol"),
                ("10_run_diagnostics", "Diagnostics"),
            ]:
                try:
                    # Click the tab by visible text
                    await page.locator(f'div.q-tab__label:has-text("{tab_label}")').first.click()
                    await page.wait_for_timeout(2000)
                    out = SCREENSHOTS_DIR / f"{tab_name}.png"
                    await page.screenshot(path=str(out), full_page=True)
                    print(f"    -> {out.name} ({out.stat().st_size} bytes)")
                except Exception as e:
                    print(f"    {tab_name} FAILED: {e}")

        await browser.close()


if __name__ == "__main__":
    asyncio.run(capture())
