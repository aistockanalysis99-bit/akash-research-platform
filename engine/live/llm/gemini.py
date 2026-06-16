"""Gemini Pro / Flash async client with Pydantic structured output.

Built on google-genai's unified SDK (the post-2025 client; the old
google-generativeai package is deprecated).

Two model tiers used by the pipeline:
    GeminiPro    — analyst-tier reasoning (Fundamental, News, Macro, Position Monitor)
    GeminiFlash  — triage / cheap tasks (Pre-Filter, Tech context, Briefing composer)

Both use the same client class with a different default model.
"""
from __future__ import annotations

import asyncio
import logging
import random
import re
from typing import Type, TypeVar

from google import genai
from google.genai import types
from pydantic import BaseModel

from ...config import GOOGLE_API_KEY

log = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


# Current Gemini model identifiers (May 2026).
MODEL_GEMINI_PRO = "gemini-2.5-pro"
MODEL_GEMINI_FLASH = "gemini-2.5-flash"


class GeminiClient:
    """Async wrapper around google-genai with structured output support.

    Instantiates a fresh genai.Client per object on purpose: jobs run in
    worker threads with their own event loops, and a process-level singleton
    binds async resources to the loop that created it. Fresh instances per
    call cost ~nothing — the SDK does its own connection pooling internally.
    """

    def __init__(self, model: str = MODEL_GEMINI_PRO, temperature: float = 0.2) -> None:
        if not GOOGLE_API_KEY:
            raise RuntimeError(
                "GOOGLE_API_KEY is not set. Add it to .env to use the Gemini client."
            )
        self.client = genai.Client(api_key=GOOGLE_API_KEY)
        self.model = model
        self.temperature = temperature

    async def invoke_structured(self, prompt: str, schema: Type[T]) -> T | None:
        """Call Gemini and parse the response into a Pydantic instance.

        Returns the parsed instance on success, None if Gemini's structured
        output failed validation. Callers wanting a hard guarantee should use
        engine.live.llm.structured.invoke_structured_or_freetext().
        """
        cfg = types.GenerateContentConfig(
            temperature=self.temperature,
            response_mime_type="application/json",
            response_schema=schema,
        )
        response = await self._call_with_backoff(prompt, cfg)

        # google-genai sets response.parsed when the schema validates.
        parsed = getattr(response, "parsed", None)
        if isinstance(parsed, schema):
            return parsed

        # Sometimes parsed is None but response.text holds valid JSON.
        # Defer to the structured.py helper for fallback parsing.
        log.warning(
            "gemini structured output returned no parsed instance (model=%s, schema=%s)",
            self.model, schema.__name__,
        )
        return None

    async def invoke_text(self, prompt: str) -> str:
        """Plain text call — used as the fallback path."""
        cfg = types.GenerateContentConfig(temperature=self.temperature)
        response = await self._call_with_backoff(prompt, cfg)
        return response.text or ""

    # ------------------------------------------------------------------ #
    # Retry helper
    # ------------------------------------------------------------------ #

    async def _call_with_backoff(self, prompt: str, cfg, max_retries: int = 6):
        """Call generate_content with retries on transient errors.

        Gemini's "503 UNAVAILABLE — model experiencing high demand" spikes are
        temporary but can last longer than a couple of seconds, so we retry up
        to `max_retries` times with a capped exponential backoff (~60s of total
        coverage). Honors the server's `retryDelay` hint when present. For
        non-transient errors (400, 401, 402, 404) we fail fast.
        """
        last_exc: Exception | None = None
        for attempt in range(max_retries):
            try:
                return await self.client.aio.models.generate_content(
                    model=self.model, contents=prompt, config=cfg,
                )
            except Exception as e:  # noqa: BLE001 — we filter by string
                last_exc = e
                msg = str(e)
                lower = msg.lower()
                transient = (
                    "429" in msg or "RESOURCE_EXHAUSTED" in msg
                    or "500" in msg or "502" in msg or "503" in msg or "504" in msg
                    or "UNAVAILABLE" in msg or "INTERNAL" in msg
                    or "overloaded" in lower or "high demand" in lower
                    or "try again" in lower
                )
                if not transient or attempt == max_retries - 1:
                    raise
                # Server-suggested delay (capped), else jittered, capped exponential.
                server = _parse_retry_delay(msg)
                if server is not None:
                    wait = min(server, 60.0)
                else:
                    wait = min(30.0, 2.0 * (2 ** attempt)) + random.uniform(0, 1.0)
                log.warning(
                    "Gemini transient error (attempt %d/%d): %s — sleeping %.1fs",
                    attempt + 1, max_retries, msg[:120], wait,
                )
                await asyncio.sleep(wait)
        # unreachable
        if last_exc:
            raise last_exc


_RETRY_DELAY_RE = re.compile(r"retryDelay['\"]?\s*[:=]\s*['\"]?(\d+(?:\.\d+)?)s")


def _parse_retry_delay(err_msg: str) -> float | None:
    """Pull the server's suggested retry delay (seconds) out of an error string."""
    m = _RETRY_DELAY_RE.search(err_msg)
    if not m:
        return None
    try:
        return float(m.group(1))
    except ValueError:
        return None


def gemini_pro(temperature: float = 0.2) -> GeminiClient:
    return GeminiClient(MODEL_GEMINI_PRO, temperature=temperature)


def gemini_flash(temperature: float = 0.2) -> GeminiClient:
    return GeminiClient(MODEL_GEMINI_FLASH, temperature=temperature)
