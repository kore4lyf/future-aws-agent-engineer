"""
cli/scenarios.py
================
Local test scenarios.

Moved from agent_orchestrator.py lines ~918-949.
"""

from __future__ import annotations

import sys
import os
import uuid
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from agent_observability import setup_logging, flush_logs, print_trace_hint, tracer
from workflow.graph import build_agent_graph
from agent_utils import _strip_xml_tags
from deploy.guardrail import BLOCKED_INPUT_MESSAGE, BLOCKED_OUTPUT_MESSAGE
from telemetry.guardrails import (
    clear_invocation_id,
    process_captured_responses,
    set_invocation_id,
)
from telemetry.contract import format_guardrail_line


__all__ = ['TEST_CASES', 'run_test_scenarios']


# Order IDs match infrastructure/seed_data.py.
TEST_CASES = [
    ("CUST-001", "I want to return my wireless headphones from order ORD-27176"),
    ("CUST-002", "What is the return policy for premium customers?"),
    ("CUST-003", "How much would 5 items at $29.99 be with a 10% discount?"),
]


def run_test_scenarios() -> None:
    """Run the three scenarios locally; every request is traced to X-Ray."""
    print("Running local agent test...")
    setup_logging(to_cloudwatch=True)
    orchestrator = build_agent_graph()

    for customer_id, query in TEST_CASES:
        session_id = str(uuid.uuid4())[:8]
        print(f"\n{'─'*60}")
        print(f"Session: {session_id} | Customer: {customer_id}")
        print(f"Query: {query}")
        prompt = f"[Session ID: {session_id}] [Customer ID: {customer_id}] {query}"
        invocation_id = session_id
        set_invocation_id(invocation_id)
        with tracer.trace_request(session_id, customer_id, query):
            response = orchestrator(prompt)
        events = process_captured_responses(invocation_id)
        clear_invocation_id()
        print(f"Response: {response}")
        text = _strip_xml_tags(str(response))
        if BLOCKED_INPUT_MESSAGE in text or BLOCKED_OUTPUT_MESSAGE in text:
            if not events:
                logging.getLogger('novamart.observability').info(
                    format_guardrail_line(
                        policy='Unknown', action='BLOCK',
                        trace_id=tracer.last_trace_id,
                        category='UNKNOWN', source='fallback',
                    )
                )
        print_trace_hint()
    flush_logs()
