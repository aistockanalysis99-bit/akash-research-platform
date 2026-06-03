"""Live AI pipeline — Phase 2.

Quant-first, AI-second portfolio research system. The quant signal generator
(engine.strategy + engine.portfolio.hybrid) produces candidate tickers; this
package wraps each candidate in a multi-agent AI deliberation pipeline that
yields an institutional-grade approve/resize/reject verdict.

Two entry points feed the pipeline:
    - Quant model (engine.strategy)
    - Manual ticker entry (web app)

Per-stock research artifacts are written as markdown to AI_RESEARCH_DIR so
that every agent's reasoning is permanently auditable.
"""
