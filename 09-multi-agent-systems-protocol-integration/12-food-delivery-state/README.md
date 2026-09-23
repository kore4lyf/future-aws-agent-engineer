# Food Delivery — Shared State with DynamoDB Optimistic Locking

Four agents (Restaurant Confirm, Driver Assign, Price Calculate, Status Track) write to the **same** DynamoDB order record using optimistic locking. `recover_order` cleans partial data when an order is rejected.

## Patterns

| Pattern | Where |
|---|---|
| Optimistic locking | `update_order` — version + `ConditionExpression` + retry |
| Exponential backoff | `0.1 * 2**attempt` on `ConditionalCheckFailedException` |
| Concurrent orchestration | `ThreadPoolExecutor` (Scenario 2, 4 workers) |
| State recovery | `recover_order` — reset driver/price, status `cancelled` |
| TTL | 2-hour expiry on `create_order` (`ttl` attribute) |

## Scenarios

1. **Sequential** — four agents one after another (ORD-001)
2. **Concurrent** — four agents in a thread pool; conflicts resolved via optimistic locking (ORD-002)
3. **Recovery** — partial writes cleaned up after rejection (ORD-003)

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
