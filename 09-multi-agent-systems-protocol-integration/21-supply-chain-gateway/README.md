# Supply Chain Gateway — Lesson 11 Demo

Plugin-architecture supply chain agent connecting to independently deployed Lambda functions through a centralized gateway.

## Architecture

| Component | Role |
|-----------|------|
| **LambdaGateway** | Central registry: register, discover, invoke tool backends |
| **Inventory API** | Check stock levels, reorder points |
| **Shipping API** | Track shipment status and ETA |
| **Supplier API** | List suppliers, lead times, ratings |
| **Quality Inspection API** | Inspect defect rates and issues (dynamically registered) |
| **SupplyChainAgent** | Discovers tools via gateway, routes queries using Nova Lite |

## Key concepts

- **Loose coupling**: tools live outside the agent; agent discovers them at runtime
- **Dynamic registration**: add tools mid-run without agent restart
- **Centralized observability**: every invocation logged in `gateway.invocation_log`
- **Production swap**: LambdaGateway → managed AgentCore Gateway (MCP endpoint)

## Setup

```bash
cp .env.example .env
python infrastructure/deploy_stack.py
uv run python supply_chain_gateway.py
```

## Cleanup

```bash
aws cloudformation delete-stack --stack-name lesson-11-demo-gateway --region us-east-1
```
