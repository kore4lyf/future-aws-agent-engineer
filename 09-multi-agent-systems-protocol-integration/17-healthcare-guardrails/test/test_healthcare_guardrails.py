import json
import os
import sys
from unittest.mock import MagicMock, Mock, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("AWS_ACCESS_KEY_ID", "")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "")
os.environ.setdefault("AWS_SESSION_TOKEN", "")
os.environ.setdefault("AWS_REGION", "us-east-1")
os.environ.setdefault("HEALTHCARE_GUARDRAIL_ID", "")
os.environ.setdefault("EVAL_MODEL", "us.anthropic.claude-sonnet-4-5-20250929-v1:0")

import healthcare_guardrails as hg


def _unwrap_tool(fn):
    for attr in ("_tool_function", "function", "func", "__wrapped__"):
        raw = getattr(fn, attr, None)
        if callable(raw):
            return raw
    return fn


# --- clean_response ---

def test_clean_response_strips_thinking_tags():
    raw = "<thinking>internal notes</thinking>I have a headache."
    assert hg.clean_response(raw) == "I have a headache."


def test_clean_response_handles_closing_only():
    assert hg.clean_response("answer</thinking>") == "answer"


def test_truncate_display():
    assert hg.truncate_display("short") == "short"
    long = "x" * 80
    assert len(hg.truncate_display(long)) == 55
    assert hg.truncate_display(long).endswith("...")


# --- extract_policy ---

def test_extract_policy_content():
    assert hg.extract_policy([{"contentPolicy": {"filters": []}}]) == "CONTENT_POLICY_FILTER"


def test_extract_policy_pii():
    assert hg.extract_policy([{"sensitiveInformationPolicy": {"piiEntities": []}}]) == "PII"


def test_extract_policy_topic():
    assert hg.extract_policy([{"topicPolicy": {"topics": []}}]) == "TOPIC_POLICY"


def test_extract_policy_word():
    assert hg.extract_policy([{"wordPolicy": {"words": []}}]) == "WORD_POLICY"


def test_extract_policy_unknown():
    assert hg.extract_policy([]) == "UNKNOWN"
    assert hg.extract_policy(None) == "UNKNOWN"


# --- apply_guardrail ---

def test_apply_guardrail_fails_open_on_api_error():
    client = Mock()
    client.apply_guardrail.side_effect = RuntimeError("throttle")
    with patch.object(hg, "HEALTHCARE_GUARDRAIL_ID", "gr_1"):
        result = hg.apply_guardrail("hello", direction="INPUT", client=client)
    assert result["action"] == "ALLOWED"
    assert result["failed_open"] is True
    assert "throttle" in result["error"]


def test_apply_guardrail_fails_open_when_id_missing():
    with patch.object(hg, "HEALTHCARE_GUARDRAIL_ID", ""):
        result = hg.apply_guardrail("hello", direction="INPUT")
    assert result["action"] == "ALLOWED"
    assert result["failed_open"] is True


def test_apply_guardrail_maps_intervened_to_blocked():
    client = Mock()
    client.apply_guardrail.return_value = {
        "action": "GUARDRAIL_INTERVENED",
        "assessments": [{"sensitiveInformationPolicy": {"piiEntities": [{"type": "SSN"}]}}],
    }
    with patch.object(hg, "HEALTHCARE_GUARDRAIL_ID", "gr_1"):
        result = hg.apply_guardrail("SSN 123-45-6789", direction="INPUT", client=client)
    assert result["action"] == "BLOCKED"
    assert result["policy"] == "PII"


def test_apply_guardrail_maps_none_to_allowed():
    client = Mock()
    client.apply_guardrail.return_value = {"action": "NONE", "assessments": []}
    with patch.object(hg, "HEALTHCARE_GUARDRAIL_ID", "gr_1"):
        result = hg.apply_guardrail("I have a headache", direction="INPUT", client=client)
    assert result["action"] == "ALLOWED"
    assert result["policy"] is None


# --- RateLimiter ---

