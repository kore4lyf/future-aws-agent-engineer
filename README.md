# Future AWS Agent Engineer

**Korede Faleye** — built through the Udacity AWS AI & ML Scholars Program
(AWS AI & ML Scholars, Nanodegree: Future AWS Agent Engineer).

This repo is the full arc of that program, from first prompts to a deployed
team of cooperating agents: prompt craft in the Bedrock Playground and API,
single agents with the Strands SDK on AgentCore, multi-agent orchestration
patterns, and finally NovaMart — a guarded, observable multi-agent customer
support system with its own chat app and telemetry dashboard.

## Flagship: NovaMart multi-agent customer support

Three projects that run as one system:

| Project | What it is |
|---|---|
| `10-novamart-multiagent-e-commerce-rag` | Orchestrator + Inventory, Refund, Policy (3-KB RAG), and Communication agents on Strands + AgentCore Runtime. Bedrock Guardrail (deny topics, prompt-injection filter), DynamoDB workflow state, X-Ray tracing, CloudWatch log shipping. |
| `10-novamart-customer-support-app` | Customer-facing chat: React + Tailwind frontend, Cognito auth, Express gateway that verifies JWTs and SigV4-signs `InvokeAgentRuntime`. Demo mode runs without AWS. |
| `10-novamart-agent-observability-dashboard` | Standalone telemetry UI. A local boto3 proxy (credentials never reach the browser) serves CloudWatch Logs Insights, `aws/spans` subsegments, and AgentCore metrics: invocations, per-agent latency, guardrail violations by policy with trace-id lookup. |

Verified end to end: 9/9 adversarial guardrail blocks across four attack
categories, each attributed to its real policy on the dashboard; deployed
runtime re-verified after every promotion.

## Course projects

- `06-capstone-project-1-customer-support-chatbot` — support chatbot on the
  AgentCore harness: routing system prompt, multi-turn bug intake, gateway
  ticket filing, with tests and evidence.
- `07-bedrock-strands-agent` — Strands agent collection: web search, code
  interpreter, long-term memory, RAG knowledge base, browser search,
  observability.
- `08-ai-support-agent` — AI support agent with conversation state, schemas,
  and Lambda targets.
- `09-multi-agent-systems-protocol-integration` — 22 exercises from routing
  and parallel workflows through sagas, multi-agent RAG, governance, and
  deployment walkthroughs.

## Foundations (`00`–`05`)

Bedrock API fluency (`invoke_model`, Converse), AgentCore harness setup,
prompt chaining and conditional flows, feedback loops, and a restaurant
recommendation assistant — the primitives everything above composes.

## Stack

Python 3.12 · Strands Agents SDK · Amazon Bedrock (AgentCore Runtime,
Knowledge Bases, Guardrails) · CloudWatch Logs/X-Ray · DynamoDB ·
S3 Vectors · Cognito · TypeScript/React/Tailwind/Express · boto3

## Run it

```bash
# NovaMart agents (from the project dir)
pip install -r 10-novamart-multiagent-e-commerce-rag/requirements.txt
python 10-novamart-multiagent-e-commerce-rag/src/agent_orchestrator.py deploy
python 10-novamart-multiagent-e-commerce-rag/src/agent_orchestrator.py chat

# Dashboard
python 10-novamart-agent-observability-dashboard/server.py
# open http://127.0.0.1:8787 — /api/diagnose first if panels show unavailable

# Chat app (demo mode, no AWS)
cd 10-novamart-customer-support-app && npm run dev
```

AWS calls need standard credentials (`aws configure` or
`AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY`, plus `AWS_SESSION_TOKEN`
for lab sessions). The dashboard needs no credentials in the browser; the
gateway is the only component that signs AWS calls client-side-adjacent.

## Conventions

- `.env` files are never committed (`.env.example` documents every key).
- Guardrail telemetry is a first-class output: every intervention is logged
  with its policy and trace id because Bedrock publishes no guardrail metric.
- Offline-capable tests gate every telemetry change; live tests prove the
  AWS path with real data.
