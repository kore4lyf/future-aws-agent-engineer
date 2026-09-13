# Observability Agent — Horizon Travel (Standalone)

Every invocation as a trace via **aws-opentelemetry-distro** → CloudWatch GenAI Observability.

## Enable
Add to `pyproject.toml` / `requirements.txt`:
```
aws-opentelemetry-distro >= 0.10.0
```
No code change — AgentCore Runtime auto-instruments Strands. Dockerfile auto-wires via `agentcore configure/deploy`.

## Tools
- `search_flights(origin, destination)` — reads `datasets/flights.json`, filters `status != CANCELLED`
- `search_hotels(city, max_price=500.0)` — reads `datasets/hotels.json`, filters `available` + price

## What you get
- **Agent invocation traces**: model, token counts, latency, grouped by runtime session
- **Tool call spans**: inputs, outputs, duration
- **Grouping**: by `runtime session` in GenAI Dashboard (`agentcore stop-session` to break)
- **Other services**: Memory, Gateway, Browser, Code Interpreter traces also appear

## Find traces
CloudWatch → GenAI Observability → Bedrock AgentCore → Sessions → trace tree.
Requires **Transaction Search** enabled (lab IAM may block `application-signals:StartDiscovery` — check Logs `/aws/bedrock-agentcore/runtimes/...` as fallback).

## Run
`uv sync && agentcore dev` then `agentcore invoke '{"prompt": "Find flights from London to Tokyo"}'`
