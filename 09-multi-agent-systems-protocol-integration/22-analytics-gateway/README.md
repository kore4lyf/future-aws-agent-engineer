# Analytics Gateway — Lesson 11 Exercise

AI-powered analytics assistant using the gateway pattern for dynamic tool discovery.

## Architecture

| Component | Role |
|-----------|------|
| **LambdaGateway** | Central registry: register, discover, invoke Lambda backends |
| **Weather API** | Current weather conditions by city |
| **Currency API** | Currency conversion with live rates |
| **News API** | Latest news articles by category |
| **Stock Price API** | Current stock price and change (dynamically registered) |
| **AnalyticsAgent** | Discovers tools via gateway, routes queries using Nova Lite |

## Key concepts

- **Loose coupling**: agent never hardcodes tool names; discovers them from gateway at runtime
- **Deterministic routing**: Nova Lite temperature=0.0 for predictable tool selection
- **Dynamic registration**: stock_price tool added mid-run without agent restart
- **Centralized observability**: invocation_log records every tool call

## Setup

```bash
cp .env.example .env
python infrastructure/deploy_stack.py
uv run python analytics_gateway.py
```

## Cleanup

```bash
aws cloudformation delete-stack --stack-name lesson-11-exercise-gateway --region us-east-1
```
