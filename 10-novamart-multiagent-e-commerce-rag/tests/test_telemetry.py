"""
tests/test_telemetry.py
=======================
Tests for src/telemetry/guardrails.py.

Validates trace extraction without requiring live AWS calls.
"""

from __future__ import annotations

import sys
import os
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from telemetry.guardrails import (
    clear_invocation_id,
    emit_guardrail_event,
    extract_guardrail_events,
    GuardrailEvent,
    instrument_bedrock_model,
    process_captured_responses,
    set_invocation_id,
)


class TestExtractGuardrailEvents(unittest.TestCase):

    def test_denied_topic_competitor_products(self):
        response = {
            "trace": {
                "guardrail": {
                    "inputAssessment": {
                        "g1": {
                            "topicPolicy": {
                                "topics": [
                                    {
                                        "name": "CompetitorProducts",
                                        "type": "DENY",
                                        "action": "BLOCKED",
                                    }
                                ]
                            }
                        }
                    }
                }
            }
        }
        events = extract_guardrail_events(response)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].policy, "CompetitorProducts")
        self.assertEqual(events[0].category, "DENIED_TOPIC")
        self.assertEqual(events[0].source, "input")

    def test_denied_topic_pricing_negotiations(self):
        response = {
            "trace": {
                "guardrail": {
                    "inputAssessment": {
                        "g1": {
                            "topicPolicy": {
                                "topics": [
                                    {
                                        "name": "PricingNegotiations",
                                        "type": "DENY",
                                        "action": "BLOCKED",
                                    }
                                ]
                            }
                        }
                    }
                }
            }
        }
        events = extract_guardrail_events(response)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].policy, "PricingNegotiations")
        self.assertEqual(events[0].category, "DENIED_TOPIC")

    def test_denied_topic_legal_threats(self):
        response = {
            "trace": {
                "guardrail": {
                    "inputAssessment": {
                        "g1": {
                            "topicPolicy": {
                                "topics": [
                                    {
                                        "name": "LegalThreats",
                                        "type": "DENY",
                                        "action": "BLOCKED",
                                    }
                                ]
                            }
                        }
                    }
                }
            }
        }
        events = extract_guardrail_events(response)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].policy, "LegalThreats")
        self.assertEqual(events[0].category, "DENIED_TOPIC")

    def test_prompt_attack_content_filter(self):
        response = {
            "trace": {
                "guardrail": {
                    "inputAssessment": {
                        "g1": {
                            "contentPolicy": {
                                "filters": [
                                    {
                                        "type": "PROMPT_ATTACK",
                                        "confidence": "HIGH",
                                        "action": "BLOCKED",
                                    }
                                ]
                            }
                        }
                    }
                }
            }
        }
        events = extract_guardrail_events(response)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].policy, "PromptInjection")
        self.assertEqual(events[0].category, "PROMPT_ATTACK")
        self.assertEqual(events[0].confidence, "HIGH")

    def test_allowed_request_no_events(self):
        response = {
            "stopReason": "end_turn",
            "trace": {
                "guardrail": {
                    "inputAssessment": {
                        "g1": {
                            "topicPolicy": {
                                "topics": [
                                    {
                                        "name": "CompetitorProducts",
                                        "type": "DENY",
                                        "action": "NONE",
                                    }
                                ]
                            }
                        }
                    }
                }
            }
        }
        events = extract_guardrail_events(response)
        self.assertEqual(len(events), 0)

    def test_invoke_model_shape(self):
        response = {
            "amazon-bedrock-trace": {
                "guardrail": {
                    "input": {
                        "g1": {
                            "topicPolicy": {
                                "topics": [
                                    {
                                        "name": "CompetitorProducts",
                                        "type": "DENY",
                                        "action": "BLOCKED",
                                    }
                                ]
                            }
                        }
                    }
                }
            }
        }
        events = extract_guardrail_events(response)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].policy, "CompetitorProducts")
        self.assertEqual(events[0].category, "DENIED_TOPIC")

    def test_multiple_triggered_policies(self):
        response = {
            "trace": {
                "guardrail": {
                    "inputAssessment": {
                        "g1": {
                            "topicPolicy": {
                                "topics": [
                                    {
                                        "name": "CompetitorProducts",
                                        "type": "DENY",
                                        "action": "BLOCKED",
                                    },
                                    {
                                        "name": "PricingNegotiations",
                                        "type": "DENY",
                                        "action": "BLOCKED",
                                    },
                                ]
                            },
                            "contentPolicy": {
                                "filters": [
                                    {
                                        "type": "PROMPT_ATTACK",
                                        "confidence": "HIGH",
                                        "action": "BLOCKED",
                                    }
                                ]
                            }
                        }
                    }
                }
            }
        }
        events = extract_guardrail_events(response)
        self.assertEqual(len(events), 3)
        policies = {e.policy for e in events}
        self.assertIn("CompetitorProducts", policies)
        self.assertIn("PricingNegotiations", policies)
        self.assertIn("PromptInjection", policies)

    def test_malformed_trace_does_not_crash(self):
        response = {
            "trace": {
                "guardrail": {
                    "inputAssessment": {
                        "g1": {
                            "topicPolicy": {
                                "topics": [
                                    {
                                        "action": "BLOCKED",
                                    }
                                ]
                            }
                        }
                    }
                }
            }
        }
        events = extract_guardrail_events(response)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].policy, "Unknown")
        self.assertEqual(events[0].category, "DENIED_TOPIC")

    def test_output_assessment(self):
        response = {
            "trace": {
                "guardrail": {
                    "outputAssessments": {
                        "g1": {
                            "topicPolicy": {
                                "topics": [
                                    {
                                        "name": "LegalThreats",
                                        "type": "DENY",
                                        "action": "BLOCKED",
                                    }
                                ]
                            }
                        }
                    }
                }
            }
        }
        events = extract_guardrail_events(response)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].policy, "LegalThreats")
        self.assertEqual(events[0].source, "output")

    def test_custom_word_blocked(self):
        response = {
            "trace": {
                "guardrail": {
                    "inputAssessment": {
                        "g1": {
                            "wordPolicy": {
                                "customWords": [
                                    {
                                        "match": "forbidden-term",
                                        "action": "BLOCKED",
                                    }
                                ]
                            }
                        }
                    }
                }
            }
        }
        events = extract_guardrail_events(response)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].policy, "forbidden-term")
        self.assertEqual(events[0].category, "CUSTOM_WORD")

    def test_pii_blocked(self):
        response = {
            "trace": {
                "guardrail": {
                    "inputAssessment": {
                        "g1": {
                            "sensitiveInformationPolicy": {
                                "piiEntities": [
                                    {
                                        "type": "CREDIT_DEBIT_CARD_NUMBER",
                                        "action": "BLOCKED",
                                    }
                                ]
                            }
                        }
                    }
                }
            }
        }
        events = extract_guardrail_events(response)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].policy, "CREDIT_DEBIT_CARD_NUMBER")
        self.assertEqual(events[0].category, "PII")


