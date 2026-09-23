import json
import os
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("AWS_ACCESS_KEY_ID", "")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "")
os.environ.setdefault("AWS_SESSION_TOKEN", "")
os.environ.setdefault("AWS_REGION", "us-east-1")
os.environ.setdefault("DRUG_INTERACTIONS_KB_ID", "")
os.environ.setdefault("CLINICAL_GUIDELINES_KB_ID", "")
os.environ.setdefault("SIMULATE_FAILURE", "")

import clinical_literature_rag as clr


def _p(doc_id, score, kb="DDR", content=None, title=None):
    return {
        "doc_id": doc_id,
        "title": title or doc_id,
        "source": f"s3://bkt/{doc_id.lower()}.md",
        "content": content if content is not None else f"unique body for {doc_id}",
        "score": score,
        "kb": kb,
    }


def _unwrap_tool(fn):
    for attr in ("_tool_function", "function", "func", "__wrapped__"):
        raw = getattr(fn, attr, None)
        if callable(raw):
            return raw
    return fn


# --- Doc ID ---

def test_doc_id_from_uri():
    assert clr._doc_id_from("s3://b/drugs/drugs_001_metformin.md", "DDR") == "DDR-001"
    assert clr._doc_id_from("s3://b/guidelines/guidelines_002_type2_diabetes.md", "CGL") == "CGL-002"


# --- Aggregate: merge / dedup / rank / top-K ---

def test_aggregate_merges_both_clinical_sources():
    drugs = [_p("DDR-001", 0.9), _p("DDR-002", 0.7)]
    guides = [_p("CGL-001", 0.85, kb="CGL")]
    result = clr.aggregate_results(drugs, guides)
    assert [p["doc_id"] for p in result] == ["DDR-001", "CGL-001", "DDR-002"]


def test_deduplicate_same_doc_id_keeps_high_score():
    drugs = [_p("DDR-001", 0.60, content="unique-a")]
    guides = [_p("DDR-001", 0.95, kb="CGL", content="unique-b")]
    result = clr.deduplicate_passages(drugs + guides)
    assert len(result) == 1
    assert result[0]["score"] == 0.95


def test_deduplicate_near_identical_first_100_chars():
    body = "Metformin reduces hepatic glucose production and improves insulin sensitivity."
    a = _p("DDR-001", 0.70, content=body)
    b = _p("DDR-999", 0.90, kb="CGL", content="  Metformin reduces hepatic glucose production and improves insulin sensitivity.  ")
    result = clr.deduplicate_passages([a, b])
    assert len(result) == 1
    assert result[0]["doc_id"] == "DDR-999"
    assert result[0]["score"] == 0.90


def test_deduplicate_does_not_drop_distinct_content():
    a = _p("DDR-001", 0.7, content="Drug A increases bleeding risk with warfarin.")
    b = _p("CGL-001", 0.8, kb="CGL", content="Check INR weekly when starting antibiotics.")
    result = clr.deduplicate_passages([a, b])
    assert len(result) == 2


def test_aggregate_sorts_descending():
    drugs = [_p("DDR-001", 0.3), _p("DDR-002", 0.95)]
    guides = [_p("CGL-001", 0.5, kb="CGL")]
    result = clr.aggregate_results(drugs, guides)
    scores = [p["score"] for p in result]
    assert scores == sorted(scores, reverse=True)


def test_aggregate_top_k_limit():
    drugs = [_p(f"DDR-{i:03d}", 0.05 * i) for i in range(1, 15)]
    result = clr.aggregate_results(drugs, [], top_k=5)
    assert len(result) == 5


def test_aggregate_default_top_k_is_10():
    assert clr.TOP_K == 10


def test_aggregate_empty():
    assert clr.aggregate_results([], []) == []


def test_dedup_runs_before_rank_and_trim():
    # Ranking first would drop the high-score duplicate's low-score twin
    # before dedup could merge them — order must be dedup -> sort -> slice.
    drugs = [_p("DDR-001", 0.5, content="same prefix " + "x" * 80)]
    guides = [
        _p("CGL-001", 0.95, kb="CGL", content="same prefix " + "x" * 80),
        _p("CGL-002", 0.55, kb="CGL", content="other guideline body"),
    ]
    result = clr.aggregate_results(drugs, guides, top_k=2)
    ids = {p["doc_id"] for p in result}
    assert "DDR-001" not in ids  # folded into CGL-001
    assert "CGL-001" in ids


# --- Config fail-fast ---

def test_require_kb_config_raises_when_missing():
    with patch.object(clr, "DRUG_INTERACTIONS_KB_ID", ""), \
         patch.object(clr, "CLINICAL_GUIDELINES_KB_ID", ""):
        with pytest.raises(clr.ConfigError, match="DRUG_INTERACTIONS_KB_ID"):
            clr.require_kb_config()


def test_require_kb_config_passes_when_set():
    with patch.object(clr, "DRUG_INTERACTIONS_KB_ID", "kb1"), \
         patch.object(clr, "CLINICAL_GUIDELINES_KB_ID", "kb2"):
        clr.require_kb_config()


# --- Builders ---

def test_drug_retriever_tool_name():
    with patch.object(clr, "BedrockModel"):
        agent = clr.build_drug_interactions_retriever()
    assert list(agent.tool_registry.registry) == ["retrieve_drug_interactions"]


