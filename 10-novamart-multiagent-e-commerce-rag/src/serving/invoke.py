"""
serving/invoke.py
=================
AgentCore Runtime invocation.

Moved from agent_orchestrator.py lines ~816-843.
"""

from __future__ import annotations

import sys
import os
import json
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config


__all__ = ['invoke_agent']

_agentcore_client = None

def _get_agentcore_client():
    global _agentcore_client
    if _agentcore_client is None:
        import boto3
        _agentcore_client = boto3.client('bedrock-agentcore', region_name=config.AWS_REGION)
    return _agentcore_client


def invoke_agent(session_id: str, customer_id: str, user_message: str) -> dict:
    """
    Invoke the deployed agent via AgentCore Runtime (see run_serve).

    AgentCore requires runtimeSessionId to be at least 33 characters, so the
    short project session id is embedded in a longer, unique runtime session id.
    """
    if not config.AGENTCORE_RUNTIME_ARN:
        raise RuntimeError("AGENTCORE_RUNTIME_ARN is not set - run the deploy command first")

    runtime_session_id = f"{session_id}-{uuid.uuid4().hex}"     # >= 33 chars
    payload = json.dumps({
        'prompt':      user_message,
        'session_id':  session_id,
        'customer_id': customer_id,
    })
    response = _get_agentcore_client().invoke_agent_runtime(
        agentRuntimeArn=config.AGENTCORE_RUNTIME_ARN,
        runtimeSessionId=runtime_session_id,
        contentType='application/json',
        accept='application/json',
        payload=payload,
    )
    body = response['response'].read()
    try:
        return json.loads(body)
    except (TypeError, ValueError):
        return {'result': body.decode('utf-8', errors='replace') if isinstance(body, bytes) else str(body)}
