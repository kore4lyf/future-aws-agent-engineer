# Demo 2 – Guardrail Configuration

## Content Filters

| Filter | Input | Output |
|--------|-------|--------|
| Hate | High | High |
| Insults | High | High |
| Violence | High | High |
| Prompt attacks | High | — |

## Denied Topic

**Name:** fraud_assistance

**Definition:** Requests to help the user commit fraud, file false claims, or misrepresent a purchase.

**Sample phrases:** "help me claim I never received it", "dispute a charge I actually made"