def test_rate_limiter_allows_up_to_burst_then_denies():
    t = [1000.0]
    rl = hg.RateLimiter(rate_per_second=10, burst_limit=5, clock=lambda: t[0])
    for _ in range(5):
        assert rl.allow_request() is True
    assert rl.allow_request() is False


def test_rate_limiter_refills_over_time():
    t = [1000.0]
    rl = hg.RateLimiter(rate_per_second=10, burst_limit=5, clock=lambda: t[0])
    for _ in range(5):
        assert rl.allow_request()
    assert not rl.allow_request()
    t[0] += 1.0  # +10 tokens, capped at burst
    assert rl.allow_request()


# --- KillSwitch ---

def test_kill_switch_not_triggered_below_threshold():
    ks = hg.KillSwitch(threshold=3, window_seconds=300, cloudwatch=Mock())
    ks.record_request(was_violation=True)
    ks.record_request(was_violation=True)
    assert ks.check() is False


def test_kill_switch_triggers_at_threshold_with_min_total():
    ks = hg.KillSwitch(threshold=3, window_seconds=300, cloudwatch=Mock())
    for _ in range(3):
        ks.record_request(was_violation=True)
    assert ks.check() is True


def test_kill_switch_requires_min_three_total_requests():
    ks = hg.KillSwitch(threshold=1, window_seconds=300, cloudwatch=Mock())
    ks.record_request(was_violation=True)
    assert ks.check() is False  # only 1 total request in window
    ks.record_request(was_violation=False)
    ks.record_request(was_violation=False)
    assert ks.check() is True  # total >= 3 and violations >= 1


def test_kill_switch_emits_cloudwatch_metrics():
    cw = Mock()
    ks = hg.KillSwitch(threshold=3, cloudwatch=cw)
    ks.record_request(was_violation=True)
    ks.record_request(was_violation=False)
    assert cw.put_metric_data.call_count == 2
    first = cw.put_metric_data.call_args_list[0]
    assert first.kwargs["Namespace"] == "HealthcareGuardrails"
    assert first.kwargs["MetricData"][0]["MetricName"] == "GuardrailViolations"
    second = cw.put_metric_data.call_args_list[1]
    assert second.kwargs["MetricData"][0]["MetricName"] == "GuardrailAllowed"


def test_kill_switch_no_auto_reset_after_old_violations_age_out():
    ks = hg.KillSwitch(threshold=3, window_seconds=1, cloudwatch=Mock())
    for _ in range(3):
        ks.record_request(was_violation=True)
    assert ks.check() is True
    # Even if window would now be clean, is_triggered latches True
    assert ks.is_triggered is True


# --- MetricsDashboard ---

def test_dashboard_records_allowed_blocked_policies():
    dash = hg.MetricsDashboard()
    dash.record({"action": "ALLOWED", "assessments": []}, latency=0.5)
    dash.record({"action": "BLOCKED", "policy": "PII", "assessments": []})
    dash.record({"action": "BLOCKED", "policy": "TOPIC_POLICY", "assessments": []})
    dash.record_rate_limited()
    summary = dash.summary()
    assert summary["allowed"] == 1
    assert summary["blocked"] == 2
    assert summary["rate_limited"] == 1
    assert summary["policy_breakdown"]["PII"] == 1
    assert summary["policy_breakdown"]["TOPIC_POLICY"] == 1
    assert summary["avg_latency"] == 0.5


def test_dashboard_counts_anonymized_pii():
    dash = hg.MetricsDashboard()
    dash.record({
        "action": "ALLOWED",
        "assessments": [{
            "sensitiveInformationPolicy": {
                "piiEntities": [{"type": "NAME", "action": "ANONYMIZE"}],
            },
        }],
    })
    assert dash.summary()["anonymized"] == 1


# --- Pipeline order ---

def test_pipeline_kill_switch_short_circuits_first():
    ks = hg.KillSwitch(threshold=1, cloudwatch=Mock())
    ks.is_triggered = True
    rl = hg.RateLimiter(clock=lambda: 1000.0)
    dash = hg.MetricsDashboard()
    with patch.object(hg, "apply_guardrail") as mock_guard, \
         patch.object(hg, "build_healthcare_agent") as mock_agent:
        result = hg.run_governance_pipeline({"input": "hi"}, rl, ks, dash)
    assert result == {"action": "KILLED", "policy": "KILL_SWITCH"}
    mock_guard.assert_not_called()
    mock_agent.assert_not_called()


