# =============================================================================
# Clinical Literature — Multi-Agent RAG Exercise (Lesson 8)
# =============================================================================
# Two clinical retrievers (Drug Interactions, Clinical Guidelines) query
# separate Bedrock KBs in parallel. Aggregation merges, deduplicates
# (doc_id + near-identical content), and ranks passages. Synthesis emits a
# strict three-section clinical summary and flags partial/degraded results.
#
# Data flow:
#   Doctor question
#     -> ThreadPoolExecutor(2) parallel retrieval
#     -> aggregate + dedup + top-K rank
#     -> synthesis (Drug Interactions | Guidelines | Integrated Recommendation)
# ============================================================================

import hashlib
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

AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
NOVA_LITE_MODEL = os.environ.get("NOVA_LITE_MODEL", "amazon.nova-lite-v1:0")
NOVA_PRO_MODEL = os.environ.get("NOVA_PRO_MODEL", "amazon.nova-pro-v1:0")

DRUG_INTERACTIONS_KB_ID = os.environ.get("DRUG_INTERACTIONS_KB_ID", "").strip()
CLINICAL_GUIDELINES_KB_ID = os.environ.get("CLINICAL_GUIDELINES_KB_ID", "").strip()

# simulate_failure: "" | "drugs" | "guidelines" — forces one KB to fail
SIMULATE_FAILURE = os.environ.get("SIMULATE_FAILURE", "").strip().lower()

TOP_K = 8

retrieval_results: dict[str, list[dict]] = {"drugs": [], "guidelines": []}


class ConfigError(RuntimeError):
    """Raised when required KB IDs are not configured."""


def require_kb_config() -> None:
    missing = [
        name
        for name, value in (
            ("DRUG_INTERACTIONS_KB_ID", DRUG_INTERACTIONS_KB_ID),
            ("CLINICAL_GUIDELINES_KB_ID", CLINICAL_GUIDELINES_KB_ID),
        )
        if not value
    ]
    if missing:
        raise ConfigError(
            f"Missing setup: set {', '.join(missing)} in .env "
            "(create Knowledge Bases in the Bedrock console first)."
        )


# ============================================================================
# PROVIDED: retrieval API helper + retry wrapper
# ============================================================================

def _doc_id_from(uri: str, kb_name: str) -> str:
    stem = Path(uri.replace("s3://", "").split("?")[0]).stem
    match = re.search(r"(\d{3})", stem)
    number = match.group(1) if match else "000"
    return f"{kb_name}-{number}"


def retrieve_from_kb(kb_id: str, query: str, kb_name: str, top_k: int = TOP_K) -> list[dict]:
    """Call bedrock-agent-runtime.retrieve() and return uniform passage dicts."""
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
        passages.append({
            "doc_id": _doc_id_from(source or title, kb_name),
            "title": title,
            "source": source,
            "content": (result.get("content") or {}).get("text", ""),
            "score": float(result.get("score", 0.0)),
            "kb": kb_name,
        })
    return passages


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


# ============================================================================
# TODO 1: Retriever agents — one specialized agent per clinical KB
# ============================================================================

def _build_retriever(tool_fn, system_prompt: str) -> Agent:
    model = BedrockModel(model_id=NOVA_LITE_MODEL, region_name=AWS_REGION, temperature=0.0)
    return Agent(model=model, system_prompt=system_prompt, tools=[tool_fn])


def build_drug_interactions_retriever() -> Agent:
    """Agent that searches ONLY the Drug Interactions knowledge base."""

    @tool
    def retrieve_drug_interactions(query: str) -> str:
        """Search drug-drug and drug-class interaction evidence."""
        if SIMULATE_FAILURE == "drugs":
            raise ConnectionError("Simulated Drug Interactions KB outage")
        passages = retrieve_from_kb(DRUG_INTERACTIONS_KB_ID, query, "DDR")
        retrieval_results["drugs"] = passages
        return f"Found {len(passages)} drug-interaction passages"

    return _build_retriever(
        retrieve_drug_interactions,
        "You are a Drug Interactions retrieval agent. Call retrieve_drug_interactions "
        "once, then report what you found. Do not synthesize or give clinical advice.",
    )


def build_clinical_guidelines_retriever() -> Agent:
    """Agent that searches ONLY the Clinical Guidelines knowledge base."""

    @tool
    def retrieve_clinical_guidelines(query: str) -> str:
        """Search clinical practice guideline passages."""
        if SIMULATE_FAILURE == "guidelines":
            raise ConnectionError("Simulated Clinical Guidelines KB outage")
        try:
            passages = retrieve_from_kb(CLINICAL_GUIDELINES_KB_ID, query, "CGL")
        except ConnectionError:
            passages = []
        retrieval_results["guidelines"] = passages
        return f"Found {len(passages)} guideline passages"

    return _build_retriever(
        retrieve_clinical_guidelines,
        "You are a Clinical Guidelines retrieval agent. Call retrieve_clinical_guidelines "
        "once, then report what you found. Do not synthesize or give clinical advice.",
    )


