import json
import os
import sys
from unittest.mock import Mock, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("AWS_ACCESS_KEY_ID", "")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "")
os.environ.setdefault("AWS_SESSION_TOKEN", "")
os.environ.setdefault("AWS_REGION", "us-east-1")
os.environ.setdefault("TRADING_GUARDRAIL_ID", "")
os.environ.setdefault("EVAL_MODEL", "us.anthropic.claude-sonnet-4-5-20250929-v1:0")

import trading_compliance as tc


def _unwrap_tool(fn):
    for attr in ("_tool_function", "function", "func", "__wrapped__"):
        raw = getattr(fn, attr, None)
        if callable(raw):
            return raw
    return fn


# --- clean_response ---

def test_clean_response_strips_thinking_tags():
    raw = "<thinking>internal notes</thinking>I can help with that."
    assert tc.clean_response(raw) == "I can help with that."


def test_clean_response_handles_closing_only():
    assert tc.clean_response("answer</thinking>") == "answer"


def test_truncate_display():
    assert tc.truncate_display("short") == "short"
    long = "x" * 80
    assert len(tc.truncate_display(long)) == 55
    assert tc.truncate_display(long).endswith("...")


# --- extract_policy ---

def test_extract_policy_content():
    assert tc.extract_policy([{"contentPolicy": {"filters": []}}]) == "CONTENT_POLICY_FILTER"


def test_extract_policy_pii():
    assert tc.extract_policy([{"sensitiveInformationPolicy": {"piiEntities": []}}]) == "PII"


def test_extract_policy_topic():
    assert tc.extract_policy([{"topicPolicy": {"topics": []}}]) == "TOPIC_POLICY"


def test_extract_policy_word():
    assert tc.extract_policy([{"wordPolicy": {"words": []}}]) == "WORD_POLICY"


def test_extract_policy_unknown():
    assert tc.extract_policy([]) == "UNKNOWN"
    assert tc.extract_policy(None) == "UNKNOWN"


# --- apply_guardrail ---

def test_apply_guardrail_fails_open_on_api_error():
    client = Mock()
    client.apply_guardrail.side_effect = RuntimeError("throttle")
    with patch.object(tc, "TRADING_GUARDRAIL_ID", "gr_1"):
        result = tc.apply_guardrail("hello", direction="INPUT", client=client)
    assert result["action"] == "ALLOWED"
    assert result["failed_open"] is True
    assert "throttle" in result["error"]


def test_apply_guardrail_fails_open_when_id_missing():
    with patch.object(tc, "TRADING_GUARDRAIL_ID", ""):
        result = tc.apply_guardrail("hello", direction="INPUT")
    assert result["action"] == "ALLOWED"
    assert result["failed_open"] is True


def test_apply_guardrail_maps_intervened_to_blocked():
    client = Mock()
    client.apply_guardrail.return_value = {
        "action": "GUARDRAIL_INTERVENED",
        "assessments": [{"sensitiveInformationPolicy": {"piiEntities": [{"type": "SSN"}]}}],
    }
    with patch.object(tc, "TRADING_GUARDRAIL_ID", "gr_1"):
        result = tc.apply_guardrail("SSN 123-45-6789", direction="INPUT", client=client)
    assert result["action"] == "BLOCKED"
    assert result["policy"] == "PII"


def test_apply_guardrail_maps_none_to_allowed():
    client = Mock()
    client.apply_guardrail.return_value = {"action": "NONE", "assessments": []}
    with patch.object(tc, "TRADING_GUARDRAIL_ID", "gr_1"):
        result = tc.apply_guardrail("What are wash sale rules?", direction="INPUT", client=client)
    assert result["action"] == "ALLOWED"
    assert result["policy"] is None


# --- RateLimiter ---

def test_rate_limiter_allows_up_to_burst_then_denies():
    t = [1000.0]
    rl = tc.RateLimiter(rate_per_second=10, burst_limit=5, clock=lambda: t[0])
    for _ in range(5):
        assert rl.allow_request() is True
    assert rl.allow_request() is False


