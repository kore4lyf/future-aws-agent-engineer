# Multi-Model Incident Response

Course 4, Module 2 — tiered multi-agent pipeline, one model per job.

## What we're building

Server incidents flow through three specialists, each on the cheapest model that can do its job:

1. **Alert Router (Nova Lite, temp 0.0)** — keyword-classifies severity (CRITICAL/WARNING/INFO), writes to `classification_cache`.
2. **Root Cause Analyzer (Claude Sonnet, temp 0.1)** — joins the incident to the `KNOWN_ISSUES` runbook, synthesizes Root Cause / Action / ETA.
3. **Status Drafter (Nova Pro, temp 0.3)** — writes the team-facing status update; slightly warmer for natural prose.

The orchestrator reads severity from `classification_cache` (never LLM prose) and `main()` adds latency + cost projection vs. a Claude-for-everything baseline (~80% savings at 10K incidents/day).

## Layout

- `main.py` — entrypoint: AgentCore `invoke` plus local CLI
- `src/main.py` — pipeline: builders, coordinator, data tables, helpers (clean scaffold; domain logic next)

## Build plan

1. Data tables: `INCIDENTS` (CPU spike / disk filling / clean deploy), `SEVERITY_KEYWORDS`, `KNOWN_ISSUES` runbook, `STATUS_TEMPLATES`.
2. Builders: routing, analysis, status — same shape, different model + temperature.
3. Coordinator + `main()`: cache handoff, latency table, cost projection.
4. Run: `cp .env.example .env`, load AWS creds, `uv run main.py`.