# ============================================================================
# TODO 2: Aggregate + deduplicate + rank
# ============================================================================

def _content_fingerprint(passage: dict) -> str:
    """Stable hash of normalized content for near-duplicate detection."""
    text = re.sub(r"\s+", " ", (passage.get("content") or "").strip().lower())
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def aggregate_results(drug_passages: list[dict], guideline_passages: list[dict],
                      top_k: int = TOP_K) -> list[dict]:
    """Merge both KBs, drop redundant entries, rank by score, keep top-K.

    Redundancy rules:
      1. Same doc_id  -> keep highest score
      2. Near-identical content (same fingerprint) -> keep highest score
    """
    # MERGE
    all_passages = list(drug_passages) + list(guideline_passages)

    # DEDUP by doc_id (keep max score)
    best_by_id: dict[str, dict] = {}
    for passage in all_passages:
        existing = best_by_id.get(passage["doc_id"])
        if existing is None or passage["score"] > existing["score"]:
            best_by_id[passage["doc_id"]] = passage

    # DEDUP near-identical content across different doc_ids
    best_by_content: dict[str, dict] = {}
    for passage in best_by_id.values():
        key = _content_fingerprint(passage)
        existing = best_by_content.get(key)
        if existing is None or passage["score"] > existing["score"]:
            best_by_content[key] = passage

    # RANK
    ranked = sorted(best_by_content.values(), key=lambda x: x["score"], reverse=True)
    return ranked[:top_k]


def format_passages(passages: list[dict]) -> str:
    blocks = []
    for p in passages:
        blocks.append(
            f"[{p['doc_id']}] {p['title']} (kb={p['kb']}, score={p['score']:.3f})\n"
            f"{p['content']}"
        )
    return "\n\n".join(blocks) if blocks else "(no passages)"


# ============================================================================
# TODO 3: Synthesis agent — strict three-section clinical structure
# ============================================================================

SYNTHESIS_STRUCTURE = """You are a clinical literature synthesis agent.
Answer ONLY from the passages (and the degradation note, if present).

Output EXACTLY these three markdown sections, in order:

## Drug Interactions
Relevant interaction evidence from passages. Cite every claim as [DOC_ID].
Write "No relevant interaction passages retrieved." if none apply.

## Clinical Guidelines
Applicable guideline recommendations from passages. Cite every claim as [DOC_ID].
Write "No relevant guideline passages retrieved." if none apply.

## Integrated Recommendation
Combine interaction + guideline evidence into a concise clinical summary for the
ordering clinician. Cite [DOC_ID] for factual claims. Explicitly state when
evidence is one-sided or incomplete. Do NOT invent facts.

Rules:
1. Every factual claim MUST use [DOC_ID] citations from the passages only
2. If passages lack relevant info, say so honestly — never hallucinate
3. If a knowledge base was unavailable, begin with a degradation notice:
   "DEGRADED RESULT: One or more knowledge bases were unavailable; this summary may be incomplete."
4. This is decision support, not a substitute for clinical judgment"""


def build_synthesis_agent(passages: list[dict], query: str,
                          degraded: bool = False,
                          missing_domains: list[str] | None = None) -> Agent:
    model = BedrockModel(model_id=NOVA_PRO_MODEL, region_name=AWS_REGION, temperature=0.2)
    degradation = ""
    if degraded:
        missing = ", ".join(missing_domains or ["unknown"])
        degradation = (
            f"\nDEGRADATION NOTICE: The following knowledge source(s) failed or were empty: "
            f"{missing}. Flag the result as partial.\n"
        )
    system_prompt = (
        f"{SYNTHESIS_STRUCTURE}\n"
        f"{degradation}\n"
        f"Passages:\n{format_passages(passages)}\n\n"
        f"Clinical question: {query}"
    )
    return Agent(model=model, system_prompt=system_prompt, tools=[])


# ============================================================================
# TODO 4: Orchestrator — parallel retrieve -> aggregate -> synthesize
# ============================================================================

