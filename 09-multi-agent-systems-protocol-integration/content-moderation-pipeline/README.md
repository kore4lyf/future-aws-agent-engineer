# Content Moderation Pipeline

Course 4 — tiered multi-model moderation: screen all, review borderline, notify on harmful.

## What we're building

A cost-aware backend for a high-volume social platform. Three specialists with conditional routing:

1. **Screening (Nova Lite, temp 0.0)** — every post via `screen_post` -> `SAFE` | `HARMFUL` | `BORDERLINE` + confidence. Fast and deterministic.
2. **Deep Review (Claude Sonnet, temp 0.1)** — only `BORDERLINE` via `deep_review_post` -> `SAFE` | `HARMFUL` + one-sentence reason. Reasoning depth.
3. **Notice (Nova Pro, temp 0.3)** — only final `HARMFUL` via `draft_notice` -> user-facing message. Slight warmth for communications.

`run_moderation_pipeline` (plain Python) routes on labels: screen -> if `BORDERLINE` then review -> if final verdict is `HARMFUL` then notice. Nine sample posts cover all paths.

## Layout

- `main.py` — entrypoint: AgentCore `invoke` plus local CLI (`--post-id` for one, no flag for all nine)
- `src/main.py` — shared data, tools, three model-specific agent builders, coordinator, and caches

## Implementation notes

- `screening_cache`, `review_cache`, and `notice_cache` store structured tool receipts; the coordinator reads receipts instead of parsing agent prose.
- Screening uses Nova Lite at temperature `0.0`; deep review uses Claude Sonnet at `0.1`; notice drafting uses Nova Pro at `0.3`.
- The coordinator screens every post, reviews only `BORDERLINE` posts, and sends notices only for final `HARMFUL` verdicts.
- Safe posts use one agent, harmful posts use screening plus notice, and borderline posts use screening plus review, with notice only when review returns `HARMFUL`.

Run: `cp .env.example .env`, load AWS credentials, then `uv run main.py`; use `--post-id POST-001` to process one post or omit it to process all nine.