def test_pipeline_rate_limited_before_guardrail():
    t = [1000.0]
    rl = hg.RateLimiter(rate_per_second=0, burst_limit=1, clock=lambda: t[0])
    assert rl.allow_request()  # exhaust the single burst token
    ks = hg.KillSwitch(cloudwatch=Mock())
    dash = hg.MetricsDashboard()
    with patch.object(hg, "apply_guardrail") as mock_guard, \
         patch.object(hg, "build_healthcare_agent") as mock_agent:
        result = hg.run_governance_pipeline({"input": "hi"}, rl, ks, dash)
    assert result["action"] == "RATE_LIMITED"
    assert result["policy"] == "RATE_LIMITER"
    assert dash.summary()["rate_limited"] == 1
    mock_guard.assert_not_called()
    mock_agent.assert_not_called()


def test_pipeline_blocked_input_skips_agent_records_violation():
    ks = hg.KillSwitch(threshold=3, cloudwatch=Mock())
    rl = hg.RateLimiter(clock=lambda: 1000.0)
    dash = hg.MetricsDashboard()
    blocked = {"action": "BLOCKED", "policy": "PII", "assessments": [], "direction": "INPUT"}
    with patch.object(hg, "apply_guardrail", return_value=blocked), \
         patch.object(hg, "build_healthcare_agent") as mock_agent:
        result = hg.run_governance_pipeline(
            {"input": "SSN 123-45-6789"}, rl, ks, dash,
        )
    mock_agent.assert_not_called()
    assert result["action"] == "BLOCKED"
    assert result["policy"] == "PII"
    assert len(ks.violations) == 1
    assert dash.summary()["blocked"] == 1


def test_pipeline_allowed_invokes_agent_and_records_ok():
    ks = hg.KillSwitch(threshold=3, cloudwatch=Mock())
    rl = hg.RateLimiter(clock=lambda: 1000.0)
    dash = hg.MetricsDashboard()
    allowed = {"action": "ALLOWED", "policy": None, "assessments": [], "direction": "INPUT"}
    mock_agent_inst = Mock()
    mock_agent_inst.return_value = "<thinking>triage</thinking>I can help with that headache."
    with patch.object(hg, "apply_guardrail", return_value=allowed), \
         patch.object(hg, "build_healthcare_agent", return_value=mock_agent_inst):
        result = hg.run_governance_pipeline({"input": "headache"}, rl, ks, dash)
    mock_agent_inst.assert_called_once()
    assert result["action"] == "ALLOWED"
    assert "agent_response" in result
    assert "thinking" not in result["agent_response"]
    assert len(ks.violations) == 0
    assert dash.summary()["allowed"] == 1


def test_pipeline_three_blocked_then_kill_switch_rejects_later():
    """Demo narrative: 3 violations trip the breaker; later inputs never hit guardrail."""
    ks = hg.KillSwitch(threshold=3, cloudwatch=Mock())
    rl = hg.RateLimiter(clock=lambda: 1000.0)
    dash = hg.MetricsDashboard()
    blocked = {"action": "BLOCKED", "policy": "TOPIC_POLICY", "assessments": [], "direction": "INPUT"}
    with patch.object(hg, "apply_guardrail", return_value=blocked), \
         patch.object(hg, "build_healthcare_agent") as mock_agent:
        for _ in range(3):
            hg.run_governance_pipeline({"input": "bad"}, rl, ks, dash)
        assert ks.check() is True
        result = hg.run_governance_pipeline({"input": "prescription"}, rl, ks, dash)
    assert result["action"] == "KILLED"
    assert mock_agent.assert_not_called is not None
    mock_agent.assert_not_called()
    # Third blocked input still called guardrail; fourth did not
    assert dash.summary()["blocked"] == 3


# --- Healthcare agent ---

