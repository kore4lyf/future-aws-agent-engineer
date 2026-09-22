import json
import os
import sys
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("AWS_ACCESS_KEY_ID", "")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "")
os.environ.setdefault("AWS_SESSION_TOKEN", "")
os.environ.setdefault("AWS_REGION", "us-east-1")
os.environ.setdefault("DYNAMODB_TABLE", "routing-audit-test")

import financial_router as fr


# --- REQ-001, REQ-002: wire/transfer keywords → PaymentsAgent (rule) ---

def test_req001_wire_transfer_to_payments():
    request = {"id": "REQ-001", "text": "I need to send a wire transfer to my vendor", "amount": 5000}
    result = fr.hybrid_route(request)
    assert result["target_agent"] == "PaymentsAgent"
    assert result["method"] == "rule"
    assert result["confidence"] == 1.0


def test_req002_payment_keyword_to_payments():
    request = {"id": "REQ-002", "text": "Please process a payment to my supplier", "amount": 3000}
    result = fr.hybrid_route(request)
    assert result["target_agent"] == "PaymentsAgent"
    assert result["method"] == "rule"
    assert result["confidence"] == 1.0


# --- REQ-003, REQ-004: fraud/unauthorized keywords → FraudAgent (rule) ---

def test_req003_fraud_keyword_to_fraud():
    request = {"id": "REQ-003", "text": "I noticed fraudulent charges on my account", "amount": 0}
    result = fr.hybrid_route(request)
    assert result["target_agent"] == "FraudAgent"
    assert result["method"] == "rule"
    assert result["confidence"] == 1.0


def test_req004_unauthorized_keyword_to_fraud():
    request = {"id": "REQ-004", "text": "There are unauthorized transactions on my card", "amount": 0}
    result = fr.hybrid_route(request)
    assert result["target_agent"] == "FraudAgent"
    assert result["method"] == "rule"
    assert result["confidence"] == 1.0


# --- REQ-005, REQ-006: balance/statement keywords → AccountAgent (rule) ---

def test_req005_balance_keyword_to_account():
    request = {"id": "REQ-005", "text": "Can you check my account balance?", "amount": 0}
    result = fr.hybrid_route(request)
    assert result["target_agent"] == "AccountAgent"
    assert result["method"] == "rule"
    assert result["confidence"] == 1.0


def test_req006_statement_keyword_to_account():
    request = {"id": "REQ-006", "text": "I need a copy of my account statement", "amount": 0}
    result = fr.hybrid_route(request)
    assert result["target_agent"] == "AccountAgent"
    assert result["method"] == "rule"
    assert result["confidence"] == 1.0


# --- REQ-007, REQ-008: high value → SeniorReviewAgent (priority) ---

def test_req007_high_value_50k_to_senior_review():
    request = {"id": "REQ-007", "text": "Send $50,000 wire to offshore account", "amount": 50000}
    result = fr.hybrid_route(request)
    assert result["target_agent"] == "SeniorReviewAgent"
    assert result["method"] == "priority"
    assert result["confidence"] == 1.0


def test_req008_high_value_25k_to_senior_review():
    request = {"id": "REQ-008", "text": "Transfer $25,000 to investment fund", "amount": 25000}
    result = fr.hybrid_route(request)
    assert result["target_agent"] == "SeniorReviewAgent"
    assert result["method"] == "priority"
    assert result["confidence"] == 1.0


# --- REQ-009: ambiguous → LLM classifier (high confidence) ---

def test_req009_ambiguous_to_llm_classifier():
    mock_result = json.dumps({"intent": "payments", "confidence": 0.85})
    with patch("financial_router.run_agent_with_retry", return_value=mock_result):
        request = {"id": "REQ-009", "text": "I need help moving some funds around", "amount": 0}
        result = fr.hybrid_route(request)
    assert result["target_agent"] == "PaymentsAgent"
    assert result["method"] == "llm"
    assert result["confidence"] == 0.85


# --- REQ-010: nonsensical → GeneralSupportAgent (fallback) ---

def test_req010_nonsensical_to_fallback():
    mock_result = json.dumps({"intent": "general", "confidence": 0.2})
    with patch("financial_router.run_agent_with_retry", return_value=mock_result):
        request = {"id": "REQ-010", "text": "purple elephant dancing on mars", "amount": 0}
        result = fr.hybrid_route(request)
    assert result["target_agent"] == "GeneralSupportAgent"
    assert result["method"] == "fallback"
    assert result["confidence"] == 0.2


# --- Audit logging test ---

def test_log_routing_decision_writes_to_dynamodb():
    mock_table = MagicMock()
    with patch("financial_router.audit_table", mock_table):
        fr.log_routing_decision("REQ-001", "rule", "PaymentsAgent", 1.0, 12.5)
    mock_table.put_item.assert_called_once()
    item = mock_table.put_item.call_args[1]["Item"]
    assert item["request_id"] == "REQ-001"
    assert item["method"] == "rule"
    assert item["target_agent"] == "PaymentsAgent"
    assert "ttl" in item


# --- Full flow test ---

def test_process_request_returns_full_result():
    mock_table = MagicMock()
    with patch("financial_router.audit_table", mock_table):
        request = {"id": "REQ-005", "text": "check my balance", "amount": 0}
        result = fr.process_request(request)
    assert result["request_id"] == "REQ-005"
    assert result["target_agent"] == "AccountAgent"
    assert result["method"] == "rule"
    assert "latency_ms" in result


# --- Live test skipped ---

def test_live_pipeline_runs_with_aws_credentials():
    pytest.skip("Requires deployed DynamoDB table and valid AWS credentials")
