"""
agents/orchestrator/__init__.py
=================================
Orchestrator Agent — routes requests and manages WorkflowState.
Uses factory-made routing tools that capture worker agent references via closure.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent))

from strands import Agent
from strands.models import BedrockModel

import config
from agents.orchestrator.tools import (
    make_initialize_session,
    make_route_to_inventory_agent,
    make_route_to_policy_agent,
    make_route_to_refund_agent,
    make_route_to_communication_agent,
)


__all__ = ['build_orchestrator_agent']


def build_orchestrator_agent(
    inventory_agent:      Agent,
    refund_agent:         Agent,
    policy_agent:         Agent,
    communication_agent:  Agent,
) -> Agent:
    """
    Build the Orchestrator Agent that routes requests and manages WorkflowState.
    """
    model = BedrockModel(
        model_id=config.ORCHESTRATOR_MODEL_ID,
        region_name=config.AWS_REGION,
        temperature=0.0,
    )

    system_prompt = """You are the Orchestrator Agent for NovaMart customer support.
You do NOT answer customer questions directly. Your job is to route each request
to the correct specialist agent and manage the shared WorkflowState.

Routing rules (follow these exactly):
  1. Every request: call initialize_session FIRST to create a WorkflowState record.
  2. Order status, returns, or refund requests:
       Call route_to_inventory_agent FIRST, then route_to_refund_agent.
  3. Policy questions (return windows, shipping rates, warranty terms):
       Call route_to_policy_agent.
  4. Account questions ("what is my tier?", "am I premium?"):
       Call route_to_inventory_agent. NEVER call route_to_policy_agent -
       it only knows policy text, not customer data.
  5. Math or calculation questions:
       Skip Inventory, Policy, and Refund. Go directly to
       route_to_communication_agent.
  6. Every request (ALWAYS last step):
       Call route_to_communication_agent to compose the final reply.

CRITICAL: You must NEVER write the final customer-facing response yourself.
You must always delegate to route_to_communication_agent as your very last
tool call - no exceptions, even when you believe you already have a complete answer."""

    # Bind worker agents into routing tools via factory-made closures.
    # The LLM only sees natural parameters (session_id, customer_id, request);
    # the agent instances are captured internally.
    return Agent(
        model=model,
        system_prompt=system_prompt,
        tools=[
            make_initialize_session(),
            make_route_to_inventory_agent(lambda: inventory_agent),
            make_route_to_policy_agent(lambda: policy_agent),
            make_route_to_refund_agent(lambda: refund_agent),
            make_route_to_communication_agent(lambda: communication_agent),
        ],
    )
