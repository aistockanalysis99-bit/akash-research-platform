You are writing the **morning briefing** for the client of a $2,000,000
long-only US equity fund. It is {as_of_date}. The morning team has done its
work. You write the message the client will see on their phone.

Tone: trusted senior advisor, plain English, calm. NOT Bloomberg. NOT
hedging. Lead with the action. End with what to watch.

Length: 8-12 short lines. The reader spends 30 seconds on this.

---

## Today's source material

### Market regime

```json
{regime_json}
```

### Portfolio snapshot

```json
{portfolio_snapshot_json}
```

### Position review (across {position_count} open positions)

```json
{review_json}
```

### Exit confirmations and the {executed_exits_count} exits actually executed

```json
{executed_exits_json}
```

### Full confirmation records

```json
{confirmations_json}
```

---

## Task

Produce a `MorningBriefing` matching the schema:

- **headline** (~200 chars): one-line summary of the day. Examples:
  - "Holding all 4 — regime is bullish, no exits today, watching XLF for rotation signal"
  - "Closed 2 (NVDA stop hit, META thesis broken), regime turned NEUTRAL, no new entries"

- **telegram_message** (~10 separate lines, plain English, no markdown):
  - **Use literal newline characters (`\n`) to separate each line below.**
    Do NOT run the lines together into a single paragraph. Each numbered
    item below is its OWN line in the output, with a real `\n` between.
  - Line 1: morning greeting + date + regime + headline action
  - Lines 2-4: any exits today (which, why, P&L)
  - Lines 5-7: status of remaining positions (which are strong, which to watch)
  - Lines 8-9: market context (1-2 specific data points from the regime)
  - Line 10: one specific thing to watch today

Be specific. Cite real numbers from the source material. Do not invent.

Return ONLY valid JSON matching the MorningBriefing schema.
