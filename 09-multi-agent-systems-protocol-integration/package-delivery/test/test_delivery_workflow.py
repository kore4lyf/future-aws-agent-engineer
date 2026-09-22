import os
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("AWS_ACCESS_KEY_ID", "")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "")
os.environ.setdefault("AWS_SESSION_TOKEN", "")
os.environ.setdefault("AWS_REGION", "us-east-1")

import delivery_workflow as dw


def test_packages_have_required_fields():
    for pkg in dw.PACKAGES:
        assert "id" in pkg
        assert "sender" in pkg
        assert "recipient" in pkg
        assert "weight_kg" in pkg
        assert "value" in pkg


def test_pkg003_has_empty_sender_address():
    pkg = next(p for p in dw.PACKAGES if p["id"] == "PKG-003")
    assert pkg["sender"]["address"] == ""


def test_pkg001_is_domestic():
    pkg = next(p for p in dw.PACKAGES if p["id"] == "PKG-001")
    assert pkg["sender"]["country"] == pkg["recipient"]["country"]


def test_pkg002_is_international():
    pkg = next(p for p in dw.PACKAGES if p["id"] == "PKG-002")
    assert pkg["sender"]["country"] != pkg["recipient"]["country"]


def test_orchestrate_halts_on_invalid_address():
    with patch("delivery_workflow.run_agent_with_retry") as mock_retry:
        mock_retry.side_effect = _mock_address_validator
        result = dw.orchestrate_delivery("PKG-003")
    assert result["status"] == "HALTED"
    assert result["phases_completed"] == ["gate"]


def test_orchestrate_domestic_route():
    with patch("delivery_workflow.run_agent_with_retry") as mock_retry:
        mock_retry.side_effect = _mock_all_agents
        result = dw.orchestrate_delivery("PKG-001")
    assert result["package"]["id"] == "PKG-001"
    assert result["shipping"]["shipping_type"] == "domestic"


def test_orchestrate_international_route():
    with patch("delivery_workflow.run_agent_with_retry") as mock_retry:
        mock_retry.side_effect = _mock_all_agents
        result = dw.orchestrate_delivery("PKG-002")
    assert result["package"]["id"] == "PKG-002"
    assert result["shipping"]["shipping_type"] == "international"


def test_phase2_timing_stored_in_workflow_state():
    with patch("delivery_workflow.run_agent_with_retry") as mock_retry:
        mock_retry.side_effect = _mock_all_agents
        dw.orchestrate_delivery("PKG-001")
    assert "phase2_seconds" in dw.workflow_state
    assert isinstance(dw.workflow_state["phase2_seconds"], float)


def _mock_address_validator(agent_builder, prompt):
    pkg_id = prompt.split()[-1]
    pkg = next(p for p in dw.PACKAGES if p["id"] == pkg_id)
    valid = all([pkg["sender"]["address"], pkg["sender"]["city"], pkg["sender"]["country"]])
    dw.workflow_state["validation"] = {"package_id": pkg_id, "valid": valid, "reason": "ok" if valid else "missing"}
    return "ok"


def _mock_all_agents(agent_builder, prompt):
    pkg_id = prompt.split()[-1]
    if "validat" in prompt.lower():
        pkg = next(p for p in dw.PACKAGES if p["id"] == pkg_id)
        valid = all([pkg["sender"]["address"], pkg["sender"]["city"], pkg["sender"]["country"]])
        dw.workflow_state["validation"] = {"package_id": pkg_id, "valid": valid, "reason": "ok" if valid else "missing"}
    elif "label" in prompt.lower():
        dw.workflow_state["label"] = {"package_id": pkg_id, "label_id": f"LBL-{pkg_id}"}
    elif "insurance" in prompt.lower():
        dw.workflow_state["insurance"] = {"package_id": pkg_id, "cost": 10.0}
    elif "carrier" in prompt.lower():
        pkg = next(p for p in dw.PACKAGES if p["id"] == pkg_id)
        is_intl = pkg["sender"]["country"] != pkg["recipient"]["country"]
        dw.workflow_state["carrier"] = {"package_id": pkg_id, "carrier": "DHL" if is_intl else "USPS", "international": is_intl}
    elif "domestic" in prompt.lower():
        dw.workflow_state["shipping"] = {"package_id": pkg_id, "shipping_type": "domestic", "status": "initiated"}
    elif "international" in prompt.lower():
        dw.workflow_state["shipping"] = {"package_id": pkg_id, "shipping_type": "international", "status": "initiated"}
    return "ok"


def test_live_pipeline_runs_with_aws_credentials(capsys):
    pytest.skip("AWS session token has expired; live test cannot run")
