"""
telemetry/guardrails.py
=======================
Bedrock guardrail trace extraction and centralized telemetry.

Wraps each agent's bedrock-runtime client to capture raw Converse /
ConverseStream responses, then normalizes the guardrail assessment into
application-level events emitted once per top-level invocation.
"""

from __future__ import annotations

import contextvars
import logging
import threading
from dataclasses import dataclass
from typing import Any

from agent_observability import tracer
from telemetry.contract import format_guardrail_line


__all__ = [
    "GuardrailEvent",
    "set_invocation_id",
    "clear_invocation_id",
    "capture_response",
    "get_and_clear_responses",
    "extract_guardrail_events",
    "emit_guardrail_event",
    "process_captured_responses",
    "instrument_bedrock_model",
    "install_agent_hooks",
]


logger = logging.getLogger(__name__)

# Guardrail telemetry must travel on the `novamart` logger hierarchy:
# setup_logging() attaches the CloudWatch handler (and the INFO level) to
# `novamart`, while the root logger on AgentCore Runtime sits at WARNING.
# Emitting here (instead of `telemetry.guardrails`) is what makes the line
# shippable. Regression: named events were silently dropped on the runtime
# while local runs (root at INFO) worked fine.
telemetry_logger = logging.getLogger('novamart.observability')

# ---------------------------------------------------------------------------
# Invocation tracking
# ---------------------------------------------------------------------------

_invocation_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "guardrail_invocation_id", default=None
)

_response_store: dict[str, list[dict[str, Any]]] = {}
_store_lock = threading.Lock()


def set_invocation_id(invocation_id: str) -> None:
    _invocation_id_var.set(invocation_id)


def clear_invocation_id() -> None:
    _invocation_id_var.set(None)


def capture_response(response: dict[str, Any]) -> None:
    invocation_id = _invocation_id_var.get(None)
    if invocation_id is None:
        return
    with _store_lock:
        _response_store.setdefault(invocation_id, []).append(response)


def get_and_clear_responses(invocation_id: str) -> list[dict[str, Any]]:
    with _store_lock:
        return _response_store.pop(invocation_id, [])


# ---------------------------------------------------------------------------
# Event model
# ---------------------------------------------------------------------------

@dataclass
class GuardrailEvent:
    policy: str
    category: str
    action: str = "BLOCK"
    source: str = "input"
    confidence: str | None = None
    trace_id: str | None = None


# ---------------------------------------------------------------------------
# Trace extraction
# ---------------------------------------------------------------------------

def _extract_from_assessment(
    assessment: dict[str, Any] | list[Any], source: str
) -> list[GuardrailEvent]:
    """Normalize one guardrail assessment (dict or list) into events."""
    events: list[GuardrailEvent] = []

    if isinstance(assessment, list):
        for item in assessment:
            events.extend(_extract_from_assessment(item, source=source))
        return events

    if not isinstance(assessment, dict):
        return events

    for topic in assessment.get("topicPolicy", {}).get("topics", []):
        if topic.get("action") == "BLOCKED":
            events.append(
                GuardrailEvent(
                    policy=topic.get("name", "Unknown"),
                    category="DENIED_TOPIC",
                    source=source,
                )
            )

    for filt in assessment.get("contentPolicy", {}).get("filters", []):
        if filt.get("action") == "BLOCKED":
            filter_type = filt.get("type", "Unknown")
            policy = "PromptInjection" if filter_type == "PROMPT_ATTACK" else filter_type
            events.append(
                GuardrailEvent(
                    policy=policy,
                    category=filter_type,
                    source=source,
                    confidence=filt.get("confidence"),
                )
            )

    for word in assessment.get("wordPolicy", {}).get("customWords", []):
        if word.get("action") == "BLOCKED":
            events.append(
                GuardrailEvent(
                    policy=word.get("match", "Unknown"),
                    category="CUSTOM_WORD",
                    source=source,
                )
            )

    for pii in assessment.get("sensitiveInformationPolicy", {}).get("piiEntities", []):
        if pii.get("action") == "BLOCKED":
            events.append(
                GuardrailEvent(
                    policy=pii.get("type", "Unknown"),
                    category="PII",
                    source=source,
                )
            )

    return events


