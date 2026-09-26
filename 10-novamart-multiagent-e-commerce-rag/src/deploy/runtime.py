"""
deploy/runtime.py
=================
Task 3b - AgentCore Runtime deployment.

Moved from agent_orchestrator.py lines ~446-508.
"""

from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from agent_observability import wait_for_runtime_ready


__all__ = ['deploy_to_agentcore_runtime']


def deploy_to_agentcore_runtime(
    orchestrator_agent,
    guardrail_id: str,
    guardrail_version: str
) -> str:
    """
    Deploy the multi-agent system to Amazon Bedrock AgentCore Runtime with
    the AgentCore CLI (src/agentcore_cli.py wraps it).

    AgentCore does not serialize Python objects, so `orchestrator_agent` is
    not uploaded directly. Instead the pre-written staging step copies this
    file, which doubles as the HTTP entry point (see run_serve), together
    with its helper modules and config.py to build/runtime/. `agentcore
    deploy` then packages that directory with arm64 dependencies and creates
    or updates the runtime ("direct code deployment"). Re-running is safe:
    an unchanged runtime is left alone, a changed one is updated in place.

    The guardrail is attached by environment variables: inside the runtime
    build_agent_graph() reads GUARDRAIL_ID / GUARDRAIL_VERSION and applies
    them to every agent's model (see _apply_guardrail), exactly as `test`
    and `chat` do locally.

    Returns:
        The AgentCore Runtime ARN
    """
    import agentcore_cli
    import boto3

    agentcore_control = boto3.client('bedrock-agentcore-control', region_name=config.AWS_REGION)

    runtime_name = config.AGENTCORE_RUNTIME_NAME
    print(f"  AWS Account: {config.ACCOUNT_ID}  |  Region: {config.AWS_REGION}")
    print(f"  Runtime: {runtime_name}  |  CLI project: agentcore/agentcore.json "
          f"(stack {agentcore_cli.stack_name()})")
    previous_arn = agentcore_cli.deployed_runtime_arn()
    if previous_arn:
        print(f"  Runtime already deployed - updating it: {previous_arn}")

    # Stage the code the CLI packages (src modules + config.py + pyproject.toml).
    agentcore_cli.stage_runtime_code()

    # TODO: Configure and deploy the runtime with the AgentCore CLI
    # 1. Build the runtime environment variables dict `runtime_env` with:
    #      AWS_REGION, PROJECT_NAME (config.AWS_REGION / config.PROJECT_NAME),
    #      RETURNS_KB_ID, SHIPPING_KB_ID, WARRANTY_KB_ID (from config),
    #      AGENT_LOG_GROUP (config.AGENT_LOG_GROUP), and the guardrail
    #      (GUARDRAIL_ID = guardrail_id, GUARDRAIL_VERSION = guardrail_version)
    # 2. Write the runtime settings to agentcore/agentcore.json with
    #      agentcore_cli.configure_runtime(env_vars=runtime_env,
    #                                      network_mode='PUBLIC',
    #                                      protocol='HTTP',
    #                                      execution_role_arn=config.AGENTCORE_ROLE_ARN)
    # 3. Deploy:  agentcore_cli.deploy()        (runs `agentcore deploy -y`)
    # 4. Read the ARN the CLI recorded:
    #      runtime_arn = agentcore_cli.deployed_runtime_arn()
    runtime_arn = None

    if not runtime_arn:
        raise NotImplementedError("deploy_to_agentcore_runtime: AgentCore CLI deployment not implemented")

    # Wait for the runtime to become READY and return its ARN.
    print(f"  Runtime deployed: {runtime_arn}")
    print("  Waiting for runtime status READY", end='', flush=True)
    wait_for_runtime_ready(agentcore_control, runtime_arn.split('/')[-1])
    print(' ready.')
    return runtime_arn
