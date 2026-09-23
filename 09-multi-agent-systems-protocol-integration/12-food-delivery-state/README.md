# Food Delivery — Shared State with DynamoDB Optimistic Locking

Four agents (Restaurant Confirm, Driver Assign, Price Calculate, Status Track) write to the **same** DynamoDB order record using optimistic locking. `recover_order` cleans partial data when the restaurant rejects an order. `customer_memory` (in-process stand-in for AgentCore Memory `SESSION_SUMMARY`) retains driver/restaurant/address preferences across orders.

## Patterns

| Pattern | Where |
|---|---|
| Optimistic locking | `update_order` — version + `ConditionExpression` + retry |
| Exponential backoff | `0.1 * 2**attempt` on `ConditionalCheckFailedException` |
| Concurrent orchestration | `ThreadPoolExecutor` (Scenario 2, 4 workers) |
| State recovery | `recover_order` — reset driver/total_price, status `cancelled`, progress log |
| Cross-session memory | `customer_memory` dict via `assign_driver` / `confirm_restaurant` |
| TTL | 2-hour expiry on `create_order` (`ttl` attribute) |

## Scenarios

1. **Sequential** — four agents one after another (ORD-001, Alice / Tokyo Ramen House)
2. **Concurrent** — four agents in a thread pool; conflicts resolved via optimistic locking (ORD-002, Bob / Bella Italia)
3. **State recovery** — driver + price write first, restaurant rejects (`simulate_rejection=True`), `recover_order` cleans orphan state (ORD-003, Carlos / Green Garden)

## Pricing

`subtotal + 8% tax + $4.99 delivery fee`

## Run

```bash
cp .env.example .env  # paste AWS credentials
aws cloudformation deploy --template-file infrastructure/stack.yaml \
    --stack-name lesson-06-exercise-shared-state
uv run python main.py
```

## Test

```bash
uv run --with pytest --with boto3 pytest -q
```

## Cleanup

```bash
aws cloudformation delete-stack --stack-name lesson-06-exercise-shared-state
```

