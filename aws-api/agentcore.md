# Amazon Bedrock AgentCore — Lessons Learned

## Overview

There are **two distinct AWS services** for building agents on Bedrock. They are NOT the same API version — they are separate products:

| Service | boto3 Client | Status | Notes |
|---------|--------------|--------|-------|
| **Bedrock Agents (Classic)** | `bedrock-agent` | In maintenance mode (no new agent creation) | Older service. Uses `create_agent`, action groups, agent aliases |
| **Bedrock AgentCore** | `bedrock-agentcore` + `bedrock-agentcore-control` | Actively developed (current) | Newer service. Uses Gateways + Targets + Agent Runtimes |

**Important:** The original demo code was written for **AgentCore**, but many online examples and the Udacity course may reference **Bedrock Agents (Classic)**. They are different APIs — do not mix them.

### Bedrock Agents (Classic) — Key Facts

- Client: `boto3.client("bedrock-agent")`
- Creates agents with `create_agent(agentName=..., instruction=..., foundationModel=..., agentResourceRoleArn=...)`
- Tools attached via **action groups** (`create_agent_action_group`)
- Deployed via **agent aliases** (`create_agent_alias`)
- **As of Aug 2026: in maintenance mode** — new agent creation returns:
  `Bedrock Agents is in Maintenance Mode. New agent creation is not available for accounts without prior service usage.`

### AgentCore — Key Facts

- Two clients: `bedrock-agentcore` (runtime) and `bedrock-agentcore-control` (control plane)
- Tools exposed via **Gateway → Targets** (MCP protocol)
- Deployed as **Agent Runtime** (`create_agent_runtime`)
- Runs the ReAct loop server-side

## Architecture (AgentCore)

```
User → chat.py → AgentCore Harness (ReAct Loop) → Gateway → Lambda Tools
                              ↓
                    Thought → Action → Observation → Answer
```

## Key Learnings

### 1. Two Different API Clients (AgentCore only)

AgentCore uses **two separate boto3 clients**:

| Client | Purpose | Methods |
|--------|---------|---------|
| `bedrock-agentcore` | Runtime operations | `invoke_agent_runtime`, `invoke_agent_runtime_command` |
| `bedrock-agentcore-control` | Control plane operations | `create_gateway`, `create_gateway_target`, `create_agent_runtime`, `list_agent_runtimes` |

```python
# WRONG - using same client for everything
bedrock = boto3.client("bedrock-agentcore", region_name="us-east-1")
bedrock.create_gateway(...)  # ❌ AttributeError: no create_gateway

# CORRECT - use separate clients
bedrock = boto3.client("bedrock-agentcore", region_name="us-east-1")
bedrock_control = boto3.client("bedrock-agentcore-control", region_name="us-east-1")
bedrock_control.create_gateway(...)  # ✅ Works
```

### 2. Gateway Creation Parameters

The `create_gateway` API (AgentCore) requires specific parameters:

```python
# WRONG - wrong field names
bedrock_control.create_gateway(
    gatewayName="my-gateway",  # ❌ Wrong name
    roleArn=role_arn,
    authorizerType="CUSTOM_JWT"  # ❌ Requires authorizerConfiguration
)

# CORRECT
bedrock_control.create_gateway(
    name="my-gateway",  # ✅ Correct name
    roleArn=role_arn,
    authorizerType="NONE",  # ✅ No authorizer config needed
    protocolType="MCP"  # ✅ Required
)
```

**Required fields:** `name`, `roleArn`, `authorizerType`

### 3. Gateway Target Creation Parameters (Lambda)

The `create_gateway_target` API requires:
- `gatewayIdentifier` (NOT `gatewayId`)
- `name` (NOT `targetName`)
- `credentialProviderConfigurations` — **required list, min 1 item**
- `targetConfiguration` — nested under `mcp.lambda`

**Critical discovery — credential provider:**
Lambda targets only support `GATEWAY_IAM_ROLE` as the `credentialProviderType`. Other types (`OAUTH`, `API_KEY`, `CALLER_IAM_CREDENTIALS`, `JWT_PASSTHROUGH`) fail. The `iamCredentialProvider` sub-structure is NOT accepted for Lambda targets — pass the type only.

