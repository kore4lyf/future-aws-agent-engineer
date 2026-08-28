# Amazon Bedrock AgentCore — Lessons Learned

## Overview

AgentCore is AWS's managed agent runtime that runs the ReAct (Reason + Act) loop for you. You define tools and prompts, AWS handles the orchestration.

## Architecture

```
User → chat.py → AgentCore Harness (ReAct Loop) → Gateway → Lambda Tools
                              ↓
                    Thought → Action → Observation → Answer
```

## Key Learnings

### 1. Two Different API Clients

AgentCore uses **two separate boto3 clients**:

| Client | Purpose | Methods |
|--------|---------|---------|
| `bedrock-agentcore` | Runtime operations | `invoke_agent_runtime`, `invoke_agent_runtime_command` |
| `bedrock-agentcore-control` | Control plane operations | `create_gateway`, `create_gateway_target`, `create_agent_runtime`, `list_agent_runtimes` |

```python
# WRONG - using same client for everything
bedrock = boto3.client("bedrock-agentcore", region_name="us-east-1")
bedrock.create_gateway(...)  # ❌ AttributeError

# CORRECT - use separate clients
bedrock = boto3.client("bedrock-agentcore", region_name="us-east-1")
bedrock_control = boto3.client("bedrock-agentcore-control", region_name="us-east-1")
bedrock_control.create_gateway(...)  # ✅ Works
```

### 2. Gateway Creation Parameters

The `create_gateway` API has specific required parameters:

```python
# WRONG - old parameter names
bedrock_control.create_gateway(
    gatewayName="my-gateway",  # ❌ Wrong name
    roleArn=role_arn,
    authorizerType="CUSTOM_JWT"  # ❌ Requires authorizerConfiguration
)

# CORRECT - new parameter names
bedrock_control.create_gateway(
    name="my-gateway",  # ✅ Correct name
    roleArn=role_arn,
    authorizerType="NONE",  # ✅ No authorizer config needed
    protocolType="MCP"  # ✅ Required
)
```

### 3. Gateway Target Creation Parameters

The `create_gateway_target` API has changed significantly:

```python
# WRONG - old parameter names
bedrock_control.create_gateway_target(
    gatewayId=gateway_id,  # ❌ Wrong name
    targetName="weather",  # ❌ Wrong name
    targetDescription="Weather tool",  # ❌ Wrong name
    targetUri=lambda_arn,  # ❌ Wrong name
    protocolType="MCP",  # ❌ Not a parameter
    toolSchema=[...]  # ❌ Not a parameter
)

# CORRECT - new parameter names
bedrock_control.create_gateway_target(
    gatewayIdentifier=gateway_id,  # ✅ Correct name
    name="weather",  # ✅ Correct name
    description="Weather tool",  # ✅ Correct name
    targetConfiguration={  # ✅ New structure
        "lambda": {
            "lambdaArn": lambda_arn
        }
    }
)
```

### 4. Agent Runtime Creation (Major API Change)

The `create_agent_runtime` API has completely changed:

```python
# OLD API (no longer works)
bedrock_control.create_agent_runtime(
    name="my-harness",
    modelId="amazon.nova-lite-v1:0",
    instructionPrompt="You are a helpful assistant...",
    tools=[...],
    roleArn=role_arn
)

# NEW API (current)
bedrock_control.create_agent_runtime(
    agentRuntimeName="my-harness",
    agentRuntimeArtifact={
        "codeConfiguration": {
            "code": {"s3": {"s3Uri": "s3://bucket/code.zip"}},
            "runtime": "python3.11",
            "entryPoint": ["handler"]
        }
    },
    roleArn=role_arn,
    description="My agent"
)
```

**Key Changes:**
- `name` → `agentRuntimeName`
- `modelId`, `instructionPrompt`, `tools` → `agentRuntimeArtifact`
- Code must be stored in S3
- `entryPoint` is now a list, not a string

### 5. Gateway Response Field Names

The `list_gateways` response uses different field names:

```python
# WRONG - old field names
for gateway in response.get("items", []):
    gateway_name = gateway["gatewayName"]  # ❌ KeyError

# CORRECT - new field names
for gateway in response.get("items", []):
    gateway_name = gateway["name"]  # ✅ Correct
    gateway_id = gateway["gatewayId"]  # ✅ Same
```

### 6. IAM Role Trust Policy

The IAM role must trust both AgentCore AND Lambda:

```python
# WRONG - only AgentCore
trust_policy = {
    "Statement": [{
        "Effect": "Allow",
        "Principal": {"Service": "bedrock-agentcore.amazonaws.com"},
        "Action": "sts:AssumeRole"
    }]
}
# ❌ Lambda cannot assume this role

# CORRECT - both services
trust_policy = {
    "Statement": [{
        "Effect": "Allow",
        "Principal": {
            "Service": ["bedrock-agentcore.amazonaws.com", "lambda.amazonaws.com"]
        },
        "Action": "sts:AssumeRole"
    }]
}
# ✅ Both AgentCore and Lambda can assume this role
```

### 7. Tool Naming Convention

Tools are namespaced as `<targetName>___<toolName>`:

```python
# Tool definitions
tools = [
    {
        "name": "weather___get_weather",  # target___tool
        "description": "Get weather for a city",
        "inputSchema": {...}
    },
    {
        "name": "attractions___get_top_attractions",  # target___tool
        "description": "Get top attractions",
        "inputSchema": {...}
    }
]
```

