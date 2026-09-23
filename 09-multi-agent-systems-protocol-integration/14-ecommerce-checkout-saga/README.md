# E-commerce Checkout — Saga Pattern (Exercise)

Same Saga mechanics as the travel demo, applied to checkout: Inventory → Payment → Shipping, with reverse compensation behind a distributed lock. **Structural improvement:** each compensation tool owns its own `increment_barrier` call (atomic DynamoDB `ADD`), so parallel compensations are safe and the orchestrator only checks the barrier after releasing the lock.

## Patterns

| Pattern | Where |
|---|---|
| Saga forward path | `run_saga` — reserve → charge → schedule |
| Reverse compensation | completed steps reversed, then cancel_mode agents |
| Tool-owned barrier | `release_items` / `refund_card` / `cancel_delivery` call `increment_barrier` |
| Atomic counter | `ADD compensations_completed :one` with `ReturnValues=ALL_NEW` |
| Distributed lock | `acquire_lock` / `release_lock` — conditional `locked` flag |
| Barrier fields on create | `create_saga` seeds `compensations_needed` / `compensations_completed` |
| Dual-mode agents | builders take `cancel_mode` to flip forward/compensating tools |

## Scenarios

1. **Success** — Alice Pro Laptop + Sleeve, all three steps (CHECKOUT-001)
2. **Payment fails** — Bob phones + chargers → only inventory `REL-002` (CHECKOUT-002)
3. **Shipping fails** — Carol desk + monitor → refund then release, barrier 2/2 (CHECKOUT-003)

## Why reverse order?

Later steps may depend on earlier ones; refund the card before releasing inventory, cancel delivery before refunding payment when those steps completed.

## Run

```bash
cp .env.example .env  # paste AWS credentials
aws cloudformation deploy --template-file infrastructure/stack.yaml \
    --stack-name lesson-07-exercise-saga
uv run python main.py
```

## Test

```bash
uv run --with pytest --with boto3 pytest -q
```

## Cleanup

```bash
aws cloudformation delete-stack --stack-name lesson-07-exercise-saga
```
