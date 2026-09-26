"""
agents/communication/tools.py
===============================
Tool functions for the Communication Agent.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent))

from strands import tool
from pydantic import ValidationError
from botocore.exceptions import ClientError

from agent_orchestrator import _read_workflow_state
from agents.communication.schema import (
    GetFullWorkflowContextInput,
    GetFullWorkflowContextOutput,
)


@tool
def get_full_workflow_context(session_id: str) -> dict:
    """
    Read the complete WorkflowState to access all findings from previous agents.

    Args:
        session_id: The current session identifier

    Returns:
        Full WorkflowState dict (inventory_agent, policy_agent, refund_agent)
    """
    input_data = GetFullWorkflowContextInput(session_id=session_id)
    try:
        state = _read_workflow_state(input_data.session_id)
        if not state:
            output = GetFullWorkflowContextOutput(error='WorkflowState not found for this session.')
            return output.model_dump()
        output = GetFullWorkflowContextOutput(
            inventory_agent=state.get('inventory_agent'),
            policy_agent=state.get('policy_agent'),
            refund_agent=state.get('refund_agent'),
        )
        return output.model_dump()
    except (ClientError, ValidationError) as exc:
        return GetFullWorkflowContextOutput(error=str(exc)).model_dump()
