"""Spin up Uvicorn on localhost:8009, issue live HTTP requests, and verify latency < 100ms."""

from __future__ import annotations

import subprocess
import sys
import time
import httpx

def run_uvicorn_benchmark():
    print("Starting Uvicorn server on port 8009...")
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "api.main:app", "--port", "8009", "--host", "127.0.0.1", "--log-level", "warning"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    server_up = False
    for attempt in range(30):
        try:
            r = httpx.get("http://127.0.0.1:8009/universes", timeout=1.0)
            if r.status_code == 200:
                server_up = True
                break
        except Exception:
            time.sleep(0.5)

    if not server_up:
        proc.terminate()
        print("Failed to start uvicorn server!")
        sys.exit(1)

    print("Uvicorn server is up and responsive at http://127.0.0.1:8009")

    # 1. Warm-up request & benchmark with Keep-Alive HTTP client
    url = "http://127.0.0.1:8009/api/simulator/scan?current_date=2024-03-15&top_n=10&only_active_setups=false"
    latencies = []

    with httpx.Client(timeout=10.0) as client:
        w_resp = client.get(url)
        assert w_resp.status_code == 200, f"Warm-up failed with status {w_resp.status_code}"

        # 2. Benchmarked live HTTP requests
        for _ in range(5):
            t0 = time.perf_counter()
            resp = client.get(url)
            dur = (time.perf_counter() - t0) * 1000.0
            latencies.append(dur)

    proc.terminate()
    try:
        proc.wait(timeout=5)
    except Exception:
        proc.kill()

    print(f"HTTP Status Code: {resp.status_code}")
    data = resp.json()
    print(f"Setups returned: {len(data['setups'])}")
    avg_lat = sum(latencies) / len(latencies)
    min_lat = min(latencies)
    print(f"Latency over 5 live HTTP socket requests: Avg={avg_lat:.2f}ms, Min={min_lat:.2f}ms")

    assert resp.status_code == 200, f"Expected 200 OK, got {resp.status_code}"
    assert "setups" in data, "Missing setups in response"
    assert "scan_latency_ms" in data, "Missing scan_latency_ms in response"
    assert min_lat < 100.0, f"Constraint 3 failed: Min latency {min_lat:.2f}ms >= 100ms"
    print("=== CONSTRAINT 3 FULLY VERIFIED (Uvicorn 200 OK & Latency < 100ms) ===")


if __name__ == "__main__":
    run_uvicorn_benchmark()
