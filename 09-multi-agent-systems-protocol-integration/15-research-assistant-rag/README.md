# Research Assistant — Multi-Agent RAG Demo (Lesson 8)

Parallel retriever agents query separate Bedrock Knowledge Bases (CS + Biology), the aggregator merges/dedups/ranks passages, and a grounded synthesis agent answers with `[DOC_ID]` citations.

## Patterns

| Pattern | Where |
|---|---|
| Parallel retrieval | `ThreadPoolExecutor(max_workers=2)` — CS + Bio KBs at once |
| Specialized retrievers | one agent + one `@tool` per knowledge base |
| Aggregate / dedup / rank | `aggregate_results` — merge, best `doc_id` by score, top-K |
| Grounded synthesis | Nova Pro, no tools, strict `[DOC_ID]` citation rules |
| Graceful degradation | Bio retriever catches `ConnectionError`; empty → partial/empty answer |
| Fail-fast config | missing `CS_KB_ID` / `BIO_KB_ID` raises setup error |

## Queries demonstrated

1. **Cross-domain** — “applications of machine learning in genomics” → both KBs contribute
2. **Domain-specific** — “CRISPR gene-editing for crop improvement” → bio only
3. **Out of scope** — “blockchain consensus mechanisms for IoT networks” → no relevant results

## Setup (KBs are manual — cannot be created by CloudFormation)

```bash
cp .env.example .env   # paste AWS credentials

# 1. S3 source bucket
aws cloudformation deploy --template-file infrastructure/stack.yaml \
    --stack-name lesson-08-demo-rag

# 2. Seed 24 documents (cs/, bio/, drugs/, guidelines/)
uv run python seed_documents.py

# 3. Bedrock console → Create Knowledge Base (x2)
#    Data source: s3://<bucket>/cs/  and  s3://<bucket>/bio/
#    Embedding: amazon.titan-embed-text-v2:0
#    Vector store: Amazon S3 Vectors
#    Click Sync, then copy KB IDs into .env (CS_KB_ID, BIO_KB_ID)

# 4. Run
uv run python research_assistant_rag.py
```

## Test

```bash
uv run --with pytest --with boto3 pytest -q
```

Unit tests cover aggregation/dedup/ranking without AWS. Live retrieval tests skip unless KB IDs + credentials are set.

## Cleanup

Delete both Knowledge Bases in the Bedrock console first, then:

```bash
aws cloudformation delete-stack --stack-name lesson-08-demo-rag
```
