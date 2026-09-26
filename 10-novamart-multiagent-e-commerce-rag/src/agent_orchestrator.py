"""
agent_orchestrator.py
=====================
Enterprise Multi-Agent Customer Support System
Built with Strands Agents SDK + Amazon Bedrock AgentCore

Architecture implemented:

  Customer Request
        │
  OrchestratorAgent  (Claude Haiku 4.5 - fast routing, manages WorkflowState)
        │
   ┌────┼────────────────────┬────────────────────────┐
   │    │                    │                        │
InventoryAgent   PolicyAgent   RefundAgent  CommunicationAgent
(DynamoDB)    (Multi-Agent RAG)  (DynamoDB)   (composes response)
                 │
          ┌──────────┼──────────┐
     ReturnsPolicyRetriever  ShippingPolicyRetriever  WarrantyPolicyRetriever
        (KB: returns)           (KB: shipping)           (KB: warranty)
        └──────────── all run in PARALLEL ────────────┘

Shared state flows through DynamoDB WorkflowStateTable.
OrchestratorAgent creates state at start, each routing tool reads and
updates it after the worker responds.

Commands:
  python src/agent_orchestrator.py test            # 3 scenarios, local run, traced to X-Ray
  python src/agent_orchestrator.py chat            # interactive terminal chat
  python src/agent_orchestrator.py deploy          # Tasks 3-6 deployment pipeline (uses the AgentCore CLI)
  python src/agent_orchestrator.py invoke "<msg>"  # call the deployed AgentCore Runtime
  python src/agent_orchestrator.py serve           # HTTP server (what AgentCore Runtime runs)

Deployment uses the AgentCore CLI (`agentcore`, npm package @aws/agentcore,
https://github.com/aws/agentcore-cli) through the pre-written helper
src/agentcore_cli.py - see the README for the prerequisites (Node.js 20+, uv).

FUNCTION -> REAL FILE MAPPING (reviewer: start here)
─────────────────────────────────────────────────────
  _create_workflow_state, _read_workflow_state, _update_workflow_state, trace
      -> src/workflow/state.py

  build_agent_graph, _apply_guardrail
      -> src/workflow/graph.py

  create_guardrail
      -> src/deploy/guardrail.py

  deploy_to_agentcore_runtime
      -> src/deploy/runtime.py

  configure_memory
      -> src/deploy/memory.py

  configure_observability
      -> src/deploy/observability.py

  deploy_agentcore_gateway
      -> src/deploy/gateway.py

  invoke_agent
      -> src/serving/invoke.py

  run_serve
      -> src/serving/serve.py

  deploy_all
      -> src/cli/main.py

  TEST_CASES, run_test_scenarios
      -> src/cli/scenarios.py

  TEST_CUSTOMERS, run_chat, run_invoke
      -> src/cli/chat.py

  build_inventory_agent, build_refund_agent, build_policy_agent,
  build_communication_agent, build_orchestrator_agent
      -> src/agents/<name>/__init__.py
"""

import sys
import os
import logging

# When executed as `python src/agent_orchestrator.py` the module name is
# __main__, but agents/policy and agents/orchestrator/tools import names
# from `agent_orchestrator`. Register the executing module under that name
# so the circular import resolves to the already-running module.
if __name__ == '__main__':
    sys.modules['agent_orchestrator'] = sys.modules['__main__']

# Ensure the parent directory is on sys.path so config.py and
# bedrock_kb_retrieval.py are importable regardless of where this
# script is invoked from (e.g. python src/agent_orchestrator.py)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Configure logging for debugging
logging.basicConfig(
    level=logging.WARNING,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────
# WORKFLOW STATE — re-exported from workflow/
# Must come BEFORE agents/ because agents/orchestrator/tools.py
# and agents/policy/__init__.py import trace and workflow
# functions from agent_orchestrator at module load time.
# ─────────────────────────────────────────────────────
from workflow.state import (
    _create_workflow_state,
    _read_workflow_state,
    _update_workflow_state,
    trace,
)


# ─────────────────────────────────────────────────────
# AGENT GRAPH — re-exported from workflow/
# ─────────────────────────────────────────────────────
from workflow.graph import (
    build_agent_graph,
    _apply_guardrail,
)


# ─────────────────────────────────────────────────────
# AGENT BUILDERS — re-exported from agents/ for tests
# ─────────────────────────────────────────────────────
from agents import (
    build_inventory_agent,
    build_refund_agent,
    build_policy_agent,
    build_communication_agent,
    build_orchestrator_agent,
)


# ─────────────────────────────────────────────────────
# DEPLOYMENT — re-exported from deploy/
# ─────────────────────────────────────────────────────
from deploy.guardrail import create_guardrail
from deploy.runtime import deploy_to_agentcore_runtime
from deploy.memory import configure_memory
from deploy.observability import configure_observability
from deploy.gateway import deploy_agentcore_gateway


# ─────────────────────────────────────────────────────
# SERVING — re-exported from serving/
# ─────────────────────────────────────────────────────
from serving.invoke import invoke_agent
from serving.serve import run_serve


# ─────────────────────────────────────────────────────
# CLI — re-exported from cli/
# ─────────────────────────────────────────────────────
from cli.scenarios import run_test_scenarios, TEST_CASES
from cli.chat import run_chat, run_invoke, TEST_CUSTOMERS
from cli.main import deploy_all


__all__ = [
    'build_inventory_agent',
    'build_refund_agent',
    'build_policy_agent',
    'build_communication_agent',
    'build_orchestrator_agent',
    '_create_workflow_state',
    '_read_workflow_state',
    '_update_workflow_state',
    'trace',
    'build_agent_graph',
    '_apply_guardrail',
    'create_guardrail',
    'deploy_to_agentcore_runtime',
    'configure_memory',
    'configure_observability',
    'deploy_agentcore_gateway',
    'invoke_agent',
    'run_serve',
    'deploy_all',
    'run_test_scenarios',
    'run_chat',
    'run_invoke',
    'TEST_CASES',
    'TEST_CUSTOMERS',
]


# ═══════════════════════════════════════════════════════
#  CLI ENTRY POINT
# ═══════════════════════════════════════════════════════

_RUNTIME_MARKER = '.agentcore-runtime'         # written by agentcore_cli.stage_runtime_code()
_SRC_DIR        = os.path.dirname(os.path.abspath(__file__))


if __name__ == '__main__':
    # AgentCore Runtime starts the staged entry point with no arguments. The
    # .agentcore-runtime marker (written by agentcore_cli.stage_runtime_code)
    # is what distinguishes that from a bare `python src/agent_orchestrator.py`,
    # so the runtime serves HTTP instead of printing the CLI usage text.
    if not sys.argv[1:] and os.path.exists(os.path.join(_SRC_DIR, _RUNTIME_MARKER)):
        from serving.serve import run_serve
        run_serve()
    else:
        from cli.main import main as _cli_main
        _cli_main()
