# Trading Compliance — Lesson 9 Exercise

Financial trading compliance agent for a brokerage firm: **kill switch → rate limiter → input guardrail → compliance agent → output guardrail → LLM-as-judge**.

## Seven layers

| # | Layer | Class / function | Behavior |
|---|-------|------------------|----------|
| 0 | Kill switch | `KillSwitch` | Circuit breaker: 3 violations in 60s → `is_triggered`; CloudWatch `GuardrailViolations`; no auto-reset |
| 1 | Rate limiter | `RateLimiter` | Token bucket 100 req/s, burst 200 → `RATE_LIMITED` |
| 2 | Input guardrail | `apply_guardrail` | Bedrock `apply_guardrail(INPUT)` — PII block/anonymize, topic denial, content, profanity; **fails open** |
| 3 | Compliance agent | `build_compliance_agent` | Nova Lite + `check_trading_rules`; refuses trade recommendations and insider info |
| 4 | Output guardrail | `apply_guardrail(direction="OUTPUT")` | Scans agent response before reaching user |
| 5 | LLM-as-judge | `build_evaluator_agent` | Claude Sonnet (`EVAL_MODEL`), `score_response` tool, 4 criteria 1–5 (compliance, relevance, safety, completeness) |
| 6 | Metrics | `MetricsDashboard` | allowed / blocked / rate_limited / anonymized + policy breakdown |

Pipeline order (short-circuit at each gate):

```
kill_switch.check() → rate_limiter.allow_request() → apply_guardrail(INPUT)
  BLOCKED  → dashboard.record + kill_switch.record_violation() → return
  ALLOWED  → agent → clean_response → apply_guardrail(OUTPUT)
    BLOCKED  → dashboard.record + kill_switch.record_violation() → return
    ALLOWED  → dashboard.record + return response
```

## Setup (region `us-east-1`)

```bash
cp .env.example .env   # paste AWS credentials + TradingGuardrailId
uv run python main.py
```

## Test

```bash
uv run --with pytest --with boto3 --with python-dotenv python -m pytest test/ -q
```

Live tests skip without `TRADING_GUARDRAIL_ID` + AWS credentials.

## Cleanup

```bash
aws cloudformation delete-stack --stack-name lesson-09-exercise-guardrails --region us-east-1
```
