# Demo 3 – Evals

## Prompt Iteration: Weak vs. Refined

Evals are most useful when you compare two prompt versions. Below are the two prompts used in this demo.

### Version 1 – Weak Prompt (baseline)

```
You are a customer support agent.
Reply to this customer email:

{{customer_email}}
```

**Problems:** No tone guidance, no required structure, no reference to company policy. The model may make up shipping timelines, sound robotic, or miss the customer's specific concern entirely.

### Version 2 – Refined Prompt

```
You are a customer support agent for ShopFast, an e-commerce retailer.
Draft a professional reply to the customer email below.

Structure your reply as:
1. Apology – acknowledge the specific issue sincerely
2. Resolution – explain exactly what will happen next
3. Follow-up – one concrete next step with a timeframe

Company policy:
{{policy}}

Brand voice: {{brand_voice}}

Customer email:
{{customer_email}}

Write only the reply body. Do not include a subject line.
```

**Improvements:** Explicit 3-part structure, company policy grounding (no invented promises), and brand voice consistency.

Running both versions through the same eval set lets you see whether refinements actually improve scores — not just feel better.

## Eval JSONL Format

Each line written to `eval_responses.jsonl` follows this schema:

```json
{
  "prompt": "<customer question>",
  "referenceResponse": "<ideal answer used for scoring>",
  "modelResponses": [
    {
      "response": "<model output>",
      "modelIdentifier": "<label for this run>"
    }
  ]
}
```

## Eval Job Configuration

| Field | Value |
|-------|-------|
| Evaluation method | Automatic |
| Inference | BYOI – use my own responses |
| Metrics | ROUGE, BERTScore, METEOR |

## Metrics

| Metric | What it measures |
|--------|------------------|
| ROUGE-L | Key phrase overlap with the reference response |
| BERTScore | Semantic similarity to the reference response |
| METEOR | Word-level precision and recall with synonym matching |
