import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("AWS_ACCESS_KEY_ID", "")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "")
os.environ.setdefault("AWS_SESSION_TOKEN", "")
os.environ.setdefault("AWS_REGION", "us-east-1")

import contract_compliance as cc


def test_synthesizer_approves_low_risk():
    cc.regulatory_cache.clear()
    cc.financial_cache.clear()
    cc.ip_cache.clear()

    cc.regulatory_cache["CONTRACT-001"] = {"risk_level": "LOW"}
    cc.financial_cache["CONTRACT-001"] = {"risk_level": "LOW"}
    cc.ip_cache["CONTRACT-001"] = {"risk_level": "LOW"}

    result = cc.synthesize_compliance("CONTRACT-001")
    data = cc.json.loads(result)

    assert data["recommendation"] == "APPROVE"
    assert data["overall_risk"] == "LOW"


def test_synthesizer_rejects_multiple_high_risks():
    cc.regulatory_cache.clear()
    cc.financial_cache.clear()
    cc.ip_cache.clear()

    cc.regulatory_cache["CONTRACT-002"] = {"risk_level": "HIGH"}
    cc.financial_cache["CONTRACT-002"] = {"risk_level": "HIGH"}
    cc.ip_cache["CONTRACT-002"] = {"risk_level": "HIGH"}

    result = cc.synthesize_compliance("CONTRACT-002")
    data = cc.json.loads(result)

    assert data["recommendation"] == "REJECT"
    assert data["overall_risk"] == "HIGH"


def test_live_pipeline_runs_with_aws_credentials(capsys):
    pytest.skip("Claude model access is not available; live pipeline test requires Anthropic Bedrock subscription")
