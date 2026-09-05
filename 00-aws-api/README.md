# AWS API Notes — Lessons Learned

This folder contains notes and lessons learned from working with AWS Bedrock services.

## Purpose

These notes serve as a reference for future development, documenting:
- API quirks and gotchas
- Common mistakes and how to fix them
- Cost optimization strategies
- Debugging tips

## Contents

### [Bedrock Flows](./bedrock-flows.md)

Notes on building visual AI workflows with Bedrock Flows.

**Key Topics:**
- Node types and required input/output names
- Expression syntax (`$.data` format)
- Condition node requirements
- Connection patterns
- Cost optimization with model selection

**Status:** ✅ Working — flow created and tested successfully

### [AgentCore](./agentcore.md)

Notes on building agents with Amazon Bedrock AgentCore.

**Key Topics:**
- Two API clients (`bedrock-agentcore` vs `bedrock-agentcore-control`)
- Gateway and target creation
- Agent runtime creation (API has changed)
- Tool naming conventions
- Session management

**Status:** ✅ Working — AgentCore uses `create_harness` / `invoke_harness` (verified against boto3 service model)

## Quick Reference

### Bedrock Flows

```python
# Create flow
bedrock_agent = boto3.client("bedrock-agent", region_name="us-east-1")

response = bedrock_agent.create_flow(
    name="my-flow",
    executionRoleArn=role_arn,
    definition={
        "nodes": [...],
        "connections": [...]
    }
)

# Invoke flow
bedrock_runtime = boto3.client("bedrock-runtime", region_name="us-east-1")

response = bedrock_runtime.invoke_flow(
    flowIdentifier=flow_id,
    flowAliasIdentifier=alias_arn,
    inputs=[{"nodeOutputName": "document", "content": {"document": "Hello"}}]
)
```

### AgentCore (Harness)

```python
# Control client — create gateway + harness
bedrock_control = boto3.client("bedrock-agentcore-control", region_name="us-east-1")

response = bedrock_control.create_gateway(
    name="my-gateway",
    roleArn=role_arn,
    authorizerType="NONE",
    protocolType="MCP"
)

response = bedrock_control.create_harness(
    harnessName="my-harness",
    executionRoleArn=role_arn,
    model={"bedrockModelConfig": {"modelId": "amazon.nova-lite-v1:0"}},
    systemPrompt=[{"text": "You are a helpful assistant."}],
    tools=[{"type": "agentCoreGateway", "name": "weather___get_weather",
            "config": {"agentCoreGateway": {"gatewayArn": gateway_arn, "outboundAuth": {"none": {}}}}}]
)

# Runtime client — invoke harness
bedrock = boto3.client("bedrock-agentcore", region_name="us-east-1")

response = bedrock.invoke_harness(
    harnessArn=harness_arn,
    runtimeSessionId="session-1234567890123456789abc",
    messages=[{"role": "user", "content": [{"text": "Hello"}]}]
)
```

## Common Patterns

### .env File Structure

```bash
# AWS Credentials
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
AWS_SESSION_TOKEN=...
AWS_DEFAULT_REGION=us-east-1

# Shared Config
AWS_REGION=us-east-1
MODEL_ID=amazon.nova-lite-v1:0
```

### Loading .env in Python

```python
from dotenv import load_dotenv
import os
from pathlib import Path

# Load from root .env (one level up)
root_dir = Path(__file__).parent.parent
load_dotenv(root_dir / ".env")

# Use environment variables
REGION = os.getenv("AWS_REGION", "us-east-1")
MODEL_ID = os.getenv("MODEL_ID", "amazon.nova-lite-v1:0")
```

## Cost Optimization

### Model Selection

| Model | Input (per 1M) | Output (per 1M) | Use When |
|-------|----------------|------------------|----------|
| Nova Micro | $0.035 | $0.14 | Simple classification |
| Nova Lite | $0.06 | $0.24 | Most tasks |
| Nova Pro | $0.80 | $3.20 | Complex reasoning |

### Bedrock Flows

- **Node transitions:** $0.035 per 1,000 nodes
- **Model invocation:** Standard Bedrock pricing
- **Recommendation:** Use Nova Lite for most tasks

### AgentCore

- **Gateway:** $0.005 per 1,000 tool invocations
- **Agent Runtime:** $0.0895 per vCPU-hour, $0.00945 per GB-hour
- **Lambda:** Standard Lambda pricing
- **Model:** Standard Bedrock pricing

## Next Steps

1. **Update AgentCore code** for new API
2. **Create CloudFormation templates** for infrastructure as code
3. **Add more Lambda functions** for different tools
4. **Implement proper error handling** and retries
5. **Add monitoring** with CloudWatch

## References

- [Bedrock Flows Documentation](https://docs.aws.amazon.com/bedrock/latest/userguide/flows.html)
- [AgentCore Documentation](https://docs.aws.amazon.com/bedrock/latest/userguide/agentcore.html)
- [Bedrock Pricing](https://aws.amazon.com/bedrock/pricing/)
