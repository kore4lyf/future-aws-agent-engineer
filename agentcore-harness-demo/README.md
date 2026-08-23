# AgentCore Harness Demo — Automating the ReACT Loop

This demo demonstrates the **ReAct (Reason + Act) pattern** using the Amazon Bedrock AgentCore managed harness. The assistant answers travel questions by fetching real weather data and attraction information through Lambda tools.

## Architecture

```
User → chat.py → AgentCore Harness → ReAct Loop → Lambda Tools → Response
                                    ↓
                         ┌─────────┴─────────┐
                         │                   │
                    get_weather         get_top_attractions
                    (Lambda)            (Lambda)
```

## Prerequisites

- Python 3.11+
- AWS credentials configured for `us-east-1`
- Required packages: `boto3`

## Files

| File | Purpose |
|------|---------|
| `setup.py` | Creates IAM roles, Lambdas, Gateway, and harness |
| `chat.py` | Interactive chat interface with the agent |
| `cleanup.py` | Deletes all created resources |
| `demo_config.json` | Generated config (created by setup.py) |
| `lambda/get_weather/` | Lambda function for weather data |
| `lambda/get_top_attractions/` | Lambda function for attractions data |

## Quick Start

```bash
# 1. Install dependencies
pip install boto3

# 2. Set up all resources
python setup.py

# 3. Chat with the assistant
python chat.py "I'll be in London this Saturday with my family. What should we do?"

# 4. Interactive mode (multi-turn)
python chat.py

# 5. Clean up when done
python cleanup.py
```

## How It Works

1. **User sends a message** → `chat.py` invokes the AgentCore harness
2. **Harness runs ReAct loop** server-side:
   - **Thought:** Model reasons about what tools to call
   - **Action:** Model calls `weather___get_weather` and/or `attractions___get_top_attractions`
   - **Observation:** Results fed back to model
   - **Final Answer:** Model generates response grounded in tool results
3. **Response streams** back showing each tool call and result

## Tool Naming Convention

Tools are namespaced as `<targetName>___<toolName>`:
- `weather___get_weather` — Weather lookup
- `attractions___get_top_attractions` — Attractions lookup

**Important:** Only letters, digits, and underscores allowed. Dashes break tool calling.

## Debugging

```bash
# Enable debug mode to see raw stream events
python chat.py --debug "What's the weather in Paris?"

# Check Lambda logs in CloudWatch
# Log groups: /aws/lambda/demo3-get-weather
#             /aws/lambda/demo3-get-top-attractions
```

## Session Management

- Each `chat.py` invocation creates a new session by default
- Interactive mode maintains session across turns (multi-turn conversations)
- Sessions are stateful — follow-up questions keep context

## Model

Uses **Amazon Nova Pro** (`amazon.nova-pro-v1:0`) by default.
