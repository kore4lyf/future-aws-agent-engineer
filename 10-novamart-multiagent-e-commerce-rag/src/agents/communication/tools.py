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

from agent_orchestrator import _read_workflow_state


@tool
def get_full_workflow_context(session_id: str) -> dict:
    """
    Read the complete WorkflowState to access all findings from previous agents.

    Args:
        session_id: The current session identifier

    Returns:
        Full WorkflowState dict (inventory_agent, policy_agent, refund_agent)
    """
    state = _read_workflow_state(session_id)
    if not state:
        return {'error': 'WorkflowState not found for this session.'}
    return {k: state.get(k) for k in state if k not in ('session_id', 'customer_id', 'version', 'ttl', 'created_at')}
