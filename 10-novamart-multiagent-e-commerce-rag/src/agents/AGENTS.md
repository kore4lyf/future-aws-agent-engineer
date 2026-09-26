# Agents

## Overview

The NovaMart multi-agent graph. Each agent is a self-contained module with a builder function, tool implementations, and Pydantic schemas for input/output validation. The Orchestrator routes requests to specialist workers and manages shared WorkflowState in DynamoDB.

## Key files

| File | Owns |
|---|---|
| `src/agents/__init__.py` | Public API re-exporting all `build_*_agent()` functions |
| `src/agents/inventory/__init__.py` | InventoryAgent builder |
| `src/agents/inventory/tools.py` | 3 DynamoDB lookup tools |
| `src/agents/inventory/schema.py` | Input/output Pydantic schemas |
| `src/agents/refund/__init__.py` | RefundAgent builder |
| `src/agents/refund/tools.py` | Refund eligibility tools |
| `src/agents/refund/schema.py` | Refund schemas |
| `src/agents/policy/__init__.py` | PolicyAgent builder with ThreadPoolExecutor |
| `src/agents/policy/tools.py` | 3 parallel KB retriever tools |
| `src/agents/policy/schema.py` | Policy schemas |
| `src/agents/communication/__init__.py` | CommunicationAgent builder |
| `src/agents/communication/tools.py` | Response composition tool |
| `src/agents/communication/schema.py` | Communication schemas |
| `src/agents/orchestrator/__init__.py` | OrchestratorAgent builder with factory routing tools |
| `src/agents/orchestrator/tools.py` | Routing tool factories capturing workers via closure |
| `src/agents/orchestrator/schema.py` | Orchestrator schemas |

## Conventions

- Each agent folder contains exactly three files: `__init__.py` (builder), `tools.py` (implementations), `schema.py` (Pydantic models). No exceptions.
- Builder functions return `Agent` instances and accept only natural parameters. Worker agent references are captured via closure in routing tools, not passed to the LLM.
- All tool functions use `@tool` decorator and have Pydantic schemas for both input and output.
- Domain schemas (`schema.py`) have zero AWS imports. They are plain Pydantic models.
- Tools (`tools.py`) may import boto3, Bedrock, and other infrastructure. They are the boundary layer.
- Factory functions in `orchestrator/tools.py` capture worker agents via lambda closures so only natural parameters appear in the LLM tool schema.

## Gotchas

- The Orchestrator routing tools use factory functions (`make_route_to_*`) that capture worker agents via closure. Do not pass agent instances directly as tool parameters.
- PolicyAgent's `search_all_policies` runs 3 retriever sub-agents in parallel using `ThreadPoolExecutor(max_workers=3)` defined inside `build_policy_agent()` for rubric AST compliance.
- WorkflowState uses optimistic locking with version-based conditional writes in DynamoDB.

## Related specs

- Capstone project specification: `../docs/Capstone Project - Novamart - Multiagent E-commerce RAG.md`
- Scope and milestones: `../docs/scope/scope.md`

_Drafted by /audit from the repo, worth a quick human pass. Edit freely: once a line stops matching this draft, later runs treat it as curated and will flag rather than overwrite it._
