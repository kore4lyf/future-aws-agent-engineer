# Exercise – Incident Report Completion

## Overview

An operations engineer submits an incomplete incident report after a production issue. Your task is to build a Bedrock Flow and an AgentCore harness that reviews the report, identifies missing details, asks targeted follow-up questions, and generates a finalized report once all required information has been collected.

---

## What You Will Build

```
┌─────────────────────────────────────────────────────┐
│  OPTION A – Single-shot (Bedrock Flow)              │
│                                                     │
│  FlowInput (incident_report)                        │
│      │                                              │
│      ▼                                              │
│  [Prompt node: IncidentCoordinator]                 │
│      │                                              │
│      ▼                                              │
│  FlowOutput                                         │
│                                                     │
│  → Test from the Bedrock console                    │
│  → Foundation for multi-agent pipelines             │
└─────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────┐
│  OPTION B – Multi-turn (AgentCore Harness)          │
│                                                     │
│  chat.py  ←→  harness (stateful session)            │
│                                                     │
│  → Full feedback loop                               │
│  → Multi-turn conversation                          │
└─────────────────────────────────────────────────────┘
```

---

## Required Fields

A complete incident report must have all five of these:

| Field | Example |
|-------|---------|
| Severity | P1 / P2 / P3 / P4 |
| Affected service | checkout-api (us-east-1) |
| Impact | ~1,200 failed checkout attempts |
| Root cause | Load balancer misconfiguration after deploy v2.4.1 |
| Timeline | Started 14:32 UTC, detected 14:35 UTC, resolved 15:18 UTC |

---

## Part 1 – Deploy the Bedrock Flow (Option A)

The flow gives you a single-shot view of the coordinator prompt. Test it from the Bedrock console or via `test_flow.py`.

### Setup

```bash
python create_flow.py
```

This creates the flow, prepares it, and creates a `latest` alias. The alias ARN is saved to `.env` as `INCIDENT_FLOW_ALIAS_ARN`.

### Test from the console

1. Open the [Bedrock console](https://console.aws.amazon.com/bedrock) → **Flows**
2. Find `incident-report-flow` → click **Test**
3. Paste a test message and run

### Test via script

```bash
python test_flow.py
```

Runs three test cases:
1. **Minimal report** — expects a follow-up question
2. **Partial report** — expects a follow-up question about what's missing
3. **Complete report** — expects a formatted `FINAL REPORT`

### Clean up

```bash
python cleanup_flow.py
```

---

## Part 2 – Deploy the AgentCore Harness (Option B)

The harness runs the full multi-turn feedback loop. It keeps conversation state in a `runtimeSessionId`, so it can ask follow-up questions across multiple turns.

### Setup

```bash
python setup.py
```

Creates an IAM role and an AgentCore harness. The harness ARN is saved to `harness_arn.txt`.

### Chat

```bash
python chat.py
```

Starts an interactive session. Type your incident report, answer follow-up questions, and the coordinator will output a `FINAL REPORT` once all five fields are covered.

### Clean up

```bash
python cleanup.py
```

---

## Part 3 – Write the Coordinator Prompt

Both the flow and the harness share the same coordinator prompt (see `setup.py` for the full version). Key rules:

1. **Check all five fields** against what the engineer has told you.
2. **One question per turn** — ask about the single most important missing field.
3. **Never re-ask** about fields already covered.
4. **No fabricating** — only use details the engineer actually provided.
5. **Output the report** only when all five fields are covered, in this exact format:

```
FINAL REPORT
- Severity: [value]
- Affected service: [value]
- Impact: [value]
- Root cause: [value]
- Timeline: [value]
```

---

## Files

| File | Purpose |
|------|---------|
| `setup.py` | Creates IAM role + AgentCore harness |
| `chat.py` | Interactive multi-turn chat with the harness |
| `cleanup.py` | Deletes harness + IAM roles |
| `create_flow.py` | Creates the Bedrock Flow |
| `test_flow.py` | Tests the flow with 3 test cases |
| `cleanup_flow.py` | Deletes the flow + alias |
