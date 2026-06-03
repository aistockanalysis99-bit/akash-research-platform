---
symbol: TICKER
name: Example Company Name
sector: Technology
industry: Software—Application
exchange: NASDAQ
is_etf: false
last_reviewed: 2026-01-01
auto_built: false
review_cadence_days: 30
priority: tier_2
held: false
position_intent: watch
market_cap_usd: 1000000000

business_model: |
  One-paragraph description of what the company does, where revenue comes
  from, and what the moat is. Be specific.

revenue_segments:
  - name: segment_one
    pct_of_revenue: 0.65
    description: Brief description of what this segment is

geographic_revenue:
  - region: united_states
    pct_of_revenue: 0.60
  - region: international
    pct_of_revenue: 0.40

key_kpis:
  - stock_specific_metric_1
  - stock_specific_metric_2

bull_thesis_pillars:
  - text: "Specific argument with numbers"
    confidence: moderate
    last_updated: 2026-01-01

bear_thesis_pillars:
  - text: "Specific risk with numbers"
    confidence: moderate
    last_updated: 2026-01-01

red_lines:
  - condition: "Specific testable exit condition"
    rationale: "Why this matters"
    measurable: true

analyst_questions:
  fundamental:
    - "Question for the Fundamental Analyst"
  news:
    - "Question for the News Analyst"
  technical:
    - "Question for the Technical Analyst"

preferred_peers: [PEER1, PEER2, PEER3]

correlation_notes: |
  How this stock relates to others in a portfolio.

recent_management_commentary:
  - date: 2026-01-01
    speaker: CEO Name
    quote: "Important forward-looking statement"
    source: "Q4 2025 earnings call"

historical_lessons: []

pm_notes: |
  CIO-level context on how to think about owning this name.
---

# TICKER — Long-form Research Notes

Free-form markdown narrative below the frontmatter goes here. Use this for
extended thesis writeups, model assumptions, or anything that doesn't fit
the structured fields above. This becomes `long_form_notes` when loaded.
