# AWS API Discovery Scripts

Reusable Python scripts for verifying the live AWS API surface while
developing Bedrock / AgentCore code. All scripts read credentials from the
project-root `.env` (two levels up).

## Prerequisites

- `boto3`, `python-dotenv`
- A `.env` at the project root with `AWS_ACCESS_KEY_ID`,
  `AWS_SECRET_ACCESS_KEY`, optional `AWS_SESSION_TOKEN`,
  `AWS_REGION=us-east-1`, `MODEL_ID=amazon.nova-lite-v1:0`

## Scripts

| Script | Purpose | Usage |
|--------|---------|-------|
| `list_client_ops.py` | List public operations on a boto3 client | `python list_client_ops.py bedrock-agentcore-control` |
| `inspect_operation.py` | Dump input/output shape of an operation | `python inspect_operation.py bedrock-agentcore-control CreateHarness` |
| `list_agentcore_resources.py` | List all gateways, targets, agent runtimes, harnesses in the region | `python list_agentcore_resources.py` |
| `inspect_gateway.py` | Show a gateway + all its targets with full detail | `python inspect_gateway.py demo3-gateway` |

## Examples

```bash
# What operations does the AgentCore control plane expose?
python list_client_ops.py bedrock-agentcore-control

# What does create_harness actually require?
python inspect_operation.py bedrock-agentcore-control CreateHarness

# What does invoke_harness accept?
python inspect_operation.py bedrock-agentcore InvokeHarness

# What's currently deployed?
python list_agentcore_resources.py

# Dump a specific gateway and its targets
python inspect_gateway.py demo3-gateway
```

## Notes

- The scripts only **read** state — they do not create or delete anything.
- `inspect_operation.py` reads the boto3 service model (no API calls), so it's
  safe to run even with expired credentials (as long as `boto3` is installed).
- The other scripts make live AWS API calls and require valid credentials.
- Add new scripts here as you discover new APIs; keep `_common.py` as the
  single source of truth for env loading and client construction.