def test_healthcare_agent_tool_name():
    with patch.object(hg, "BedrockModel"):
        agent = hg.build_healthcare_agent()
    assert list(agent.tool_registry.registry) == ["lookup_symptoms"]


def test_healthcare_prompt_forbids_prescriptions_and_legal_advice():
    assert "Do NOT prescribe" in hg.HEALTHCARE_SYSTEM_PROMPT
    assert "Do NOT give legal advice" in hg.HEALTHCARE_SYSTEM_PROMPT


def test_lookup_symptoms_maps_known_symptom():
    with patch.object(hg, "BedrockModel"):
        agent = hg.build_healthcare_agent()
    fn = agent.tool_registry.registry["lookup_symptoms"]
    raw = _unwrap_tool(fn)
    data = json.loads(raw("I have a severe chest pain"))
    assert data["urgency"] == "emergency"


# --- Evaluator ---

def test_evaluator_tool_name():
    with patch.object(hg, "BedrockModel"):
        agent = hg.build_evaluator_agent()
    assert list(agent.tool_registry.registry) == ["score_response"]


def test_score_response_clamps_and_averages():
    with patch.object(hg, "BedrockModel"):
        agent = hg.build_evaluator_agent()
    fn = agent.tool_registry.registry["score_response"]
    raw = _unwrap_tool(fn)
    payload = json.loads(raw(relevance=0, accuracy=6, safety=3, completeness=4))
    assert payload["relevance"] == 1
    assert payload["accuracy"] == 5
    assert payload["safety"] == 3
    assert payload["completeness"] == 4
    assert payload["average"] == pytest.approx((1 + 5 + 3 + 4) / 4)


def test_evaluator_prompt_requires_four_criteria():
    assert "relevance" in hg.EVALUATOR_SYSTEM_PROMPT
    assert "accuracy" in hg.EVALUATOR_SYSTEM_PROMPT
    assert "safety" in hg.EVALUATOR_SYSTEM_PROMPT
    assert "completeness" in hg.EVALUATOR_SYSTEM_PROMPT
    assert "score_response" in hg.EVALUATOR_SYSTEM_PROMPT


def test_evaluator_uses_different_model_id_by_default():
    assert hg.EVAL_MODEL != hg.NOVA_LITE_MODEL


# --- Test input narrative ---

def test_demo_inputs_cover_five_legit_five_adversarial():
    assert len(hg.TEST_INPUTS) == 10
    assert hg.TEST_INPUTS[0]["label"].startswith("Legit")
    assert hg.TEST_INPUTS[5]["label"].startswith("Adversarial")
    ssn = hg.TEST_INPUTS[5]["input"]
    assert "123-45-6789" in ssn
    assert "malpractice" in hg.TEST_INPUTS[7]["input"].lower()
    assert "prescribe" in hg.TEST_INPUTS[8]["input"].lower()


# --- Live tests ---

def test_live_apply_guardrail_input():
    if not os.getenv("HEALTHCARE_GUARDRAIL_ID") or not os.getenv("AWS_ACCESS_KEY_ID"):
        pytest.skip("HEALTHCARE_GUARDRAIL_ID or AWS credentials not set")
    result = hg.apply_guardrail("I have a dull headache.", direction="INPUT")
    assert result["action"] in ("ALLOWED", "BLOCKED")


def test_live_pipeline_single_legit_input():
    if not os.getenv("HEALTHCARE_GUARDRAIL_ID") or not os.getenv("AWS_ACCESS_KEY_ID"):
        pytest.skip("HEALTHCARE_GUARDRAIL_ID or AWS credentials not set")
    if not os.getenv("NOVA_LITE_MODEL"):
        pytest.skip("NOVA_LITE_MODEL not set")
    rl = hg.RateLimiter()
    ks = hg.KillSwitch(cloudwatch=Mock())
    dash = hg.MetricsDashboard()
    result = hg.run_governance_pipeline(
        {"input": "I have a dull headache after long hours at my desk."},
        rl, ks, dash,
    )
    assert result["action"] in ("ALLOWED", "BLOCKED", "RATE_LIMITED")
    assert not ks.check()
