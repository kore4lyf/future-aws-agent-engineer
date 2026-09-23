# Parallel Document Analysis

Course 4 — Parallel multi-agent workflow demo: three specialists analyze documents concurrently, then a synthesizer combines their findings.

## What we're building

A document analysis system that demonstrates parallel execution patterns:

1. **Security Specialist (Nova Lite, temp 0.0)** — reviews documents for security concerns
2. **Scalability Specialist (Claude Sonnet, temp 0.1)** — analyzes scalability bottlenecks
3. **Cost Specialist (Nova Pro, temp 0.1)** — evaluates cost implications
4. **Synthesizer (Claude Sonnet, temp 0.2)** — combines all findings into final report

All three specialists run **in parallel** using ThreadPoolExecutor, then the synthesizer produces a launch-readiness decision (APPROVE, APPROVE-WITH-CONDITIONS, or BLOCK).

## Architecture

```
┌─────────────────┐
│   Document      │
│   (DOC-001)     │
└────────┬────────┘
         │
         ▼
┌─────────────────────────────┐
│  ThreadPoolExecutor         │
│  (max_workers=3)           │
├────────────┬───────────────┤
│            │               │
▼            ▼               ▼
Security   Scalability    Cost
(Nova Lite) (Claude)     (Nova Pro)
   │            │            │
   └────────────┼────────────┘
                │ (all caches populated)
                ▼
         Synthesizer
         (Claude)
                │
                ▼
         Final Report
```

## Key Patterns Demonstrated

1. **Parallel execution** — specialists run concurrently (2-3x speedup)
2. **Shared state via caches** — each agent writes to its own cache
3. **Model specialization** — different models for different tasks
4. **Coordinator pattern** — plain Python orchestrates the flow
5. **Synthesizer pattern** — combines independent findings into unified report

## Layout

- `main.py` — entrypoint CLI
- `src/main.py` — core implementation with all agents and coordinator
- `test/test_main.py` — unit tests

## Setup

```bash
cd 05-parallel-document-analysis
cp .env.example .env
# Load AWS credentials
export AWS_ACCESS_KEY_ID="..."
export AWS_SECRET_ACCESS_KEY="..."
export AWS_SESSION_TOKEN="..."
export AWS_REGION="us-east-1"

# Run with uv
uv sync
uv run python main.py                 # Analyze all 3 documents
uv run python main.py --document-id DOC-001  # Analyze single document
```

## Test Documents

| ID | Title | Key Concerns |
|----|-------|--------------|
| DOC-001 | Microservices Migration Plan | Data consistency, network latency, operational complexity |
| DOC-002 | Real-Time Analytics Platform | GDPR compliance, cost at scale, fault tolerance |
| DOC-003 | AI-Powered Recommendation Engine | Model drift, A/B testing, cold start problem |

## Expected Outcomes

Each specialist produces a 3-line report:
- **Security**: Risk Level, Critical Issues count, Recommendation
- **Scalability**: Bottleneck Risk, Challenges count, Recommendation
- **Cost**: Cost Tier, Drivers count, Recommendation

The synthesizer combines these into:
- **APPROVE**: All risks manageable
- **APPROVE-WITH-CONDITIONS**: Some concerns need addressing
- **BLOCK**: Critical issues must be resolved

## Test Status

✅ **Implementation complete**
- ✅ Three specialist agents with dedicated models
- ✅ Parallel execution with ThreadPoolExecutor
- ✅ Shared caches for state handoff
- ✅ Synthesizer with decision logic
- ✅ Timing measurement for performance comparison
- ⚠️ **Claude Sonnet requires AWS Marketplace subscription**
  - Workaround: Use `amazon.nova-lite-v1:0` for all models in `.env`
