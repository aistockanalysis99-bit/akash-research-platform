"""Render SummaryReport — just pass through the LLM-written markdown body."""
from __future__ import annotations

from ..schemas import SummaryReport


def render(r: SummaryReport) -> str:
    # The LLM has already produced the markdown body. Pass it through, with
    # a deterministic header so all summaries have a consistent first line.
    body = r.summary_markdown.lstrip()
    # Don't double-up the header if the LLM already added one.
    if not body.startswith("# "):
        body = f"# {r.symbol} — Analysis Summary ({r.as_of_date})\n\n{body}"
    return body + ("\n" if not body.endswith("\n") else "")