def extract_guardrail_events(response: dict[str, Any]) -> list[GuardrailEvent]:
    events: list[GuardrailEvent] = []

    trace = response.get("trace", {}).get("guardrail")
    if not trace:
        trace = response.get("amazon-bedrock-trace", {}).get("guardrail")
    if not trace:
        return events

    input_assessments = trace.get("inputAssessment", {})
    if not input_assessments:
        input_assessments = trace.get("input", {})
    if isinstance(input_assessments, dict):
        for assessment in input_assessments.values():
            events.extend(_extract_from_assessment(assessment, source="input"))
    elif isinstance(input_assessments, list):
        for assessment in input_assessments:
            events.extend(_extract_from_assessment(assessment, source="input"))

    output_assessments = trace.get("outputAssessments", {})
    if not output_assessments:
        output_assessments = trace.get("outputs", {})
    if isinstance(output_assessments, dict):
        for assessment in output_assessments.values():
            events.extend(_extract_from_assessment(assessment, source="output"))
    elif isinstance(output_assessments, list):
        for assessment in output_assessments:
            events.extend(_extract_from_assessment(assessment, source="output"))

    return events


# ---------------------------------------------------------------------------
# Telemetry emission
# ---------------------------------------------------------------------------

def emit_guardrail_event(event: GuardrailEvent) -> None:
    trace_id = tracer.last_trace_id or event.trace_id
    telemetry_logger.info(
        format_guardrail_line(
            policy=event.policy,
            action=event.action,
            trace_id=trace_id or "unknown",
            category=event.category,
            source=event.source,
        )
    )


def process_captured_responses(invocation_id: str) -> list[GuardrailEvent]:
    responses = get_and_clear_responses(invocation_id)
    all_events: list[GuardrailEvent] = []
    for response in responses:
        for event in extract_guardrail_events(response):
            emit_guardrail_event(event)
            all_events.append(event)
    return all_events


# ---------------------------------------------------------------------------
# Bedrock client instrumentation
# ---------------------------------------------------------------------------

def instrument_bedrock_model(model: Any) -> None:
    client = getattr(model, "client", None)
    if client is None:
        return

    original_converse = getattr(client, "converse", None)
    original_converse_stream = getattr(client, "converse_stream", None)

    if original_converse is None and original_converse_stream is None:
        return

    def _wrap_converse(method):
        def wrapper(**kwargs):
            response = method(**kwargs)
            try:
                capture_response(response)
            except Exception:  # noqa: BLE001
                pass
            return response
        return wrapper

    def _wrap_converse_stream(method):
        def wrapper(**kwargs):
            response = method(**kwargs)
            try:
                stream = response.get("stream") if isinstance(response, dict) else None
                if stream is not None:
                    # Strands consumes the trace from stream chunks; the
                    # initial response carries none. Snoop the chunks as they
                    # flow so guardrail assessments reach capture_response.
                    response["stream"] = _TraceSnoopingStream(stream)
                else:
                    capture_response(response)
            except Exception:  # noqa: BLE001
                pass
            return response
        return wrapper

    if original_converse is not None:
        try:
            client.converse = _wrap_converse(original_converse)
        except Exception:  # noqa: BLE001
            pass

    if original_converse_stream is not None:
        try:
            client.converse_stream = _wrap_converse_stream(original_converse_stream)
        except Exception:  # noqa: BLE001
            pass


class _TraceSnoopingStream:
    """Pass-through wrapper that harvests guardrail trace chunks.

    Strands iterates ``response["stream"]`` with a plain ``for`` loop (and
    calls ``.close()`` only on cancellation), so a generator-backed proxy is
    fully compatible. Chunks are yielded untouched; the first chunk carrying
    ``metadata.trace.guardrail`` is stashed via ``capture_response`` in the
    shape ``extract_guardrail_events`` already understands. Only the first
    such chunk per stream is kept so one intervention is never double
    counted across repeated metadata frames.
    """

    def __init__(self, inner: Any) -> None:
        self._inner = inner
        self._snooped = False

    def __iter__(self):
        for chunk in self._inner:
            if not self._snooped and isinstance(chunk, dict) and "metadata" in chunk:
                try:
                    metadata = chunk.get("metadata") or {}
                    trace = (metadata.get("trace") or {}).get("guardrail")
                    if trace is not None:
                        self._snooped = True
                        capture_response({"trace": {"guardrail": trace}})
                except Exception:  # noqa: BLE001
                    pass
            yield chunk

    def close(self) -> None:
        close = getattr(self._inner, "close", None)
        if callable(close):
            close()


# ---------------------------------------------------------------------------
# Strands hook installation
# ---------------------------------------------------------------------------

def install_agent_hooks(agent: Any) -> None:
    try:
        from strands.hooks.events import AfterModelCallEvent

        def _on_after_model_call(event: Any) -> None:
            stop_response = getattr(event, "stop_response", None)
            if stop_response is None:
                return
            stop_reason = getattr(stop_response, "stop_reason", None)
            if stop_reason == "guardrail_intervened":
                logger.debug(
                    "Guardrail intervened for agent model call (trace=%s)",
                    tracer.last_trace_id,
                )

        agent.add_hook(_on_after_model_call, AfterModelCallEvent)
    except Exception:  # noqa: BLE001
        pass
