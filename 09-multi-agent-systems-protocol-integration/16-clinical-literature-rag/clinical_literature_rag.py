# =============================================================================
# Clinical Literature — Multi-Agent RAG Exercise (Lesson 8)
# =============================================================================
# Two clinical retrievers (Drug Interactions, Clinical Guidelines) query
# separate Bedrock KBs in parallel. A failing KB returns an empty list +
# structured error inside the tool (graceful degradation). Aggregation is
# merge -> deduplicate -> rank -> top-K. Synthesis emits a strict three-section
# clinical summary; when one KB was unavailable, a PARTIAL RESULTS disclaimer
# is injected into the synthesis prompt.
#
# Data flow:
#   Doctor question
#     -> ThreadPoolExecutor(2) parallel retrieval (tools catch ConnectionError)
#     -> merge + deduplicate_passages + rank + top-K
#     -> synthesis (DRUG INTERACTIONS | CLINICAL GUIDELINES | INTEGRATED RECOMMENDATION)
# ============================================================================

import hashlib
import json
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

# Optional override: "drugs" | "guidelines" — forces that KB offline for the demo.
SIMULATE_FAILURE = os.environ.get("SIMULATE_FAILURE", "").strip().lower()

# Clinical decisions need more supporting evidence than the demo's TOP_K=5.
TOP_K = 10

retrieval_results: dict[str, list[dict]] = {"drug": [], "guidelines": []}


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


def retrieve_from_kb(kb_id: str, query: str, kb_name: str,
                     top_k: int = TOP_K, simulate_failure: bool = False) -> list[dict]:
    """Call bedrock-agent-runtime.retrieve(); optionally simulate a KB outage."""
    if simulate_failure:
        raise ConnectionError(f"Simulated {kb_name} KB outage")
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
#          Graceful failure lives INSIDE each tool (try/except ConnectionError)
# ============================================================================

def _build_retriever(tool_fn, system_prompt: str) -> Agent:
    model = BedrockModel(model_id=NOVA_LITE_MODEL, region_name=AWS_REGION, temperature=0.0)
    return Agent(model=model, system_prompt=system_prompt, tools=[tool_fn])


def _passage_summary(passages: list[dict]) -> list[dict]:
    return [
        {"doc_id": p["doc_id"], "title": p["title"], "score": p["score"]}
        for p in passages
    ]


def build_drug_interactions_retriever(simulate_failure: bool = False) -> Agent:
    """Agent that searches ONLY the Drug Interactions knowledge base."""

    @tool
    def retrieve_drug_interactions(search_query: str) -> str:
        """Search drug-drug and drug-class interaction evidence."""
        try:
            passages = retrieve_from_kb(
                DRUG_INTERACTIONS_KB_ID, search_query, "DDR", TOP_K, simulate_failure
            )
            retrieval_results["drug"] = passages
        except ConnectionError as error:
            retrieval_results["drug"] = []
            return json.dumps(
                {"kb": "Drug Interactions", "error": str(error), "passages_found": 0},
                indent=2,
            )
        return json.dumps(
            {
                "kb": "Drug Interactions",
                "passages_found": len(passages),
                "passages": _passage_summary(passages),
            },
            indent=2,
        )

    return _build_retriever(
        retrieve_drug_interactions,
        "You are a Drug Interactions retrieval agent. Call retrieve_drug_interactions "
        "once, then report what you found. Do not synthesize or give clinical advice.",
    )


def build_clinical_guidelines_retriever(simulate_failure: bool = False) -> Agent:
    """Agent that searches ONLY the Clinical Guidelines knowledge base."""

    @tool
    def retrieve_clinical_guidelines(search_query: str) -> str:
        """Search clinical practice guideline passages."""
        try:
            passages = retrieve_from_kb(
                CLINICAL_GUIDELINES_KB_ID, search_query, "CGL", TOP_K, simulate_failure
            )
            retrieval_results["guidelines"] = passages
        except ConnectionError as error:
            retrieval_results["guidelines"] = []
            return json.dumps(
                {"kb": "Clinical Guidelines", "error": str(error), "passages_found": 0},
                indent=2,
            )
        return json.dumps(
            {
                "kb": "Clinical Guidelines",
                "passages_found": len(passages),
                "passages": _passage_summary(passages),
            },
            indent=2,
        )

    return _build_retriever(
        retrieve_clinical_guidelines,
        "You are a Clinical Guidelines retrieval agent. Call retrieve_clinical_guidelines "
        "once, then report what you found. Do not synthesize or give clinical advice.",
    )


# ============================================================================
# TODO 2: Merge, deduplicate, then rank (order matters)
# ============================================================================

def _content_fingerprint(passage: dict) -> str:
    """Hash of the first 100 chars of normalized content (near-dupe key)."""
    text = re.sub(r"\s+", " ", (passage.get("content") or "").strip().lower())[:100]
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def deduplicate_passages(passages: list[dict]) -> list[dict]:
    """Drop redundant passages before ranking.

    1. Same doc_id -> keep highest score
    2. Same first-100-char content hash -> keep highest score
       (Production: swap for embedding cosine similarity.)
    """
    best_by_id: dict[str, dict] = {}
    for passage in passages:
        existing = best_by_id.get(passage["doc_id"])
        if existing is None or passage["score"] > existing["score"]:
            best_by_id[passage["doc_id"]] = passage

    best_by_hash: dict[str, dict] = {}
    for passage in best_by_id.values():
        key = _content_fingerprint(passage)
        existing = best_by_hash.get(key)
        if existing is None or passage["score"] > existing["score"]:
            best_by_hash[key] = passage
    return list(best_by_hash.values())


