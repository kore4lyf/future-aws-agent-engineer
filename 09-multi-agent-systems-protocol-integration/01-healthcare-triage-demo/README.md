# Sequential Coordinator Demo

Course 4, Module 1 — sequential multi-agent coordinator pattern with the Strands Agents SDK.

## Goal

Run a sequential multi-agent pipeline where specialized single-responsibility agents hand structured JSON to each other through a plain-Python coordinator.

## Demo 1 — Healthcare Triage

Three agents, one job each: `SymptomAnalyzer` (complaint → conditions/severity via `lookup_symptoms`), `UrgencyClassifier` (severity → urgent/standard/routine via `classify_urgency`), `AppointmentScheduler` (urgency → time slot via `book_appointment`). The coordinator `run_triage_pipeline` clears the shared `_tool_results` dict per patient, calls each agent in order, and threads tool JSON into the next prompt — never LLM prose. Fresh agent instances per patient avoid context bleed.

## Test Results

### Data Validation ✅ PASSED
- ✅ 3 patients with unique IDs and complete data
- ✅ 6 symptom conditions with severity levels (high/medium/low)
- ✅ 3 urgency levels with time slots (urgent/standard/routine)
- ✅ Patient symptoms match expected condition keywords

### Patient Data
| Patient ID | Name | Symptoms | Expected Urgency |
|------------|------|----------|------------------|
| P-1001 | Alice Johnson | Chest pain, shortness of breath, dizziness | urgent |
| P-1002 | Bob Smith | Headache, runny nose | routine |
| P-1003 | Carol Davis | Swollen ankle | standard |

### Symptom Conditions
| Symptom | Condition | Severity |
|---------|-----------|----------|
| chest pain | Possible cardiac event | high |
| shortness of breath | Respiratory distress | high |
| dizziness | Circulatory issue | medium |
| headache | Tension headache | low |
| runny nose | Upper respiratory infection | low |
| swollen ankle | Possible sprain | medium |

### Quick Start

```bash
cd 01-healthcare-triage-demo
cp .env.example .env

# Use Nova Lite to avoid Claude Marketplace access issues
echo "MODEL_ID=amazon.nova-lite-v1:0" >> .env

# Load AWS credentials
export AWS_ACCESS_KEY_ID="..."
export AWS_SECRET_ACCESS_KEY="..."
export AWS_SESSION_TOKEN="..."
export AWS_REGION="us-east-1"

# Run pipeline
uv run python main.py                    # All 3 patients
uv run python main.py --patient-id P-1001  # Single patient
```

### Layout

- `main.py` — entrypoint: AgentCore `invoke` plus local CLI
- `src/main.py` — pipeline: builders, coordinator, data tables, helpers

### Build plan

1. Healthcare triage pipeline (done) — proves model + prompt + tool per agent and JSON handoff via coordinator.
2. Next: smart-home device-management pipeline on the same pattern (retriever → diagnoser → resolver).
3. Test locally, then deploy with `agentcore deploy`.