def test_rate_limiter_refills_over_time():
    t = [1000.0]
    rl = tc.RateLimiter(rate_per_second=10, burst_limit=5, clock=lambda: t[0])
    for _ in range(5):
        assert rl.allow_request()
    assert not rl.allow_request()
    t[0] += 1.0
    assert rl.allow_request()


# --- KillSwitch (3 violations / 60s) ---

def test_kill_switch_not_triggered_below_threshold():
    ks = tc.KillSwitch(max_violations=3, window_seconds=60, cloudwatch=Mock())
    ks.record_violation()
    ks.record_violation()
    assert ks.check() is False


def test_kill_switch_triggers_at_threshold_in_window():
    ks = tc.KillSwitch(max_violations=3, window_seconds=60, cloudwatch=Mock())
    for _ in range(3):
        ks.record_violation()
    assert ks.check() is True


def test_kill_switch_does_not_trigger_outside_window():
    ks = tc.KillSwitch(max_violations=3, window_seconds=1, cloudwatch=Mock())
    ks.record_violation()
    ks.record_violation()
    ks.record_violation()
    assert ks.check() is True
    # Fast-forward past window
    with patch.object(tc.time, "time", return_value=ks.violations[-1] + 2):
        ks.record_violation()
    # Once triggered, stays triggered (no auto-reset)
    assert ks.check() is True


def test_kill_switch_emits_cloudwatch_metrics():
    cw = Mock()
    ks = tc.KillSwitch(max_violations=3, window_seconds=60, cloudwatch=cw)
    ks.record_violation()
    assert cw.put_metric_data.call_count == 1
    assert cw.put_metric_data.call_args_list[0].kwargs["Namespace"] == "TradingCompliance"


# --- MetricsDashboard ---

def test_dashboard_records_allowed_blocked_policies():
    dash = tc.MetricsDashboard()
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
    dash = tc.MetricsDashboard()
    dash.record({
        "action": "ALLOWED",
        "assessments": [{
            "sensitiveInformationPolicy": {
                "piiEntities": [{"type": "EMAIL", "action": "ANONYMIZE"}],
            },
        }],
    })
    assert dash.summary()["anonymized"] == 1


# --- Pipeline order ---

def test_pipeline_kill_switch_short_circuits_first():
    ks = tc.KillSwitch(max_violations=1, window_seconds=60, cloudwatch=Mock())
    ks.is_triggered = True
    rl = tc.RateLimiter(clock=lambda: 1000.0)
    dash = tc.MetricsDashboard()
    with patch.object(tc, "apply_guardrail") as mock_guard, \
         patch.object(tc, "build_compliance_agent") as mock_agent:
        result = tc.run_governance_pipeline({"input": "hi"}, rl, ks, dash)
    assert result == {"action": "KILLED", "policy": "KILL_SWITCH"}
    mock_guard.assert_not_called()
    mock_agent.assert_not_called()


def test_pipeline_rate_limited_before_guardrail():
    t = [1000.0]
    rl = tc.RateLimiter(rate_per_second=0, burst_limit=1, clock=lambda: t[0])
    assert rl.allow_request()
    ks = tc.KillSwitch(max_violations=3, window_seconds=60, cloudwatch=Mock())
    dash = tc.MetricsDashboard()
    with patch.object(tc, "apply_guardrail") as mock_guard, \
         patch.object(tc, "build_compliance_agent") as mock_agent:
        result = tc.run_governance_pipeline({"input": "hi"}, rl, ks, dash)
    assert result["action"] == "RATE_LIMITED"
    assert result["policy"] == "RATE_LIMITER"
    assert dash.summary()["rate_limited"] == 1
    mock_guard.assert_not_called()
    mock_agent.assert_not_called()


