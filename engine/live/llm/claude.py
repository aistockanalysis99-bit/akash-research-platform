"""Claude Sonnet async client with Pydantic structured output.

For Phase 2 we use ONLY Claude Sonnet — never Opus. Sonnet is ~10x cheaper
and handles fiduciary-grade reasoning well at our agent scope.

Structured output uses Anthropic's tool-use pattern: we define a "tool" whose
input_schema is the target Pydantic schema, force the model to call it, then
read the tool_use block's input as our structured result. This is more
reliable than asking for JSON in the prompt.

The class exposes the same interface as GeminiClient (invoke_structured,
invoke_text) so engine.live.llm.structured.invoke_structured_or_freetext()
works with either client polymorphically.
"""
from __future__ import annotations

import asyncio
import logging
import random
from typing import Type, TypeVar

from anthropic import AsyncAnthropic
from pydantic import BaseModel, ValidationError

from ...config import ANTHROPIC_API_KEY

log = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


# Current Anthropic model identifiers (May 2026).
MODEL_CLAUDE_SONNET = "claude-sonnet-4-6"
MODEL_CLAUDE_OPUS = "claude-opus-4-7"


class ClaudeClient:
    """Async wrapper around Anthropic Claude with tool-use-based structured output.

    Instantiates a fresh AsyncAnthropic per object on purpose: jobs run in
    worker threads with their own event loops, and a process-level singleton
    binds async resources to the loop that created it. Fresh instances cost
    ~nothing — the SDK does its own connection pooling internally.
    """

    def __init__(
        self,
        model: str = MODEL_CLAUDE_SONNET,
        temperature: float = 0.2,
        max_tokens: int = 4096,
    ) -> None:
        if not ANTHROPIC_API_KEY:
            raise RuntimeError(
                "ANTHROPIC_API_KEY is not set. Add it to .env to use the Claude client."
            )
        self.client = AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens

    @property
    def _supports_temperature(self) -> bool:
        # Opus 4.7+ rejects `temperature` as deprecated. Skip it for those models.
        return not self.model.startswith("claude-opus-4-7")

    def _temperature_kwargs(self) -> dict:
        return {"temperature": self.temperature} if self._supports_temperature else {}

    async def invoke_structured(self, prompt: str, schema: Type[T]) -> T | None:
        """Force the model to emit a structured object matching `schema`.

        Returns the parsed Pydantic instance, or None if Claude couldn't comply.
        Callers wanting a guarantee should use invoke_structured_or_freetext().
        """
        tool_name = f"emit_{schema.__name__.lower()}"
        try:
            response = await self._messages_create_with_backoff(
                max_tokens=self.max_tokens,
                **self._temperature_kwargs(),
                tools=[
                    {
                        "name": tool_name,
                        "description": (
                            f"Emit a {schema.__name__} object representing the "
                            f"analysis. You MUST call this tool exactly once."
                        ),
                        "input_schema": schema.model_json_schema(),
                    }
                ],
                tool_choice={"type": "tool", "name": tool_name},
                messages=[{"role": "user", "content": prompt}],
            )
        except Exception as e:  # noqa: BLE001 — fallback is in structured.py
            log.warning("claude invoke_structured raised: %s", e)
            return None

        # Scan content blocks for the expected tool_use.
        for block in response.content:
            block_type = getattr(block, "type", None)
            if block_type != "tool_use":
                continue
            if getattr(block, "name", None) != tool_name:
                continue
            try:
                return schema.model_validate(block.input)
            except ValidationError as e:
                log.warning(
                    "claude tool_use input failed %s validation: %s",
                    schema.__name__, e,
                )
                return None
        log.warning(
            "claude returned no tool_use block (model=%s, schema=%s)",
            self.model, schema.__name__,
        )
        return None

    async def invoke_text(self, prompt: str) -> str:
        """Plain text call — used as the fallback path by structured.py."""
        response = await self._messages_create_with_backoff(
            max_tokens=self.max_tokens,
            **self._temperature_kwargs(),
            messages=[{"role": "user", "content": prompt}],
        )
        for block in response.content:
            if getattr(block, "type", None) == "text":
                return getattr(block, "text", "") or ""
        return ""

    # ------------------------------------------------------------------ #
    # Retry helper
    # ------------------------------------------------------------------ #

    async def _messages_create_with_backoff(self, max_retries: int = 3, **kwargs):
        """Call Anthropic messages.create with retries on transient 429/529 errors."""
        last_exc: Exception | None = None
        for attempt in range(max_retries):
            try:
                return await self.client.messages.create(model=self.model, **kwargs)
            except Exception as e:  # noqa: BLE001 — filter by string/type
                last_exc = e
                msg = str(e)
                status = getattr(e, "status_code", None)
                transient = (status in (429, 529, 503, 502)
                             or "429" in msg or "529" in msg
                             or "overloaded" in msg.lower()
                             or "rate" in msg.lower())
                if not transient or attempt == max_retries - 1:
                    raise
                wait = 2 ** attempt + random.uniform(0, 0.5)
                log.warning(
                    "Anthropic transient error (attempt %d/%d): %s — sleeping %.1fs",
                    attempt + 1, max_retries, msg[:120], wait,
                )
                await asyncio.sleep(wait)
        if last_exc:
            raise last_exc


def claude_sonnet(
    temperature: float = 0.2, max_tokens: int = 4096
) -> ClaudeClient:
    return ClaudeClient(MODEL_CLAUDE_SONNET, temperature=temperature, max_tokens=max_tokens)


def claude_opus(
    temperature: float = 0.2, max_tokens: int = 6000
) -> ClaudeClient:
    """The PM/CIO model — deeper reasoning, ~10× the Sonnet cost.

    Use sparingly: only for final verdicts (PM Agent 9, Weekly Reviewer
    Agent 14) where the cost of a sloppy decision exceeds the cost of
    a bigger model.
    """
    return ClaudeClient(MODEL_CLAUDE_OPUS, temperature=temperature, max_tokens=max_tokens)
