import os
import sys
from unittest.mock import patch, MagicMock

import boto3
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("AWS_ACCESS_KEY_ID", "")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "")
os.environ.setdefault("AWS_SESSION_TOKEN", "")
os.environ.setdefault("AWS_REGION", "us-east-1")
os.environ.setdefault("DYNAMODB_TABLE", "telecom-routing-audit")

import telecom_router as tr


# --- Priority: cancellation intent → RetentionAgent (Tier 1) ---

def test_tkt015_cancel_service_to_retention():
    ticket = {"id": "TKT-015", "text": "I want to cancel my service"}
    result = tr.hybrid_route(ticket)
    assert result["target_agent"] == "RetentionAgent"
    assert result["method"] == "priority"
    assert result["confidence"] == 1.0


def test_tkt016_terminate_plan_to_retention():
    ticket = {"id": "TKT-016", "text": "I'm switching to another provider, terminate my plan"}
    result = tr.hybrid_route(ticket)
    assert result["target_agent"] == "RetentionAgent"
    assert result["method"] == "priority"
    assert result["confidence"] == 1.0


def test_priority_pattern_switch_provider():
    assert tr.priority_route("I want to switch provider") == "RetentionAgent"


def test_priority_pattern_discontinue():
    assert tr.priority_route("Please discontinue my line") == "RetentionAgent"


def test_priority_pattern_leave_plan():
    assert tr.priority_route("I plan to leave this plan") == "RetentionAgent"


# --- Rules: billing keywords → BillingAgent (Tier 2) ---

def test_tkt001_overcharged_bill_to_billing():
    ticket = {"id": "TKT-001", "text": "I was overcharged on my bill this month"}
    result = tr.hybrid_route(ticket)
    assert result["target_agent"] == "BillingAgent"
    assert result["method"] == "rule"
    assert result["confidence"] == 1.0


def test_tkt002_invoice_charge_to_billing():
    ticket = {"id": "TKT-002", "text": "There's an incorrect charge on my invoice"}
    result = tr.hybrid_route(ticket)
    assert result["target_agent"] == "BillingAgent"
    assert result["method"] == "rule"


def test_tkt003_payment_not_applied_to_billing():
    ticket = {"id": "TKT-003", "text": "Why was my payment not applied to my account?"}
    result = tr.hybrid_route(ticket)
    assert result["target_agent"] == "BillingAgent"
    assert result["method"] == "rule"


def test_tkt004_roaming_charge_to_billing():
    ticket = {"id": "TKT-004", "text": "I need to dispute a roaming charge on my bill"}
    result = tr.hybrid_route(ticket)
    assert result["target_agent"] == "BillingAgent"
    assert result["method"] == "rule"


def test_tkt005_subscription_rate_to_billing():
    ticket = {"id": "TKT-005", "text": "My subscription rate seems too high"}
    result = tr.hybrid_route(ticket)
    assert result["target_agent"] == "BillingAgent"
    assert result["method"] == "rule"


def test_tkt006_explain_charge_invoice_to_billing():
    ticket = {"id": "TKT-006", "text": "Please explain this charge on my latest invoice"}
    result = tr.hybrid_route(ticket)
    assert result["target_agent"] == "BillingAgent"
    assert result["method"] == "rule"


def test_tkt007_update_payment_to_billing():
    ticket = {"id": "TKT-007", "text": "I want to update my payment method for the bill"}
    result = tr.hybrid_route(ticket)
    assert result["target_agent"] == "BillingAgent"
    assert result["method"] == "rule"


def test_tkt008_double_charge_to_billing():
    ticket = {"id": "TKT-008", "text": "There's a double charge on my billing statement"}
    result = tr.hybrid_route(ticket)
    assert result["target_agent"] == "BillingAgent"
    assert result["method"] == "rule"


# --- Rules: technical keywords → TechnicalAgent (Tier 2) ---

def test_tkt009_outage_to_technical():
    ticket = {"id": "TKT-009", "text": "There's an outage in my area"}
    result = tr.hybrid_route(ticket)
    assert result["target_agent"] == "TechnicalAgent"
    assert result["method"] == "rule"
    assert result["confidence"] == 1.0


def test_tkt010_no_signal_to_technical():
    ticket = {"id": "TKT-010", "text": "I have no signal on my phone"}
    result = tr.hybrid_route(ticket)
    assert result["target_agent"] == "TechnicalAgent"
    assert result["method"] == "rule"


def test_tkt011_slow_internet_to_technical():
    ticket = {"id": "TKT-011", "text": "My internet is slow since yesterday"}
    result = tr.hybrid_route(ticket)
    assert result["target_agent"] == "TechnicalAgent"
    assert result["method"] == "rule"


def test_tkt012_dropped_calls_to_technical():
    ticket = {"id": "TKT-012", "text": "My calls keep getting dropped"}
    result = tr.hybrid_route(ticket)
    assert result["target_agent"] == "TechnicalAgent"
    assert result["method"] == "rule"


def test_tkt013_disconnecting_to_technical():
    ticket = {"id": "TKT-013", "text": "The service keeps disconnecting"}
    result = tr.hybrid_route(ticket)
    assert result["target_agent"] == "TechnicalAgent"
    assert result["method"] == "rule"


