# Bedrock Strands Agent — WanderBot

Horizon Travel's AI travel assistant built with Strands Agents and Amazon Bedrock AgentCore.

## Versions

| Version | Directory | Features |
|---------|-----------|----------|
| v1 | `wanderbot/` | Basic agent with calculator, current time, travel persona |
| v2 | `wanderbot-v2/` | Function calling with flight search, hotel search, currency exchange |
| v3 | `wanderbot-v3/` | Structured outputs with Pydantic validation, machine-readable JSON |
| v4 | `wanderbot-v4/` | AgentCore Memory — session-scoped short-term memory via HookProvider |

## Feature Comparison

| Feature | v1 | v2 | v3 | v4 |
|---------|:--:|:--:|:--:|:--:|
| Strands Agent | ✅ | ✅ | ✅ | ✅ |
| BedrockModel (Nova Lite) | ✅ | ✅ | ✅ | ✅ |
| `calculator` tool | ✅ | ✅ | ✅ | ✅ |
| `current_time` tool | ✅ | ✅ | ✅ | ✅ |
| `search_flights` tool | — | ✅ | ✅ | ✅ |
| `search_hotels` tool | — | ✅ | ✅ | ✅ |
| `get_exchange_rate` tool | — | ✅ | ✅ | ✅ |
| Pydantic input validation | — | — | ✅ | ✅ |
| Pydantic output validation | — | — | ✅ | ✅ |
| `model_dump_json()` returns | — | — | ✅ | ✅ |
| Custom datasets (JSON) | — | ✅ | ✅ | ✅ |
| Tool chaining | — | ✅ | ✅ | ✅ |
| `src/` layout | — | — | ✅ | ✅ |
| AgentCore Memory | — | — | — | ✅ |
| `HookProvider` | — | — | — | ✅ |
| `session_id` / `actor_id` | — | — | — | ✅ |

## Datasets (v2, v3)

- `datasets/flights.json` — 15 flights across 6 airlines
- `datasets/hotels.json` — 10 hotels in 4 cities
- `datasets/exchange_rates.json` — 15 currency exchange rates

## Quick Start

```bash
# v1
cd wanderbot && agentcore dev

# v2
cd wanderbot-v2 && agentcore dev

# v3
cd wanderbot-v3 && agentcore dev
```

## Deploy

```bash
cd wanderbot-v3 && agentcore deploy
```
