# Exercise – Incident Report Completion with an Agent Node

## Overview

An operations engineer submits an incomplete incident report after a production issue. Your task is to build a Bedrock Flow that reviews the report, identifies what operational details are missing, asks targeted follow-up questions, and generates a finalized report once all required information has been collected.

---

## What You Will Build

```
Flow Input (incident_report)
    │
    ▼
[Agent: IncidentReviewAgent]  ←→  asks follow-up questions (multi-turn)
    │  (when agent has collected all missing details, outputs a formatted report)
    ▼
Flow Output
```

---

## Task 1 – Create the Bedrock Agent

1. Open the [Amazon Bedrock console](https://console.aws.amazon.com/bedrock) and navigate to **Agents**
2. Click **Create agent** and name it `IncidentReviewAgent`
3. Under **Agent instructions**, write a prompt that instructs the agent to:
   - Review the submitted incident report for missing or vague information
   - Identify gaps across these required fields: affected systems, severity, root cause hypothesis, and impact
   - Ask targeted follow-up questions — one to three at a time — until all fields are covered
   - Not fabricate or assume any details
   - When all fields are collected, output a finalized, structured incident report with clearly labeled fields

> **TODO:** Write the agent instructions.

4. Under **Model**, select **Amazon Nova Pro**
5. Under **Additional settings**, enable **User input**
6. Click **Save and prepare** and wait for **Prepared** status

---

## Task 2 – Test the Agent in the Console Chat

Before wiring the agent into a flow, verify that it behaves correctly using the built-in test chat.

1. On the agent detail page, click **Test** to open the chat panel
2. Click **Prepare** if prompted, then start a new session

### Test 1 – Minimal report

```
Database went down around 3pm. Fixed it.
```

Confirm the agent asks focused follow-up questions rather than accepting the report as complete.

### Test 2 – Partially complete report

```
Incident: API gateway returning 503 errors
Started at 14:32 UTC, resolved 15:18 UTC
Affected: checkout service in us-east-1
Root cause: misconfigured load balancer after deploy at 14:28 UTC
Action taken: rolled back the deployment
```

Confirm the agent asks only about what is genuinely missing (severity, impact) and not about fields already provided.

### Test 3 – Already complete report

```
Severity: P1
Affected systems: checkout-api (us-east-1), payment-processor integration
Timeline: Started 14:32 UTC, detected 14:35 UTC, resolved 15:18 UTC
Root cause: Load balancer misconfiguration introduced in deploy v2.4.1 at 14:28 UTC
Impact: ~1,200 failed checkout attempts, estimated $34k in lost transactions
Remediation: Rolled back to v2.4.0, confirmed 503 rate dropped to zero at 15:18 UTC
```

Confirm the agent outputs a formatted final report without asking any follow-up questions.

---

## Task 3 – Create the Flow

1. Navigate to **Flows** and click **Create flow**
2. Name it `incident-report-completion` and click **Create**

---

## Task 4 – Configure the Flow Input

The flow takes a single input:
- `incident_report` (String) — the raw, potentially incomplete report submitted by the engineer

Configure the **Flow input** node to expose this single field.

---

## Task 5 – Add the Agent Node

1. Click **+** → **Agent**, name it `IncidentReviewAgent`
2. Select the `IncidentReviewAgent` you created and its alias
3. Set the input to `incident_report` (String)

---

## Task 6 – Connect the Nodes

| From | To | What to map |
|------|----|-------------|
| Flow input | IncidentReviewAgent | `incident_report` → agent input |
| IncidentReviewAgent (output) | Flow output | agent response → output |

---

## Task 7 – Prepare and Test

Click **Prepare**, wait for **Prepared** status, then test the flow end-to-end with the inputs from Task 2.

---

## Deliverable

- Screenshots of the completed flow and the agent node configuration
- The agent instructions you wrote for `IncidentReviewAgent`
- An example conversation showing the agent collecting missing details before producing a final report
