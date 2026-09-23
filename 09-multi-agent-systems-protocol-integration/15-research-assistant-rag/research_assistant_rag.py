# =============================================================================
# Research Assistant — Multi-Agent RAG with Parallel Knowledge Base Retrieval
# =============================================================================
# Two retriever agents (CS, Biology) query separate Bedrock Knowledge Bases
# in parallel. An aggregator merges, deduplicates, and ranks passages; a
# grounded synthesis agent answers with strict [DOC_ID] citations.
#
# Architecture:
#   Retrieve:   ThreadPoolExecutor(max_workers=2) → one agent per KB
#   Aggregate:  merge → dedup by doc_id (keep max score) → sort → top-K
#   Synthesize: Nova Pro, no tools, passages embedded in system prompt
#   Degrade:    empty / one-KB / both-KB outcomes all produce a valid answer
# ============================================================================

import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import boto3
from dotenv import load_dotenv
from strands import Agent, tool
from strands.models import BedrockModel

load_dotenv()

# --- Region / models (Bedrock KBs require us-east-1 or us-west-2) ---
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
NOVA_LITE_MODEL = os.environ.get("NOVA_LITE_MODEL", "amazon.nova-lite-v1:0")
NOVA_PRO_MODEL = os.environ.get("NOVA_PRO_MODEL", "amazon.nova-pro-v1:0")

# --- Knowledge base IDs (fail fast if missing) ---
CS_KB_ID = os.environ.get("CS_KB_ID", "").strip()
BIO_KB_ID = os.environ.get("BIO_KB_ID", "").strip()

TOP_K = 6

# Shared handoff: retriever tools stash passages here for the aggregator.
retrieval_results: dict[str, list[dict]] = {"cs": [], "bio": []}

SYNTHESIS_RULES = """Strict citation rules:
1. Every factual claim MUST cite a specific passage using [DOC_ID] format
2. If passages don't contain relevant information, say so honestly
3. Do NOT invent or hallucinate information not in the passages
4. If results are from only one domain, note that the answer is partial"""


class ConfigError(RuntimeError):
    """Raised when required KB IDs are not configured."""


def require_kb_config() -> None:
    missing = [
        name for name, value in (("CS_KB_ID", CS_KB_ID), ("BIO_KB_ID", BIO_KB_ID))
        if not value
    ]
    if missing:
        raise ConfigError(
            f"Missing setup: set {', '.join(missing)} in .env "
            "(create Knowledge Bases in the Bedrock console first)."
        )


# ============================================================================
# RETRIEVAL — real bedrock-agent-runtime.retrieve() helper
# ============================================================================

def _doc_id_from(uri: str, kb_name: str) -> str:
    """Derive a stable citation id like CS-001 / BIO-003 from the source URI."""
    stem = Path(uri.replace("s3://", "").split("?")[0]).stem
    match = re.search(r"(\d{3})", stem)
    number = match.group(1) if match else "000"
    return f"{kb_name.upper()}-{number}"


def retrieve_from_kb(kb_id: str, query: str, kb_name: str, top_k: int = TOP_K) -> list[dict]:
    """Embed the query, vector-search the KB, return uniform passage dicts."""
    client = boto3.client("bedrock-agent-runtime", region_name=AWS_REGION)
    response = client.retrieve(
        knowledgeBaseId=kb_id,
        retrievalQuery={"text": query},
        retrievalConfiguration={
            "vectorSearchConfiguration": {"numberOfResults": top_k}
        },
    )
    passages = []
    for result in response.get("retrievalResults", []):
        metadata = result.get("metadata", {}) or {}
        source = metadata.get("x-amz-bedrock-kb-source-uri") or metadata.get("source", "")
        title = metadata.get("x-amz-bedrock-kb-title") or Path(source).stem or kb_name
        score = float(result.get("score", 0.0))
        content = (result.get("content") or {}).get("text", "")
        passages.append({
            "doc_id": _doc_id_from(source or title, kb_name),
            "title": title,
            "source": source,
            "content": content,
            "score": score,
            "kb": kb_name,
        })
    return passages


