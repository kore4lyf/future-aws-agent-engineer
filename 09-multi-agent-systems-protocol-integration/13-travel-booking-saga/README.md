# Travel Booking — Saga Pattern

Python orchestrator coordinates three LLM booking agents (Flight, Hotel, Car) with DynamoDB as the state machine. On failure, compensating `cancel_*` tools run in **reverse order** behind a distributed lock and an atomic barrier.

## Patterns

| Pattern | Where |
|---|---|
| Saga forward path | `run_saga` — sequential book flight → hotel → car |
| Reverse compensation | `completed.reverse()` then cancel in reverse |
| Distributed lock | `acquire_lock` / `release_lock` — conditional `lock` flag |
| Atomic barrier | `increment_barrier` — DynamoDB `ADD compensations_done` |
| Dual-mode agents | builders take `cancel_mode` to flip book/cancel tools |
| Step state machine | pending → executing → completed / failed → compensating → compensated |

## Scenarios

1. **Success** — all three complete (SAGA-001)
2. **Rollback** — car fails → compensate hotel, then flight (SAGA-002)
3. **Mid-path** — hotel fails after flight → only flight compensated (SAGA-003)

## Why reverse order?

Later steps may depend on earlier ones; unwinding from the most recent completed step prevents orphaned references.

## Run

```bash
cp .env.example .env  # paste AWS credentials
aws cloudformation deploy --template-file infrastructure/stack.yaml \
    --stack-name lesson-07-demo-saga
uv run python main.py
```

## Test

```bash
uv run --with pytest --with boto3 pytest -q
```

## Cleanup

```bash
aws cloudformation delete-stack --stack-name lesson-07-demo-saga
```
