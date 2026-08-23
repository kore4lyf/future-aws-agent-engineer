# Exercise Solution – Incident Report Completion with an Agent Node

## Flow Structure

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

## Bedrock Agent: IncidentReviewAgent

**Agent instructions:**
```
You are an incident response coordinator. When an engineer submits an incident report, your job is to review it and collect any missing information before the report can be escalated or handed off.

A complete incident report must cover all four of these fields:
- Affected systems: which services, components, or regions were impacted
- Severity: P1 / P2 / P3 / P4
- Root cause: what caused the incident
- Impact: who or what was affected and to what extent

Review the submitted report and identify which fields are missing or too vague to act on. Ask focused follow-up questions — one to three at a time — until you have specific answers for every field. Do not fabricate or assume any details.

When all fields are covered, output a finalized incident report in this exact format. Write each bullet point on a separate line.

## Incident Report

* **Affected systems:** [value]
* **Severity:** [value]
* **Root cause hypothesis:** [value]
* **Impact:** [value]
```

**Model:** Amazon Nova Pro

**Additional settings:** User input — enabled

---

## Connection Map

| From | To | Mapping |
|------|----|---------|
| Flow input | IncidentReviewAgent | `incident_report` → agent input |
| IncidentReviewAgent (output) | Flow output | agent response → output |

---

## Expected Outputs

### Test Case 1 – Minimal report

Input: `Database went down around 3pm. Fixed it.`

The primary Postgres database. The API and the background job processor both depend on it.
End users got errors for about 25 minutes. Severity P2.
Root cause: Disk filled up due to unrotated logs. We cleared the logs and restarted the service.

The agent asks several rounds of questions. Example exchange:

> **Agent:** Which database was affected, and which services or teams depend on it?
>
> **User:** The primary Postgres database. The API and the background job processor both depend on it.
>
> **Agent:** How severe was the impact — were end users affected, or was this limited to internal systems? And approximately how long was the outage?
>
> **User:** End users got errors for about 25 minutes. Severity P2.
>
> **Agent:** What caused the outage, and what steps were taken to restore the database?
>
> **User:** Disk filled up due to unrotated logs. We cleared the logs and restarted the service.

Agent then outputs the finalized report:

```
## Incident Report

**Affected systems:** Primary Postgres database; API service and background job processor
**Severity:** P2
**Root cause hypothesis:** Disk exhaustion caused by unrotated log files
**Impact:** End users received errors for approximately 25 minutes
```

### Test Case 2 – Partially complete report

Input includes affected system and root cause — but severity and impact are missing.

The agent asks only about the missing fields:

> **Agent:** What severity level would you assign to this incident? And approximately how many users or transactions were affected during the outage window?

After receiving answers, it outputs the finalized formatted report.

### Test Case 3 – Already complete report

The agent outputs the formatted report immediately without asking any follow-up questions.

---

## Why This Design Works

**The agent instructions list exactly four required fields.** This gives the agent a concrete checklist to evaluate the submitted report against, rather than making a vague judgment about whether the report is "good enough". The agent asks only about what is missing — it does not re-ask for information already provided.

**The agent produces the final formatted report directly.** Because the agent both collects information and formats the output, the flow needs only a single node between input and output. This keeps the flow simple while still supporting multi-turn conversation.

**User input is enabled on the agent.** Without this setting, the agent cannot pause mid-execution to ask the user a question. It is required for any agent that needs multi-turn conversation.
