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
    print(f"  Runtime: {runtime_name}  |  CLI: {agentcore_cli.cli_version()} "
          f"({agentcore_cli.cli_path()})")
    previous_arn = agentcore_cli.deployed_runtime_arn()
    if previous_arn:
        print(f"  Runtime already deployed - updating it: {previous_arn}")

    # Stage the code the CLI packages (src modules + packages + config.py + requirements).
    agentcore_cli.stage_runtime_code()

    # Build the runtime environment variables dict with AWS_REGION,
    # PROJECT_NAME, KB IDs, AGENT_LOG_GROUP, and guardrail config.
    runtime_env = {
        'AWS_REGION':      config.AWS_REGION,
        'PROJECT_NAME':    config.PROJECT_NAME,
        'RETURNS_KB_ID':   config.RETURNS_KB_ID,
        'SHIPPING_KB_ID':  config.SHIPPING_KB_ID,
        'WARRANTY_KB_ID':  config.WARRANTY_KB_ID,
        'AGENT_LOG_GROUP': config.AGENT_LOG_GROUP,
        'GUARDRAIL_ID':    guardrail_id,
        'GUARDRAIL_VERSION': guardrail_version,
    }

    # Write the runtime settings to agentcore/agentcore.json with
    # PUBLIC networking, HTTP protocol and the foundation execution role.
    agentcore_cli.configure_runtime(
        env_vars=runtime_env,
        network_mode='PUBLIC',
        protocol='HTTP',
        execution_role_arn=config.AGENTCORE_ROLE_ARN,
    )

    # Deploy the runtime via the AgentCore CLI.
    agentcore_cli.deploy()

    # Read the ARN the CLI recorded after deployment.
    runtime_arn = agentcore_cli.deployed_runtime_arn()

    # Wait for the runtime to become READY and return its ARN.
    print(f"  Runtime deployed: {runtime_arn}")
    print("  Waiting for runtime status READY", end='', flush=True)
    wait_for_runtime_ready(agentcore_control, runtime_arn.split('/')[-1])
    print(' ready.')
    return runtime_arn
