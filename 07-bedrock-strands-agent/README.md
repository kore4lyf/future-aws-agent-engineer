# Bedrock Strands Agent — WanderBot

Horizon Travel's AI travel assistant built with Strands Agents and Amazon Bedrock AgentCore.

## Versions

| Version | Directory | Features |
|---------|-----------|----------|
| v1 | `wanderbot/wanderbot-v1/` | Basic agent with calculator, current time, travel persona |
| v2 | `wanderbot/wanderbot-v2/` | Function calling with flight search, hotel search, currency exchange |
| v3 | `wanderbot/wanderbot-v3/` | Structured outputs with Pydantic validation, machine-readable JSON |
| v4 | `wanderbot/wanderbot-v4/` | AgentCore Memory — session-scoped short-term memory via HookProvider |
| v5 | `wanderbot/wanderbot-v5/` | AgentCore Gateway — Lambda booking tools via MCPClient |
| v6 | `wanderbot/wanderbot-v6/` | AgentCore Identity — managed API keys, Gateway injected `x-api-key` |

## Feature Comparison

| Feature | v1 | v2 | v3 | v4 | v5 | v6 |
|---------|:--:|:--:|:--:|:--:|:--:|:--:|
| Strands Agent | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| BedrockModel (Nova Lite) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| `calculator` tool | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| `current_time` tool | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| `search_flights` tool | — | ✅ | ✅ | ✅ | ✅ | ✅ |
| `search_hotels` tool | — | ✅ | ✅ | ✅ | ✅ | ✅ |
| `get_exchange_rate` tool | — | ✅ | ✅ | ✅ | ✅ | ✅ |
| Pydantic input validation | — | — | ✅ | ✅ | ✅ | ✅ |
| Pydantic output validation | — | — | ✅ | ✅ | ✅ | ✅ |
| `model_dump_json()` returns | — | — | ✅ | ✅ | ✅ | ✅ |
| Custom datasets (JSON) | — | ✅ | ✅ | ✅ | ✅ | ✅ |
| Tool chaining | — | ✅ | ✅ | ✅ | ✅ | ✅ |
| `src/` layout | — | — | ✅ | ✅ | ✅ | ✅ |
| AgentCore Memory | — | — | — | ✅ | ✅ | ✅ |
| `HookProvider` | — | — | — | ✅ | ✅ | ✅ |
| `session_id` / `actor_id` | — | — | — | ✅ | ✅ | ✅ |
| AgentCore Gateway | — | — | — | — | ✅ | ✅ |
| `MCPClient` + `streamable_http_client` | — | — | — | — | ✅ | ✅ |
| Lambda booking tools | — | — | — | — | ✅ | ✅ |
| AgentCore Identity | — | — | — | — | — | ✅ |

## Standalone Examples

| Example | Directory | Purpose |
|---------|-----------|---------|
| Web Browser Search Agent | `web-browser-search-agent/` | Browser-only AgentCore Browser demo (not WanderBot) |

## Datasets (v2+)

- `datasets/flights.json` — 15 flights
- `datasets/hotels.json` / `hotels_broken.json`
- `datasets/exchange_rates.json`

## Quick Start

```bash
cd wanderbot/wanderbot-v6 && agentcore dev
```

## Deploy

```bash
cd wanderbot/wanderbot-v6 && agentcore deploy
```
