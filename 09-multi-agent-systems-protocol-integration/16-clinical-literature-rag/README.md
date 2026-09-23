# Clinical Literature — Multi-Agent RAG Exercise (Lesson 8)

Hospital-network assistant: parallel Drug Interactions + Clinical Guidelines KBs, dedup/rank, then a **three-section** clinical summary (Drug Interactions → Clinical Guidelines → Integrated Recommendation) with degradation notices.

## Requirements covered

| Requirement | Where |
|---|---|
| Two specialized retrievers | `build_drug_interactions_retriever`, `build_clinical_guidelines_retriever` |
| Dedup + aggregate + rank | `aggregate_results` — doc_id + near-identical content fingerprint |
| Three-section synthesis | `build_synthesis_agent` / `SYNTHESIS_STRUCTURE` |
| Partial-result flagging | `SIMULATE_FAILURE`, `degraded`, `missing_domains` → DEGRADED RESULT notice |
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

Force a partial-result path:

```bash
# in .env
SIMULATE_FAILURE=drugs
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
