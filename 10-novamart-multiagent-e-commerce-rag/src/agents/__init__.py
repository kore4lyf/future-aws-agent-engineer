"""
agents/__init__.py
===================
Public API for the NovaMart agent graph.

Importing from `agents` gives you every builder function without needing
to know which submodule each one lives in:

    from agents import (
        build_inventory_agent,
        build_refund_agent,
        build_policy_agent,
        build_communication_agent,
        build_orchestrator_agent,
    )
"""

from agents.inventory import build_inventory_agent
from agents.refund import build_refund_agent
from agents.policy import build_policy_agent
from agents.communication import build_communication_agent
from agents.orchestrator import build_orchestrator_agent

__all__ = [
    'build_inventory_agent',
    'build_refund_agent',
    'build_policy_agent',
    'build_communication_agent',
    'build_orchestrator_agent',
]
