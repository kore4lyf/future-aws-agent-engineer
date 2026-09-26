# PR: feat: implement Bedrock Guardrail with content, PII, topic, and word policies

## What

This PR implements the Bedrock Guardrail for the NovaMart multi-agent customer support system. The guardrail enforces four safety policies: content filtering, PII protection, topic denial, and profanity filtering. It is created programmatically in `create_guardrail()` and published as a numbered version for use by the deployed agents.

## Why

The project requires a Bedrock Guardrail to block harmful content, PII exposure, off-topic subjects, and profanity. The guardrail is attached to every agent's BedrockModel so that all model invocations are filtered automatically. This is a core safety requirement for a customer-facing AI system.

## Changes

- Implemented `create_guardrail()` in `src/agent_orchestrator.py` with four policy blocks:
  - Content policy: SEXUAL, VIOLENCE, HATE at HIGH strength; INSULTS, MISCONDUCT at MEDIUM strength
  - PII policy: BLOCK credit card numbers and SSNs; ANONYMIZE emails and phone numbers
  - Topic policy: DENY competitor products, pricing negotiations, legal threats (STANDARD tier)
  - Word policy: managed PROFANITY list enabled
- Added `crossRegionConfig` with `guardrailProfileIdentifier: us.guardrail.v1:0`
- Added `create_guardrail_version()` call to publish a numbered version
- Added deduplication logic to reuse an existing guardrail if one with the same name exists
- Added error handling for AWS API failures
- Updated `.env` with the created guardrail ID and version

## How to test or verify

```bash
python tests/test_agent.py task3
```

Expected result: 13/20 points for guardrail creation and policy validation. The remaining 7 points require AgentCore Runtime deployment (Task 4).

## Risk & rollout

Low risk, no migrations, no flags. The guardrail is created once and its ID/version are stored in `.env`. If the guardrail already exists, the function reuses it. The only risk is if the guardrail policies are too restrictive and block legitimate customer queries, but the topic definitions are narrow enough to allow normal support conversations.

## Notes for reviewers

The topic policy for pricing negotiations is defined narrowly as haggling or requests to change an advertised price, while allowing arithmetic with an already-specified price and discount. This avoids blocking the math scenario in the test suite. The STANDARD tier is used with `crossRegionConfig` to ensure consistent behavior across regions.
