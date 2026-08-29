# Amazon Bedrock AgentCore — Lessons Learned

## Overview

There are **two distinct AWS services** for building agents on Bedrock. They are NOT the same API version — they are separate products:

| Service | boto3 Client | Status | Notes |
|---------|--------------|--------|-------|
| **Bedrock Agents (Classic)** | `bedrock-agent` | In maintenance mode (no new agent creation) | Older service. Uses `create_agent`, action groups, agent aliases |
| **Bedrock AgentCore** | `bedrock-agentcore` (runtime) + `bedrock-agentcore-control` (control) | Actively developed (current) | Newer service. Uses **Gateways + Targets + Harness** |

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
- Deployed as a **Harness** via `create_harness` (NOT `create_agent_runtime`)
- Runs the ReAct loop server-side
- Invoked via `invoke_harness` (NOT `invoke_agent_runtime`)

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
| `bedrock-agentcore` | Runtime operations | `invoke_harness`, `invoke_agent_runtime`, `invoke_agent_runtime_command` |
| `bedrock-agentcore-control` | Control plane operations | `create_gateway`, `create_gateway_target`, `create_harness`, `list_harnesses` |

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

### 4. Harness Creation — `create_harness` (NOT `create_agent_runtime`)

**Critical correction:** The original demo failed because it called `create_agent_runtime`, which is the **wrong** control-plane method for a managed ReAct harness. The correct method is **`create_harness`** (on `bedrock-agentcore-control`). This is the AgentCore equivalent of the original intent — it takes a model, system prompt, and tools directly. **No S3 code storage is needed.** (There is also a separate `create_agent_runtime` for shipping your own application code/container, but that is a different use case.)

**Required fields:** `harnessName`, `executionRoleArn`

```python
harness = bedrock_control.create_harness(
    harnessName="demo3-harness",
    executionRoleArn=role_arn,                       # IAM role (AgentCore + Lambda trust)
    model={
        "bedrockModelConfig": {
            "modelId": "amazon.nova-lite-v1:0"        # ✅ Nested under bedrockModelConfig
        }
    },
    systemPrompt=[{"text": SYSTEM_PROMPT}],           # ✅ List of {text}, not a string
    tools=[
        {
            "type": "agentCoreGateway",
            "name": "weather___get_weather",
            "config": {
                "agentCoreGateway": {
                    "gatewayArn": gateway_arn,        # ✅ ARN of the Gateway, not inline schema
                    "outboundAuth": {"none": {}}
                }
            }
        },
        {
            "type": "agentCoreGateway",
            "name": "attractions___get_top_attractions",
            "config": {
                "agentCoreGateway": {
                    "gatewayArn": gateway_arn,
                    "outboundAuth": {"none": {}}
                }
            }
        }
    ]
)
harness_arn = harness["harnessArn"]
```

**Key shape notes (verified from the boto3 service model):**
- `model` is a structure with `bedrockModelConfig.modelId` (not a flat `modelId`)
- `systemPrompt` is a **list** of `{text: ...}`, not a plain string
- `tools[].type` must be `"agentcore_gateway"` (snake_case enum; allowed values: `remote_mcp`, `agentcore_code_interpreter`, `agentcore_gateway`, `agentcore_browser`, `inline_function`). The tool config references the **Gateway ARN** (`agentCoreGateway.gatewayArn`). The tool name still uses the `target___tool` namespacing.
- Gateway ARN is obtained from `get_gateway(gatewayIdentifier=...)` → `gatewayArn` (note: `list_gateways` returns `gatewayId`, but `create_harness` needs the full ARN).
- `harnessName` must match `^[a-zA-Z][a-zA-Z0-9_]{0,39}$` — **no dashes** (use `demo3_harness`, not `demo3-harness`).
- `create_harness` response is wrapped: `response["harness"]["harnessId"]` and `response["harness"]["arn"]` (the field is `arn`, not `harnessArn`).
- `invoke_harness` requires `harnessArn` (use the `arn` value) + `runtimeSessionId` (33–43 chars) + `messages` as `[{role, content:[{text}]}]`.

