"""
cli/chat.py
===========
Interactive terminal chat and single-invoke helper.

Moved from agent_orchestrator.py lines ~925-1058.
"""

from __future__ import annotations

import sys
import os
import time
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from agent_utils import _C, _trace_print, _trace_writer, _real_stdout, _strip_xml_tags
from agent_observability import setup_logging, tracer, flush_logs, print_trace_hint
from workflow.state import _read_workflow_state, trace
from workflow.graph import build_agent_graph


__all__ = ['TEST_CUSTOMERS', 'run_chat', 'run_invoke']


# Test customers shown by the chat command. Data matches seed_data.py.
TEST_CUSTOMERS = [
    ("CUST-001", "Alice Johnson", "Premium",  "ORD-27176", "Wireless Headphones Pro"),
    ("CUST-002", "Bob Smith",     "Standard", "ORD-28001", "Mechanical Keyboard K2"),
    ("CUST-003", "Carol Davis",   "Premium",  "ORD-29001", "Laptop UltraBook 14"),
    ("CUST-004", "David Lee",     "Standard", "ORD-30001", "Phone Case Slim"),
]


def run_chat() -> None:
    """Interactive terminal chat - educational mode."""
    W = _C.W

    # -- Welcome banner
    print()
    print(f"  {_C.GRY}{'=' * W}{_C.RESET}")
    print(f"  {_C.ORCH}{_C.BOLD}{'NovaMart -- Multi-Agent Customer Support':^{W}}{_C.RESET}")
    print(f"  {_C.GRY}{'Strands Agents SDK  +  Amazon Bedrock AgentCore':^{W}}{_C.RESET}")
    print(f"  {_C.GRY}{'=' * W}{_C.RESET}")
    print()

    # -- Test customers
    print(f"  {_C.GRY}{'─' * W}{_C.RESET}")
    print(f"  {_C.BOLD}Test Customers{_C.RESET}")
    print(f"  {_C.GRY}{'─' * W}{_C.RESET}")
    print(f"  {_C.GRY}{'ID':<10}  {'Name':<18}  {'Tier':<10}  {'Order':<12}  Product{_C.RESET}")
    print(f"  {_C.GRY}{'─'*8}  {'─'*16}  {'─'*8}  {'─'*10}  {'─'*20}{_C.RESET}")
    for cid, name, tier, order, product in TEST_CUSTOMERS:
        tier_col = _C.INV if tier == 'Premium' else _C.GRY
        print(f"  {_C.BOLD}{cid}{_C.RESET}  {name:<18}  "
              f"{tier_col}{tier:<10}{_C.RESET}  {order}  {product}")
    print(f"  {_C.GRY}{'─' * W}{_C.RESET}")
    print()

    customer_id = (
        input(f"  Enter Customer ID (default: CUST-001): ").strip()
        or "CUST-001"
    )
    session_id  = str(uuid.uuid4())[:8]
    print()
    print(f"  {_C.GRY}Session  : {_C.RESET}{_C.BOLD}{session_id}{_C.RESET}")
    print(f"  {_C.GRY}Customer : {_C.RESET}{_C.BOLD}{customer_id}{_C.RESET}")
    print(f"  {_C.GRY}Type a question and press Enter.  Type 'quit' to exit.{_C.RESET}")
    print()

    # -- Build agents and show initialization order.
    print(f"  {_C.GRY}[SYSTEM]  Initializing agent graph...{_C.RESET}")
    setup_logging(to_cloudwatch=True)
    orchestrator = build_agent_graph(verbose=True)
    print(f"  {_C.GRY}[SYSTEM]  All 5 agents ready.{_C.RESET}")
    print()

    # -- Conversation loop
    while True:
        try:
            user_input = input(
                f"  {_C.BOLD}You >{_C.RESET} "
            ).strip()
        except (EOFError, KeyboardInterrupt):
            print(f"\n  {_C.GRY}Session ended.{_C.RESET}")
            break

        if not user_input:
            continue
        if user_input.lower() in ('quit', 'exit', 'q'):
            print(f"  {_C.GRY}Session ended.{_C.RESET}")
            break

        prompt  = (f"[Session ID: {session_id}] "
                   f"[Customer ID: {customer_id}] {user_input}")
        t0_turn = time.time()

        # -- Install proxy, run orchestrator (traced), restore stdout
        trace.new_turn()
        sys.stdout = _trace_writer
        try:
            with tracer.trace_request(session_id, customer_id, user_input):
                response = orchestrator(prompt)
        finally:
            sys.stdout = _real_stdout   # always restore, even on exception

        elapsed = time.time() - t0_turn

        # -- Resolve the final customer-facing text
        final_state = _read_workflow_state(session_id) or {}
        comm_result = final_state.get('communication_agent', '')
        text = _strip_xml_tags(comm_result or str(response))

        # -- DynamoDB workflow state summary
        trace.summary(session_id, elapsed)

        # -- Final customer-facing response
        print()
        print(f"  {_C.GRY}{'=' * W}{_C.RESET}")
        print(f"  {_C.COM}{_C.BOLD}AGENT RESPONSE{_C.RESET}")
        print(f"  {_C.GRY}{'=' * W}{_C.RESET}")
        for line in text.splitlines():
            print(f"  {line}")
        print(f"  {_C.GRY}{'=' * W}{_C.RESET}")
        if tracer.last_trace_id:
            print(f"  {_C.GRY}X-Ray trace : {tracer.last_trace_id}"
                  f"{'' if tracer.last_published else '  (not published)'}{_C.RESET}")
        print()
    flush_logs()


def run_invoke(message: str, customer_id: str = "CUST-001") -> None:
    """Send one message to the deployed AgentCore Runtime and print the reply."""
    from serving.invoke import invoke_agent

    session_id = str(uuid.uuid4())[:8]
    print(f"Invoking {config.AGENTCORE_RUNTIME_ARN}")
    print(f"Session: {session_id} | Customer: {customer_id}")
    print(f"Query: {message}\n")
    result = invoke_agent(session_id, customer_id, message)
    print(f"Response: {result.get('result', result)}")
    if result.get('trace_id'):
        print(f"X-Ray trace: {result['trace_id']}")
