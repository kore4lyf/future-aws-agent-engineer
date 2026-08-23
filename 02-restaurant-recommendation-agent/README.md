# Restaurant Recommendation Agent

This exercise builds a restaurant recommendation agent using the Amazon Bedrock AgentCore managed harness. The agent uses the ReAct pattern to recommend restaurants based on user preferences and real availability data.

## Architecture

```
User → invoke_agent.py → AgentCore Harness → ReAct Loop → Lambda Tools → Response
                                              ↓
                              ┌───────────────┼───────────────┐
                              │               │               │
                      get_cuisines    search_restaurants    get_availability
                      (Lambda)        (Lambda)              (Lambda)
```

## Prerequisites

- Python 3.11+
- AWS credentials with Bedrock access in `us-east-1`
- Required packages: `boto3`, `python-dotenv`

## Files

| File | Purpose |
|------|---------|
| `template.yaml` | CloudFormation template for Lambda functions and IAM roles |
| `setup_agent.py` | Creates Gateway and harness with SYSTEM_PROMPT and tools |
| `invoke_agent.py` | Tests the agent with a user message |
| `cleanup.py` | Deletes all resources |
| `.env` | AWS credentials (not committed to git) |
| `.gitignore` | Prevents secrets from being committed |
| `demo_config.json` | Generated config (created by setup_agent.py) |

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Deploy CloudFormation stack (Lambda functions + IAM roles)
aws cloudformation deploy \
  --template-file template.yaml \
  --stack-name restaurant-agent \
  --capabilities CAPABILITY_NAMED_IAM \
  --region us-east-1

# 3. Create Gateway and harness
python setup_agent.py

# 4. Test the agent
python invoke_agent.py "Find me an Italian restaurant for tonight."

# 5. Clean up when done
python cleanup.py
```

## How It Works

1. **User sends a message** → `invoke_agent.py` invokes the AgentCore harness
2. **Harness runs ReAct loop** server-side:
   - **Thought:** Model reasons about which tools to call
   - **Action:** Model calls `cuisines___get_cuisines`, `restaurants___search_restaurants`, and/or `availability___get_availability`
   - **Observation:** Results fed back to model
   - **Final Answer:** Model generates response grounded in tool results
3. **Response streams** back showing each tool call and result

## Tool Flow

The agent should call all three tools in order:
1. `get_cuisines` — Discover available cuisine types
2. `search_restaurants` — Find restaurants matching user's preference
3. `get_availability` — Confirm each restaurant has availability tonight

## Tool Naming Convention

Tools are namespaced as `<targetName>___<toolName>`:
- `cuisines___get_cuisines` — Cuisine types lookup
- `restaurants___search_restaurants` — Restaurant search
- `availability___get_availability` — Availability check

**Important:** Only letters, digits, and underscores allowed. Dashes break tool calling.

## Debugging

```bash
# Enable debug mode to see raw stream events
python invoke_agent.py --debug "Find me an Italian restaurant for tonight?"

# Check Lambda logs in CloudWatch
# Log groups: /aws/lambda/restaurant-agent-get-cuisines
#             /aws/lambda/restaurant-agent-search-restaurants
#             /aws/lambda/restaurant-agent-get-availability
```

## Iterating on the Prompt

To test changes without redeploying Lambdas:

```bash
# Keep the CloudFormation stack
python cleanup.py --keep-stack

# Edit SYSTEM_PROMPT in setup_agent.py
# Recreate just the harness
python setup_agent.py

# Test again
python invoke_agent.py "Find me an Italian restaurant for tonight."
```

## Multi-turn Conversations

Harness sessions are stateful. Re-run with `--session` to continue:

```bash
# First turn
python invoke_agent.py "Find me an Italian restaurant for tonight."
# Output includes: Session: abc123...

# Continue the conversation
python invoke_agent.py --session abc123 "What about Japanese food?"
```

## Success Criteria

A correct implementation:
- Calls all three tools before making a recommendation
- Only recommends restaurants that appear in tool results
- Confirms availability before recommending
- Skips unavailable restaurants and tries the next option
- Never invents restaurants, ratings, or availability

## Model

Uses **Amazon Nova Pro** (`amazon.nova-pro-v1:0`) by default.