def test_guideline_retriever_tool_name():
    with patch.object(clr, "BedrockModel"):
        agent = clr.build_clinical_guidelines_retriever()
    assert list(agent.tool_registry.registry) == ["retrieve_clinical_guidelines"]


def test_synthesis_agent_has_no_tools():
    with patch.object(clr, "BedrockModel"):
        agent = clr.build_synthesis_agent([_p("DDR-001", 0.9)], "q")
    assert list(agent.tool_registry.registry) == []


def test_synthesis_temperature_is_zero_point_one():
    with patch.object(clr, "BedrockModel") as mock_model:
        clr.build_synthesis_agent([], "q")
    assert mock_model.call_args.kwargs["temperature"] == 0.1


def test_synthesis_prompt_enforces_three_sections():
    with patch.object(clr, "BedrockModel"), patch.object(clr, "Agent") as mock_agent:
        clr.build_synthesis_agent([_p("DDR-001", 0.9)], "warfarin question")
    prompt = mock_agent.call_args.kwargs["system_prompt"]
    assert "DRUG INTERACTIONS" in prompt
    assert "CLINICAL GUIDELINES" in prompt
    assert "INTEGRATED RECOMMENDATION" in prompt
    assert "[DOC_ID]" in prompt


def test_partial_notice_injected_only_when_partial():
    with patch.object(clr, "BedrockModel"), patch.object(clr, "Agent") as mock_agent:
        clr.build_synthesis_agent([], "q", partial=True)
    prompt = mock_agent.call_args.kwargs["system_prompt"]
    assert "PARTIAL RESULTS" in prompt
    assert "incomplete data" in prompt
    assert "verify against the unavailable source" in prompt

    with patch.object(clr, "BedrockModel"), patch.object(clr, "Agent") as mock_agent:
        clr.build_synthesis_agent([], "q", partial=False)
    prompt = mock_agent.call_args.kwargs["system_prompt"]
    assert "PARTIAL RESULTS" not in prompt


# --- simulate_failure inside the retriever tool (caught -> structured error) ---

def test_simulate_failure_tool_returns_structured_error_not_raise():
    with patch.object(clr, "BedrockModel"):
        agent = clr.build_drug_interactions_retriever(simulate_failure=True)
    fn = agent.tool_registry.registry["retrieve_drug_interactions"]
    raw = _unwrap_tool(fn)
    result = raw("metformin and lisinopril")
    payload = json.loads(result)
    assert payload["kb"] == "Drug Interactions"
    assert payload["passages_found"] == 0
    assert "error" in payload
    assert clr.retrieval_results["drug"] == []


def test_guideline_simulate_failure_returns_structured_error():
    with patch.object(clr, "BedrockModel"):
        agent = clr.build_clinical_guidelines_retriever(simulate_failure=True)
    fn = agent.tool_registry.registry["retrieve_clinical_guidelines"]
    raw = _unwrap_tool(fn)
    result = raw("type 2 diabetes")
    payload = json.loads(result)
    assert payload["passages_found"] == 0
    assert "error" in payload
    assert clr.retrieval_results["guidelines"] == []


# --- Orchestrator: both empty -> skip synthesis LLM ---

def test_empty_result_skips_synthesis_with_no_relevant_results():
    healthy = {"drug": [], "guidelines": []}
    with patch.object(clr, "require_kb_config"), \
         patch.object(clr, "run_agent_with_retry", return_value="unused") as mock_run, \
         patch.object(clr, "retrieval_results", healthy):
        result = clr.run_rag_query("no matches expected")
    assert result["synthesis"] == "No relevant results found."
    assert result["partial"] is False
    # Only 2 retriever agents run; synthesis LLM not invoked
    assert mock_run.call_count == 2


def test_fail_at_sets_partial_and_drugs_key():
    healthy = {"drug": [], "guidelines": []}
    with patch.object(clr, "require_kb_config"), \
         patch.object(clr, "run_agent_with_retry", return_value="unused") as mock_run, \
         patch.object(clr, "retrieval_results", healthy):
        result = clr.run_rag_query("outage path", fail_at="drug")
    assert result["partial"] is True
    assert mock_run.call_count == 2  # still no synthesis when all empty


# --- Live tests ---

def test_live_retrieve_drugs_kb():
    if not os.getenv("DRUG_INTERACTIONS_KB_ID") or not os.getenv("AWS_ACCESS_KEY_ID"):
        pytest.skip("DRUG_INTERACTIONS_KB_ID or AWS credentials not set")
    passages = clr.retrieve_from_kb(clr.DRUG_INTERACTIONS_KB_ID, "metformin", "DDR", top_k=3)
    assert isinstance(passages, list)


def test_live_full_clinical_rag():
    if not (os.getenv("DRUG_INTERACTIONS_KB_ID")
            and os.getenv("CLINICAL_GUIDELINES_KB_ID")
            and os.getenv("AWS_ACCESS_KEY_ID")):
        pytest.skip("KB IDs or AWS credentials not set")
    result = clr.run_rag_query("drug interactions between metformin and lisinopril")
    assert result["synthesis"]
    assert "DRUG INTERACTIONS" in result["synthesis"]
    assert "INTEGRATED RECOMMENDATION" in result["synthesis"]
