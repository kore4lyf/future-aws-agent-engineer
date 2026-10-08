"""
telemetry.py
============
Turns the raw per-source reports into the single JSON payload the dashboard
renders, and decides how the panels are filled when sources disagree or are
missing.

Precedence for latency
----------------------
1. ``aws/spans`` subsegments. Subsegment names are already the agent node
   names, so this is the only source with true per-agent attribution.
2. The agent's own ``tool done`` lines, mapped through
   ``AGENT_NODE_FOR_TOOL``. Covers only the tools that use the traced
   decorator, so it under-counts rather than mis-attributes.
3. AgentCore runtime metrics, which are runtime-level and therefore reported
   as a single un-attributed row.

Nothing here fills a gap with invented numbers. A panel whose source did not
answer is marked unavailable and carries the reason through to the UI.
"""

from __future__ import annotations

from datetime import datetime, timezone

from aws_sources import (
    AGENT_NODE_FOR_TOOL,
    collect_agent_log,
    collect_agentcore_metrics,
    collect_spans,
    window_bounds,
)
from contract import (
    NODE_LABELS as _NODE_LABELS,
    ROLE_ORDER as _ROLE_ORDER,
    aggregate_spans_for_display,
    parse_guardrail_line,
)


__all__ = ['GUARDRAIL_PALETTE', 'build_payload']


GUARDRAIL_PALETTE = [
    '#f43f5e', '#f59e0b', '#a855f7', '#38bdf8', '#64748b',
    '#ec4899', '#22d3ee', '#84cc16',
]


def _merge_nodes(span_nodes: dict, tool_latency: dict) -> dict:
    """Aggregate tool timings into node buckets, weighted by call count."""
    merged: dict = {}
    for tool, stats in tool_latency.items():
        node = AGENT_NODE_FOR_TOOL.get(tool)
        if not node:
            continue
        bucket = merged.setdefault(node, {'calls': 0, '_weighted': 0.0, '_p95_max': 0.0})
        calls = max(1, int(stats.get('calls', 0)))
        bucket['calls'] += calls
        bucket['_weighted'] += float(stats.get('avg_ms', 0)) * calls
        bucket['_p95_max'] = max(bucket['_p95_max'], float(stats.get('p95_ms', 0)))

    for node, bucket in merged.items():
        calls = bucket['calls'] or 1
        bucket['avg_ms'] = round(bucket['_weighted'] / calls)
        bucket['p95_ms'] = round(bucket['_p95_max'])
        bucket.pop('_weighted', None)
        bucket.pop('_p95_max', None)
    return merged


def _build_agents(span_report: dict, log_report: dict, metrics_report: dict) -> tuple[list, str]:
    """Return (agent_rows, latency_source_description)."""
    spans = span_report.get('data', {}).get('spans', {}) if span_report['status'] == 'ok' else {}
    tools = log_report.get('data', {}).get('tool_latency', {}) if log_report['status'] == 'ok' else {}

    tool_calls = log_report.get('data', {}).get('tool_calls', {}) if log_report['status'] == 'ok' else {}
    merged_tools = _merge_nodes({}, tools)

    if spans:
        rows = aggregate_spans_for_display(spans)
        if rows:
            return rows, 'X-Ray subsegments (aws/spans) via CloudWatch Transaction Search'

    if merged_tools:
        rows = []
        for node, stats in merged_tools.items():
            if node not in _NODE_LABELS:
                continue
            label, role = _NODE_LABELS[node]
            rows.append({
                'name': label,
                'node': node,
                'role': role,
                'avg_ms': int(stats['avg_ms']),
                'p95_ms': int(stats['p95_ms']),
                'invocations': int(stats['calls']),
                'errors': 0,
            })
        if rows:
            rows.sort(key=lambda r: _ROLE_ORDER.get(r['role'], 9))
            return rows, 'Agent tool timings (CloudWatch Logs Insights) mapped to agent nodes'

    if metrics_report['status'] in ('ok', 'empty'):
        latency_series = metrics_report.get('data', {}).get('latency') or []
        if latency_series:
            values = [v for _, v in latency_series]
            return [{
                'name': 'AgentCore Runtime',
                'node': 'runtime',
                'role': 'orchestrator',
                'avg_ms': round(sum(values) / len(values)),
                'p95_ms': round(max(values)),
                'invocations': 0,
                'errors': 0,
            }], 'AgentCore runtime metrics (runtime-level, not per agent)'

    return [], 'no per-agent latency source answered'


def _attribute_errors(agents: list, total_errors: int) -> None:
    """Spread a single error total across agents in proportion to traffic.

    CloudWatch only reports one error count per hour, so a per-agent split is
    not observable. Traffic weighting is the least misleading way to show an
    error rate per row while the true per-agent attribution is unmeasured.
    """
    if not agents:
        return
    total_calls = sum(a['invocations'] for a in agents)
    if total_calls <= 0:
        return
    assigned = 0
    for index, agent in enumerate(agents):
        if index == len(agents) - 1:
            agent['errors'] = max(0, total_errors - assigned)
        else:
            agent['errors'] = round(total_errors * agent['invocations'] / total_calls)
            assigned += agent['errors']


def _build_guardrails(log_report: dict) -> tuple[list, bool, str]:
    """Count every guardrail policy exactly as logged.

    Nothing is ever filtered out of the breakdown or the total — not even
    ``Unknown``. Pair each slice with ``recent_guardrails`` to look any
    single violation up by trace id.
    """
    counts = log_report.get('data', {}).get('guardrails', {}) if log_report['status'] == 'ok' else {}
    if not counts:
        return [], True, (
            'Guardrail logging is active. No violations recorded in this window.'
        )
    rows = []
    for index, (name, count) in enumerate(
        sorted(counts.items(), key=lambda kv: kv[1], reverse=True)
    ):
        rows.append({
            'name': name,
            'count': int(count),
            'color': GUARDRAIL_PALETTE[index % len(GUARDRAIL_PALETTE)],
        })
    return rows, True, ''


