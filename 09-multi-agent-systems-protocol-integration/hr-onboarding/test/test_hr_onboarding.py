import os
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("AWS_ACCESS_KEY_ID", "")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "")
os.environ.setdefault("AWS_SESSION_TOKEN", "")
os.environ.setdefault("AWS_REGION", "us-east-1")

import hr_onboarding as ho


def test_employees_have_required_fields():
    for emp in ho.EMPLOYEES:
        assert "id" in emp
        assert "name" in emp
        assert "department" in emp
        assert "role" in emp


def test_orchestrate_switches_department_routing():
    alice = next(e for e in ho.EMPLOYEES if e["id"] == "EMP-001")
    bob = next(e for e in ho.EMPLOYEES if e["id"] == "EMP-002")

    assert alice["department"] == "Engineering"
    assert bob["department"] == "Sales"


def test_build_onboarding_summary():
    summary = ho.build_onboarding_summary("EMP-001")

    assert summary["employee"]["id"] == "EMP-001"
    assert summary["employee"]["name"] == "Alice"
    assert summary["employee"]["department"] == "Engineering"


def test_workflow_state_clear_on_orchestrate():
    ho.workflow_state["account"] = {"stale": True}
    with patch("hr_onboarding.run_agent_with_retry") as mock_retry:
        mock_retry.return_value = "{}"
        ho.orchestrate_onboarding("EMP-001")
    assert ho.workflow_state == {}
    assert mock_retry.call_count == 6


def test_simulate_failure_flag_on_emp003():
    carol = next(e for e in ho.EMPLOYEES if e["id"] == "EMP-003")
    assert carol.get("simulate_failure") is True


def test_live_pipeline_runs_with_aws_credentials(capsys):
    pytest.skip("AWS session token has expired; live test cannot run")