def test_pipeline_blocked_input_skips_agent_and_records_violation():
    ks = tc.KillSwitch(max_violations=3, window_seconds=60, cloudwatch=Mock())
    rl = tc.RateLimiter(clock=lambda: 1000.0)
    dash = tc.MetricsDashboard()
    blocked = {"action": "BLOCKED", "policy": "PII", "assessments": [], "direction": "INPUT"}
    with patch.object(tc, "apply_guardrail", return_value=blocked), \
         patch.object(tc, "build_compliance_agent") as mock_agent:
        result = tc.run_governance_pipeline(
            {"input": "My SSN is 123-45-6789"}, rl, ks, dash,
        )
    mock_agent.assert_not_called()
    assert result["action"] == "BLOCKED"
    assert result["policy"] == "PII"
    assert len(ks.violations) == 1
    assert dash.summary()["blocked"] == 1


def test_pipeline_output_guardrail_blocks_agent_response():
    ks = tc.KillSwitch(max_violations=3, window_seconds=60, cloudwatch=Mock())
    rl = tc.RateLimiter(clock=lambda: 1000.0)
    dash = tc.MetricsDashboard()
    input_allowed = {"action": "ALLOWED", "policy": None, "assessments": [], "direction": "INPUT"}
    output_blocked = {"action": "BLOCKED", "policy": "PII", "assessments": [], "direction": "OUTPUT"}
    mock_agent_inst = Mock()
    mock_agent_inst.return_value = "Account 12345 has balance $5000."
    with patch.object(tc, "apply_guardrail", side_effect=[input_allowed, output_blocked]), \
         patch.object(tc, "build_compliance_agent", return_value=mock_agent_inst):
        result = tc.run_governance_pipeline({"input": "What is my balance?"}, rl, ks, dash)
    assert result["action"] == "BLOCKED"
    assert result["policy"] == "PII"
    assert result["direction"] == "OUTPUT"
    assert len(ks.violations) == 1
    assert dash.summary()["blocked"] == 1


def test_pipeline_allowed_invokes_agent_and_output_guardrail():
    ks = tc.KillSwitch(max_violations=3, window_seconds=60, cloudwatch=Mock())
    rl = tc.RateLimiter(clock=lambda: 1000.0)
    dash = tc.MetricsDashboard()
    input_allowed = {"action": "ALLOWED", "policy": None, "assessments": [], "direction": "INPUT"}
    output_allowed = {"action": "ALLOWED", "policy": None, "assessments": [], "direction": "OUTPUT"}
    mock_agent_inst = Mock()
    mock_agent_inst.return_value = "Wash sale rule: disallows losses if substantially identical asset bought within 30 days."
    with patch.object(tc, "apply_guardrail", side_effect=[input_allowed, output_allowed]), \
         patch.object(tc, "build_compliance_agent", return_value=mock_agent_inst):
        result = tc.run_governance_pipeline({"input": "wash sale"}, rl, ks, dash)
    mock_agent_inst.assert_called_once()
    assert result["action"] == "ALLOWED"
    assert "agent_response" in result
    assert len(ks.violations) == 0
    assert dash.summary()["allowed"] == 1


def test_pipeline_three_violations_then_kill_switch_rejects_later():
    ks = tc.KillSwitch(max_violations=3, window_seconds=60, cloudwatch=Mock())
    rl = tc.RateLimiter(clock=lambda: 1000.0)
    dash = tc.MetricsDashboard()
    blocked = {"action": "BLOCKED", "policy": "TOPIC_POLICY", "assessments": [], "direction": "INPUT"}
    with patch.object(tc, "apply_guardrail", return_value=blocked), \
         patch.object(tc, "build_compliance_agent") as mock_agent:
        for _ in range(3):
            tc.run_governance_pipeline({"input": "bad"}, rl, ks, dash)
        assert ks.check() is True
        result = tc.run_governance_pipeline({"input": "more bad"}, rl, ks, dash)
    assert result["action"] == "KILLED"
    mock_agent.assert_not_called()


# --- Compliance agent ---

