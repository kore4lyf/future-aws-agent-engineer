"""
workflow/graph.py
=================
Agent graph construction and guardrail application.

Moved from agent_orchestrator.py lines ~228-270.
"""

from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from agent_utils import _C

from workflow.state import _create_workflow_state, _read_workflow_state, _update_workflow_state, trace


__all__ = ['_apply_guardrail', 'build_agent_graph']


def _apply_guardrail(agents: list) -> None:
    """
    Attach the Bedrock Guardrail (Task 3) to every agent's BedrockModel.

    Guardrails are enforced per model invocation, so once GUARDRAIL_ID /
    GUARDRAIL_VERSION are known (in .env locally, as runtime environment
    variables when deployed) every agent in the graph runs behind the
    guardrail - no change to the agents themselves is needed.
    """
    guardrail_id      = config.GUARDRAIL_ID
    guardrail_version = config.GUARDRAIL_VERSION
    if not guardrail_id or not guardrail_version:
        return
    # The project requires a published (numbered) version, not DRAFT - Bedrock
    # rejects DRAFT at model construction with an opaque error, so fail here
    # with something actionable instead.
    if not str(guardrail_version).isdigit():
        raise ValueError(
            f"GUARDRAIL_VERSION must be a published, numbered version, got "
            f"{guardrail_version!r}. Run `python src/agent_orchestrator.py deploy` "
            f"and copy the printed version into .env."
        )
    for agent in agents:
        model = getattr(agent, 'model', None)
        if model is not None and hasattr(model, 'update_config'):
            model.update_config(guardrail_id=guardrail_id,
                                guardrail_version=guardrail_version)


def build_agent_graph(verbose: bool = False) -> "Agent":
    """Build all five agents, apply the guardrail, return the orchestrator."""
    from agents import (
        build_inventory_agent,
        build_refund_agent,
        build_policy_agent,
        build_communication_agent,
        build_orchestrator_agent,
    )

    def _ok(label):
        if verbose:
            print(f"  {_C.GRY}          {_C.OK}[OK]{_C.RESET}{_C.GRY}  {label}{_C.RESET}", flush=True)

    inventory_agent     = build_inventory_agent();     _ok('InventoryAgent')
    refund_agent        = build_refund_agent();        _ok('RefundAgent')
    policy_agent        = build_policy_agent();        _ok('PolicyAgent')
    communication_agent = build_communication_agent(); _ok('CommunicationAgent')
    orchestrator = build_orchestrator_agent(
        inventory_agent, refund_agent, policy_agent, communication_agent
    )
    _ok('Orchestrator')
    _apply_guardrail([inventory_agent, refund_agent, policy_agent,
                      communication_agent, orchestrator])
    if verbose and config.GUARDRAIL_ID:
        print(f"  {_C.GRY}          Guardrail {config.GUARDRAIL_ID} "
              f"(v{config.GUARDRAIL_VERSION}) attached to all agents{_C.RESET}")
    return orchestrator
