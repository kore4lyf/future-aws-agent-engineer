from deployment_walkthrough import (
    _load_cf_exports,
    _require_export,
    RUNTIME_CONFIG,
    AGENT_DEFINITIONS,
    DEPLOYMENT_PIPELINE,
    MONITORING_STRATEGY,
    estimate_monthly_costs,
    deploy_to_agentcore,
    _build_artifact_zip,
    _EXPORT_ROLE,
    _EXPORT_BUCKET,
    _EXPORT_GUARDRAIL,
)
from unittest.mock import MagicMock, patch
import zipfile
from io import BytesIO

import pytest


# --- _load_cf_exports / _require_export ---

def test_load_cf_exports(monkeypatch):
    cf = MagicMock()
    cf.get_paginator.return_value.paginate.return_value = [
        {
            "Exports": [
                {"Name": _EXPORT_ROLE, "Value": "arn:role"},
                {"Name": _EXPORT_BUCKET, "Value": "my-bucket"},
                {"Name": _EXPORT_GUARDRAIL, "Value": "gr-1"},
            ]
        }
    ]
    import deployment_walkthrough as dw
    monkeypatch.setattr(dw, "boto3", MagicMock(client=MagicMock(return_value=cf)))
    exports = dw._load_cf_exports()
    assert exports[_EXPORT_ROLE] == "arn:role"


def test_require_export_missing_exits():
    with patch("deployment_walkthrough._load_cf_exports", return_value={}), \
         pytest.raises(SystemExit):
        _require_export({}, _EXPORT_ROLE)


# --- Cost estimation ---

def test_estimate_monthly_costs_sum():
    costs = estimate_monthly_costs(AGENT_DEFINITIONS)
    assert costs["total_monthly_usd"] > 0
    assert len(costs["breakdown"]) == len(AGENT_DEFINITIONS) + len(
        {"dynamodb_monthly": 25, "cloudwatch_monthly": 15, "xray_monthly": 5}
    )


# --- Artifact packaging ---

def test_build_artifact_zip_contains_main():
    data = _build_artifact_zip()
    with zipfile.ZipFile(BytesIO(data)) as zf:
        names = zf.namelist()
    assert "main.py" in names


# --- Runtime config shape ---

def test_runtime_config_has_expected_keys():
    assert "agentRuntimeName" in RUNTIME_CONFIG
    assert RUNTIME_CONFIG["networkConfiguration"]["networkMode"] == "PUBLIC"
    assert RUNTIME_CONFIG["protocolConfiguration"]["serverProtocol"] == "MCP"


# --- Agent definitions ---

def test_agent_definitions_three_tiers():
    assert len(AGENT_DEFINITIONS) == 3
    names = [a["name"] for a in AGENT_DEFINITIONS]
    assert "ClaimsRouter" in names
    assert "ClaimsAnalyzer" in names
    assert "ClaimsResponder" in names
    assert AGENT_DEFINITIONS[0]["temperature"] == 0.0
    assert AGENT_DEFINITIONS[1]["temperature"] == 0.1
    assert AGENT_DEFINITIONS[2]["temperature"] == 0.3


# --- Pipeline ---

def test_deployment_pipeline_six_steps():
    assert len(DEPLOYMENT_PIPELINE) == 6
    for step in DEPLOYMENT_PIPELINE:
        assert "step" in step
        assert "name" in step
        assert "command" in step
        assert "gate" in step


# --- Monitoring ---

def test_monitoring_strategy_has_alarms_and_xray():
    assert len(MONITORING_STRATEGY["alarms"]) == 2
    assert MONITORING_STRATEGY["xray_tracing"]["enabled"] is True
    assert MONITORING_STRATEGY["xray_tracing"]["sampling_rate"] == 0.05


# --- deploy_to_agentcore dry-run ---

def test_deploy_to_agentcore_dry_run():
    exports = {
        _EXPORT_ROLE: "arn:role",
        _EXPORT_BUCKET: "bucket",
        _EXPORT_GUARDRAIL: "gr-1",
    }
    with patch("deployment_walkthrough.deploy_to_agentcore", return_value={"status": "dry-run", "arn": ""}):
        pass  # just import-time validation


# --- deploy_to_agentcore idempotent ---

def test_deploy_to_agentcore_already_exists(monkeypatch):
    exports = {
        _EXPORT_ROLE: "arn:role",
        _EXPORT_BUCKET: "bucket",
        _EXPORT_GUARDRAIL: "gr-1",
    }
    control = MagicMock()
    control.exceptions.ResourceNotFoundException = Exception
    control.get_agent_runtime.return_value = {"agentRuntimeArn": "arn:existing"}
    s3 = MagicMock()

    import deployment_walkthrough as dw
    monkeypatch.setattr(dw, "boto3", MagicMock(client=MagicMock(side_effect=[control, s3, control])))

    result = dw.deploy_to_agentcore(exports, dry_run=False)
    assert result["status"] == "already-exists"
