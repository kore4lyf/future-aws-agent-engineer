# Code Interpreter Agent — Horizon Travel (Standalone)

Exact totals via **AgentCore Code Interpreter** sandbox.

## Architecture
```
User: "2 flights $450 + 3 nights $180, 7% tax, 10% loyalty"
  → LLM writes Python: total = (450*2 + 180*3)*1.07*0.9; print(f"${total:.2f}")
  → calculate_trip_cost(code) → code_session(REGION).invoke("executeCode", {code, language:"python", clearContext:True})
  → streamed stdout → agent formats itemized answer
```

## Why clearContext=True
Prevents state leaking between calls — each execution is isolated, no leftover variables from prior totals.

## Tool
`calculate_trip_cost(code: str) -> str` — runs LLM-written Python in `bedrock_agentcore.tools.code_interpreter_client.code_session`.

## Run
`uv sync && uv run python -m src.main` or `agentcore dev`
Test: `{"message": "Trip: 2 flights $450, 3 nights hotel $180/night, 7% tax, 10% loyalty discount. Total?"}`
