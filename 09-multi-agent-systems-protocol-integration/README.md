# Multi-Agent Systems Protocol Integration

Twenty-two projects covering sequential, parallel, conditional, hierarchical, shared-state, saga, RAG, governance, production deployment, and gateway patterns on Amazon Bedrock.

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
| 15 | `15-research-assistant-rag` | Parallel multi-KB RAG, aggregate/dedup, grounded synthesis | ✅ unit tests |
| 16 | `16-clinical-literature-rag` | Clinical dual-KB RAG, structured 3-section synthesis | ✅ unit tests |
| 17 | `17-healthcare-guardrails` | Six-layer governance: kill switch, rate limit, Bedrock guardrails, LLM-as-judge | ✅ unit tests |
| 18 | `18-trading-compliance` | Seven-layer governance: stricter kill switch, output guardrail, compliance agent, LLM-as-judge | ✅ unit tests |
| 19 | `19-deployment-walkthrough` | Production deployment: AgentCore Runtime, CF exports, gated pipeline, monitoring, cost estimation | ✅ unit tests |
| 20 | `20-vectrabank-architecture` | VPC runtime, 4-tier agents, monitoring strategy, cost estimate, operational runbooks | ✅ unit tests |
| 21 | `21-supply-chain-gateway` | Gateway pattern: dynamic tool discovery, Lambda backends, centralized observability | ✅ unit tests |
| 22 | `22-analytics-gateway` | Exercise: analytics agent with 4 Lambda backends, deterministic routing, dynamic stock_price registration | ✅ unit tests |

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

# Research Assistant RAG (needs CS_KB_ID + BIO_KB_ID in .env)
cd 15-research-assistant-rag
uv run --with pytest --with boto3 pytest -q
uv run python main.py

# Clinical Literature RAG (needs DRUG_INTERACTIONS_KB_ID + CLINICAL_GUIDELINES_KB_ID)
cd 16-clinical-literature-rag
uv run --with pytest --with boto3 pytest -q
uv run python main.py

# Healthcare Guardrails (needs HEALTHCARE_GUARDRAIL_ID in .env)
cd 17-healthcare-guardrails
uv run --with pytest --with boto3 --with python-dotenv python -m pytest test/ -q
uv run python main.py

# Trading Compliance (needs TRADING_GUARDRAIL_ID in .env)
cd 18-trading-compliance
uv run --with pytest --with boto3 --with python-dotenv python -m pytest test/ -q
uv run python main.py

# Deployment Walkthrough (deploy stack first)
cd 19-deployment-walkthrough
python infrastructure/deploy_stack.py
uv run python deployment_walkthrough.py

# VectraBank Architecture (deploy stack first)
cd 20-vectrabank-architecture
python infrastructure/deploy_stack.py
uv run python vectrabank_architecture.py

# Supply Chain Gateway (deploy stack first)
cd 21-supply-chain-gateway
python infrastructure/deploy_stack.py
uv run python supply_chain_gateway.py

# Analytics Gateway (deploy stack first)
cd 22-analytics-gateway
python infrastructure/deploy_stack.py
uv run python analytics_gateway.py
```

Load AWS credentials from your session environment (never commit them). CloudFormation stacks used by the hybrid routers, shared-state, saga, RAG, and guardrail demos: `lesson-05-demo-routing`, `lesson-05-exercise-routing`, `lesson-06-demo-shared-state`, `lesson-06-exercise-shared-state`, `lesson-07-demo-saga`, `lesson-07-exercise-saga`, `lesson-08-demo-rag`, `lesson-08-exercise-rag`, `lesson-09-demo-guardrails`, `lesson-09-exercise-guardrails`, `lesson-10-demo-runtime`, `lesson-10-exercise-runtime`, `lesson-11-demo-gateway`.