```python
credential_config = [
    {"credentialProviderType": "GATEWAY_IAM_ROLE"}
]

bedrock_control.create_gateway_target(
    gatewayIdentifier=gateway_id,        # ✅ NOT gatewayId
    name="weather",                      # ✅ NOT targetName
    description="Weather lookup tool",
    credentialProviderConfigurations=credential_config,  # ✅ REQUIRED
    targetConfiguration={
        "mcp": {
            "lambda": {
                "lambdaArn": lambda_arn,
                "toolSchema": {
                    "inlinePayload": [        # ✅ List of tool defs
                        {
                            "name": "get_weather",
                            "description": "Get current weather for a city on a specific date",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "city": {"type": "string", "description": "The city name"},
                                    "date": {"type": "string", "description": "The date in YYYY-MM-DD format"}
                                },
                                "required": ["city", "date"]
                            }
                        }
                    ]
                }
            }
        }
    }
)
```

**Tool schema goes inline** under `targetConfiguration.mcp.lambda.toolSchema.inlinePayload` — NOT as a top-level `toolSchema` argument.

### 4. Agent Runtime Creation (AgentCore)

`create_agent_runtime` requires:
- `agentRuntimeName` (NOT `name`)
- `agentRuntimeArtifact` — contains either `codeConfiguration` (S3 code) or `containerConfiguration` (container image)
- `roleArn`

```python
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

**Key constraint discovered:** Agent Runtime now expects application code (stored in S3) — it is a general runtime host, NOT a simple "prompt + tools" definition like the old harness API. This means the original demo's `modelId`/`instructionPrompt`/`tools` parameters no longer exist. For a quick lab, create the Agent Runtime via the **AWS Console** (it provides a UI for model + prompt + tools), then use boto3 only for `invoke_agent_runtime`.

**Working alternative we confirmed:** Bedrock Agents (Classic) `create_agent` is simpler (only `agentName` required), but it is in maintenance mode and blocked for new accounts — so AgentCore is the only path.

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

## Two Services, Not an API Change

**Clarification:** The AgentCore API did NOT "change" from the original demo code. The original demo was written for **AgentCore**, but there is a separate, older product — **Bedrock Agents (Classic)** — that many tutorials reference. They are different services with different clients and different APIs. Do not assume one evolved from the other.

| Concept | Bedrock Agents (Classic) | AgentCore |
|---------|--------------------------|-----------|
| Client | `bedrock-agent` | `bedrock-agentcore` + `bedrock-agentcore-control` |
| Resource | Agent + Action Group | Gateway + Target + Agent Runtime |
| Tool wiring | Action group → Lambda | Target (MCP) → Lambda |
| Deploy | Agent Alias | Agent Runtime |
| Create call | `create_agent(agentName=...)` | `create_agent_runtime(agentRuntimeName=..., agentRuntimeArtifact=...)` |
| Status | Maintenance mode (no new agents) | Current / actively developed |

### Current Status (as of August 2026)

| Resource | Status |
|----------|--------|
| Gateway creation | ✅ Works (`bedrock-agentcore-control.create_gateway`) |
| Gateway targets | ✅ Works with `credentialProviderConfigurations=[{"credentialProviderType": "GATEWAY_IAM_ROLE"}]` |
| Agent runtime (boto3) | ⚠️ Requires S3 code artifact (`agentRuntimeArtifact`) — not a simple prompt+tools call |
| Agent runtime (console) | ✅ Works — use console UI for model + prompt + tools, then `invoke_agent_runtime` |
| Bedrock Agents (classic) | ❌ Maintenance mode, new creation blocked for this account |

### Gateway Target Creation (Working)

```python
bedrock_control.create_gateway_target(
    gatewayIdentifier=gateway_id,
    name="weather",
    description="Weather lookup tool",
    credentialProviderConfigurations=[
        {"credentialProviderType": "GATEWAY_IAM_ROLE"}
    ],
    targetConfiguration={
        "mcp": {
            "lambda": {
                "lambdaArn": lambda_arn,
                "toolSchema": {
                    "inlinePayload": [
                        {
                            "name": "get_weather",
                            "description": "Get weather for a city",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "city": {"type": "string"}
                                },
                                "required": ["city"]
                            }
                        }
                    ]
                }
            }
        }
    }
)
```

### Agent Runtime (Requires Console)

The `create_agent_runtime` API now requires:
- `agentRuntimeName`
- `agentRuntimeArtifact` with S3 code storage
- `roleArn`

**Workaround:** Create agent runtime via AWS Console, then use boto3 for `invoke_agent_runtime`.

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
