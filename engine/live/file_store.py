"""Per-stock research folder writer.

Layout on disk:
    AI_RESEARCH_DIR/
    └── NVDA/
        └── 2026-05-24/
            ├── 00_signal.md          (the input signal)
            ├── 01_pre_filter.md      (deterministic gate result)
            ├── 02_fundamental.md     (Fundamental Analyst report)
            ├── 03_news.md            (News Analyst report)
            ├── 04_bull.md            (Bull case)
            ├── 05_bear.md            (Bear case)
            ├── 06_pm_verdict.md      (PM final decision + Telegram draft)
            ├── _summary.md           (LLM-written 1-page rollup)
            └── _raw.json             (full SignalState dump for debugging)

Every file is written atomically (tmp + os.replace) so a crashed pipeline never
leaves a half-written artifact on disk.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel

from ..config import AI_RESEARCH_DIR


FILE_NAMES = {
    "signal":         "00_signal.md",
    "pre_filter":     "01_pre_filter.md",
    "fundamental":    "02_fundamental.md",
    "news":           "03_news.md",
    # Path B inserts technical alongside news, and risk_manager between debate and PM.
    # Using letter-suffixed numeric prefixes preserves alphabetical sort without
    # invalidating older runs that don't have these files.
    "technical":      "03a_technical.md",
    "institutional_flow":  "03b_institutional_flow.md",
    "options_structure":   "03c_options_structure.md",
    "macro_regime":        "03d_macro_regime.md",
    "bull":           "04_bull.md",
    "bear":           "05_bear.md",
    "judge":          "05_judge.md",
    "risk_manager":   "05a_risk_manager.md",
    "macro_context":  "_macro_context.md",
    "pm":             "06_pm_verdict.md",
    "summary":        "_summary.md",
    "raw":            "_raw.json",
    # Morning loop artifacts (stored under _morning/{date}/)
    "regime":             "10_regime.md",
    "position_monitor":   "11_position_monitor.md",
    "exit_confirmer":     "12_exit_confirmer.md",  # base name; suffix per-symbol
    "morning_briefing":   "13_morning_briefing.md",
}


class FileStore:
    """Thin wrapper over the on-disk per-stock folder layout."""

    def __init__(self, root: Optional[Path] = None) -> None:
        self.root = root or AI_RESEARCH_DIR

    # ----------------------------------------------------------------------- #
    # Paths
    # ----------------------------------------------------------------------- #

    def folder(self, symbol: str, date_iso: str) -> Path:
        return self.root / symbol.upper() / date_iso

    def morning_folder(self, date_iso: str) -> Path:
        return self.root / "_morning" / date_iso

    def write_morning(self, date_iso: str, stage: str, content: str,
                       suffix: str = "") -> Path:
        """Write a morning-cycle markdown artifact. `suffix` for per-symbol files."""
        filename = FILE_NAMES.get(stage, f"{stage}.md")
        if suffix:
            # e.g. exit_confirmer_NVDA.md
            stem, dot, ext = filename.rpartition(".")
            filename = f"{stem}_{suffix}.{ext}" if dot else f"{filename}_{suffix}"
        folder = self.morning_folder(date_iso)
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / filename
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(content, encoding="utf-8")
        os.replace(tmp, path)
        return path

    def write_morning_raw(self, date_iso: str, state: dict[str, Any]) -> Path:
        folder = self.morning_folder(date_iso)
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / "_raw.json"
        return _atomic_write(path, _json_dump(state))

    def list_morning_dates(self) -> list[str]:
        """Return all dates that have morning-cycle artifacts."""
        d = self.root / "_morning"
        if not d.exists():
            return []
        return sorted(
            (p.name for p in d.iterdir() if p.is_dir()), reverse=True,
        )

    def read_morning_files(self, date_iso: str) -> dict[str, str]:
        """Read every markdown file in a morning-cycle folder."""
        folder = self.morning_folder(date_iso)
        if not folder.exists():
            return {}
        out: dict[str, str] = {}
        for p in sorted(folder.glob("*.md")):
            out[p.stem] = p.read_text(encoding="utf-8")
        return out

    def path_for(self, symbol: str, date_iso: str, stage: str) -> Path:
        try:
            filename = FILE_NAMES[stage]
        except KeyError as e:
            raise ValueError(
                f"Unknown stage '{stage}'. Valid: {sorted(FILE_NAMES.keys())}"
            ) from e
        return self.folder(symbol, date_iso) / filename

    # ----------------------------------------------------------------------- #
    # Writers
    # ----------------------------------------------------------------------- #

    def write_markdown(
        self, symbol: str, date_iso: str, stage: str, content: str
    ) -> Path:
        """Write markdown for a given pipeline stage. Atomic."""
        target = self.path_for(symbol, date_iso, stage)
        return _atomic_write(target, content)

    def write_raw_state(
        self, symbol: str, date_iso: str, state: dict[str, Any]
    ) -> Path:
        """Dump the full SignalState as JSON for debugging."""
        target = self.path_for(symbol, date_iso, "raw")
        # Use Pydantic-aware serialization where possible.
        return _atomic_write(target, _json_dump(state))

    def append_error(
        self, symbol: str, date_iso: str, agent: str, error: str
    ) -> Path:
        """Append an error line to an _errors.md tail file (created on first error)."""
        target = self.folder(symbol, date_iso) / "_errors.md"
        target.parent.mkdir(parents=True, exist_ok=True)
        line = f"- **{agent}** — {error}\n"
        with target.open("a", encoding="utf-8") as f:
            f.write(line)
        return target

    # ----------------------------------------------------------------------- #
    # Readers
    # ----------------------------------------------------------------------- #

    def exists(self, symbol: str, date_iso: str, stage: str) -> bool:
        return self.path_for(symbol, date_iso, stage).exists()

    def read_markdown(self, symbol: str, date_iso: str, stage: str) -> str:
        return self.path_for(symbol, date_iso, stage).read_text(encoding="utf-8")

    def list_dates_for(self, symbol: str) -> list[str]:
        d = self.root / symbol.upper()
        if not d.exists():
            return []
        return sorted(p.name for p in d.iterdir() if p.is_dir())


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _atomic_write(target: Path, content: str) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    os.replace(tmp, target)
    return target


def _json_dump(obj: Any) -> str:
    """JSON dump that knows how to serialize Pydantic models."""

    def default(o: Any) -> Any:
        if isinstance(o, BaseModel):
            return o.model_dump(mode="json")
        if hasattr(o, "isoformat"):
            return o.isoformat()
        raise TypeError(f"not serializable: {type(o)}")

    return json.dumps(obj, indent=2, default=default, ensure_ascii=False)
