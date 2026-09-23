# Multi-Model Incident Response

Course 4, Module 2 — tiered multi-agent pipeline, one model per job.

## What we're building

Server incidents flow through three specialists, each on the cheapest model that can do its job:

1. **Alert Router (Nova Lite, temp 0.0)** — keyword-classifies severity (CRITICAL/WARNING/INFO), writes to `classification_cache`.
2. **Root Cause Analyzer (Claude Sonnet, temp 0.1)** — joins the incident to the `KNOWN_ISSUES` runbook, synthesizes Root Cause / Action / ETA.
3. **Status Drafter (Nova Pro, temp 0.3)** — writes the team-facing status update; slightly warmer for natural prose.

The orchestrator reads severity from `classification_cache` (never LLM prose) and `main()` adds latency + cost projection vs. a Claude-for-everything baseline (~80% savings at 10K incidents/day).

## Test Status

### Implementation ✅ COMPLETE
- ✅ Multi-model scaffold (Nova Lite, Claude Sonnet, Nova Pro)
- ✅ Classification cache for structured data handoff
- ✅ Retry logic with exponential backoff
- ✅ Helper functions (clean_response, _parse_json)
- ✅ Agent builders for all three stages

### Known Limitation
- ❌ Claude Sonnet requires AWS Marketplace subscription
- ✅ Workaround: Use `amazon.nova-lite-v1:0` for all models

## Layout

- `main.py` — entrypoint: AgentCore `invoke` plus local CLI
- `src/main.py` — pipeline: builders, coordinator, data tables, helpers (clean scaffold; domain logic next)

## Build plan

1. Data tables: `INCIDENTS` (CPU spike / disk filling / clean deploy), `SEVERITY_KEYWORDS`, `KNOWN_ISSUES` runbook, `STATUS_TEMPLATES`.
2. Builders: routing, analysis, status — same shape, different model + temperature.
3. Coordinator + `main()`: cache handoff, latency table, cost projection.
4. Run: `cp .env.example .env`, load AWS creds, `uv run main.py`.

## Quick Start

```bash
cd 03-incident-response-demo
cp .env.example .env

# Use Nova Lite to avoid Claude Marketplace access issues
echo "NOVA_LITE_MODEL=amazon.nova-lite-v1:0" >> .env
echo "CLAUDE_MODEL=amazon.nova-lite-v1:0" >> .env
echo "NOVA_PRO_MODEL=amazon.nova-lite-v1:0" >> .env

# Load AWS credentials
export AWS_ACCESS_KEY_ID="..."
export AWS_SECRET_ACCESS_KEY="..."
export AWS_SESSION_TOKEN="..."
export AWS_REGION="us-east-1"

# Run pipeline
uv run python main.py --incident-id INC-001
```