### 5. Invoking the Harness — `invoke_harness` (NOT `invoke_agent_runtime`)

Once created, invoke with **`invoke_harness`** on the **runtime** client (`bedrock-agentcore`), not `invoke_agent_runtime` (which is for the code-artifact Agent Runtime).

```python
runtime = boto3.client("bedrock-agentcore", region_name="us-east-1")

response = runtime.invoke_harness(
    harnessArn=harness_arn,
    runtimeSessionId=session_id,               # 33-43 char session id
    messages=[{"role": "user", "content": [{"text": "I'll be in London Saturday. What should we do?"}]}]
)

# Streaming events
for event in response.get("events", []):
    if "chunk" in event:
        text = event["chunk"]["bytes"].decode("utf-8")
    elif "toolCall" in event:
        name = event["toolCall"]["name"]
        args = event["toolCall"]["arguments"]
    elif "toolResult" in event:
        result = event["toolResult"]["result"]
```

**Note:** `runtimeSessionId` must be 33–43 characters (use the UUID-padding trick from the original `chat.py`).

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
| Client | `bedrock-agent` | `bedrock-agentcore` (runtime) + `bedrock-agentcore-control` (control) |
| Resource | Agent + Action Group | Gateway + Target + **Harness** |
| Tool wiring | Action group → Lambda | Target (MCP) → Lambda |
| Deploy | Agent Alias | Harness (`create_harness` / `invoke_harness`) |
| Create call | `create_agent(agentName=...)` | `create_harness(harnessName=..., executionRoleArn=..., model=..., systemPrompt=..., tools=...)` |
| Status | Maintenance mode (no new agents) | Current / actively developed |

### Current Status (as of August 2026)

| Resource | Status |
|----------|--------|
| Gateway creation | ✅ Works (`bedrock-agentcore-control.create_gateway`) |
| Gateway targets | ✅ Works with `credentialProviderConfigurations=[{"credentialProviderType": "GATEWAY_IAM_ROLE"}]` |
| Harness creation | ✅ Works (`create_harness` — model + prompt + tools, no S3 needed) |
| Harness invocation | ✅ Works (`invoke_harness` on runtime client) |
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

### Working End-to-End Pattern (verified)

1. `create_gateway` → get `gatewayId`, then `get_gateway(gatewayIdentifier=...)` → `gatewayArn`
2. `create_gateway_target` (one per tool, `credentialProviderConfigurations=[{"credentialProviderType": "GATEWAY_IAM_ROLE"}]`)
3. `create_harness(harnessName=..., executionRoleArn=..., model={bedrockModelConfig:{modelId}}, systemPrompt=[{text}], tools=[{type:"agentCoreGateway", name, config:{agentCoreGateway:{gatewayArn, outboundAuth:{none:{}}}}}]})`
4. Wait for harness `status == "READY"` (poll `get_harness`)
5. `invoke_harness(harnessArn=..., runtimeSessionId=..., messages=[...])` on the **runtime** client

**Note:** `create_agent_runtime` / `invoke_agent_runtime` exist but are for the *code-artifact* runtime (your own app code in S3/container). For the managed ReAct harness, always use `create_harness` / `invoke_harness`.

## Recommendations

### For Learning

1. **Use `create_harness` / `invoke_harness`** — the managed ReAct harness, no code packaging needed
2. **Reference Gateway ARN in tools**, not inline schemas (schemas live on the Target)
3. **Document the two services** — AgentCore (Harness) vs Agents (Classic) use different clients

### For Production

1. **Pin boto3 version** — AgentCore is actively developed; shapes can shift
2. **Use CloudFormation/SAM** — infrastructure as code is more reliable
3. **Monitor AWS announcements** — AgentCore adds capabilities (browser, code interpreter, memory) regularly

## Alternative: AWS Console

For a visual walkthrough:

