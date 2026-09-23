# Ride Sharing — Shared State with DynamoDB and AgentCore Memory

Coordinates three agents (Driver Match, Pricing, ETA) writing to the **same** DynamoDB trip record using optimistic locking, plus cross-session rider memory (AgentCore `SESSION_SUMMARY` stand-in).

## Patterns

| Pattern | Where |
|---|---|
| Optimistic locking | `update_trip` — version + `ConditionExpression` + retry |
| Exponential backoff | `0.1 * 2**attempt` on `ConditionalCheckFailedException` |
| Concurrent orchestration | `ThreadPoolExecutor` (Scenario 2) |
| State recovery | `recover_incomplete_trip` — resets non-confirmed trips |
| Cross-session memory | `rider-memory` table via `select_driver_for_rider` |

## Run

```bash
cp .env.example .env  # paste AWS credentials
aws cloudformation deploy --template-file infrastructure/stack.yaml \
    --stack-name lesson-06-demo-shared-state
uv run python main.py
```

## Test

```bash
uv run --with pytest --with boto3 pytest -q
```

## Cleanup

```bash
aws cloudformation delete-stack --stack-name lesson-06-demo-shared-state
```
