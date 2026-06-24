"""OpenRouter client — one API key, many open/closed models.

Used by the Model Lab "Compare Mode" harness to run the SAME stock analysis
through several models (DeepSeek-R1, GLM-5.2, Qwen, Claude…) and compare them
side by side — BEFORE committing to local hardware.

OpenAI-compatible chat endpoint. Captures cost + latency per call so the
comparison shows what each model would cost.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from typing import Any, Optional

import httpx

from ...config import OPENROUTER_API_KEY

log = logging.getLogger(__name__)

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


class OpenRouterError(RuntimeError):
    pass


class OpenRouterClient:
    """Thin async wrapper around OpenRouter's chat completions."""

    def __init__(self, api_key: Optional[str] = None) -> None:
        self.api_key = api_key or OPENROUTER_API_KEY
        if not self.api_key:
            raise OpenRouterError("OPENROUTER_API_KEY is not set.")

    async def complete(
        self,
        model: str,
        prompt: str,
        system: Optional[str] = None,
        temperature: float = 0.2,
        max_tokens: int = 4000,
        max_retries: int = 4,
    ) -> dict[str, Any]:
        """Call one model. Returns {text, cost_usd, latency_s, tokens, error}."""
        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "X-Title": "Akash Model Lab",
        }
        body = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        started = time.monotonic()
        last_err: Optional[str] = None
        for attempt in range(max_retries):
            try:
                async with httpx.AsyncClient(timeout=180.0) as client:
                    r = await client.post(OPENROUTER_URL, headers=headers, json=body)
                if r.status_code == 200:
                    j = r.json()
                    choice = (j.get("choices") or [{}])[0]
                    text = (choice.get("message") or {}).get("content") or ""
                    usage = j.get("usage") or {}
                    return {
                        "text": text,
                        "cost_usd": float(usage.get("cost") or 0.0),
                        "latency_s": round(time.monotonic() - started, 1),
                        "tokens": usage.get("total_tokens"),
                        "error": None,
                    }
                # Transient → retry; otherwise fail
                last_err = f"HTTP {r.status_code}: {r.text[:200]}"
                if r.status_code not in (408, 429, 500, 502, 503, 504) or attempt == max_retries - 1:
                    break
            except Exception as e:  # noqa: BLE001
                last_err = str(e)[:200]
                if attempt == max_retries - 1:
                    break
            await asyncio.sleep(min(20.0, 2.0 * (2 ** attempt)))

        return {
            "text": "",
            "cost_usd": 0.0,
            "latency_s": round(time.monotonic() - started, 1),
            "tokens": None,
            "error": last_err or "unknown error",
        }


def extract_json(text: str) -> Optional[dict]:
    """Pull the first JSON object out of a model response.

    Models (especially reasoning ones) often wrap JSON in prose or ```json
    fences, or emit <think> blocks first. Be forgiving.
    """
    if not text:
        return None
    # Strip reasoning/think blocks
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    # Prefer a fenced ```json block
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    candidate = fence.group(1) if fence else None
    if candidate is None:
        # Else the first {...} that spans to the last }
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            candidate = text[start : end + 1]
    if not candidate:
        return None
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        return None
