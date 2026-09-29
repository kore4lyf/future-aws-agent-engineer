# Screenshots

Five captures to make. Each command prints a short, self-contained block, so
one terminal screenshot per command is enough.

Open a terminal with the environment ready:

```bash
cd 10-novamart-multiagent-e-commerce-rag
. "C:/Users/Korede/AppData/Local/Temp/opencode/awsenv.ps1"   # if still present
export PYTHONIOENCODING=utf-8
```

If `awsenv.ps1` is gone, export `AWS_ACCESS_KEY_ID`,
`AWS_SECRET_ACCESS_KEY` and `AWS_SESSION_TOKEN` for your current session
credentials first. The suite fails immediately without valid, unexpired
credentials.

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

Expect `RESULT: PromptInjection - 2/2 blocked`.

**Important:** capture this one *alone*. Run on its own it blocks both cases.
Run as part of the full suite the first case is not blocked, because the
classifier weighs the preceding context differently. See the README - the
full-suite result (1/2) is the honest one, so screenshot the isolated run only
as an illustration and cite the README for the discrepancy rather than
implying injection is always caught.

## 5. Combined summary

```bash
bash proof/adversarial-guardrail-testing/script.sh
```

Expect `TOTAL 7/8 blocked` with the per-category breakdown. This is the
capstone capture for the checklist item.

## Tips

- Each block is roughly 20 lines, so a single terminal window captures one
  category without scrolling.
- Colour is emitted. If the terminal background washes it out, set
  `FORCE_COLOR=0` before running.
- The block reason is always printed as `via guardrail blockedInputMessaging`,
  which is the evidence that the intervention came from Bedrock rather than
  from the model declining.
