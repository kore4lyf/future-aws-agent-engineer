"""
telemetry/contract.py
=====================
Single source of truth for the NovaMart telemetry log-line contract.

Both the agent (emitter) and the observability dashboard (consumer) import
from this module. It is deliberately stdlib-only so the standalone
dashboard proxy can import it without pulling in boto3/strands/config.

What is pinned here
-------------------
1. ``AGENT_NODE_FOR_TOOL`` — routing tool -> X-Ray node name. Only the four
   ``route_to_*`` tools open *remote* subsegments named after a worker
   agent. Every other tool (``initialize_session``, ``retrieve_*``,
   ``search_all_policies``, ``retrieve_from_knowledge_base``) opens a local
   subsegment or no node at all, so it is intentionally unmapped. Mapping
   them to invented node names silently drops their buckets downstream.
2. ``NODE_LABELS`` / ``ROLE_ORDER`` — span node -> dashboard display row.
   The three ``KnowledgeBase:*`` spans aggregate into ONE "RAG Agent" row
   (see ``aggregate_spans_for_display``); emitting one row per KB span
   renders the RAG agent three times.
3. ``format_guardrail_line`` — the canonical 5-field line every emitter
   must write. The dashboard parser accepts the legacy 3-field line too,
   but new code must always emit the canonical form.
4. Marker substrings the dashboard's Logs Insights filters match on.

Change rule: edit this file, then mirror the change to the dashboard's
fallback copy (``contract.py`` next to ``server.py``). The parity test
(``tests/test_contract_parity.py``) fails if the two copies diverge.
"""

from __future__ import annotations

import re


__all__ = [
    'SERVICE_NAME',
    'SPANS_LOG_GROUP',
    'AGENT_NODE_FOR_TOOL',
    'NODE_LABELS',
    'ROLE_ORDER',
    'KB_NODE_PREFIX',
    'RAG_AGENT_LABEL',
    'TOOL_CALL_MARKER',
    'TOOL_DONE_MARKER',
    'TRACE_PUBLISHED_MARKER',
    'GUARDRAIL_MARKER',
    'GUARDRAIL_LINE_RE',
    'format_guardrail_line',
    'parse_guardrail_line',
    'aggregate_spans_for_display',
]


SERVICE_NAME = 'NovaMart-Orchestrator'
SPANS_LOG_GROUP = 'aws/spans'

# Routing tool -> remote X-Ray node. Four entries only; see module docstring
# for why initialize_session / retrieve_* are NOT mapped.
AGENT_NODE_FOR_TOOL = {
    'route_to_inventory_agent': 'InventoryAgent',
    'route_to_policy_agent': 'PolicyAgent',
    'route_to_refund_agent': 'RefundAgent',
    'route_to_communication_agent': 'CommunicationAgent',
}

# X-Ray node name -> (dashboard label, role). KnowledgeBase:* nodes share one
# label and are merged by aggregate_spans_for_display, never shown per-KB.
RAG_AGENT_LABEL = 'RAG Agent'
KB_NODE_PREFIX = 'KnowledgeBase:'
NODE_LABELS = {
    'NovaMart-Orchestrator': ('Routing Agent', 'orchestrator'),
    'InventoryAgent': ('Inventory Agent', 'tooling'),
    'RefundAgent': ('Refund Agent', 'transaction'),
    'PolicyAgent': ('Policy Agent', 'support'),
    'CommunicationAgent': ('Communication Agent', 'support'),
    'KnowledgeBase:returns': (RAG_AGENT_LABEL, 'knowledge'),
    'KnowledgeBase:shipping': (RAG_AGENT_LABEL, 'knowledge'),
    'KnowledgeBase:warranty': (RAG_AGENT_LABEL, 'knowledge'),
}

ROLE_ORDER = {
    'orchestrator': 0, 'support': 1, 'knowledge': 2, 'transaction': 3, 'tooling': 4,
}

# Substrings the dashboard's Logs Insights queries filter on. The emitter
# must keep logging lines containing these markers.
TOOL_CALL_MARKER = 'tool call'
TOOL_DONE_MARKER = 'tool done'
TRACE_PUBLISHED_MARKER = 'published to X-Ray'
GUARDRAIL_MARKER = 'GUARDRAIL'

# Matches both the canonical 5-field line and the legacy 3-field line:
#   GUARDRAIL policy=X category=Y action=Z source=W trace=V   (canonical)
#   GUARDRAIL policy=X action=Z trace=V                        (legacy)
GUARDRAIL_LINE_RE = re.compile(
    r'GUARDRAIL\s+policy=(?P<policy>\S+)'
    r'(?:\s+category=(?P<category>\S+))?'
    r'\s+action=(?P<action>\S+)'
    r'(?:\s+source=(?P<source>\S+))?'
    r'(?:\s+trace=(?P<trace>\S+))?'
)


def format_guardrail_line(policy: str, action: str = 'BLOCK',
                           trace_id: str = 'unknown', category: str = 'UNKNOWN',
                           source: str = 'unknown') -> str:
    """Build the canonical 5-field guardrail log line.

    Field order is fixed (policy, category, action, source, trace) so a
    single Insights parse covers every emitter.
    """
    return (
        f'{GUARDRAIL_MARKER} policy={policy or "Unknown"} '
        f'category={category or "UNKNOWN"} action={action or "BLOCK"} '
        f'source={source or "unknown"} trace={trace_id or "unknown"}'
    )


def parse_guardrail_line(line: str) -> dict | None:
    """Parse a guardrail log line of either format. None when no match."""
    if not line or GUARDRAIL_MARKER not in line:
        return None
    match = GUARDRAIL_LINE_RE.search(line)
    if not match:
        return None
    return {
        'policy': match.group('policy'),
        'category': match.group('category') or 'UNKNOWN',
        'action': match.group('action'),
        'source': match.group('source') or 'unknown',
        'trace': match.group('trace') or 'unknown',
    }


def aggregate_spans_for_display(spans: dict) -> list:
    """Fold raw span stats into dashboard rows, merging KB nodes into one.

    ``spans`` maps X-Ray node name -> {'calls', 'avg_ms', 'p95_ms'}.
    Unknown node names are skipped. The three ``KnowledgeBase:*`` nodes
    merge into a single RAG Agent row (call-weighted average, max p95,
    summed calls). Rows sort by role order.
    """
    merged: dict = {}
    for node, stats in spans.items():
        if node not in NODE_LABELS:
            continue
        label, role = NODE_LABELS[node]
        bucket = merged.setdefault(
            label, {'label': label, 'role': role, 'calls': 0,
                    '_weighted': 0.0, '_p95_max': 0.0, 'nodes': []})
        calls = max(0, int(stats.get('calls', 0)))
        bucket['calls'] += calls
        bucket['_weighted'] += float(stats.get('avg_ms', 0)) * calls
        bucket['_p95_max'] = max(bucket['_p95_max'], float(stats.get('p95_ms', 0)))
        bucket['nodes'].append(node)

    rows = []
    for bucket in merged.values():
        calls = bucket['calls'] or 1
        rows.append({
            'name': bucket['label'],
            'node': bucket['nodes'][0] if len(bucket['nodes']) == 1 else bucket['label'],
            'role': bucket['role'],
            'avg_ms': round(bucket['_weighted'] / calls),
            'p95_ms': round(bucket['_p95_max']),
            'invocations': bucket['calls'],
            'errors': 0,
        })
    rows.sort(key=lambda r: ROLE_ORDER.get(r['role'], 9))
    return rows
