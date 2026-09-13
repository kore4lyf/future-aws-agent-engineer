# Long-Term Memory Agent — Horizon Travel (Standalone)

Cross-session memory via **AgentCore Memory (SEMANTIC + USER_PREFERENCE)** backed by DynamoDB + Bedrock.

## Architecture
```
User message → MessageAddedEvent → retrieve_memories(namespace=/users/{actor_id}, top_k=3) → inject into prompt
Agent completes → AfterInvocationEvent → create_event(USER, ASSISTANT) → persisted to Memory
```

## Setup
1. Create Memory in AgentCore → Memory → Create
   - Name: `WanderBot-LTM`
   - Strategies: `SEMANTIC` (facts), `USER_PREFERENCE` (window seat, dietary needs)
   - Namespaces: `/users/{actorId}` and `/users/{actorId}/preferences`
2. Copy `MEMORY_ID` → set in `.env` / deploy env
3. `uv sync && uv run python -m src.main` or `agentcore dev`

## Wiring
```python
memory_client = MemoryClient(region_name="us-east-1")
hooks = [LongTermMemoryHookProvider(memory_client, MEMORY_ID)]
agent = Agent(model=model, system_prompt=SYSTEM_PROMPT, hooks=hooks)
agent.state.set("actor_id", payload.get("actor_id", "default"))
agent.state.set("session_id", payload.get("session_id", "default"))
```

## Env
```
MEMORY_ID=abc123
AWS_REGION=us-east-1
```