**Important:** Only letters, digits, and underscores allowed. Dashes break tool calling.

### 8. Session Management

Each invocation needs a session ID for multi-turn conversations:

```python
import uuid

# Generate session ID
session_id = str(uuid.uuid4()).replace("-", "")[:43]
while len(session_id) < 33:
    session_id += str(uuid.uuid4()).replace("-", "")[:10]
session_id = session_id[:43]
```

### 9. Streaming Response Handling

AgentCore streams responses as server-sent events:

```python
for event in response.get("events", []):
    if "chunk" in event:
        # Text chunk
        text = event["chunk"]["bytes"].decode("utf-8")
    elif "toolCall" in event:
        # Tool invocation
        tool_name = event["toolCall"]["name"]
        tool_args = event["toolCall"]["arguments"]
    elif "toolResult" in event:
        # Tool result
        result = event["toolResult"]["result"]
```

## API Versioning Issue

**Warning:** The AgentCore API is evolving rapidly. The original code in this repository was written for an older version and may not work with the current API.

### What Changed

| Feature | Old API | New API |
|---------|---------|---------|
| Gateway creation | `gatewayName` | `name` |
| Gateway target | `gatewayId`, `targetName`, `toolSchema` | `gatewayIdentifier`, `name`, `targetConfiguration` |
| Agent runtime | `name`, `modelId`, `instructionPrompt`, `tools` | `agentRuntimeName`, `agentRuntimeArtifact` |
| Code storage | Inline | S3 only |

### Current Status (as of August 2026)

| Resource | Status |
|----------|--------|
| Gateway creation | ✅ Works with new API |
| Gateway targets | ✅ Works with new API |
| Agent runtime | ⚠️ Requires S3 code storage |
| Tool schemas | ⚠️ May need to be defined differently |

## Recommendations

### For Learning

1. **Use AWS Console** for initial setup — easier to understand the flow
2. **Use boto3 for runtime** — `invoke_agent_runtime` is stable
3. **Document API changes** — the API is evolving rapidly

### For Production

1. **Pin boto3 version** — avoid breaking changes
2. **Use CloudFormation/SAM** — infrastructure as code is more reliable
3. **Monitor AWS announcements** — AgentCore is actively developed

## Alternative Approach: AWS Console

Given the API changes, consider using the AWS Console for setup:

1. Go to **Bedrock → AgentCore → Gateways**
2. Create a gateway with MCP protocol
3. Add targets (Lambda functions)
4. Create an agent runtime
5. Test with the console playground

Then use boto3 for runtime operations:

```python
bedrock = boto3.client("bedrock-agentcore", region_name="us-east-1")

response = bedrock.invoke_agent_runtime(
    agentRuntimeId="your-harness-id",
    sessionId="your-session-id",
    messages=[{"role": "user", "content": "Hello"}]
)
```

## Cost Considerations

### AgentCore Pricing

| Component | Cost |
|-----------|------|
| Gateway | $0.005 per 1,000 tool invocations |
| Agent Runtime | $0.0895 per vCPU-hour, $0.00945 per GB-hour |
| Lambda | Standard Lambda pricing |
| Model invocation | Standard Bedrock pricing |

### Cost Per Invocation

For a simple travel assistant:
- **Gateway:** ~$0.000005 per tool call
- **Agent Runtime:** ~$0.001 per invocation (assuming 1s CPU time)
- **Lambda:** ~$0.0000002 per invocation
- **Model (Nova Lite):** ~$0.0001 per invocation
- **Total:** ~$0.001 per invocation

## Debugging Tips

1. **Enable debug mode** in chat.py to see raw stream events
2. **Check Lambda logs** in CloudWatch
3. **Verify IAM permissions** — role must trust both AgentCore and Lambda
4. **Check tool naming** — must be `target___tool` format
5. **Verify session ID** — must be 33-43 characters

## Files in This Demo

| File | Purpose |
|------|---------|
| `setup.py` | Creates all resources (IAM, Lambda, Gateway, Harness) |
| `chat.py` | Interactive chat interface |
| `cleanup.py` | Deletes all created resources |
| `lambda/get_weather/` | Lambda function for weather data |
| `lambda/get_top_attractions/` | Lambda function for attractions data |
| `requirements.txt` | Python dependencies |

## Lambda Functions

### get_weather.py

Returns hardcoded weather data for London, Paris, and New York.

```python
def lambda_handler(event, context):
    city = event.get("city", "Unknown")
    date = event.get("date", "Unknown")
    
    weather_data = {
        "London": {"condition": "Light rain", "temperature_high": "18C", ...},
        "Paris": {"condition": "Sunny", "temperature_high": "24C", ...},
        "New York": {"condition": "Overcast", "temperature_high": "28C", ...}
    }
    
    return weather_data.get(city, {"condition": "Data not available", ...})
```

### get_top_attractions.py

Returns hardcoded attractions data for London, Paris, and New York.

```python
def lambda_handler(event, context):
    city = event.get("city", "Unknown")
    
    attractions_data = {
        "London": {"attractions": [{"name": "British Museum", ...}, ...]},
        "Paris": {"attractions": [{"name": "Louvre Museum", ...}, ...]},
        "New York": {"attractions": [{"name": "Central Park", ...}, ...]}
    }
    
    return attractions_data.get(city, {"attractions": []})
```
