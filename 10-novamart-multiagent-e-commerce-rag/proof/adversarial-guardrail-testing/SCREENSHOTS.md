# Screenshots

Five captures. Each command prints a short self-contained block, so one
terminal screenshot per command is enough.

```bash
cd 10-novamart-multiagent-e-commerce-rag
export PYTHONIOENCODING=utf-8
```

Valid unexpired AWS credentials must be exported for the session
(`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_SESSION_TOKEN`). The suite
fails immediately without them.

## 1. Competitor mentions

```bash
bash proof/adversarial-guardrail-testing/script.sh competitor
```

Expect `RESULT: CompetitorProducts - 2/2 blocked`.

## 2. Pricing negotiations

```bash
bash proof/adversarial-guardrail-testing/script.sh pricing
```

Expect `RESULT: PricingNegotiations - 2/2 blocked`.

## 3. Legal threats

```bash
bash proof/adversarial-guardrail-testing/script.sh legal
```

Expect `RESULT: LegalThreats - 2/2 blocked`.

## 4. Prompt injection

```bash
bash proof/adversarial-guardrail-testing/script.sh injection
```

Expect `RESULT: PromptInjection - 0/3 blocked`.

**This category is not blocked by the guardrail, and the screenshot should show
that.** Each case prints `VERDICT: NOT BLOCKED` with
`via model answered (no guardrail hit)`, and the response is the Orchestrator
refusing in natural language.

That is the honest result. Do not present these as blocked - the guardrail has
no prompt-injection topic, so what the screenshot demonstrates is that the
*model* refused, which is a weaker and different guarantee. The README explains
the distinction and a reviewer will check.

## 5. Combined summary

```bash
bash proof/adversarial-guardrail-testing/script.sh
```

Expect `TOTAL 6/9 blocked`, with CompetitorProducts, PricingNegotiations and
LegalThreats at 2/2 each and PromptInjection at 0/3. This is the capstone
capture for the checklist item.

## Tips

- Each block is roughly 20 lines, so one terminal window captures a category
  without scrolling.
- If the terminal background washes out the colour, set `FORCE_COLOR=0`.
- Blocked lines print `via guardrail blockedInputMessaging`, which is the
  evidence the intervention came from Bedrock rather than the model declining
  on its own. Unblocked lines print `via model answered (no guardrail hit)`.
