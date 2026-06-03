"""Abstract Agent base class — every concrete agent inherits this.

Encodes the common pipeline contract:
    1. each agent declares what data + prior agent outputs it needs (manifest)
    2. each agent renders a prompt from state + a template
    3. each agent calls an LLM with structured output (with free-text fallback)
    4. each agent writes its rendered markdown to the per-stock folder
    5. each agent returns a new SignalState with its slot filled

Concrete subclasses implement build_prompt() and render(). Everything else is here.
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import ClassVar, Type

from pydantic import BaseModel

from ..file_store import FileStore
from ..llm.gemini import GeminiClient
from ..llm.structured import invoke_structured_or_freetext
from ..state import SignalState

log = logging.getLogger(__name__)

# Resolve once at import time. Each agent loads its prompt template from here.
PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"


class Agent(ABC):
    """Base class. Subclasses set the ClassVars and implement build_prompt + render."""

    NAME: ClassVar[str]                          # state slot name (e.g. "fundamental")
    LLM_TIER: ClassVar[str]                      # 'pro' | 'flash' | 'sonnet' | 'opus'
    REQUIRES_DATA: ClassVar[list[str]] = []      # context bundle keys this agent reads
    REQUIRES_AGENTS: ClassVar[list[str]] = []    # other agents' outputs we need
    OUTPUT_SCHEMA: ClassVar[Type[BaseModel]]     # Pydantic model for structured output
    STAGE: ClassVar[str]                          # file_store stage name (e.g. "fundamental")
    PROMPT_FILE: ClassVar[str]                    # filename inside prompts/ dir

    def __init__(self, llm: GeminiClient, file_store: FileStore) -> None:
        self.llm = llm
        self.fs = file_store

    # --------------------------------------------------------------------- #
    # Required overrides
    # --------------------------------------------------------------------- #

    @abstractmethod
    def build_prompt(self, state: SignalState) -> str:
        """Render the prompt template with values pulled from state."""

    @abstractmethod
    def render(self, output: BaseModel) -> str:
        """Render the structured output as markdown for the per-stock folder."""

    # --------------------------------------------------------------------- #
    # Shared run logic
    # --------------------------------------------------------------------- #

    def load_prompt_template(self) -> str:
        return (PROMPTS_DIR / self.PROMPT_FILE).read_text(encoding="utf-8")

    async def run(self, state: SignalState) -> SignalState:
        """Execute the agent against state, return a new state with our slot filled."""
        agent_start = datetime.utcnow().isoformat()
        log.info("[%s] starting for %s", self.NAME, state.get("symbol"))

        # 1. Build prompt
        prompt = self.build_prompt(state)

        # 2. Call LLM with structured output (and free-text fallback)
        result = await invoke_structured_or_freetext(
            self.llm, prompt, self.OUTPUT_SCHEMA
        )
        if result.used_fallback:
            log.warning("[%s] used free-text fallback for %s",
                        self.NAME, state.get("symbol"))

        # 3. Render to markdown + write to per-stock folder
        markdown = self.render(result.instance)
        path = self.fs.write_markdown(
            state["symbol"], state["signal_date"], self.STAGE, markdown
        )

        # 4. Merge into new state (TypedDicts are mutable but we copy for safety)
        new_state: SignalState = dict(state)  # type: ignore[assignment]
        new_state[self.NAME] = result.instance  # type: ignore[literal-required]
        meta = dict(new_state.get("meta", {}))
        meta.setdefault("agents_run", []).append(self.NAME)
        meta[f"{self.NAME}_completed_at"] = datetime.utcnow().isoformat()
        meta[f"{self.NAME}_started_at"] = agent_start
        meta[f"{self.NAME}_used_fallback"] = result.used_fallback
        new_state["meta"] = meta  # type: ignore[typeddict-item]

        log.info("[%s] complete for %s -> %s",
                 self.NAME, state.get("symbol"), path)
        return new_state
