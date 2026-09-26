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

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from agent_observability import setup_logging, flush_logs, print_trace_hint, tracer
from workflow.graph import build_agent_graph


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
        with tracer.trace_request(session_id, customer_id, query):
            response = orchestrator(prompt)
        print(f"Response: {response}")
        print_trace_hint()
    flush_logs()