def aggregate_results(drug_passages: list[dict], guideline_passages: list[dict],
                      top_k: int = TOP_K) -> list[dict]:
    """1. MERGE both KBs  2. DEDUP  3. RANK by score  4. trim to top_k."""
    all_passages = list(drug_passages) + list(guideline_passages)
    all_passages = deduplicate_passages(all_passages)
    all_passages.sort(key=lambda x: x["score"], reverse=True)
    return all_passages[:top_k]


def format_passages(passages: list[dict]) -> str:
    blocks = []
    for p in passages:
        blocks.append(
            f"[{p['doc_id']}] {p['title']} (Score: {p['score']:.3f}, KB: {p['kb']})\n"
            f"Content: {p['content']}"
        )
    return "\n\n".join(blocks) if blocks else "(no passages)"


# ============================================================================
# TODO 3: Synthesis agent — three sections + optional PARTIAL RESULTS notice
# ============================================================================

def build_synthesis_agent(passages: list[dict], query: str,
                          partial: bool = False) -> Agent:
    # Clinical advice: tighter risk tolerance than the demo's temperature=0.2.
    model = BedrockModel(model_id=NOVA_PRO_MODEL, region_name=AWS_REGION, temperature=0.1)

    partial_notice = ""
    if partial:
        partial_notice = """
PARTIAL RESULTS: One knowledge base was unavailable. Include a confidence
disclaimer noting that this answer is based on incomplete data and the doctor
should verify against the unavailable source."""

    system_prompt = f"""You are a clinical literature synthesis agent.
Answer ONLY from the retrieved passages (and the partial-results notice, if present).

RULES:
1. Every factual claim MUST cite a specific passage using [DOC_ID] format
2. Structure your answer as: DRUG INTERACTIONS / CLINICAL GUIDELINES / INTEGRATED RECOMMENDATION
3. Do NOT invent information not in the passages
4. If a section has no supporting passages, write "No relevant passages retrieved."
{partial_notice}
RETRIEVED PASSAGES:
{format_passages(passages)}
CLINICAL QUESTION: {query}"""

    return Agent(model=model, system_prompt=system_prompt, tools=[])


# ============================================================================
# TODO 4: Orchestrator — parallel retrieve -> aggregate -> synthesize
# ============================================================================

def run_rag_query(query: str, fail_at: str | None = None) -> dict:
    """Parallel clinical retrieval, dedup/rank, then structured synthesis.

    fail_at: None (healthy) | "drug" | "guidelines" — sets partial=True and
    forces that retriever's tool to raise ConnectionError (caught inside tool).
    """
    require_kb_config()
    retrieval_results["drug"] = []
    retrieval_results["guidelines"] = []

    partial = fail_at is not None

    print("\n" + "=" * 70)
    print(f"Clinical query: {query}")
    print("=" * 70)
    if fail_at:
        print(f"  simulate_failure={fail_at}")

    timings: dict[str, float] = {}
    errors: dict[str, str] = {}

    # Submit BOTH retrievers before collecting (do not serialize).
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = {
            executor.submit(
                run_agent_with_retry,
                lambda: build_drug_interactions_retriever(
                    simulate_failure=(fail_at == "drug")
                ),
                f"Search for: {query}",
            ): "drug",
            executor.submit(
                run_agent_with_retry,
                lambda: build_clinical_guidelines_retriever(
                    simulate_failure=(fail_at == "guidelines")
                ),
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

    drug_passages = retrieval_results["drug"]
    guideline_passages = retrieval_results["guidelines"]
    top_passages = aggregate_results(drug_passages, guideline_passages)

    print(f"  aggregate: drug={len(drug_passages)} guidelines={len(guideline_passages)} "
          f"-> top {len(top_passages)} after dedup  partial={partial}")

    # Never call the LLM with nothing to ground on.
    if not top_passages:
        print("  synthesis: skipped (no passages) -> 'No relevant results found.'")
        return {
            "query": query,
            "synthesis": "No relevant results found.",
            "avg_score": 0.0,
            "drugs_count": len(drug_passages),
            "guidelines_count": len(guideline_passages),
            "top_passages": [],
            "timings": timings,
            "errors": errors,
            "partial": partial,
        }

    print(f"  synthesize: three-section clinical summary (partial={partial})")
    answer = run_agent_with_retry(
        lambda: build_synthesis_agent(top_passages, query, partial=partial),
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
        "partial": partial,
    }


# ============================================================================
# MAIN — Query 1/2 healthy, Query 3 fails the Drug Interactions KB
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
    for index, query in enumerate(QUERIES):
        # Query 3 is the degradation test: drug KB offline (or .env override).
        fail_at = None
        if index == 2:
            fail_at = "guidelines" if SIMULATE_FAILURE == "guidelines" else "drug"
            if SIMULATE_FAILURE in ("drugs", "drug"):
                fail_at = "drug"
        result = run_rag_query(query, fail_at=fail_at)
        results.append(result)
        print("\n--- Clinical summary ---")
        print(result["synthesis"])

    print("\n" + "=" * 70)
    print("Summary")
    print("=" * 70)
    for r in results:
        print(f"  avg_score={r['avg_score']:.3f}  "
              f"drug={r['drugs_count']}  guidelines={r['guidelines_count']}  "
              f"partial={r['partial']}  query={r['query']!r}")


if __name__ == "__main__":
    main()
