"""OpenRouterLLM — adapter that lets ANY OpenRouter model drive a pipeline agent.

Implements the same interface the agents use (invoke_structured / invoke_text),
so the full 11-agent pipeline can run end-to-end on an open model (DeepSeek-R1,
GLM-5.2, Qwen…) instead of Gemini+Claude. Used by the full-pipeline bake-off.

Tracks per-call cost into an optional shared sink so a whole run's cost can be
summed.
"""
from __future__ import annotations

import json
import logging
from typing import Optional, Type, TypeVar

from pydantic import BaseModel

from .openrouter import OpenRouterClient, extract_json

log = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


class OpenRouterLLM:
    """Drop-in LLM client backed by one OpenRouter model."""

    def __init__(self, model: str, cost_sink: Optional[list] = None,
                 temperature: float = 0.2) -> None:
        self.model = model
        self.client = OpenRouterClient()
        self.cost_sink = cost_sink   # optional list[float] to accumulate $ cost
        self.temperature = temperature

    def _track(self, res: dict) -> None:
        if self.cost_sink is not None and res.get("cost_usd"):
            self.cost_sink.append(res["cost_usd"])

    async def invoke_structured(self, prompt: str, schema: Type[T]) -> T | None:
        schema_json = json.dumps(schema.model_json_schema())
        system = ("You are a precise financial analyst. Return ONLY a single JSON "
                  "object that matches the given schema — no prose, no markdown fences.")
        full = f"{prompt}\n\nReturn ONLY valid JSON matching this schema:\n{schema_json}"
        res = await self.client.complete(
            self.model, full, system=system,
            temperature=self.temperature, max_tokens=14000,
        )
        self._track(res)
        data = extract_json(res.get("text") or "")
        if not data:
            log.warning("OpenRouterLLM(%s): no JSON for %s", self.model, schema.__name__)
            return None
        try:
            return schema.model_validate(data)
        except Exception as e:  # noqa: BLE001
            log.warning("OpenRouterLLM(%s): schema validation failed for %s: %s",
                        self.model, schema.__name__, str(e)[:120])
            return None

    async def invoke_text(self, prompt: str) -> str:
        res = await self.client.complete(
            self.model, prompt, temperature=self.temperature, max_tokens=8000,
        )
        self._track(res)
        return res.get("text") or ""
