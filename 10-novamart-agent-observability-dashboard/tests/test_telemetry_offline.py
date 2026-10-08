"""
Offline tests for the dashboard payload logic (no AWS credentials needed).

Unlike test_dashboard.py (live integration, requires real CloudWatch data),
these feed fake source reports into telemetry._build_agents and friends, so
they run anywhere — including CI — and pin the behaviors the refactor
fixed: single RAG row, unmapped tools dropped, guardrail query shape.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path


DASHBOARD_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(DASHBOARD_DIR))

import aws_sources  # noqa: E402
import telemetry  # noqa: E402
from contract import parse_guardrail_line  # noqa: E402


def _ok(data: dict) -> dict:
    return {"status": "ok", "data": data, "note": ""}


class TestBuildAgentsOffline(unittest.TestCase):
    def test_kb_spans_yield_single_rag_row(self):
        span_report = _ok({"spans": {
            "KnowledgeBase:returns": {"calls": 4, "avg_ms": 200, "p95_ms": 300},
            "KnowledgeBase:shipping": {"calls": 2, "avg_ms": 400, "p95_ms": 500},
            "KnowledgeBase:warranty": {"calls": 2, "avg_ms": 100, "p95_ms": 150},
            "InventoryAgent": {"calls": 8, "avg_ms": 120, "p95_ms": 200},
        }})
        rows, source = telemetry._build_agents(
            span_report, {"status": "empty", "data": {}, "note": ""},
            {"status": "empty", "data": {}, "note": ""},
        )
        self.assertIn("subsegments", source)
        rag_rows = [r for r in rows if r["name"] == "RAG Agent"]
        self.assertEqual(len(rag_rows), 1, f"expected one RAG row, got: {rows}")
        self.assertEqual(rag_rows[0]["invocations"], 8)

    def test_spans_win_over_tool_latency(self):
        span_report = _ok({"spans": {
            "PolicyAgent": {"calls": 5, "avg_ms": 300, "p95_ms": 450},
        }})
        log_report = _ok({"tool_latency": {
            "route_to_policy_agent": {"calls": 5, "avg_ms": 999, "p95_ms": 999},
        }})
        rows, source = telemetry._build_agents(
            span_report, log_report,
            {"status": "empty", "data": {}, "note": ""},
        )
        self.assertIn("subsegments", source)
        self.assertEqual(rows[0]["avg_ms"], 300)  # span value, not tool value

    def test_tool_fallback_drops_unmapped_tools(self):
        log_report = _ok({"tool_latency": {
            "route_to_refund_agent": {"calls": 3, "avg_ms": 250, "p95_ms": 400},
            # Real tools with no node mapping must not invent rows:
            "initialize_session": {"calls": 10, "avg_ms": 50, "p95_ms": 80},
            "retrieve_returns_policy": {"calls": 7, "avg_ms": 600, "p95_ms": 900},
            "search_all_policies": {"calls": 4, "avg_ms": 700, "p95_ms": 800},
        }})
        rows, source = telemetry._build_agents(
            {"status": "empty", "data": {}, "note": ""}, log_report,
            {"status": "empty", "data": {}, "note": ""},
        )
        self.assertIn("tool timings", source)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["name"], "Refund Agent")

    def test_metrics_fallback_single_runtime_row(self):
        metrics = _ok({"latency": [("t1", 100.0), ("t2", 200.0)], "resolved_metrics": {}})
        rows, source = telemetry._build_agents(
            {"status": "empty", "data": {}, "note": ""},
            {"status": "empty", "data": {}, "note": ""}, metrics,
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["name"], "AgentCore Runtime")
        self.assertEqual(rows[0]["avg_ms"], 150)

    def test_error_attribution_sums_to_total(self):
        agents = [
            {"name": "A", "invocations": 70, "errors": 0},
            {"name": "B", "invocations": 30, "errors": 0},
        ]
        telemetry._attribute_errors(agents, 10)
        self.assertEqual(sum(a["errors"] for a in agents), 10)

    def test_guardrail_rows_sorted_by_count(self):
        rows, available, _ = telemetry._build_guardrails(
            _ok({"guardrails": {"X": 2, "Y": 9}}))
        self.assertTrue(available)
        self.assertEqual([r["name"] for r in rows], ["Y", "X"])

    def test_unknown_counted_not_dropped(self):
        # Every violation stays visible: unattributed lines count too.
        rows, available, _ = telemetry._build_guardrails(
            _ok({"guardrails": {"Unknown": 11, "LegalThreats": 3}}))
        self.assertTrue(available)
        self.assertEqual([(r["name"], r["count"]) for r in rows],
                         [("Unknown", 11), ("LegalThreats", 3)])
        total = sum(r["count"] for r in rows)
        self.assertEqual(total, 14)

    def test_recent_guardrails_parse_to_lookup_entries(self):
        rows = [
            {"timestamp": "2026-10-08 13:19:34.793",
             "message": "2026-10-08 INFO novamart.observability GUARDRAIL policy=LegalThreats category=DENIED_TOPIC action=BLOCK source=input trace=1-abc"},
            {"timestamp": "", "message": "not a guardrail line"},
        ]
        log_report = {"status": "ok", "data": {"guardrail_recent": rows}, "note": ""}
        recent = telemetry._build_recent_guardrails(log_report)
        self.assertEqual(len(recent), 2)
        self.assertEqual(recent[0]["policy"], "LegalThreats")
        self.assertEqual(recent[0]["trace"], "1-abc")
        # Unparseable lines are kept, never dropped.
        self.assertEqual(recent[1]["policy"], "Unparsed")

    def test_recent_guardrails_empty_when_source_down(self):
        recent = telemetry._build_recent_guardrails(
            {"status": "unavailable", "data": {}, "note": ""})
        self.assertEqual(recent, [])


class TestGuardrailQueryShape(unittest.TestCase):
    def test_query_extracts_policy_and_action_independently(self):
        query = aws_sources._QUERY_GUARDRAILS
        # Both lines must survive this query: the canonical 5-field line
        # (category sits between policy and action) and the legacy 3-field
        # line. A single combined pattern would drop the canonical form.
        self.assertIn("policy=(?<policy>", query)
        self.assertIn("action=(?<action>", query)
        self.assertNotIn("policy=(?<policy>[^ ]+) action=", query)

    def test_sample_lines_parse(self):
        canonical = (
            "GUARDRAIL policy=CompetitorBlock category=DENIED_TOPIC "
            "action=BLOCK source=input trace=1-abc"
        )
        legacy = "GUARDRAIL policy=Unknown action=BLOCK trace=abc123"
        for line in (canonical, legacy):
            parsed = parse_guardrail_line(line)
            self.assertIsNotNone(parsed, f"failed to parse: {line}")
            self.assertTrue(parsed["policy"])
            self.assertEqual(parsed["action"], "BLOCK")


class _FakePaginator:
    def __init__(self, pages):
        self.pages = pages
        self.calls = []

    def paginate(self, **kwargs):
        self.calls.append(kwargs)
        return self.pages


class _FakeCloudWatch:
    def __init__(self, pages):
        self._paginator = _FakePaginator(pages)

    def get_paginator(self, name):
        assert name == "get_metric_data", name
        return self._paginator


class TestMetricSeriesRequest(unittest.TestCase):
    """The get_metric_data shape: Namespace/MetricName nest inside
    MetricStat.Metric, Start/End ride top-level. The old flat shape raised
    ParamValidationError (a BotoCoreError, so it was swallowed into `empty`).
    """

    def test_request_shape_and_id_sanitized(self):
        from datetime import datetime, timezone

        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        end = datetime(2026, 1, 2, tzinfo=timezone.utc)
        pages = [{"MetricDataResults": [
            {"Timestamps": [start], "Values": [3.0]},
        ]}]
        cloudwatch = _FakeCloudWatch(pages)
        series = aws_sources._get_metric_series(
            cloudwatch, "CPUUsed-vCPUHours", "AWS/Bedrock-AgentCore",
            start, end, "Sum",
            [{"Name": "Resource", "Value": "arn:example"}],
        )
        self.assertEqual(series, [(start, 3.0)])
        (call,) = cloudwatch._paginator.calls
        (query,) = call["MetricDataQueries"]
        # No hyphenated Id, no flat Namespace/MetricName/Stat/Period.
        self.assertNotIn("-", query["Id"])
        self.assertTrue(query["Id"][0].isalpha() and query["Id"][0].islower())
        self.assertNotIn("Namespace", query)
        self.assertNotIn("StartTime", query)
        metric = query["MetricStat"]["Metric"]
        self.assertEqual(metric["Namespace"], "AWS/Bedrock-AgentCore")
        self.assertEqual(metric["MetricName"], "CPUUsed-vCPUHours")
        self.assertEqual(
            metric["Dimensions"], [{"Name": "Resource", "Value": "arn:example"}])
        self.assertEqual(query["MetricStat"]["Stat"], "Sum")
        self.assertEqual(call["StartTime"], start)
        self.assertEqual(call["EndTime"], end)

    def test_query_id_edge_cases(self):
        self.assertEqual(aws_sources._metric_query_id("Invocations"), "invocations")
        self.assertNotIn("-", aws_sources._metric_query_id("CPUUsed-vCPUHours"))
        self.assertTrue(aws_sources._metric_query_id("9lives").startswith("m_"))


if __name__ == "__main__":
    unittest.main()
