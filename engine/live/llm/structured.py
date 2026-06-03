"""Structured-output-or-fallback helper.

Borrowed from TradingAgents' invoke_structured_or_freetext pattern:
    1. First try the LLM's native structured-output mode (response_schema for
       Gemini, tool-use for Claude)
    2. If that returns None / fails validation, ask again in free-text mode
       and parse JSON out of the response, validating against the schema
    3. As a last resort, try to extract a JSON object from the prose

The fallback path is insurance. We don't accept "the night fell apart because
of one 500ms hiccup" for a $2M fund.

The helper accepts any LLM client that exposes:
    .invoke_structured(prompt, schema) -> BaseModel | None
    .invoke_text(prompt) -> str
GeminiClient and ClaudeClient both implement this duck-type.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Generic, Protocol, Type, TypeVar

from pydantic import BaseModel, ValidationError

log = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


class LLMClient(Protocol):
    """Minimal protocol both GeminiClient and ClaudeClient satisfy."""

    async def invoke_structured(self, prompt: str, schema: Type[T]) -> T | None: ...
    async def invoke_text(self, prompt: str) -> str: ...


@dataclass
class InvokeResult(Generic[T]):
    """What you get back from invoke_structured_or_freetext.

    .instance       — the parsed Pydantic instance (always set unless raise_on_fail)
    .used_fallback  — True if we had to fall back from structured to free-text
    .raw_text       — the model's raw text output (for audit / debugging)
    """

    instance: T
    used_fallback: bool
    raw_text: str


# Matches the first { ... } JSON-looking block in arbitrary text. Greedy by design.
_JSON_BLOCK_RE = re.compile(r"\{.*\}", re.DOTALL)


def _extract_json(text: str) -> str | None:
    """Best-effort extraction of a JSON object from prose. Returns None if no match."""
    if not text:
        return None
    # Strip common markdown code fences if present.
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    # Try whole text first — most common case.
    try:
        json.loads(text)
        return text
    except json.JSONDecodeError:
        pass
    m = _JSON_BLOCK_RE.search(text)
    return m.group(0) if m else None


async def invoke_structured_or_freetext(
    client: LLMClient,
    prompt: str,
    schema: Type[T],
) -> InvokeResult[T]:
    """Invoke the LLM and return a guaranteed Pydantic instance — or raise.

    Tries three paths in order: structured output, free-text JSON parse,
    free-text JSON extract. Logs whenever a fallback is used.
    """
    # Path 1: native structured output.
    try:
        parsed = await client.invoke_structured(prompt, schema)
        if isinstance(parsed, schema):
            return InvokeResult(
                instance=parsed,
                used_fallback=False,
                raw_text=parsed.model_dump_json(),
            )
    except Exception as e:  # noqa: BLE001 — broad on purpose, we have a fallback
        log.warning("structured invoke raised: %s — falling back to free-text", e)

    # Path 2 & 3: free-text with explicit JSON instruction.
    schema_hint = json.dumps(schema.model_json_schema(), indent=2)[:4000]
    fallback_prompt = (
        f"{prompt}\n\n"
        "IMPORTANT: respond with ONLY a valid JSON object matching this schema. "
        "Do not include any prose, markdown code fences, or commentary.\n\n"
        f"Schema:\n{schema_hint}"
    )
    text = await client.invoke_text(fallback_prompt)
    candidate = _extract_json(text) or text

    try:
        instance = schema.model_validate_json(candidate)
        return InvokeResult(instance=instance, used_fallback=True, raw_text=text)
    except ValidationError as e:
        # Safety net: if every error is a string-too-long, truncate the
        # offending fields at their max_length and retry. This rescues runs
        # where an LLM just got a bit too chatty — better than failing the
        # whole pipeline.
        fixed = _truncate_too_long_strings(candidate, e)
        if fixed is not None:
            try:
                instance = schema.model_validate_json(fixed)
                log.warning(
                    "rescued %s by truncating over-long fields: %s",
                    schema.__name__,
                    [tuple(err["loc"]) for err in e.errors()
                     if err["type"] == "string_too_long"],
                )
                return InvokeResult(instance=instance, used_fallback=True,
                                     raw_text=text)
            except ValidationError as e2:
                e = e2  # fall through to the hard error with the new exception

        log.error(
            "free-text fallback failed validation for %s: %s\n--- raw ---\n%s",
            schema.__name__, e, text[:600],
        )
        raise RuntimeError(
            f"LLM output could not be coerced into {schema.__name__}. "
            f"Saved raw text in error log."
        ) from e


def _truncate_too_long_strings(
    json_text: str, error: ValidationError,
) -> str | None:
    """If every error in `error` is `string_too_long`, truncate the offending
    fields at their max_length and return updated JSON text. Returns None if
    any error is something other than length.
    """
    errs = error.errors()
    if not errs or any(e["type"] != "string_too_long" for e in errs):
        return None
    try:
        data = json.loads(json_text)
    except json.JSONDecodeError:
        return None

    for err in errs:
        max_len = (err.get("ctx") or {}).get("max_length")
        if not isinstance(max_len, int) or max_len < 1:
            return None  # can't safely truncate without knowing the limit
        loc = err.get("loc") or ()
        if not loc:
            return None
        # Walk the JSON path to the offending leaf
        container = data
        try:
            for key in loc[:-1]:
                container = container[key]
            value = container[loc[-1]]
            if not isinstance(value, str):
                return None
            # Truncate with a trailing ellipsis if there's room.
            if max_len > 4:
                container[loc[-1]] = value[: max_len - 1] + "…"
            else:
                container[loc[-1]] = value[:max_len]
        except (KeyError, IndexError, TypeError):
            return None

    return json.dumps(data, ensure_ascii=False)
