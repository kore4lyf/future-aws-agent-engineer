# AI Agent Observability Dashboard

Standalone single-page dashboard for the NovaMart multi-agent support
system.

## Run

```bash
python server.py
```

Then open http://127.0.0.1:8787.

## How it gets data

A local Python proxy (boto3, no browser credentials) queries AWS and
serves JSON. No credentials are ever shipped to the page.

| Panel | AWS source |
|---|---|
| Invocations over time | CloudWatch Logs Insights — `trace ... started` lines |
| Errors over time | Same log group — ERROR/WARNING lines |
| Avg latency per agent | X-Ray subsegments in `aws/spans` (Transaction Search) |
| Runtime invocations / latency / errors | CloudWatch metrics, namespace `AWS/Bedrock-AgentCore` |
| Guardrails | Structured `GUARDRAIL policy=...` log line (see below) |

## Guardrail instrumentation

Bedrock Guardrails publish no CloudWatch metric and AgentCore emits no
guardrail signal, so the agent logs one canonical line per intervention:

```
GUARDRAIL policy=<Name> category=<Category> action=<BLOCK|ANONYMIZE> source=<input|output|fallback> trace=<id>
```

Do NOT add per-factory hooks in `src/agents/orchestrator/tools.py`.
Telemetry is centralized: `src/telemetry/guardrails.py::emit_guardrail_event`
builds the line via `telemetry.contract.format_guardrail_line`, and the
`scenarios` / `serve` / `chat` entry points emit the same canonical line
for the fallback path (blocked text but no captured trace event). The
dashboard query parses both the canonical 5-field line and legacy 3-field
lines (`GUARDRAIL policy=X action=Y trace=Z`), so old logs keep working.

## Shared contract

`contract.py` (here) is a byte-identical mirror of
`../10-novamart-multiagent-e-commerce-rag/src/telemetry/contract.py`
(canonical). It pins the tool→node map, the span node labels, the
guardrail line format, and the KB-span aggregation rule. Edit the
canonical file, copy it over verbatim, and run
`python -m unittest tests.test_contract_parity` to confirm.

## Diagnostics

`/api/diagnose` lists your AWS identity, which log groups exist, and
which metrics are published. Run that first if the dashboard shows
unavailable.

## Source precedence

Per-agent latency: X-Ray subsegments → traced `tool done` lines →
AgentCore runtime metrics (single row). Nothing is invented when a
source is missing.
