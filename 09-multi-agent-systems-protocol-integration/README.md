# Multi-Agent Systems Protocol Integration

Fourteen projects covering sequential, parallel, conditional, hierarchical, shared-state, and saga agent orchestration on Amazon Bedrock.

## Projects (chronological order)

| # | Folder | Pattern | Status |
|---|--------|---------|--------|
| 01 | `01-healthcare-triage-demo` | Sequential coordinator (3 agents) | ✅ |
| 02 | `02-smart-home-device-mgmt` | Registry/rules/actions sequential pipeline | ✅ |
| 03 | `03-incident-response-demo` | Multi-model sequential pipeline | ✅ |
| 04 | `04-content-moderation-pipeline` | Conditional routing, multi-model | ✅ 24/24 tests |
| 05 | `05-parallel-document-analysis` | Parallel fan-out analysis | ✅ |
| 06 | `06-contract-compliance` | Parallel specialists + synthesizer | ✅ 2 passed, 1 skipped |
| 07 | `07-hr-onboarding` | Sequential, parallel, conditional patterns | ✅ 5 passed, 1 skipped |
| 08 | `08-package-delivery` | Validation gate, parallel dispatch, conditional routing | ✅ 8 passed, 1 skipped |
| 09 | `09-financial-router` | 4-tier hybrid routing + DynamoDB audit | ✅ 13 tests |
| 10 | `10-telecom-router` | 4-tier hybrid routing, 20 tickets, DynamoDB audit | ✅ 30 tests |
| 11 | `11-ride-sharing-state` | Shared state, optimistic locking, concurrent agents | ✅ 19 tests |
| 12 | `12-food-delivery-state` | Shared state, optimistic locking, 4 agents, recovery | ✅ 22 tests |
| 13 | `13-travel-booking-saga` | Saga orchestration, reverse compensation, barrier, lock | ✅ 22 tests |
| 14 | `14-ecommerce-checkout-saga` | Checkout saga, tool-owned barrier increments | ✅ 21 tests |

Each project has its own `pyproject.toml`, tests under `test/`, and `.env.example`; READMEs exist except for 06–09.

## Testing Notes

### Claude Sonnet Access
Claude Sonnet (`us.anthropic.claude-sonnet-4-5-20250929-v1:0`) requires an AWS Marketplace subscription.
- ❌ Not available with current credentials
- ✅ Workaround: Use `amazon.nova-lite-v1:0` for agents where the model is configurable
- `06-contract-compliance`: financial + synthesizer agents intentionally keep `CLAUDE_MODEL` — without Claude access that live test always skips

### Quick Commands

```bash
# Content Moderation
cd 04-content-moderation-pipeline
uv run python -m pytest test/test_main.py -v  # 24 tests
uv run python demo.py

# Healthcare Triage (with Nova Lite)
cd 01-healthcare-triage-demo
echo "MODEL_ID=amazon.nova-lite-v1:0" >> .env
uv run python main.py --patient-id P-1001

# Incident Response (with Nova Lite)
cd 03-incident-response-demo
echo "NOVA_LITE_MODEL=amazon.nova-lite-v1:0" >> .env
echo "CLAUDE_MODEL=amazon.nova-lite-v1:0" >> .env
echo "NOVA_PRO_MODEL=amazon.nova-lite-v1:0" >> .env
uv run python main.py --incident-id INC-001

# Smart Home (with Nova Lite)
cd 02-smart-home-device-mgmt
echo "MODEL_ID=amazon.nova-lite-v1:0" >> .env
uv run python main.py --device-id DEV-001

# Financial Router
cd 09-financial-router
uv run --with pytest --with boto3 pytest -q
uv run python main.py

# Telecom Router
cd 10-telecom-router
uv run --with pytest --with boto3 pytest -q
uv run python main.py

# Ride Sharing State
cd 11-ride-sharing-state
uv run --with pytest --with boto3 pytest -q
uv run python main.py

# Food Delivery State
cd 12-food-delivery-state
uv run --with pytest --with boto3 pytest -q
uv run python main.py

# Travel Booking Saga
cd 13-travel-booking-saga
uv run --with pytest --with boto3 pytest -q
uv run python main.py

# E-commerce Checkout Saga
cd 14-ecommerce-checkout-saga
uv run --with pytest --with boto3 pytest -q
uv run python main.py
```

Load AWS credentials from your session environment (never commit them). CloudFormation stacks used by the hybrid routers, shared-state, and saga demos: `lesson-05-demo-routing`, `lesson-05-exercise-routing`, `lesson-06-demo-shared-state`, `lesson-06-exercise-shared-state`, `lesson-07-demo-saga`, `lesson-07-exercise-saga`.
