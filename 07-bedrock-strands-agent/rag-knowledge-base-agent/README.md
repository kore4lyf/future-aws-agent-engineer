# RAG Knowledge Base Agent — Horizon Travel (Standalone)

Grounded answers via **S3 Vectors + Bedrock Knowledge Base + Titan Text Embeddings v2**.

## Architecture
```
docs/*.md → S3 bucket → Bedrock Knowledge Base (Titan v2 embeddings → S3 Vectors)
                              ↓
                    bedrock-agent-runtime:Retrieve
                              ↓
                   Strands @tool retrieve(query, top_k)
                              ↓
                   Agent (Nova Pro) — cites Source URIs
```

## Quick Start
1. `uv sync` (or `pip install -e .`)
2. Set env: `KNOWLEDGE_BASE_ID`, `AWS_REGION=us-east-1`
3. Upload docs to S3 + create KB (see `scripts/setup_kb.py`)
4. `uv run python -m src.main` or `agentcore dev`

## Tool
`retrieve(query, top_k=5)` wraps `bedrock-agent-runtime.retrieve()` and returns quoted chunks with `Source: s3://...` and scores.

## Docs
- `docs/travel_policies.txt` — cancellation (§4), baggage, fees
- `docs/destination_guides.txt` — Kyoto, Iceland, Paris, Tokyo, Bali

## Env
```
KNOWLEDGE_BASE_ID=ABCDEF1234
AWS_REGION=us-east-1
```
