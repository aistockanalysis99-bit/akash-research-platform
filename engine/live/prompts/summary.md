You are writing a one-page **executive summary** for a $2M institutional fund's
analysis of **{symbol}** on **{as_of_date}**.

The summary is the first thing a human reads before diving into the per-agent
reports. It must be readable end-to-end in under 60 seconds.

---

## Source material

### Fundamental Analyst

```json
{fundamental_json}
```

### News Analyst

```json
{news_json}
```

### Bull Researcher

```json
{bull_json}
```

### Bear Researcher

```json
{bear_json}
```

### Portfolio Manager verdict

```json
{pm_json}
```

---

## Task

Produce a `SummaryReport` containing:

1. **headline** (~150 chars): one-line verdict. e.g.:
   - "APPROVE NVDA — full position, conviction 8/10, exit if revenue decel below 40% YoY"
   - "REJECT META — concentration risk + earnings in 4 days outweigh setup"

2. **summary_markdown**: a 1-page markdown document with these sections, in
   this order:

   - Title:  `# <SYMBOL> — Analysis Summary (<DATE>)`
   - Blockquote: the same headline you wrote above, prefixed with `> **`
   - Section `## Verdict` — 3 bullets: Decision, Conviction N/10, Size XX%
   - Section `## What the team said` — 4 bullets:
       - Fundamental score N/10 + one-sentence summary
       - News risk N/10, opportunity N/10 + one-sentence summary
       - Bull conviction N/10 + quoted strongest_point
       - Bear conviction N/10 + quoted strongest_point
   - Section `## PM rationale` — 3 short bullet points distilling the
     PM's investment_rationale paragraphs
   - Section `## Exit thesis` — direct quote from PM exit_thesis
   - Section `## What to watch` — bullet list from PM monitoring_flags

Be tight, scannable, no fluff. Quote real numbers and real conclusions —
do not invent. Use markdown for headings, bold, bullets.

Return ONLY valid JSON matching the SummaryReport schema. The
`summary_markdown` field contains the markdown body shown above.
