# Sequential Coordinator Demo

Course 4, Module 1 — sequential multi-agent coordinator pattern with the Strands Agents SDK.

## Goal

Run a sequential multi-agent pipeline where specialized single-responsibility agents hand structured JSON to each other through a plain-Python coordinator.

## Demo 1 — Healthcare Triage

Three agents, one job each: `SymptomAnalyzer` (complaint → conditions/severity via `lookup_symptoms`), `UrgencyClassifier` (severity → urgent/standard/routine via `classify_urgency`), `AppointmentScheduler` (urgency → time slot via `book_appointment`). The coordinator `run_triage_pipeline` clears the shared `_tool_results` dict per patient, calls each agent in order, and threads tool JSON into the next prompt — never LLM prose. Fresh agent instances per patient avoid context bleed.

Setup: `cp .env.example .env` with AWS credentials loaded, then `uv run main.py` (all patients) or `uv run main.py --patient-id P-1001` (one patient).

## Layout

- `main.py` — entrypoint: AgentCore `invoke` plus local CLI
- `src/main.py` — pipeline: builders, coordinator, data tables, helpers

## Build plan

1. Healthcare triage pipeline (done) — proves model + prompt + tool per agent and JSON handoff via coordinator.
2. Next: smart-home device-management pipeline on the same pattern (retriever → diagnoser → resolver).
3. Test locally, then deploy with `agentcore deploy`.