def run_rag_query(query: str) -> dict:
    """Parallel clinical retrieval, dedup/rank, then structured synthesis."""
    require_kb_config()
    retrieval_results["drugs"] = []
    retrieval_results["guidelines"] = []

    print("\n" + "=" * 70)
    print(f"Clinical query: {query}")
    print("=" * 70)
    if SIMULATE_FAILURE:
        print(f"  simulate_failure={SIMULATE_FAILURE}")

    timings: dict[str, float] = {}
    errors: dict[str, str] = {}

    # Submit BOTH retrievers before collecting (do not serialize).
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = {
            executor.submit(
                run_agent_with_retry,
                build_drug_interactions_retriever,
                f"Search for: {query}",
            ): "drugs",
            executor.submit(
                run_agent_with_retry,
                build_clinical_guidelines_retriever,
                f"Search for: {query}",
            ): "guidelines",
        }
        for future in as_completed(futures):
            label = futures[future]
            start = time.perf_counter()
            try:
                future.result()
            except Exception as error:
                errors[label] = f"{error.__class__.__name__}: {error}"
                retrieval_results[label] = []
                print(f"  {label:12s} retriever error: {errors[label]}")
            timings[label] = time.perf_counter() - start
            print(f"  {label:12s} finished in {timings[label]:.2f}s "
                  f"({len(retrieval_results[label])} passages)")

    drug_passages = retrieval_results["drugs"]
    guideline_passages = retrieval_results["guidelines"]
    top_passages = aggregate_results(drug_passages, guideline_passages)

    print(f"  aggregate: drugs={len(drug_passages)} guidelines={len(guideline_passages)} "
          f"-> top {len(top_passages)} after dedup")

    missing_domains = []
    if errors.get("drugs") or not drug_passages:
        missing_domains.append("Drug Interactions KB")
    if errors.get("guidelines") or not guideline_passages:
        missing_domains.append("Clinical Guidelines KB")

    # Degraded if a retriever errored (partial data must be flagged).
    degraded = bool(errors)
    # Both empty -> still degraded for the clinician (no evidence available).
    if not top_passages:
        degraded = True
        if not missing_domains:
            missing_domains = ["no matching passages in either KB"]

    if not top_passages:
        notice = (
            "DEGRADED RESULT: One or more knowledge bases were unavailable; "
            "this summary may be incomplete."
            if errors else
            "No relevant passages found for this clinical question."
        )
        answer = (
            f"{notice}\n\n"
            "## Drug Interactions\nNo relevant interaction passages retrieved.\n\n"
            "## Clinical Guidelines\nNo relevant guideline passages retrieved.\n\n"
            "## Integrated Recommendation\n"
            "Insufficient evidence to synthesize a clinical recommendation. "
            "Consider alternate search terms or direct database access."
        )
        print("  synthesis: empty/degraded structured response (no LLM call needed for empty set)")
        return {
            "query": query,
            "synthesis": answer,
            "avg_score": 0.0,
            "drugs_count": len(drug_passages),
            "guidelines_count": len(guideline_passages),
            "top_passages": [],
            "timings": timings,
            "errors": errors,
            "degraded": degraded,
            "missing_domains": missing_domains,
        }

    print("  synthesize: three-section clinical summary")
    answer = run_agent_with_retry(
        lambda: build_synthesis_agent(
            top_passages, query, degraded=degraded, missing_domains=missing_domains
        ),
        f"Answer the clinical question: {query}",
    )
    avg_score = sum(p["score"] for p in top_passages) / len(top_passages)

    return {
        "query": query,
        "synthesis": answer,
        "avg_score": avg_score,
        "drugs_count": len(drug_passages),
        "guidelines_count": len(guideline_passages),
        "top_passages": top_passages,
        "timings": timings,
        "errors": errors,
        "degraded": degraded,
        "missing_domains": missing_domains,
    }


# ============================================================================
# MAIN
# ============================================================================

QUERIES = [
    "drug interactions between metformin and lisinopril",
    "guidelines for type 2 diabetes glycemic control",
    "warfarin and antibiotic interaction management recommendations",
]


def main() -> None:
    require_kb_config()
    print("=" * 70)
    print("Clinical Literature - Parallel Multi-Agent RAG")
    print("=" * 70)

    results = []
    for query in QUERIES:
        result = run_rag_query(query)
        results.append(result)
        print("\n--- Clinical summary ---")
        print(result["synthesis"])
        if result["degraded"]:
            print(f"  [degradation] missing: {result['missing_domains']}")

    print("\n" + "=" * 70)
    print("Summary")
    print("=" * 70)
    for r in results:
        print(f"  avg_score={r['avg_score']:.3f}  "
              f"drugs={r['drugs_count']}  guidelines={r['guidelines_count']}  "
              f"degraded={r['degraded']}  query={r['query']!r}")


if __name__ == "__main__":
    main()