1. Go to **Bedrock → AgentCore → Gateways** → create gateway (MCP)
2. Add targets (Lambda functions) with `GATEWAY_IAM_ROLE` credential
3. Go to **AgentCore → Harnesses** → create harness (model + system prompt + gateway tools)
4. Test in the console playground

Then use boto3 for runtime:

```python
bedrock = boto3.client("bedrock-agentcore", region_name="us-east-1")

response = bedrock.invoke_harness(
    harnessArn="arn:aws:bedrock-agentcore:us-east-1:123456789012:harness/demo3-harness/...",
    runtimeSessionId="session-1234567890123456789abc",
    messages=[{"role": "user", "content": [{"text": "Hello"}]}]
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

---

## ⚠️ AgentCore Gateway Console — Schema Gotchas (Aug 2026)

When creating a Gateway target via the AWS Console, the "In-line schema editor" rejects single-object and duplicate entries. This bit us while deploying the demo from the UI. Capture for next time.

### 1. Must be an **array** of 2+ tool objects — not a single object

The JSON Schema spec defines an object as `{...}`. The Console's inline editor expects a JSON **array** of tool definitions, **and the array must contain at least 2 entries** — otherwise the API returns:

```
ValidationException: Value at
'targetConfiguration.mcp.lambda.toolSchema.inlinePayload.1.member.inputSchema'
failed to satisfy constraint: Member must not be null
```

(The `1.member` path means "the second entry in the array, which is null/missing.")

**WRONG (single object):**

```json
{
  "type": "object",
  "properties": { "city": {"type": "string"} },
  "required": ["city"]
}
```

**CORRECT (array of 2 tools):**

```json
[
  { "name": "get_weather", "description": "...", "inputSchema": { "type": "object", "properties": {...}, "required": [...] } },
  { "name": "get_weather_secondary", "description": "duplicate to satisfy UI", "inputSchema": { ... } }
]
```

Note each tool is `{name, description, inputSchema}` — **not** `{type, properties, required}`. The `type/properties/required` go **inside** `inputSchema`.

### 2. Tool names within a target must be **unique**

The API rejects `Duplicate tool found in target configuration: <name>`. So the second placeholder must use a distinct name (e.g. `<tool>_secondary` or `<tool>_dup`).

### 3. Confirmed working shape (single-tool target via Console)

```json
[
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
  },
  {
    "name": "get_weather_secondary",
    "description": "Placeholder; satisfies Console's 2-tool minimum",
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
```

The placeholder tool is never invoked at runtime — only the first one is referenced from the Harness via the Gateway's `agentcore_gateway` tool config.

### 4. How to avoid this in code (boto3)

When calling `create_gateway_target` programmatically (as `setup.py` does), pass a single tool in `inlinePayload`:

```python
targetConfiguration = {
    "mcp": {
        "lambda": {
            "lambdaArn": lambda_arn,
            "toolSchema": {
                "inlinePayload": [
                    {
                        "name": "get_weather",
                        "description": "Get current weather for a city on a specific date",
                        "inputSchema": {"type": "object", "properties": {...}, "required": [...]}
                    }
                ]
            }
        }
    }
}
```

The 2-tool minimum is a **Console-only** constraint; the boto3 API accepts a 1-element array.

### 5. Symptom → fix cheat sheet

| Symptom | Cause | Fix |
|---------|-------|-----|
| `inlinePayload.1.member.* Member must not be null` | Only 1 tool in array | Add a second tool object (with a unique name) |
| `Duplicate tool found in target configuration: <name>` | Second tool reused first tool's name | Give it a unique name like `<tool>_secondary` |
| `Member must be a structure` | Pasted raw schema (`{type, properties, ...}`) instead of tool array | Wrap in `[ {...}, {...} ]` with `name` and `description` at the top level of each tool |

**Lesson:** When the Console asks for "inline schema" on an AgentCore Gateway target, paste an **array of at least 2 tool objects**, each with a **unique `name`**, a `description`, and an `inputSchema` object. Do not paste a JSON Schema object.
