# Telecom Router — Hybrid Routing Exercise Solution

Routes telecom customer support tickets through a four-tier hybrid pipeline:

1. **Priority** — cancellation intent → `RetentionAgent` (business-critical)
2. **Rules** — regex keyword matching → `BillingAgent` / `TechnicalAgent`
3. **LLM** — Nova Lite classifier → specialist based on intent (confidence ≥ 0.6)
4. **Fallback** — low confidence → `GeneralSupportAgent` (human review)

## Run the demo

```bash
cp .env.example .env  # paste AWS credentials
aws cloudformation deploy --template-file infrastructure/stack.yaml --stack-name lesson-05-exercise-routing
uv run python main.py
```

## Run tests

```bash
uv run --with pytest --with boto3 pytest -q
```
