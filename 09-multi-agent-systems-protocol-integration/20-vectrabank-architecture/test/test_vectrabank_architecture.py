import json
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("AWS_ACCESS_KEY_ID", "")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "")
os.environ.setdefault("AWS_SESSION_TOKEN", "")
os.environ.setdefault("AWS_REGION", "us-east-1")

import vectrabank_architecture as vb


# --- _load_cf_exports / _require_export ---

def test_load_cf_exports(monkeypatch):
    cf = MagicMock()
    cf.get_paginator.return_value.paginate.return_value = [
        {
            "Exports": [
                {"Name": "lesson-10-exercise-AgentCoreRoleArn", "Value": "arn:role"},
                {"Name": "lesson-10-exercise-ArtifactBucketName", "Value": "bucket"},
                {"Name": "lesson-10-exercise-GuardrailId", "Value": "gr-1"},
            ]
        }
    ]
    monkeypatch.setattr(vb, "boto3", MagicMock(client=MagicMock(return_value=cf)))
    exports = vb._load_cf_exports()
    assert exports["lesson-10-exercise-AgentCoreRoleArn"] == "arn:role"


def test_require_export_missing_exits():
    with patch("vectrabank_architecture._load_cf_exports", return_value={}), \
         pytest.raises(SystemExit):
        vb._require_export({}, "lesson-10-exercise-AgentCoreRoleArn")


# --- Runtime config ---

def test_runtime_config_vpc_mode():
    assert vb.RUNTIME_CONFIG["networkConfiguration"]["networkMode"] == "VPC"
    assert "vpcConfiguration" in vb.RUNTIME_CONFIG["networkConfiguration"]
    assert "subnetIds" in vb.RUNTIME_CONFIG["networkConfiguration"]["vpcConfiguration"]
    assert "securityGroupIds" in vb.RUNTIME_CONFIG["networkConfiguration"]["vpcConfiguration"]


def test_runtime_config_has_env_vars():
    env = vb.RUNTIME_CONFIG["environmentVariables"]
    assert "QUERY_KB_ID" in env
    assert "MARKET_KB_ID" in env
    assert "COMPLIANCE_KB_ID" in env
    assert "STATE_TABLE_NAME" in env


# --- Agent definitions ---

def test_agent_definitions_four_agents():
    assert len(vb.AGENT_DEFINITIONS) == 4
    names = [a["name"] for a in vb.AGENT_DEFINITIONS]
    assert "QueryRouter" in names
    assert "MarketDataRetriever" in names
    assert "ComplianceRetriever" in names
    assert "FinancialAdvisor" in names


def test_agent_tiering_lightweight_for_routing():
    router = next(a for a in vb.AGENT_DEFINITIONS if a["name"] == "QueryRouter")
    retriever = next(a for a in vb.AGENT_DEFINITIONS if a["name"] == "MarketDataRetriever")
    assert router["model"] == "amazon.nova-lite-v1:0"
    assert retriever["model"] == "amazon.nova-lite-v1:0"


def test_financial_advisor_uses_capable_model():
    advisor = next(a for a in vb.AGENT_DEFINITIONS if a["name"] == "FinancialAdvisor")
    assert advisor["model"] == "us.anthropic.claude-sonnet-4-5-20250929-v1:0"
    assert advisor["temperature"] == 0.1


# --- Monitoring ---

def test_monitoring_has_six_widgets():
    assert len(vb.MONITORING_STRATEGY["cloudwatch_widgets"]) == 6


def test_monitoring_has_three_alarms():
    alarms = vb.MONITORING_STRATEGY["alarms"]
    assert len(alarms) == 3
    names = [a["name"] for a in alarms]
    assert "HighErrorRate" in names
    assert "HighLatency" in names
    assert "GuardrailViolations" in names


def test_xray_sampling_rate_for_audit():
    assert vb.MONITORING_STRATEGY["xray_tracing"]["enabled"] is True
    assert vb.MONITORING_STRATEGY["xray_tracing"]["sampling_rate"] == 1.0


# --- Cost estimation ---

def test_estimate_monthly_costs_includes_infrastructure():
    costs = vb.estimate_monthly_costs(vb.AGENT_DEFINITIONS)
    assert costs["total_monthly_usd"] > 0
    types = {item["type"] for item in costs["breakdown"]}
    assert "infrastructure" in types


def test_estimate_monthly_crops_vpc_nat():
    costs = vb.estimate_monthly_costs(vb.AGENT_DEFINITIONS)
    agents = [item["agent"] for item in costs["breakdown"]]
    assert "vpc_nat_gateway_monthly" in agents


# --- Runbooks ---

def test_runbooks_four_scenarios():
    assert len(vb.OPERATIONAL_RUNBOOKS) == 4
    expected = {"deploy_new_version", "emergency_rollback", "kill_switch", "investigate_high_latency"}
    assert set(vb.OPERATIONAL_RUNBOOKS.keys()) == expected


def test_kill_switch_runbook_steps():
    steps = vb.OPERATIONAL_RUNBOOKS["kill_switch"]["steps"]
    assert any("disable" in step.lower() for step in steps)
    assert any("notify" in step.lower() for step in steps)


def test_deploy_runbook_has_gates():
    steps = vb.OPERATIONAL_RUNBOOKS["deploy_new_version"]["steps"]
    assert any("test" in step.lower() for step in steps)
    assert any("smoke" in step.lower() for step in steps)


# --- Output formatting ---

def test_format_architecture_plan_contains_all_sections():
    plan = vb.format_architecture_plan(
        vb.RUNTIME_CONFIG, vb.AGENT_DEFINITIONS,
        vb.MONITORING_STRATEGY, vb.estimate_monthly_costs(vb.AGENT_DEFINITIONS),
        vb.OPERATIONAL_RUNBOOKS,
    )
    assert "AgentCore Runtime Configuration" in plan
    assert "Agent Definitions" in plan
    assert "Monitoring Strategy" in plan
    assert "Cost Estimate" in plan
    assert "Operational Runbooks" in plan


def test_main_prints_plan():
    with patch("vectrabank_architecture._load_cf_exports", return_value={
        "lesson-10-exercise-AgentCoreRoleArn": "arn:role",
        "lesson-10-exercise-ArtifactBucketName": "bucket",
        "lesson-10-exercise-GuardrailId": "gr-1",
    }), patch("builtins.print") as mock_print:
        vb.main()
    output = " ".join(str(call.args[0]) for call in mock_print.call_args_list if call.args)
    assert "VectraBank" in output
    assert "VPC" in output
    assert "FinancialAdvisor" in output
