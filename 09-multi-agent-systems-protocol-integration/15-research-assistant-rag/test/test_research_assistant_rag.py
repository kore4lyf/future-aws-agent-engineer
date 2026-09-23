import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("AWS_ACCESS_KEY_ID", "")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "")
os.environ.setdefault("AWS_SESSION_TOKEN", "")
os.environ.setdefault("AWS_REGION", "us-east-1")
os.environ.setdefault("CS_KB_ID", "")
os.environ.setdefault("BIO_KB_ID", "")

import research_assistant_rag as rar


def _p(doc_id, score, kb="CS", content="passage"):
    return {
        "doc_id": doc_id,
        "title": doc_id,
        "source": f"s3://bucket/{doc_id.lower()}.md",
        "content": content,
        "score": score,
        "kb": kb,
    }


# --- Doc ID derivation ---

def test_doc_id_from_uri_extracts_number():
    assert rar._doc_id_from("s3://bkt/cs/cs_001_transformers.md", "CS") == "CS-001"
    assert rar._doc_id_from("s3://bkt/bio/bio_003_single_cell_rna.md", "BIO") == "BIO-003"


def test_doc_id_falls_back_when_no_number():
    assert rar._doc_id_from("s3://bkt/notes.md", "CS") == "CS-000"


# --- aggregate_results: merge / dedup / rank ---

def test_aggregate_merges_both_retrievers():
    cs = [_p("CS-001", 0.9), _p("CS-002", 0.8)]
    bio = [_p("BIO-001", 0.85, kb="BIO")]
    result = rar.aggregate_results(cs, bio)
    assert [p["doc_id"] for p in result] == ["CS-001", "BIO-001", "CS-002"]


def test_aggregate_dedupes_keeping_higher_score():
    cs = [_p("CS-001", 0.70, content="from-cs")]
    bio = [_p("CS-001", 0.92, content="from-bio-shared")]
    result = rar.aggregate_results(cs, bio)
    assert len(result) == 1
    assert result[0]["score"] == 0.92
    assert result[0]["content"] == "from-bio-shared"


def test_aggregate_dedupes_regardless_of_list_order():
    bio = [_p("BIO-002", 0.55, kb="BIO")]
    cs = [_p("BIO-002", 0.99, content="better")]
    result = rar.aggregate_results(cs, bio)
    assert len(result) == 1
    assert result[0]["score"] == 0.99
    assert result[0]["content"] == "better"


def test_aggregate_sorts_descending_by_score():
    cs = [_p("CS-003", 0.4), _p("CS-001", 0.9)]
    bio = [_p("BIO-001", 0.6, kb="BIO")]
    result = rar.aggregate_results(cs, bio)
    scores = [p["score"] for p in result]
    assert scores == sorted(scores, reverse=True)


def test_aggregate_truncates_to_top_k():
    cs = [_p(f"CS-{i:03d}", 0.1 * i) for i in range(1, 11)]
    result = rar.aggregate_results(cs, [], top_k=3)
    assert len(result) == 3
    assert [p["score"] for p in result] == [1.0, 0.9, 0.8]


def test_aggregate_empty_inputs_return_empty():
    assert rar.aggregate_results([], []) == []


# --- format_passages ---

def test_format_passages_includes_doc_id_markers():
    text = rar.format_passages([_p("CS-001", 0.9, content="Attention is all you need")])
    assert "[CS-001]" in text
    assert "Attention is all you need" in text


# --- Config fail-fast ---

def test_require_kb_config_raises_when_missing():
    with patch.object(rar, "CS_KB_ID", ""), patch.object(rar, "BIO_KB_ID", ""):
        with pytest.raises(rar.ConfigError, match="CS_KB_ID"):
            rar.require_kb_config()


def test_require_kb_config_passes_when_set():
    with patch.object(rar, "CS_KB_ID", "kb-cs"), patch.object(rar, "BIO_KB_ID", "kb-bio"):
        rar.require_kb_config()


# --- Builder tool names ---

def test_cs_retriever_exposes_cs_tool():
    with patch.object(rar, "BedrockModel"):
        agent = rar.build_cs_retriever()
    names = list(agent.tool_registry.registry)
    assert names == ["retrieve_cs_papers"]


def test_bio_retriever_exposes_bio_tool():
    with patch.object(rar, "BedrockModel"):
        agent = rar.build_bio_retriever()
    names = list(agent.tool_registry.registry)
    assert names == ["retrieve_bio_papers"]


# --- Synthesis agent has no tools ---

def test_synthesis_agent_has_no_tools():
    passages = [_p("CS-001", 0.9)]
    with patch.object(rar, "BedrockModel"):
        agent = rar.build_synthesis_agent(passages, "What is attention?")
    assert list(agent.tool_registry.registry) == []


# --- Graceful degradation on empty aggregation ---

def test_run_rag_query_empty_returns_no_results_without_synthesis():
    with patch.object(rar, "require_kb_config"), \
         patch.object(rar, "run_agent_with_retry", return_value="ok") as mock_run, \
         patch.object(rar, "retrieval_results", {"cs": [], "bio": []}):
        result = rar.run_rag_query("blockchain consensus mechanisms for IoT networks")
    assert result["synthesis"] == "No relevant results found for this query."
    assert result["avg_score"] == 0.0
    # Only retrievers submitted (2); synthesis never invoked
    assert mock_run.call_count == 2


# --- Live tests (skip without KB IDs / credentials) ---

def test_live_retrieve_from_cs_kb():
    if not os.getenv("CS_KB_ID") or not os.getenv("AWS_ACCESS_KEY_ID"):
        pytest.skip("CS_KB_ID or AWS credentials not set")
    passages = rar.retrieve_from_kb(rar.CS_KB_ID, "machine learning", "CS", top_k=3)
    assert isinstance(passages, list)
    if passages:
        assert {"doc_id", "title", "source", "content", "score", "kb"} <= set(passages[0])
        assert passages[0]["kb"] == "CS"


def test_live_full_rag_cross_domain_query():
    if not (os.getenv("CS_KB_ID") and os.getenv("BIO_KB_ID") and os.getenv("AWS_ACCESS_KEY_ID")):
        pytest.skip("KB IDs or AWS credentials not set")
    result = rar.run_rag_query("applications of machine learning in genomics")
    assert result["synthesis"]
    assert result["cs_count"] + result["bio_count"] >= 1