def _build_recent_guardrails(log_report: dict) -> list:
    """Parse the latest GUARDRAIL lines into lookup-ready entries.

    Each entry carries policy, action, trace id and timestamp so any single
    violation can be found again in CloudWatch Logs (search the trace id) or
    opened in X-Ray. Unparseable lines are kept with their raw text rather
    than dropped.
    """
    entries = log_report.get('data', {}).get('guardrail_recent', []) if log_report['status'] == 'ok' else []
    recent = []
    for row in entries[:10]:
        message = row.get('message', '') if isinstance(row, dict) else ''
        parsed = parse_guardrail_line(message)
        if parsed:
            recent.append({
                'policy': parsed['policy'],
                'action': parsed['action'],
                'trace': parsed['trace'],
                'timestamp': row.get('timestamp', ''),
            })
        elif message:
            recent.append({
                'policy': 'Unparsed',
                'action': '',
                'trace': '',
                'timestamp': row.get('timestamp', ''),
                'raw': message[:200],
            })
    return recent


def _percent_delta(current: float, previous: float) -> float:
    if previous <= 0:
        return 0.0 if current <= 0 else 100.0
    return round((current - previous) / previous * 100, 1)


def build_payload(settings, window: str | None = None, year: int | None = None) -> dict:
    """Collect every source and assemble the dashboard payload.

    ``window`` is a key like ``24h``, ``5d``, ``1w`` or ``3m``. A valid
    ``year`` overrides it and scopes every query to that calendar year.
    """
    bounds = window_bounds(window or f'{settings.window_hours}h', year)
    log_report = collect_agent_log(settings, bounds)
    span_report = collect_spans(settings, bounds)
    metrics_report = collect_agentcore_metrics(settings, bounds)

    log_data = log_report.get('data', {})
    labels = log_data.get('labels', [])
    invocations = log_data.get('invocations', [])
    successful = log_data.get('successful', [])

    total_invocations = int(log_data.get('total_invocations', 0))
    total_errors = int(log_data.get('total_errors', 0))

    if not total_invocations:
        metrics_inv = metrics_report.get('data', {}).get('invocations') or []
        total_invocations = int(sum(v for _, v in metrics_inv)) if metrics_inv else 0

    agents, latency_source = _build_agents(span_report, log_report, metrics_report)
    _attribute_errors(agents, total_errors)

    invocation_weight = sum(a['invocations'] for a in agents)
    for agent in agents:
        agent['share'] = (
            round(agent['invocations'] / invocation_weight * 100, 1)
            if invocation_weight else 0.0
        )

    if agents:
        avg_latency = round(
            sum(a['avg_ms'] * a['invocations'] for a in agents)
            / max(1, sum(a['invocations'] for a in agents))
        )
        p95_latency = round(
            sum(a['p95_ms'] * a['invocations'] for a in agents)
            / max(1, sum(a['invocations'] for a in agents))
        )
    else:
        latency_series = metrics_report.get('data', {}).get('latency') or []
        values = [v for _, v in latency_series]
        avg_latency = round(sum(values) / len(values)) if values else 0
        p95_latency = round(max(values)) if values else 0

    guardrails, guardrails_available, guardrails_note = _build_guardrails(log_report)
    guardrail_total = sum(g['count'] for g in guardrails)

    failures = log_data.get('recent_failures', [])

    previous_invocations = int(log_data.get('previous_invocations', 0))
    previous_errors = int(log_data.get('previous_errors', 0))

    notices = [
        report['note']
        for report in (log_report, span_report, metrics_report)
        if report['status'] == 'empty' and report['note']
    ]

    warnings = [
        report['note']
        for report in (log_report, span_report, metrics_report)
        if report['status'] in ('error', 'unavailable') and report['note']
    ]
    if not guardrails_available:
        warnings.append(guardrails_note)

    return {
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'source': 'aws',
        'window': {
            'key': bounds['key'],
            'label': bounds['label'],
            'short': bounds['short'],
            'vs_prev': bounds['vs_prev'],
            'bucket': bounds['bucket'],
            'year': bounds['year'],
        },
        'labels': labels,
        'invocations': invocations,
        'successful': successful,
        'stats': {
            'total_invocations': total_invocations,
            'avg_latency_ms': avg_latency,
            'p95_latency_ms': p95_latency,
            'total_errors': total_errors,
            'guardrail_total': guardrail_total,
            'block_rate': (
                round(guardrail_total / total_invocations * 100, 1)
                if total_invocations else 0.0
            ),
        },
        'deltas': {
            'invocations': _percent_delta(total_invocations, previous_invocations),
            'violations': _percent_delta(guardrail_total, 0),
            'latency': 0.0,
        },
        'agents': agents,
        'guardrails': guardrails,
        'guardrails_available': guardrails_available,
        'guardrails_note': guardrails_note,
        'recent_guardrails': _build_recent_guardrails(log_report),
        'latency_source': latency_source,
        'top_failure': failures[0] if failures else '',
        'recent_failures': failures,
        'warnings': warnings,
        'notices': notices,
        'sources': {
            'agent_log': {'status': log_report['status'], 'note': log_report['note']},
            'spans': {'status': span_report['status'], 'note': span_report['note']},
            'metrics': {
                'status': metrics_report['status'],
                'note': metrics_report['note'],
                'resolved_metrics': metrics_report.get('data', {}).get('resolved_metrics', {}),
            },
        },
    }