# WanderBot v6 — Securing Agents with AgentCore Identity

Managed credentials for protected APIs via Gateway + Identity. Agent code unchanged from v5 — credential handling is infrastructure.

## What's New in v6

- **AgentCore Identity** — `wanderbot-loyalty-api-key` (API Key) holds the Loyalty REST API key
- **API Gateway target** — `wanderbot-loyalty-target` (`GET /loyalty/{member_id}` → tool `get_loyalty_points`) bound to that Identity with header `x-api-key`
- Gateway injects the header per-request — no keys in source; rotate in Identity, next call picks it up, no redeploy
- Same `MCPClient(lambda: streamable_http_client(url=GATEWAY_ENDPOINT))` → `list_tools_sync()` → `Agent(tools=tools)` pattern

## Project Structure

```
wanderbot-v6/
├── lambda/
│   ├── booking_lambda.py        # BK-1001.. (booking tools, Lambda target)
│   └── loyalty_points_api.py    # hz-001.. (behind REST API)
├── schema/booking_lambda.json   # booking Lambda tool schema
├── src/main.py                  # MCPClient → Gateway → Agent (+ memory hooks)
└── gateway/                     # Identity + API target live in console (see NOTES.md)
```

## Infra (console, see NOTES.md)

- Lambda `wanderbot-booking-tools` + `wanderbot-loyalty-points`
- REST `wanderbot-loyalty-api` (`/loyalty/{member_id}` GET, Lambda proxy, API key required, stage `prod`)
- API key `wanderbot-loyalty-key` + plan `wanderbot-loyalty-plan` → stage `prod`
- Identity `wanderbot-loyalty-api-key` → Gateway `wanderbot-gateway-foziumjcew` target `wanderbot-loyalty-target` (`x-api-key`)

## Test

```bash
agentcore dev
agentcore invoke --dev '{"message": "What are the loyalty points for member hz-001?"}'
# expect hz-001 → 45200 via Gateway (Identity injects x-api-key)
```
