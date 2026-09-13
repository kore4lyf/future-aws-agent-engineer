# Web Browser Search Agent — AgentCore Browser Example

Standalone browser-only example (not WanderBot): live Wikivoyage lookups via managed headless Chrome.

## Project Structure

```
web-browser-search-agent/
├── main.py               # Root shim → src/main.py
├── src/
│   ├── main.py           # AgentCoreBrowser(session_timeout=600) + tools=[browser.browser]
│   └── prompts/system.py # Wikivoyage trusted-domain prompt
├── pyproject.toml        # + playwright
└── .bedrock_agentcore.yaml
```

## Exercise Checklist

- [x] `from strands_tools.browser import AgentCoreBrowser`
- [x] Per-request `AgentCoreBrowser(session_timeout=600)` (own isolated session)
- [x] `tools=[browser.browser]` (tool object, not instance) + model + system prompt
- [ ] Deploy + two queries + Live View (Browser → Sessions in console)

## Test

```bash
agentcore dev
agentcore invoke --dev '{"message": "What neighbourhoods should I stay in when visiting Tokyo?"}'
agentcore invoke --dev '{"message": "Give me a brief travel overview of Barcelona."}'
```

While a call runs: AWS Console → Bedrock → AgentCore → Browser → Sessions → Live View.
