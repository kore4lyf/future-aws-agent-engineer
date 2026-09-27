"""
agents/orchestrator/tools.py
=============================
Tool factories for the Orchestrator Agent.

Routing tools need closure over the worker agents, so they are created
by factory functions that capture the agent instances. The returned
@tool functions expose only the natural parameters to the LLM
(session_id, customer_id, request) — the agents are bound internally.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent))

from strands import tool

from agent_orchestrator import _read_workflow_state, _update_workflow_state, trace
from agents.orchestrator.schema import (
    InitializeSessionInput,
    InitializeSessionOutput,
    RouteToCommunicationAgentInput,
    RouteToInventoryAgentInput,
    RouteToPolicyAgentInput,
    RouteToRefundAgentInput,
)


def make_initialize_session():
    @tool
    def initialize_session(session_id: str, customer_id: str) -> str:
        """
        Create a blank WorkflowState record at the start of each new session.
        Call this at the VERY BEGINNING of processing every customer request.

        Args:
            session_id:  A unique identifier for this session
            customer_id: The customer's identifier

        Returns:
            Confirmation that the session was initialized
        """
        input_data = InitializeSessionInput(session_id=session_id, customer_id=customer_id)
        from agent_orchestrator import _create_workflow_state
        try:
            state = _create_workflow_state(input_data.session_id, input_data.customer_id)
            output = InitializeSessionOutput(
                session_id=input_data.session_id,
                customer_id=input_data.customer_id,
                version=state['version'],
                message=f"Session initialized: {input_data.session_id} for customer {input_data.customer_id} (version {state['version']})",
            )
            return output.model_dump_json()
        except Exception as exc:
            output = InitializeSessionOutput(
                session_id=input_data.session_id,
                customer_id=input_data.customer_id,
                version=0,
                message=f"Session initialization note: {exc}",
            )
            return output.model_dump_json()
    return initialize_session


def make_route_to_inventory_agent(get_inventory_agent):
    @tool
    def route_to_inventory_agent(session_id: str, customer_id: str, request: str) -> str:
        """
        Route an order-related request to the Inventory Agent to gather order facts.
        Call this FIRST for any request involving order status, history, or returns.

        Args:
            session_id:  The current session identifier
            customer_id: The customer's unique identifier
            request:     The customer's original request

        Returns:
            Inventory facts retrieved by the InventoryAgent
        """
        _ = RouteToInventoryAgentInput(session_id=session_id, customer_id=customer_id, request=request)
        trace.step_start('inventory_agent')
        trace.agent_section('INVENTORY AGENT')
        state = _read_workflow_state(session_id)
        old_version = state['version'] if state else 0
        inventory_agent = get_inventory_agent()
        result = inventory_agent(f"Customer {customer_id}: {request}")
        _update_workflow_state(session_id, {'inventory_agent': str(result)}, old_version)
        trace.step_done('inventory_agent', old_version)
        return str(result)
    return route_to_inventory_agent


def make_route_to_policy_agent(get_policy_agent):
    @tool
    def route_to_policy_agent(session_id: str, request: str) -> str:
        """
        Route a policy question to the Policy Agent (multi-agent RAG).
        Call this for questions about return policies, shipping, or warranties.

        Args:
            session_id: The current session identifier
            request:    The customer's policy question

        Returns:
            Policy information retrieved and synthesized by PolicyAgent
        """
        _ = RouteToPolicyAgentInput(session_id=session_id, request=request)
        trace.step_start('policy_agent')
        trace.agent_section('POLICY AGENT')
        state = _read_workflow_state(session_id)
        old_version = state['version'] if state else 0
        policy_agent = get_policy_agent()
        result = policy_agent(request)
        _update_workflow_state(session_id, {'policy_agent': str(result)}, old_version)
        trace.step_done('policy_agent', old_version)
        return str(result)
    return route_to_policy_agent


def make_route_to_refund_agent(get_refund_agent):
    @tool
    def route_to_refund_agent(session_id: str, customer_id: str, request: str) -> str:
        """
        Route a return/refund request to the Refund Agent.
        Call this AFTER route_to_inventory_agent has gathered order facts.

        Args:
            session_id:  The current session identifier
            customer_id: The customer's unique identifier
            request:     The return/refund request

        Returns:
            Refund decision from the RefundAgent
        """
        _ = RouteToRefundAgentInput(session_id=session_id, customer_id=customer_id, request=request)
        trace.step_start('refund_agent')
        trace.agent_section('REFUND AGENT')
        state = _read_workflow_state(session_id)
        old_version = state['version'] if state else 0
        refund_agent = get_refund_agent()
        result = refund_agent(f"Customer {customer_id}: {request}")
        _update_workflow_state(session_id, {'refund_agent': str(result)}, old_version)
        trace.step_done('refund_agent', old_version)
        return str(result)
    return route_to_refund_agent


def make_route_to_communication_agent(get_communication_agent):
    @tool
    def route_to_communication_agent(session_id: str, customer_id: str,
                                      original_request: str) -> str:
        """
        Route to the Communication Agent to compose the final customer response.
        Call this LAST - after all relevant worker agents have run.

        Args:
            session_id:       The current session identifier
            customer_id:      The customer's unique identifier
            original_request: The customer's original message

        Returns:
            Final customer-facing response drafted by CommunicationAgent
        """
        _ = RouteToCommunicationAgentInput(
            session_id=session_id,
            customer_id=customer_id,
            original_request=original_request,
        )
        trace.step_start('communication_agent')
        trace.agent_section('COMMUNICATION AGENT')
        state = _read_workflow_state(session_id)
        old_version = state['version'] if state else 0
        context = _read_workflow_state(session_id)
        context_summary = ""
        if context:
            ctx_parts = []
            if context.get('inventory_agent'):
                ctx_parts.append(f"[Inventory findings]\n{context['inventory_agent']}")
            if context.get('policy_agent'):
                ctx_parts.append(f"[Policy findings]\n{context['policy_agent']}")
            if context.get('refund_agent'):
                ctx_parts.append(f"[Refund decision]\n{context['refund_agent']}")
            context_summary = "\n\n".join(ctx_parts)
        communication_agent = get_communication_agent()
        result = communication_agent(
            f"Customer {customer_id} asked: {original_request}\n\n"
            f"Context from other agents:\n{context_summary}"
        )
        _update_workflow_state(session_id, {'communication_agent': str(result)}, old_version)
        trace.step_done('communication_agent', old_version)
        return str(result)
    return route_to_communication_agent