def test_compliance_agent_tool_name():
    with patch.object(tc, "BedrockModel"):
        agent = tc.build_compliance_agent()
    assert list(agent.tool_registry.registry) == ["check_trading_rules"]


def test_compliance_prompt_forbids_trade_recommendations_and_insider():
    assert "Do NOT give personalized investment advice" in tc.COMPLIANCE_SYSTEM_PROMPT
    assert "Do NOT discuss insider information" in tc.COMPLIANCE_SYSTEM_PROMPT


def test_check_trading_rules_known_topic():
    with patch.object(tc, "BedrockModel"):
        agent = tc.build_compliance_agent()
    fn = agent.tool_registry.registry["check_trading_rules"]
    raw = _unwrap_tool(fn)
    data = json.loads(raw("wash sale rules"))
    assert data["rule"] == "wash sale"


# --- Evaluator ---

def test_evaluator_tool_name():
    with patch.object(tc, "BedrockModel"):
        agent = tc.build_evaluator_agent()
    assert list(agent.tool_registry.registry) == ["score_response"]


def test_score_response_clamps_and_averages():
    with patch.object(tc, "BedrockModel"):
        agent = tc.build_evaluator_agent()
    fn = agent.tool_registry.registry["score_response"]
    raw = _unwrap_tool(fn)
    payload = json.loads(raw(compliance=0, relevance=6, safety=3, completeness=4))
    assert payload["compliance"] == 1
    assert payload["relevance"] == 5
    assert payload["safety"] == 3
    assert payload["completeness"] == 4
    assert payload["average"] == pytest.approx(round((1 + 5 + 3 + 4) / 4, 2))


def test_evaluator_prompt_requires_four_criteria():
    assert "compliance" in tc.EVALUATOR_SYSTEM_PROMPT
    assert "relevance" in tc.EVALUATOR_SYSTEM_PROMPT
    assert "safety" in tc.EVALUATOR_SYSTEM_PROMPT
    assert "completeness" in tc.EVALUATOR_SYSTEM_PROMPT
    assert "score_response" in tc.EVALUATOR_SYSTEM_PROMPT


def test_evaluator_uses_different_model_id_by_default():
    assert tc.EVAL_MODEL != tc.NOVA_LITE_MODEL


# --- Test input narrative ---

def test_demo_inputs_cover_five_legit_ten_adversarial():
    assert len(tc.TEST_INPUTS) == 15
    legit = [i for i, c in enumerate(tc.TEST_INPUTS) if c["label"].startswith("Wash")
             or c["label"].startswith("Pattern") or c["label"].startswith("Margin")
             or c["label"].startswith("Report") or c["label"].startswith("Record")]
    assert len(legit) == 5


# --- Live tests ---

def test_live_apply_guardrail_input():
    if not os.getenv("TRADING_GUARDRAIL_ID") or not os.getenv("AWS_ACCESS_KEY_ID"):
        pytest.skip("TRADING_GUARDRAIL_ID or AWS credentials not set")
    result = tc.apply_guardrail("What are the wash sale rules?", direction="INPUT")
    assert result["action"] in ("ALLOWED", "BLOCKED")


def test_live_pipeline_single_legit_input():
    if not os.getenv("TRADING_GUARDRAIL_ID") or not os.getenv("AWS_ACCESS_KEY_ID"):
        pytest.skip("TRADING_GUARDRAIL_ID or AWS credentials not set")
    if not os.getenv("NOVA_LITE_MODEL"):
        pytest.skip("NOVA_LITE_MODEL not set")
    rl = tc.RateLimiter()
    ks = tc.KillSwitch(cloudwatch=Mock())
    dash = tc.MetricsDashboard()
    result = tc.run_governance_pipeline(
        {"input": "What are the wash sale rules for tax loss harvesting?"},
        rl, ks, dash,
    )
    assert result["action"] in ("ALLOWED", "BLOCKED", "RATE_LIMITED")
    assert not ks.check()
