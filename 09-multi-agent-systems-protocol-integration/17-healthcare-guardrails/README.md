# Healthcare Guardrails — Lesson 9 Demo

Production governance for a telehealth patient intake agent: **kill switch → rate limiter → Bedrock input guardrail → Nova Lite agent → metrics → LLM-as-judge**.

## Six layers

| # | Layer | Class / function | Behavior |
|---|-------|------------------|----------|
| 0 | Kill switch | `KillSwitch` | Circuit breaker: ≥3 violations in 300s → `is_triggered`; CloudWatch `GuardrailViolations` / `GuardrailAllowed`; no auto-reset |
| 1 | Rate limiter | `RateLimiter` | Token bucket 100 req/s, burst 200 → `RATE_LIMITED` |
| 2 | Input guardrail | `apply_guardrail` | Bedrock `apply_guardrail(INPUT)` — content, PII (SSN), topic denial (legal / prescriptions), profanity; **fails open** |
| 3 | Agent | `build_healthcare_agent` | Nova Lite + `lookup_symptoms`; system prompt forbids prescriptions and legal advice |
| 4 | Metrics | `MetricsDashboard` | allowed / blocked / rate_limited / anonymized + policy breakdown |
| 5 | LLM-as-judge | `build_evaluator_agent` | Claude Sonnet (`EVAL_MODEL`), `score_response` tool, 4 criteria 1–5 |

**Demo = INPUT scan only.** The exercise adds OUTPUT scanning.

Pipeline order (short-circuit at each gate):

```
kill_switch.check() → rate_limiter.allow_request() → apply_guardrail(INPUT)
  BLOCKED  → dashboard.record + kill_switch.record(violation) → return
  ALLOWED  → agent → clean_response → dashboard.record + kill_switch.record(ok)
```

## Setup (region `us-east-1`)

```bash
cp .env.example .env   # paste AWS credentials

aws cloudformation deploy --template-file infrastructure/stack.yaml \
    --stack-name lesson-09-demo-guardrails --region us-east-1
```

Copy **Outputs → HealthcareGuardrailId** (short ID, not ARN) into `HEALTHCARE_GUARDRAIL_ID` in `.env`.

```bash
uv run python main.py
```

Expected narrative: inputs 1–5 allowed and evaluated; 6 PII, 7 self-harm, 8 legal → 3 violations trips kill switch; 9–10 `KILLED` (never reach guardrail).

## Test

```bash
uv run --with pytest --with boto3 --with python-dotenv python -m pytest test/ -q
```

Live tests skip without `HEALTHCARE_GUARDRAIL_ID` + AWS credentials.

## Cleanup

```bash
aws cloudformation delete-stack --stack-name lesson-09-demo-guardrails --region us-east-1
```
