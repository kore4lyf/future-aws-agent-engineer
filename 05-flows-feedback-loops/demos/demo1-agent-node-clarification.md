# Demo 1 – Requirements Clarification with an Agent Node

## Flow: `requirements-with-agent`

```
Flow Input (tool_request)  →  RequirementsAgent (multi-turn)  →  Flow Output
```

---

## Agent: RequirementsAgent

**Agent instruction:**
```
You are a requirements analyst for an internal tools team. Your job is to collect enough information to write a precise requirements specification.

When a user submits a tool request, identify what critical information is missing from these three categories:
- Purpose: what the tool does and why it is needed
- Key features: the specific capabilities required
- Success criteria: how the team will know it is working correctly

Ask focused follow-up questions — one at a time — until you have specific answers for all three categories. Do not fabricate or assume any details. Do not ask questions on the categories you have information for already.

When you have gathered sufficient information, respond with:

REQUIREMENTS COMPLETE
  - Purpose: [what the tool does and why it is needed]
  - Key features: [the specific capabilities required]
  - Success criteria: [how the team will know it is working correctly]
```

**Model:** Amazon Nova Pro
**Setting:** Enable **User input** under Additional settings.

**Expected behavior:** Asks follow-up questions in groups of 1–3 until all categories are covered, then outputs `REQUIREMENTS COMPLETE` followed by the structured summary.

---

## Test Prompts

**Test 1 – Vague request** → expected: multiple rounds of follow-up questions
```
I need a dashboard for the AI agent.
```

**Test 2 – Partially detailed** → expected: questions only about missing categories
```
We need a tool to track employee onboarding. It should show which steps each new hire has completed.
```

**Test 3 – Already complete** → expected: `REQUIREMENTS COMPLETE` with no follow-up questions
```
Build an internal API status page for our platform engineers. The purpose is to help on-call engineers to quickly troubleshoot incidents. It should poll our 12 microservices every 60 seconds, show uptime percentage and last response time for each, and send a Slack alert when any service is down for more than 2 minutes. Success means on-call engineers stop checking Grafana manually during incidents.
```

---

## Flow Test Input

Run the flow with this vague input and answer follow-up questions naturally:

```
I need a dashboard for finance.
```

Sample answers to agent follow-up questions:
- *What will it show?* → "Budget vs. actuals by department, updated monthly"
- *Who uses it?* → "Finance managers and department heads"
- *Where does the data come from?* → "Our ERP system, exported as CSV each month"

**Expected:** After a few exchanges the agent outputs `REQUIREMENTS COMPLETE` followed by the structured summary.