def test_tkt014_no_service_to_technical():
    ticket = {"id": "TKT-014", "text": "There's no service at my location"}
    result = tr.hybrid_route(ticket)
    assert result["target_agent"] == "TechnicalAgent"
    assert result["method"] == "rule"


# --- LLM: ambiguous tickets → specialist (Tier 3) ---

def test_tkt017_ambiguous_to_llm():
    with patch("telecom_router.llm_classify", return_value=("technical", 0.7, {"intent": "technical", "confidence": 0.7})):
        ticket = {"id": "TKT-017", "text": "Something weird is happening with my account"}
        result = tr.hybrid_route(ticket)
    assert result["target_agent"] == "TechnicalAgent"
    assert result["method"] == "llm"
    assert result["confidence"] == 0.7


def test_tkt018_ambiguous_to_llm_billing():
    with patch("telecom_router.llm_classify", return_value=("billing", 0.65, {"intent": "billing", "confidence": 0.65})):
        ticket = {"id": "TKT-018", "text": "I'm not happy with how things are going"}
        result = tr.hybrid_route(ticket)
    assert result["target_agent"] == "BillingAgent"
    assert result["method"] == "llm"
    assert result["confidence"] == 0.65


def test_tkt019_ambiguous_to_llm_general():
    with patch("telecom_router.llm_classify", return_value=("general", 0.9, {"intent": "general", "confidence": 0.9})):
        ticket = {"id": "TKT-019", "text": "Can someone help me with my recent experience?"}
        result = tr.hybrid_route(ticket)
    assert result["target_agent"] == "GeneralSupportAgent"
    assert result["method"] == "llm"
    assert result["confidence"] == 0.9


# --- Fallback: nonsensical → GeneralSupportAgent (Tier 4) ---

def test_tkt020_nonsensical_to_fallback():
    with patch("telecom_router.llm_classify", return_value=("general", 0.2, {"intent": "general", "confidence": 0.2})):
        ticket = {"id": "TKT-020", "text": "purple elephant dancing on mars"}
        result = tr.hybrid_route(ticket)
    assert result["target_agent"] == "GeneralSupportAgent"
    assert result["method"] == "fallback"
    assert result["confidence"] == 0.2


# --- Rule helper tests ---

def test_rule_based_route_returns_none_when_no_match():
    assert tr.rule_based_route("hello world") is None


def test_priority_route_returns_none_when_no_match():
    assert tr.priority_route("hello world") is None


def test_priority_takes_precedence_over_rules():
    # Cancellation wording that also contains billing keywords
    ticket = {"id": "X", "text": "Cancel my bill and terminate service"}
    result = tr.hybrid_route(ticket)
    assert result["method"] == "priority"
    assert result["target_agent"] == "RetentionAgent"


# --- Audit logging test ---

def test_log_routing_decision_writes_to_dynamodb():
    mock_table = MagicMock()
    with patch("telecom_router.audit_table", mock_table):
        tr.log_routing_decision("TKT-001", "rule", "BillingAgent", 1.0, 12.5)
    mock_table.put_item.assert_called_once()
    item = mock_table.put_item.call_args[1]["Item"]
    assert item["request_id"] == "TKT-001"
    assert item["method"] == "rule"
    assert item["target_agent"] == "BillingAgent"
    assert "ttl" in item


# --- Full flow test ---

def test_process_ticket_returns_full_result():
    mock_table = MagicMock()
    with patch("telecom_router.audit_table", mock_table), \
         patch("telecom_router.run_worker_agent", return_value="Resolved."):
        ticket = {"id": "TKT-001", "text": "I was overcharged on my bill"}
        result = tr.process_ticket(ticket)
    assert result["ticket_id"] == "TKT-001"
    assert result["target_agent"] == "BillingAgent"
    assert result["method"] == "rule"
    assert "latency_ms" in result
    assert result["resolution"] == "Resolved."
    mock_table.put_item.assert_called_once()


# --- Worker agent prompt coverage ---

def test_all_worker_agents_have_system_prompts():
    for agent_name in ["BillingAgent", "TechnicalAgent", "RetentionAgent", "GeneralSupportAgent"]:
        assert agent_name in tr.WORKER_SYSTEM_PROMPTS
        assert tr.WORKER_SYSTEM_PROMPTS[agent_name]


# --- Live test: real DynamoDB write with AWS credentials ---

def test_live_pipeline_runs_with_aws_credentials():
    if not os.getenv("AWS_ACCESS_KEY_ID"):
        pytest.skip("AWS credentials are not set")

    table = boto3.resource("dynamodb", region_name="us-east-1").Table("telecom-routing-audit")

    ticket = {"id": "LIVE-001", "text": "I was overcharged on my bill this month"}
    with patch("telecom_router.run_worker_agent", return_value="Resolved."):
        result = tr.process_ticket(ticket)

    # Rule-based routing should succeed without LLM
    assert result["target_agent"] == "BillingAgent"
    assert result["method"] == "rule"
    assert result["confidence"] == 1.0

    # Verify the audit record was written to DynamoDB
    item = table.get_item(Key={"request_id": "LIVE-001"}).get("Item")
    assert item is not None, "Audit record not found in DynamoDB"
    assert item["target_agent"] == "BillingAgent"
    assert item["method"] == "rule"
    assert "ttl" in item