# ============================================================================
# RETRIEVER AGENTS — one KB each; tools stash into retrieval_results
# ============================================================================

def run_agent_with_retry(builder, prompt: str, max_retries: int = 3) -> str:
    for attempt in range(max_retries):
        try:
            agent = builder()
            return str(agent(prompt))
        except Exception as error:
            if attempt < max_retries - 1:
                wait = 2 ** attempt
                print(f"[Retry {attempt + 1}/{max_retries}] ({error.__class__.__name__}), waiting {wait}s...")
                time.sleep(wait)
                continue
            print(f"[Failed] ({error.__class__.__name__}) after {max_retries} attempts")
            raise


def _build_retriever(tool_fn, system_prompt: str) -> Agent:
    model = BedrockModel(model_id=NOVA_LITE_MODEL, region_name=AWS_REGION, temperature=0.0)
    return Agent(model=model, system_prompt=system_prompt, tools=[tool_fn])


def build_cs_retriever() -> Agent:
    @tool
    def retrieve_cs_papers(query: str) -> str:
        """Search the Computer Science papers knowledge base."""
        passages = retrieve_from_kb(CS_KB_ID, query, "CS")
        retrieval_results["cs"] = passages
        return f"Found {len(passages)} CS passages"

    return _build_retriever(
        retrieve_cs_papers,
        "You are a CS retrieval agent. Call retrieve_cs_papers once, "
        "then report what you found. Do not synthesize or answer the research question.",
    )


def build_bio_retriever() -> Agent:
    @tool
    def retrieve_bio_papers(query: str) -> str:
        """Search the Biology papers knowledge base."""
        try:
            passages = retrieve_from_kb(BIO_KB_ID, query, "BIO")
        except ConnectionError:
            # KB outage degrades to empty instead of crashing the pipeline.
            passages = []
        retrieval_results["bio"] = passages
        return f"Found {len(passages)} Biology passages"

    return _build_retriever(
        retrieve_bio_papers,
        "You are a Biology retrieval agent. Call retrieve_bio_papers once, "
        "then report what you found. Do not synthesize or answer the research question.",
    )


# ============================================================================
# AGGREGATE — merge, dedup by doc_id, rank, top-K
# ============================================================================

def aggregate_results(cs_passages: list[dict], bio_passages: list[dict],
                      top_k: int = TOP_K) -> list[dict]:
    # MERGE: pool all passages from both retrievers
    all_passages = list(cs_passages) + list(bio_passages)

    # DEDUP: for each doc_id, keep the highest-scoring copy only
    best_by_id: dict[str, dict] = {}
    for passage in all_passages:
        existing = best_by_id.get(passage["doc_id"])
        if existing is None or passage["score"] > existing["score"]:
            best_by_id[passage["doc_id"]] = passage

    # RANK: sort descending by score and return top-K
    deduped = sorted(best_by_id.values(), key=lambda x: x["score"], reverse=True)
    return deduped[:top_k]


def format_passages(passages: list[dict]) -> str:
    blocks = []
    for p in passages:
        blocks.append(
            f"[{p['doc_id']}] {p['title']} (kb={p['kb']}, score={p['score']:.3f})\n"
            f"{p['content']}"
        )
    return "\n\n".join(blocks)


# ============================================================================
# SYNTHESIS — grounded answer with citations (no tools)
# ============================================================================

def build_synthesis_agent(passages: list[dict], query: str) -> Agent:
    model = BedrockModel(model_id=NOVA_PRO_MODEL, region_name=AWS_REGION, temperature=0.2)
    system_prompt = (
        "You are a research synthesis agent. Answer ONLY from the passages below.\n\n"
        f"{SYNTHESIS_RULES}\n\n"
        f"Passages:\n{format_passages(passages)}\n\n"
        f"Research question: {query}"
    )
    return Agent(model=model, system_prompt=system_prompt, tools=[])


