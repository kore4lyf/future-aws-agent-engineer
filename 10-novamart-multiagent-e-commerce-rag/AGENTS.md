# NovaMart Multi-Agent Customer Support System

## Stack

- **Language / Runtime**: Python 3.12
- **Framework**: Strands Agents SDK, Amazon Bedrock AgentCore
- **Key dependencies**: boto3, strands-agents, python-dotenv
- **Package manager**: pip

## Build approach

Journey: each phase delivers a complete, testable slice of the system, building toward full end-to-end operation.

## Commands

```bash
# Install
pip install -r requirements.txt

# Verify environment
python config.py

# Run tests
python tests/test_agent.py task2

# Deploy
python src/agent_orchestrator.py deploy
```

## Specs

Stored in `docs/specs/`. Format: `docs/specs/NNNN-title.md`.

## Rules

- **Clean Architecture**: strict layer separation. Domain (agent schemas, business rules) never imports infrastructure (boto3, Bedrock). Application layer (agent builders) orchestrates domain and infrastructure interfaces.
- **Dependency rule**: outer layers depend on inner layers, never the reverse. `agents/<name>/schema.py` has zero AWS imports.
- **Agents as modules**: each agent lives in `src/agents/<name>/` with `__init__.py` (builder), `tools.py` (implementations), `schema.py` (Pydantic contracts). No other layout.
- **Pydantic everywhere**: every tool function has input and output schemas. No raw dicts cross tool boundaries.
- **Named exports only**: explicit `__all__` in every `__init__.py`. No `from module import *`.
- **snake_case**: file names, function names, variable names. No mixed styles.
- **Docstrings**: every public function and agent builder has a docstring.

## Agent skills

Declined: none

## Context files

- [src/agents/AGENTS.md](src/agents/AGENTS.md): Modular agent graph conventions, tool/schema layout, routing-tool factory pattern

_Drafted by /audit from the repo, worth a quick human pass. Edit freely: once a line stops matching this draft, later runs treat it as curated and will flag rather than overwrite it._
