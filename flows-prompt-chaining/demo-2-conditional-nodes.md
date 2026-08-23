# Demo 2 – Conditional Nodes in Bedrock Flows

## Flow: support-router

```
Flow Input (ticket)  →  ClassifyTicket  →  RouteByCategory
                                               ├── "billing"   →  BillingResponder  →  BillingOutput
                                               ├── "technical" →  TechResponder     →  TechOutput
                                               └── else        →  OtherResponder    →  OtherOutput
```

**Note:** Each branch ends in its own Flow output node (BillingOutput, TechOutput, OtherOutput). A Flow output node accepts exactly one incoming connection, so wiring all three responders into a single output node fails when you prepare the flow. Only the branch the condition selects runs, so each invocation still produces exactly one output.

## Node A: ClassifyTicket

**System prompt:**

```
You are a support ticket classifier. Your only job is to read a support message and output exactly one word: "billing", "technical", or "other".

Rules:
- Output only the single word. No explanation, no punctuation, no extra text.
- Use "billing" for messages about charges, payments, invoices, subscriptions, or pricing.
- Use "technical" for messages about errors, bugs, API issues, login problems, or product behavior.
- If the message contains both topics, choose the dominant one.
- Use "other" if the message does not clearly fit either category.

Classify this support ticket:

<ticket>
{{ticket}}
</ticket>
```

**Input variable:** `ticket` (String)

**Expected output:** Exactly billing, technical, or other — nothing else.

## Condition Node: RouteByCategory

- **Condition 1:** `category == "billing"` → BillingResponder
- **Condition 2:** `category == "technical"` → TechResponder
- **Default (else):** → OtherResponder

The condition node reads ClassifyTicket's output as `category`. The else branch catches both explicit "other" outputs and any unexpected classifier output — making it a reliable safety net regardless of what the model returns.

**Note on expression syntax:** When you enter the condition expression in the Bedrock console, the variable name in the expression must exactly match the input name you configured for the condition node. In this demo the input is named `category`, so the expressions are `category == "billing"` and `category == "technical"`. If the console pre-fills a different name (e.g. `conditionInput`), update the expressions to match — a mismatch will cause a validation error.

## Node B: BillingResponder

**System prompt:**

```
You are a billing support specialist. Your responses are professional, concise, and empathetic. You acknowledge the issue, explain what will happen next, and provide a clear next step.

Rules:
- Keep responses under 120 words
- Do not promise specific outcomes (e.g., do not guarantee a refund)
- Always end with one concrete action the customer can take or expect

Respond to this billing support request:

<ticket>
{{ticket}}
</ticket>
```

**Input variable:** `ticket` (String) — wired from Flow input, not from ClassifyTicket. ClassifyTicket outputs only a single routing word ("billing", "technical", or "other"); the responder needs the full original ticket text to generate a useful response.

**Expected output:** Under 120 words, no outcome promises, ends with a concrete next step.

## Node C: TechResponder

**System prompt:**

```
You are a technical support specialist. Your responses are direct, solution-oriented, and precise. You acknowledge the issue, suggest the most likely cause, and provide actionable troubleshooting steps.

Rules:
- Keep responses under 150 words
- Use numbered steps when providing instructions
- If you need more information to diagnose the issue, ask one specific clarifying question at the end

Respond to this technical support request:

<ticket>
{{ticket}}
</ticket>
```

**Input variable:** `ticket` (String) — wired from Flow input, not from ClassifyTicket, for the same reason: the responder needs the full ticket, not just the routing label.

**Expected output:** Under 150 words, numbered troubleshooting steps, optional single clarifying question at the end.

## Node D: OtherResponder

**System prompt:**

```
You are a support assistant. The message you received does not clearly fit a billing or technical support category.

Write a brief, polite response that:
- Acknowledges the message
- Explains that the team will need a bit more context to help
- Asks the customer to clarify whether their issue is related to billing or a technical problem

Keep the response under 80 words. Do not guess at the nature of the issue.

Customer message:

<ticket>
{{ticket}}
</ticket>
```

**Input variable:** `ticket` (String) — wired from Flow input.

**Expected output:** Under 80 words, politely asks for clarification on the category of the issue.

## Test Inputs

**Test 1 – Billing → expected route:** ClassifyTicket → "billing" → BillingResponder

```
I was charged twice for my subscription last month. I reached out last week and never heard back. I need this resolved before my next billing cycle.
```

**Test 2 – Technical → expected route:** ClassifyTicket → "technical" → TechResponder

```
Your API returns a 500 error when I submit a POST request with more than 50 items in the batch. This is happening in production and blocking our pipeline.
```

**Test 3 – Ambiguous → expected route:** ClassifyTicket → "other" → OtherResponder

```
Hi, I have a question about your product.
```

**Test 4 – Mixed (billing + technical) → observe which category the classifier picks**

```
I upgraded my plan last week and now I keep getting a 403 Forbidden error when calling the API.
```
