You are writing the daily morning briefing for the client of a $2,000,000
long-only US equity fund. It is {as_of_date}. Write the message they will
read on their phone in under 30 seconds.

Plain English only. No jargon. No markdown. No bold. No bullet points.
Numbers make it real — cite them.

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

### Position review ({position_count} open positions)
```json
{review_json}
```

### Exits executed today
```json
{executed_exits_json}
```

### Exit confirmations
```json
{confirmations_json}
```

---

## Task

Produce a `MorningBriefing`. The `telegram_message` field must follow this
**exact template** — fill in the bracketed parts with real data. Keep each
section on its own line(s), separated by a blank line.

Example output (fill in with real data — do NOT copy these fake numbers):

🌅 Morning · Jun 4, 2026

Market: Choppy · 7/10
Tech is leading while most other sectors are flat or down.

Portfolio: 21 positions · $2.1M · +$2,140 today
Exits today: None

Top movers:
↑ AMD +1.1% — strong pre-market momentum
↑ MU +0.8%
↓ NVDA -1.0% — broad semi rotation, thesis intact

Watch today:
NVDA — if it breaks below $210 on volume, thesis is weakening.

Rules:
- If no exits, write "Exits today: None"
- If all positions flat, skip "Top movers" section
- The whole message must fit in 20 lines maximum
- Every number must come from the source material above — do not invent
- Do NOT use markdown bold (**), headers (#), or bullet points (-)
- Use ↑ and ↓ for movers, that is all the formatting allowed

The `headline` field: one line, e.g.
"Holding all 21 · Bullish Choppy · AMD +1.1%, NVDA watching"

Return ONLY valid JSON matching the MorningBriefing schema.