class TestStreamingCapture(unittest.TestCase):
    """Strands reads the guardrail trace from converse_stream chunks.

    Regression test: the old wrapper captured the initial stream response
    (which carries no trace), so every streamed intervention fell through
    to the 'Unknown' fallback line on the dashboard. These tests consume a
    fake stream exactly the way strands/models/bedrock.py does and require
    the real policy name to come out.
    """

    TRACE_CHUNK = {
        "metadata": {
            "trace": {
                "guardrail": {
                    "inputAssessment": {
                        "g1": {
                            "topicPolicy": {
                                "topics": [{
                                    "name": "PricingNegotiations",
                                    "type": "DENY",
                                    "action": "BLOCKED",
                                }]
                            }
                        }
                    }
                }
            }
        }
    }

    def _instrumented(self, chunks):
        closed = []

        class FakeStream:
            def __init__(self):
                self._chunks = list(chunks)

            def __iter__(self):
                return iter(self._chunks)

            def close(self):
                closed.append(True)

        class FakeClient:
            def converse_stream(self, **kwargs):
                return {"stream": FakeStream(), "ResponseMetadata": {}}

        class FakeModel:
            def __init__(self):
                self.client = FakeClient()

        model = FakeModel()
        instrument_bedrock_model(model)
        return model, closed

    def test_streamed_block_yields_real_policy(self):
        model, _ = self._instrumented([
            {"contentBlockDelta": {"text": "partial"}},
            dict(self.TRACE_CHUNK),
            {"messageStop": {"stopReason": "guardrail_intervened"}},
        ])
        set_invocation_id("test-stream-1")
        try:
            # Consume exactly like Strands does: plain for-loop over
            # response["stream".
            response = model.client.converse_stream(modelId="m", messages=[])
            seen = [c for c in response["stream"]]
            self.assertEqual(len(seen), 3)
            self.assertIn("metadata", seen[1])  # chunks pass through untouched
            events = process_captured_responses("test-stream-1")
        finally:
            clear_invocation_id()
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].policy, "PricingNegotiations")
        self.assertEqual(events[0].category, "DENIED_TOPIC")
        self.assertEqual(events[0].source, "input")

    def test_repeated_trace_chunks_count_once(self):
        model, _ = self._instrumented([
            dict(self.TRACE_CHUNK),
            dict(self.TRACE_CHUNK),
        ])
        set_invocation_id("test-stream-2")
        try:
            response = model.client.converse_stream(modelId="m", messages=[])
            for _ in response["stream"]:
                pass
            events = process_captured_responses("test-stream-2")
        finally:
            clear_invocation_id()
        self.assertEqual(len(events), 1)

    def test_close_proxies_to_inner_stream(self):
        model, closed = self._instrumented([{"messageStop": {"stopReason": "end_turn"}}])
        response = model.client.converse_stream(modelId="m", messages=[])
        response["stream"].close()
        self.assertEqual(closed, [True])

    def test_clean_stream_captures_nothing(self):
        model, _ = self._instrumented([
            {"contentBlockDelta": {"text": "hello"}},
            {"messageStop": {"stopReason": "end_turn"}},
        ])
        set_invocation_id("test-stream-3")
        try:
            response = model.client.converse_stream(modelId="m", messages=[])
            for _ in response["stream"]:
                pass
            events = process_captured_responses("test-stream-3")
        finally:
            clear_invocation_id()
        self.assertEqual(events, [])


class TestEmitHierarchy(unittest.TestCase):
    """Named guardrail events must ship from the AgentCore Runtime.

    Regression: emit_guardrail_event logged on `telemetry.guardrails`,
    whose level inherits root (WARNING on the runtime), so named events
    were silently dropped there while local runs worked. Emission must
    travel on the `novamart` hierarchy that setup_logging() ships.
    """

    def test_emit_survives_warning_root(self):
        import logging

        root = logging.getLogger()
        previous_level = root.level
        root.setLevel(logging.WARNING)
        try:
            with self.assertLogs("novamart.observability", level="INFO") as captured:
                emit_guardrail_event(GuardrailEvent(
                    policy="PricingNegotiations", category="DENIED_TOPIC",
                    action="BLOCK", source="input", trace_id="t-1",
                ))
        finally:
            root.setLevel(previous_level)
        self.assertEqual(len(captured.records), 1)
        message = captured.records[0].getMessage()
        self.assertIn("GUARDRAIL policy=PricingNegotiations", message)
        self.assertNotIn("Unknown", message)


if __name__ == "__main__":
    unittest.main()
