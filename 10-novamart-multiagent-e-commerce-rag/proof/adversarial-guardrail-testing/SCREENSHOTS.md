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

Confirm the guardrail version before capturing - it must read
`puwoy0wtj9a7  (version 10)`. Version 9 has no `PromptInjection` topic and the
injection category will show 0/3.

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

Expect `RESULT: PromptInjection - 3/3 blocked`.

Each case shows `VERDICT: BLOCKED` with `via guardrail blockedInputMessaging`,
which is the evidence the intervention came from Bedrock rather than the model
declining on its own.

## 5. Combined summary

```bash
bash proof/adversarial-guardrail-testing/script.sh
```

Expect `TOTAL 9/9 blocked`, with all four categories at full marks. This is the
capstone capture for the checklist item.

## Tips

- Each block is roughly 20 lines, so one terminal window captures a category
  without scrolling.
- If the terminal background washes out the colour, set `FORCE_COLOR=0`.
- Run categories individually for screenshots 1-4, then the combined run for
  screenshot 5. Both give the same verdicts; the combined run is simply the
  summary.