# ============================================================================
# ORCHESTRATOR — parallel retrieve → aggregate → synthesize
# ============================================================================

def run_rag_query(query: str) -> dict:
    """Four-stage RAG loop: retrieve in parallel, aggregate, synthesize, degrade."""
    require_kb_config()
    retrieval_results["cs"] = []
    retrieval_results["bio"] = []

    print("\n" + "=" * 70)
    print(f"Query: {query}")
    print("=" * 70)
    print("  retrieve (parallel): CS + Bio knowledge bases")

    timings: dict[str, float] = {}
    errors: dict[str, str] = {}

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = {
            executor.submit(
                run_agent_with_retry,
                build_cs_retriever,
                f"Search for: {query}",
            ): "CS",
            executor.submit(
                run_agent_with_retry,
                build_bio_retriever,
                f"Search for: {query}",
            ): "Bio",
        }
        for future in as_completed(futures):
            label = futures[future]
            start = time.perf_counter()
            try:
                future.result()
            except Exception as error:
                # One KB failing leaves that side empty — partial answer is OK.
                errors[label.lower()] = f"{error.__class__.__name__}: {error}"
                print(f"  {label:4s} retriever error: {errors[label.lower()]}")
            timings[label.lower()] = time.perf_counter() - start
            print(f"  {label:4s} finished in {timings[label.lower()]:.2f}s "
                  f"({len(retrieval_results.get(label.lower(), []))} passages)")

    cs_passages = retrieval_results["cs"]
    bio_passages = retrieval_results["bio"]
    top_passages = aggregate_results(cs_passages, bio_passages)

    print(f"  aggregate: cs={len(cs_passages)} bio={len(bio_passages)} "
          f"-> top {len(top_passages)}")

    if not top_passages:
        print("  synthesis: no relevant results")
        return {
            "query": query,
            "synthesis": "No relevant results found for this query.",
            "avg_score": 0.0,
            "cs_count": len(cs_passages),
            "bio_count": len(bio_passages),
            "top_passages": [],
            "timings": timings,
            "errors": errors,
            "partial": bool(cs_passages) != bool(bio_passages) or bool(errors),
        }

    print("  synthesize: Nova Pro grounded answer")
    answer = run_agent_with_retry(
        lambda: build_synthesis_agent(top_passages, query),
        f"Answer the research question: {query}",
    )
    avg_score = sum(p["score"] for p in top_passages) / len(top_passages)
    partial = bool(errors) or (bool(cs_passages) != bool(bio_passages))

    return {
        "query": query,
        "synthesis": answer,
        "avg_score": avg_score,
        "cs_count": len(cs_passages),
        "bio_count": len(bio_passages),
        "top_passages": top_passages,
        "timings": timings,
        "errors": errors,
        "partial": partial,
    }


# ============================================================================
# MAIN — three queries: cross-domain, domain-specific, out of scope
# ============================================================================

QUERIES = [
    "applications of machine learning in genomics",
    "CRISPR gene-editing for crop improvement",
    "blockchain consensus mechanisms for IoT networks",
]


def main() -> None:
    require_kb_config()
    print("=" * 70)
    print("Research Assistant - Parallel Multi-Agent RAG")
    print("=" * 70)

    results = []
    for query in QUERIES:
        results.append(run_rag_query(query))
        result = results[-1]
        print("\n--- Answer ---")
        print(result["synthesis"])
        if result["partial"] and result["top_passages"]:
            print("  [note] partial result — one knowledge base contributed little or failed")

    print("\n" + "=" * 70)
    print("Summary")
    print("=" * 70)
    for r in results:
        print(f"  avg_score={r['avg_score']:.3f}  "
              f"cs={r['cs_count']}  bio={r['bio_count']}  "
              f"partial={r['partial']}  query={r['query']!r}")

    print("\nPattern: parallel retrievers scale horizontally; "
          "aggregation stays the hub; synthesis needs all evidence first.")


if __name__ == "__main__":
    main()
