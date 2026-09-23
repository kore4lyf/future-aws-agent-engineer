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
- `test/test_main.py` — 24 unit tests validating logic without AWS calls
- `demo.py` — demonstration script showing pipeline flow without AWS calls

## Implementation notes

- `screening_cache`, `review_cache`, and `notice_cache` store structured tool receipts; the coordinator reads receipts instead of parsing agent prose.
- Screening uses Nova Lite at temperature `0.0`; deep review uses Claude Sonnet at `0.1`; notice drafting uses Nova Pro at `0.3`.
- The coordinator screens every post, reviews only `BORDERLINE` posts, and sends notices only for final `HARMFUL` verdicts.
- Safe posts use one agent, harmful posts use screening plus notice, and borderline posts use screening plus review, with notice only when review returns `HARMFUL`.

## Test Results

### Unit Tests (24 tests - all passing)
```bash
cd 04-content-moderation-pipeline
uv pip install pytest
uv run python -m pytest test/test_main.py -v
```
**Result:** ✅ 24/24 passing

Tests cover:
- Data structure validation (6 tests)
- Keyword detection logic (8 tests)
- Cache behavior (3 tests)
- Deep review verdict mappings (3 tests)
- Notice template validation (1 test)
- Pipeline routing logic (2 tests)
- Edge cases (2 tests)

### Live AWS Tests

| Post | Classification | Models Called | Status |
|------|---------------|---------------|--------|
| POST-001 (safe pasta recipe) | SAFE | Nova Lite | ✅ PASS |
| POST-004 (harmful - "destroy") | HARMFUL | Nova Lite + Nova Pro | ✅ PASS |
| POST-007 (borderline - "idiots") | BORDERLINE | Nova Lite + Claude Sonnet | ❌ Claude access denied |

**Working paths:**
- ✅ Safe posts: Screening only (1 model call)
- ✅ Harmful posts: Screening + Notice (2 model calls, skips review)
- ❌ Borderline posts: Requires Claude Sonnet (needs AWS Marketplace subscription)

**Known limitation:** Claude Sonnet (`us.anthropic.claude-sonnet-4-5-20250929-v1:0`) requires AWS Marketplace subscription. The screening and notice models (Nova Lite, Nova Pro) work without additional subscriptions.

## Quick Start

```bash
cd 04-content-moderation-pipeline
cp .env.example .env
# Load AWS credentials
export AWS_ACCESS_KEY_ID="..."
export AWS_SECRET_ACCESS_KEY="..."
export AWS_SESSION_TOKEN="..."
export AWS_REGION="us-east-1"

# Run with uv
uv run main.py                    # Process all 9 posts
uv run main.py --post-id POST-001  # Process single post

# Run tests (no AWS required)
uv pip install pytest
uv run python -m pytest test/test_main.py -v

# Run demo (no AWS required)
uv run python demo.py
```

## Demo Output Summary

```
Total Posts: 9
  - Safe (approved): 5
  - Harmful (removed): 4  
  - Borderline (required review): 3

Pipeline Flow:
  - Posts screened: 9
  - Posts reviewed: 3
  - Notices generated: 4
```

## Project Structure

```
content-moderation-pipeline/
├── .env.example          # Environment template
├── .gitignore
├── README.md
├── demo.py               # Demo script (no AWS)
├── main.py               # Entrypoint
├── pyproject.toml        # Dependencies
├── uv.lock               # Locked dependencies
├── src/
│   ├── __init__.py
│   └── main.py           # Core pipeline
└── test/
    └── test_main.py      # Unit tests
```
