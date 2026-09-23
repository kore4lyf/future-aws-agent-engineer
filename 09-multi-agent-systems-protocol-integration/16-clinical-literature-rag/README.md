# Clinical Literature — Multi-Agent RAG Exercise (Lesson 8)

Hospital-network assistant: parallel Drug Interactions + Clinical Guidelines KBs, merge/dedup/rank, then a **three-section** clinical summary (DRUG INTERACTIONS → CLINICAL GUIDELINES → INTEGRATED RECOMMENDATION) with a PARTIAL RESULTS disclaimer when one KB is down.

## Requirements covered

| Requirement | Where |
|---|---|
| Graceful failure inside each retriever | tool `try/except ConnectionError` → `passages_found: 0` + error JSON |
| Two specialized retrievers | `build_drug_interactions_retriever`, `build_clinical_guidelines_retriever` |
| Merge → dedup → rank → top-K | `aggregate_results` / `deduplicate_passages` (`TOP_K=10`) |
| Three-section synthesis | `build_synthesis_agent` — Nova Pro `temperature=0.1` |
| Partial-results disclaimer | `fail_at` → `partial=True` → `PARTIAL RESULTS` in system prompt |
| Never LLM with empty evidence | both KBs empty → `"No relevant results found."` (no synthesis call) |
| Parallel orchestration | `ThreadPoolExecutor(max_workers=2)` — both submitted before collect |

## Setup

```bash
cp .env.example .env   # paste AWS credentials

aws cloudformation deploy --template-file infrastructure/stack.yaml \
    --stack-name lesson-08-exercise-rag

uv run python seed_documents.py

# Bedrock console → 2 Knowledge Bases:
#   s3://<bucket>/drugs/     -> DRUG_INTERACTIONS_KB_ID
#   s3://<bucket>/guidelines/ -> CLINICAL_GUIDELINES_KB_ID
#   Embedding: amazon.titan-embed-text-v2:0
#   Vector store: Amazon S3 Vectors
#   Sync, copy IDs into .env

uv run python clinical_literature_rag.py
```

Query 3 always sets `fail_at="drug"` (Drug Interactions KB offline → partial result). Override in `.env`:

```bash
SIMULATE_FAILURE=guidelines   # fail the guidelines KB instead
```

## Test

```bash
uv run --with pytest --with boto3 pytest -q
```

## Cleanup

Delete both KBs in the Bedrock console, then:

```bash
aws cloudformation delete-stack --stack-name lesson-08-exercise-rag
```
