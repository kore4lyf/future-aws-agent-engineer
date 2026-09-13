# WanderBot v5 — Gateway MCP Integration

Lambda booking tools via AgentCore Gateway + `MCPClient`.

## What's New in v5

- **Agent → Gateway → Lambda** architecture
- **MCPClient** + `streamable_http_client` for Gateway connection
- `list_tools_sync()` discovers `get_booking` / `list_bookings_by_email` — no `@tool` in agent
- Inline tool schema in `schema/booking_lambda.json`

## Project Structure

```
wanderbot-v5/
├── lambda/booking_lambda.py       # 3 bookings, 2 tools, handler
├── schema/booking_lambda.json     # Gateway tool schema
├── src/main.py                    # MCPClient → Gateway → Agent
├── src/hooks/memory.py            # from v4 (retained)
└── src/datasets/
```

## Gateway Setup

```bash
# Gateway already created: wanderbot-gateway-foziumjcew
# https://wanderbot-gateway-foziumjcew.gateway.bedrock-agentcore.us-east-1.amazonaws.com/mcp
# Target: wanderbot-booking-target → lambda: wanderbot-booking-tools
```

## Dev

```bash
agentcore dev
agentcore invoke --dev '{"message": "Get booking BK-1001"}'
```

## Deploy

```bash
agentcore deploy
agentcore invoke '{"message": "List bookings for alice@example.com"}'
```
