# WanderBot v4 — Agent State Management with AgentCore Memory

Session-scoped short-term memory via Strands `HookProvider`.

## What's New in v4

- **Custom HookProvider** — plugs into Strands lifecycle
- **AgentInitializedEvent** — injects prior turns from `MemoryClient.get_last_k_turns()` into `system_prompt`
- **MessageAddedEvent** — persists each turn via `memory_client.create_event()`
- **Session scoping** — `session_id` + `actor_id` via `agent.state`

## Project Structure

```
wanderbot-v4/
├── main.py                        # Root shim → src/main.py
├── src/
│   ├── main.py                    # Agent entrypoint + memory wiring
│   ├── hooks/
│   │   └── memory.py              # MemoryHookProvider
│   ├── tools/                     # search_flights, search_hotels, get_exchange_rate
│   ├── schemas/                   # Pydantic models
│   ├── prompts/system.py          # SYSTEM_PROMPT
│   └── datasets/
└── .bedrock_agentcore.yaml        # entrypoint: main.py
```

## Memory Flow

1. `invoke(payload)` extracts `session_id`/`actor_id` from payload/context
2. `MemoryHookProvider` registered via `hooks=[...]`
3. On `AgentInitializedEvent` → load last k turns → append to `system_prompt`
4. On `MessageAddedEvent` → `create_event(session_id, actor_id, role, content)`

## Dev

```bash
agentcore dev
agentcore invoke --dev '{"message": "I want to go to Barcelona", "session_id": "sess-123", "actor_id": "user-1"}'
agentcore invoke --dev '{"message": "What did I just say?", "session_id": "sess-123", "actor_id": "user-1"}'
```

## Deploy

```bash
agentcore deploy
agentcore invoke '{"message": "Show me hotels in Barcelona under 200", "session_id": "sess-123", "actor_id": "user-1"}'
```
