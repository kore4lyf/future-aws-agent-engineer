"""
aws_sources.py
==============
Every read the dashboard performs against AWS lives here.

Design rules
------------
1. Each source is independent. A failure in one never prevents the others from
   answering, because a half-empty dashboard is far more useful than none.
2. Nothing is invented. A source that cannot answer returns
   ``status='unavailable'`` with the reason, and the frontend says so.
3. No credential ever leaves this module.

Sources
-------
``agent_log``  CloudWatch Logs Insights over the project's own log group. Holds
               the ``trace ... started`` lines (one per request), the
               ``tool done <name> (<secs>s)`` timing lines, error lines, and
               any structured guardrail instrumentation line.
``spans``      CloudWatch Logs Insights over ``aws/spans``, where CloudWatch
               Transaction Search writes OTel subsegments. Subsegment names are
               the X-Ray node names (InventoryAgent, PolicyAgent, ...), so this
               is the only source that can break latency down by agent with no
               manual tool mapping.
``metrics``    CloudWatch GetMetricData against the ``AWS/Bedrock-AgentCore``
               namespace, for runtime-level invocations, latency and errors.
"""

from __future__ import annotations

import re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from typing import Iterable

import boto3
from botocore.config import Config as BotoConfig
from botocore.exceptions import BotoCoreError, ClientError

# Telemetry log-line contract shared with the agent project.
# Canonical source: ../10-novamart-multiagent-e-commerce-rag/src/telemetry/contract.py
# This folder's contract.py is a byte-identical mirror (parity-tested).
from contract import AGENT_NODE_FOR_TOOL


__all__ = [
    'AGENT_NODE_FOR_TOOL',
    'WINDOWS',
    'SourceReport',
    'agent_log_group_exists',
    'collect_agent_log',
    'collect_agentcore_metrics',
    'collect_spans',
    'diagnose',
    'list_agentcore_metric_names',
    'normalize_metric_name',
    'window_bounds',
]


BOTO_CONFIG = BotoConfig(
    retries={'max_attempts': 3, 'mode': 'standard'},
    connect_timeout=5,
    read_timeout=30,
)

AGENT_NODE_FOR_TOOL = dict(AGENT_NODE_FOR_TOOL)  # re-exported from contract

_METRIC_CANDIDATES = {
    'invocations': ('invocations', 'invocationcount', 'invocationsaggregated'),
    'latency': ('latency', 'invocationlatency', 'latencyms', 'endtoendlatency'),
    'errors': ('totalerrors', 'errors', 'systemerrors', 'usererrors', 'throttles'),
}


class SourceReport(dict):
    """Result envelope: status, data, and a human-readable note.

    status is one of 'ok', 'empty', 'unavailable', 'error'.
    """

    @classmethod
    def ok(cls, data: dict) -> 'SourceReport':
        return cls(status='ok', data=data, note='')

    @classmethod
    def empty(cls, note: str = 'No matching telemetry in the selected window.') -> 'SourceReport':
        return cls(status='empty', data={}, note=note)

    @classmethod
    def unavailable(cls, note: str) -> 'SourceReport':
        return cls(status='unavailable', data={}, note=note)

    @classmethod
    def error(cls, note: str) -> 'SourceReport':
        return cls(status='error', data={}, note=note)


def _client(service: str, region: str):
    return boto3.client(service, region_name=region, config=BOTO_CONFIG)


def normalize_metric_name(name: str) -> str:
    """Collapse a CloudWatch metric name to a comparable token.

    AgentCore's published names are spelled inconsistently across regions and
    doc revisions ('Invocations', 'Invocations (aggregated)', 'Total Errors'),
    so matching is done on an alphanumeric-lowercase form rather than an
    exact string compare.
    """
    return ''.join(ch for ch in name.lower() if ch.isalnum())


def _epoch_ms(moment: datetime) -> int:
    return int(moment.timestamp() * 1000)


# ─────────────────────────────────────────────────────────────────────────────
# Time windows
# ─────────────────────────────────────────────────────────────────────────────

# key -> (hours, label, short, vs_prev label)
WINDOWS = {
    '1w': (168, 'last 7 days', '1w', 'previous week'),
    '1m': (720, 'last 30 days', '1M', 'previous 30 days'),
    '3m': (2160, 'last 3 months', '3M', 'previous 3 months'),
    '6m': (4320, 'last 6 months', '6M', 'previous 6 months'),
    '12m': (8760, 'last 12 months', '12M', 'previous 12 months'),
}

_BUCKET_WORDS = {3600: 'hour', 14400: '4 hours', 86400: 'day', 604800: 'week'}

_HOUR_RE = re.compile(r'^(\d{1,4})h$')
_DAY_RE = re.compile(r'^(\d{1,3})d$')


def _resolve_window(key: str) -> tuple[int, str, str, str]:
    """Map a window key to (hours, label, short, vs_prev). Unknown -> 24h."""
    match = _HOUR_RE.match(key)
    if match:
        n = max(1, min(8760, int(match.group(1))))
        return n, f'last {n} hours', f'{n}h', f'previous {n}h'
    match = _DAY_RE.match(key)
    if match:
        n = max(1, min(90, int(match.group(1))))
        return n * 24, f'last {n} days', f'{n}d', f'previous {n} days'
    if key in WINDOWS:
        return WINDOWS[key]
    return 24, 'last 24 hours', '24h', 'previous 24h'


def _select_bins(hours: float) -> tuple[str, int]:
    """Logs Insights bin() clause and its width in seconds for a span."""
    if hours <= 48:
        return '1h', 3600
    if hours <= 168:
        return '4h', 14400
    if hours <= 4320:
        return '1d', 86400
    return '1w', 604800


def _label_format(hours: float) -> str:
    if hours <= 24:
        return '%H:%M'
    if hours <= 168:
        return '%a %H:%M'
    return '%b %d'


def window_bounds(window: str | None = None, year: int | None = None) -> dict:
    """Resolve a window key and optional year into query bounds and labels.

    A valid ``year`` wins over the relative window and covers that calendar
    year (truncated to now for the current year), with the previous window
    being the full prior year. Unknown window keys fall back to 24 hours
    rather than raising, so the dashboard always has bounds to draw.
    """
    now = datetime.now(timezone.utc)
    key = (window or '').strip().lower()
    resolved_year = None

    if isinstance(year, str) and year.strip().isdigit():
        year = int(year.strip())
    if isinstance(year, int) and 2000 <= year <= now.year:
        resolved_year = year
        start = datetime(year, 1, 1, tzinfo=timezone.utc)
        end = now if year == now.year else datetime(year + 1, 1, 1, tzinfo=timezone.utc)
        prev_start = datetime(year - 1, 1, 1, tzinfo=timezone.utc)
        prev_end = datetime(year, 1, 1, tzinfo=timezone.utc)
        if year == now.year:
            prev_end = prev_start + (end - start)
        label, short, vs_prev = f'year {year}', str(year), 'previous year'
        key = str(year)

    if resolved_year is None:
        hours, label, short, vs_prev = _resolve_window(key)
        key = key or f'{hours}h'
        start = now - timedelta(hours=hours)
        end = now
        prev_end = start
        prev_start = start - timedelta(hours=hours)

    span_hours = (end - start).total_seconds() / 3600
    bin_str, bucket_seconds = _select_bins(span_hours)
    return {
        'key': key,
        'start': start,
        'end': end,
        'prev_start': prev_start,
        'prev_end': prev_end,
        'year': resolved_year,
        'hours': round(span_hours, 1),
        'label': label,
        'short': short,
        'vs_prev': vs_prev,
        'bin': bin_str,
        'bucket_seconds': bucket_seconds,
        'bucket': _BUCKET_WORDS[bucket_seconds],
        'label_fmt': _label_format(span_hours),
    }


def _bucket_grid(known_keys: Iterable[int], start: datetime, end: datetime,
                 bucket_seconds: int) -> list[int]:
    """Epoch-second bucket starts covering [start, end).

    The grid is anchored on the buckets the query actually returned so the
    lookup can never miss on an alignment difference. With no data it falls
    back to an epoch-aligned grid, which then simply reads as zeros.
    """
    known = list(known_keys)
    offset = (min(known) % bucket_seconds) if known else 0
    first = int(start.timestamp())
    first -= (first - offset) % bucket_seconds
    last = int(end.timestamp())
    grid: list[int] = []
    cursor = first
    while cursor < last and len(grid) < 5000:
        grid.append(cursor)
        cursor += bucket_seconds
    return grid


def _bucket_label(epoch_seconds: int, bucket_seconds: int, fmt: str) -> str:
    moment = datetime.fromtimestamp(epoch_seconds, tz=timezone.utc)
    if bucket_seconds <= 3600:
        moment = moment.astimezone()
    return moment.strftime(fmt)


# ─────────────────────────────────────────────────────────────────────────────
# CloudWatch Logs Insights
# ─────────────────────────────────────────────────────────────────────────────

_QUERY_INVOCATIONS = (
    'fields @timestamp\n'
    '| filter @message like /trace / and @message like /published to X-Ray/\n'
    '| stats count() as invocations by bin({bin})\n'
    '| sort invocations asc'
)

_QUERY_ERRORS = (
    'fields @timestamp\n'
    '| filter @message like /ERROR/ or @message like /WARNING/ '
    'or @message like /Traceback/ or @message like /failed/\n'
    '| stats count() as errors by bin({bin})\n'
    '| sort errors asc'
)

_QUERY_TOOL_LATENCY = (
    'fields @message\n'
    '| filter @message like /tool done/\n'
    '| parse @message /tool done  (?<tool>[^ ]+) \\((?<secs>[0-9.]+)s\\)/\n'
    '| filter ispresent(tool) and ispresent(secs)\n'
    '| stats count() as calls, avg(secs) as avg_s, percentile(secs, 95) as p95_s by tool\n'
    '| sort calls desc'
)

_QUERY_TOOL_CALLS = (
    'fields @message\n'
    '| filter @message like /tool call/\n'
    '| parse @message /tool call  (?<tool>[^ ]+)/\n'
    '| filter ispresent(tool)\n'
    '| stats count() as calls by tool\n'
    '| sort calls desc'
)

_QUERY_GUARDRAILS = (
    'fields @timestamp\n'
    '| filter @message like /GUARDRAIL/\n'
    # Separate parses so both line shapes match: the canonical 5-field
    # line (policy/category/action/source/trace, see contract.py) and the
    # legacy 3-field line (policy/action/trace). A single combined pattern
    # would miss the canonical form because category sits between policy
    # and action.
    '| parse @message /policy=(?<policy>[^ ]+)/\n'
    '| parse @message /action=(?<action>[^ ]+)/\n'
    '| filter ispresent(policy)\n'
    '| stats count() as count by policy\n'
    '| sort count desc'
)

_QUERY_FAILURES = (
    'fields @message\n'
    '| filter @message like /failed/ or @message like /Traceback/ or @message like /ERROR/\n'
    '| sort @timestamp desc\n'
    '| limit 5\n'
    '| fields @message'
)

_QUERY_GUARDRAIL_RECENT = (
    'fields @timestamp, @message\n'
    '| filter @message like /GUARDRAIL/\n'
    '| sort @timestamp desc\n'
    '| limit 10\n'
    '| fields @timestamp, @message'
)


def _run_insights_query(
    logs,
    log_group_names: list[str],
    query: str,
    start_ms: int,
    end_ms: int,
    region: str,
    timeout_seconds: int,
    limit: int = 10000,
) -> list[dict]:
    """Start a Logs Insights query and poll until it completes.

    Returns a list of row dicts. Raises on API errors or timeout so the caller
    can record the failure against that source alone.
    """
    started = logs.start_query(
        logGroupNames=log_group_names,
        startTime=start_ms,
        endTime=end_ms,
        queryString=query,
        limit=limit,
    )
    query_id = started['queryId']

    deadline = time.monotonic() + timeout_seconds
    delay = 0.25
    while True:
        response = logs.get_query_results(queryId=query_id)
        status = response.get('status')
        if status in ('Complete', 'Failed', 'Cancelled', 'Timeout', 'Unknown'):
            break
        if time.monotonic() > deadline:
            raise TimeoutError(
                f'Logs Insights query did not finish within {timeout_seconds}s (status={status})'
            )
        time.sleep(delay)
        delay = min(delay * 1.6, 2.0)

    if status != 'Complete':
        statistics = response.get('statistics', {})
        raise RuntimeError(
            'Logs Insights query ended with status '
            f'{status}: {statistics.get("errorMessage", "no detail returned")}'
        )

    rows: list[dict] = []
    for row in response.get('results', []):
        parsed = {}
        for cell in row:
            parsed[cell['field']] = cell.get('value', '')
        rows.append(parsed)
    return rows


def _as_float(raw) -> float:
    try:
        return float(raw)
    except (TypeError, ValueError):
        return 0.0


def _bucket_map(rows: list[dict], value_key: str) -> dict:
    """Turn ``bin(...)`` stat rows into an epoch-second keyed map."""
    buckets: dict = {}
    for row in rows:
        raw = next(
            (v for k, v in row.items() if k.startswith("bin(")),
            None,
        )
        if raw is None:
            continue
        stamp = _as_float(raw)
        if not stamp:
            try:
                stamp = datetime.strptime(raw, "%Y-%m-%d %H:%M:%S.%f").timestamp()
            except (TypeError, ValueError):
                continue
        if not stamp:
            continue
        buckets[int(stamp)] = _as_float(row.get(value_key))
    return buckets


def agent_log_group_exists(logs, log_group: str) -> bool:
    """True when the configured log group is actually present in the region."""
    try:
        response = logs.describe_log_groups(logGroupNamePrefix=log_group)
    except (ClientError, BotoCoreError):
        return False
    return any(g.get('logGroupName') == log_group for g in response.get('logGroups', []))


def collect_agent_log(settings, bounds: dict | None = None) -> SourceReport:
    """Read invocations, errors, per-tool latency and guardrails from logs."""
    region = settings.region
    bounds = bounds or window_bounds(f'{settings.window_hours}h')
    start, end = bounds['start'], bounds['end']
    span = end - start

    def collect_now():
        return _collect_agent_log_window(settings, region, start, end, bounds['bin'])

    def collect_prev():
        return _collect_agent_log_window(
            settings, region, bounds['prev_start'], bounds['prev_end'], bounds['bin']
        )

    try:
        logs = _client('logs', region)
    except (ClientError, BotoCoreError) as exc:
        return SourceReport.unavailable(f'Could not create a CloudWatch Logs client: {exc}')

    if not agent_log_group_exists(logs, settings.agent_log_group):
        return SourceReport.unavailable(
            f"Log group '{settings.agent_log_group}' does not exist in {region}. "
            'Run the agent at least once with AGENT_LOG_TO_CLOUDWATCH=true, or set '
            'AGENT_LOG_GROUP to the correct name.'
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        current_future = pool.submit(collect_now)
        previous_future = pool.submit(collect_prev)
        try:
            current = current_future.result()
        except (ClientError, BotoCoreError, RuntimeError, TimeoutError) as exc:
            return SourceReport.error(
                f'CloudWatch Logs Insights query failed for '
                f"'{settings.agent_log_group}': {exc}"
            )
        try:
            previous = previous_future.result()
        except (ClientError, BotoCoreError, RuntimeError, TimeoutError):
            previous = {}

    inv_buckets = current.get('invocation_buckets', {})
    err_buckets = current.get('error_buckets', {})
    grid = _bucket_grid(
        [*inv_buckets, *err_buckets], start, end, bounds['bucket_seconds']
    )
    labels = [
        _bucket_label(k, bounds['bucket_seconds'], bounds['label_fmt']) for k in grid
    ]
    invocations = [inv_buckets.get(k, 0.0) for k in grid]
    errors = [err_buckets.get(k, 0.0) for k in grid]

    if not any(invocations) and not any(errors):
        return SourceReport.empty(
            f"No requests logged to '{settings.agent_log_group}' for {bounds['label']}."
        )

    total_invocations = sum(invocations)
    successful = [max(0.0, inv - err) for inv, err in zip(invocations, errors)]

    return SourceReport.ok({
        'labels': labels,
        'invocations': [int(v) for v in invocations],
        'successful': [int(v) for v in successful],
        'errors': [int(v) for v in errors],
        'total_invocations': int(total_invocations),
        'total_errors': int(sum(errors)),
        'previous_invocations': int(previous.get('total_invocations', 0)),
        'previous_errors': int(previous.get('total_errors', 0)),
        'tool_latency': current.get('tool_latency', {}),
        'tool_calls': current.get('tool_calls', {}),
        'guardrails': current.get('guardrails', {}),
        'guardrail_recent': current.get('guardrail_recent', []),
        'recent_failures': current.get('recent_failures', []),
    })


def _collect_agent_log_window(settings, region: str, start: datetime, end: datetime,
                              bin_str: str) -> dict:
    """Run the log queries for one time window."""
    logs = _client('logs', region)
    groups = [settings.agent_log_group]
    start_ms, end_ms = _epoch_ms(start), _epoch_ms(end)
    span_hours = (end - start).total_seconds() / 3600
    timeout = min(120, settings.query_timeout_seconds + int(span_hours / 24))

    def run(query: str) -> list[dict]:
        return _run_insights_query(logs, groups, query, start_ms, end_ms, region, timeout)

    with ThreadPoolExecutor(max_workers=7) as pool:
        invocations_future = pool.submit(run, _QUERY_INVOCATIONS.format(bin=bin_str))
        errors_future = pool.submit(run, _QUERY_ERRORS.format(bin=bin_str))
        latency_future = pool.submit(run, _QUERY_TOOL_LATENCY)
        calls_future = pool.submit(run, _QUERY_TOOL_CALLS)
        guardrails_future = pool.submit(run, _QUERY_GUARDRAILS)
        failures_future = pool.submit(run, _QUERY_FAILURES)
        guardrail_recent_future = pool.submit(run, _QUERY_GUARDRAIL_RECENT)

        invocation_rows = invocations_future.result()
        error_rows = errors_future.result()

        def tolerant(future, default):
            try:
                return future.result()
            except (ClientError, BotoCoreError, RuntimeError, TimeoutError):
                return default

        latency_rows = tolerant(latency_future, [])
        calls_rows = tolerant(calls_future, [])
        guardrail_rows = tolerant(guardrails_future, [])
        failure_rows = tolerant(failures_future, [])
        guardrail_recent_rows = tolerant(guardrail_recent_future, [])

    tool_latency = {}
    for row in latency_rows:
        tool = row.get('tool')
        if not tool:
            continue
        tool_latency[tool] = {
            'calls': int(_as_float(row.get('calls'))),
            'avg_ms': round(_as_float(row.get('avg_s')) * 1000),
            'p95_ms': round(_as_float(row.get('p95_s')) * 1000),
        }

    tool_calls = {
        row['tool']: int(_as_float(row.get('calls')))
        for row in calls_rows if row.get('tool')
    }

    guardrails = {
        row['policy']: int(_as_float(row.get('count')))
        for row in guardrail_rows if row.get('policy')
    }

    recent_failures = [
        _clean_log_message(row.get('@message', ''))
        for row in failure_rows
        if row.get('@message')
    ]

    guardrail_recent = [
        {'timestamp': row.get('@timestamp', ''), 'message': row.get('@message', '')[:300]}
        for row in guardrail_recent_rows
        if row.get('@message')
    ]

    return {
        'invocation_buckets': _bucket_map(invocation_rows, 'invocations'),
        'error_buckets': _bucket_map(error_rows, 'errors'),
        'total_invocations': sum(
            _as_float(r.get('invocations')) for r in invocation_rows
        ),
        'total_errors': sum(_as_float(r.get('errors')) for r in error_rows),
        'tool_latency': tool_latency,
        'tool_calls': tool_calls,
        'guardrails': guardrails,
        'guardrail_recent': guardrail_recent,
        'recent_failures': recent_failures[:5],
    }


def _clean_log_message(raw: str) -> str:
    """Strip the leading 'YYYY-MM-DD HH:MM:SS,mmm LEVEL logger ' prefix."""
    parts = raw.split(' ', 3)
    if len(parts) == 4 and parts[0].count('-') == 2:
        return parts[3][:200]
    return raw[:200]


# ─────────────────────────────────────────────────────────────────────────────
# X-Ray subsegments, via Transaction Search in aws/spans
# ─────────────────────────────────────────────────────────────────────────────

def _query_spans(settings, region: str, start: datetime, end: datetime) -> dict:
    """Aggregate subsegment latency by node name from the spans log group."""
    logs = _client('logs', region)
    divisor = settings.span_duration_divisor
    query = (
        'fields name, duration\n'
        '| filter ispresent(name) and ispresent(duration)\n'
        f'| stats count() as calls, avg(duration)/{divisor} as avg_d, '
        f'percentile(duration, 95)/{divisor} as p95_d by name\n'
        '| sort calls desc\n'
        '| limit 40'
    )
    rows = _run_insights_query(
        logs,
        [settings.spans_log_group],
        query,
        _epoch_ms(start),
        _epoch_ms(end),
        region,
        settings.query_timeout_seconds,
    )
    spans = {}
    for row in rows:
        node = row.get('name')
        if not node:
            continue
        spans[node] = {
            'calls': int(_as_float(row.get('calls'))),
            'avg_ms': round(_as_float(row.get('avg_d'))),
            'p95_ms': round(_as_float(row.get('p95_d'))),
        }
    return spans


def collect_spans(settings, bounds: dict | None = None) -> SourceReport:
    """Per-agent latency from X-Ray subsegments, which are named per agent."""
    region = settings.region
    bounds = bounds or window_bounds(f'{settings.window_hours}h')
    start, end = bounds['start'], bounds['end']

    try:
        logs = _client('logs', region)
        exists = agent_log_group_exists(logs, settings.spans_log_group)
    except (ClientError, BotoCoreError) as exc:
        return SourceReport.unavailable(f'Could not create a CloudWatch Logs client: {exc}')

    if not exists:
        return SourceReport.unavailable(
            f"Log group '{settings.spans_log_group}' does not exist in {region}. "
            'CloudWatch Transaction Search must be enabled before X-Ray spans are indexed.'
        )

    try:
        spans = _query_spans(settings, region, start, end)
    except (ClientError, BotoCoreError, RuntimeError, TimeoutError) as exc:
        return SourceReport.error(f'Span query failed: {exc}')

    if not spans:
        return SourceReport.empty(
            f"No indexed spans in '{settings.spans_log_group}' for {bounds['label']}."
        )

    return SourceReport.ok({'spans': spans})


# ─────────────────────────────────────────────────────────────────────────────
# AgentCore built-in CloudWatch metrics
# ─────────────────────────────────────────────────────────────────────────────

def list_agentcore_metric_names(settings) -> SourceReport:
    """Every metric name currently published in the AgentCore namespace."""
    try:
        cloudwatch = _client('cloudwatch', settings.region)
        paginator = cloudwatch.get_paginator('list_metrics')
        names: set = set()
        for page in paginator.paginate(Namespace=settings.agentcore_namespace):
            for metric in page.get('Metrics', []):
                names.add(metric['MetricName'])
    except (ClientError, BotoCoreError) as exc:
        return SourceReport.error(f'list_metrics failed: {exc}')
    return SourceReport.ok({'metric_names': sorted(names)})


def _match_metric(available: Iterable[str], slot: str) -> str | None:
    """Pick the published metric that best matches a logical slot."""
    normalized = {normalize_metric_name(name): name for name in available}
    for candidate in _METRIC_CANDIDATES.get(slot, ()):
        if candidate in normalized:
            return normalized[candidate]
    return None


def _metric_query_id(metric_name: str) -> str:
    """A legal get_metric_data Id: lowercase-led, alphanumerics/underscore only."""
    cleaned = re.sub(r'[^a-zA-Z0-9_]', '_', metric_name).lower() or 'metric'
    if not cleaned[0].isascii() or not cleaned[0].isalpha():
        cleaned = f'm_{cleaned}'
    return cleaned[:255]


def _get_metric_series(cloudwatch, metric_name: str, namespace: str,
                       start: datetime, end: datetime,
                       stat: str, dimensions=None) -> list[tuple[datetime, float]]:
    span_hours = (end - start).total_seconds() / 3600
    period = 3600 if span_hours <= 48 else (21600 if span_hours <= 168 else 86400)
    metric = {'Namespace': namespace, 'MetricName': metric_name}
    if dimensions:
        metric['Dimensions'] = dimensions

    series: list[tuple[datetime, float]] = []
    paginator = cloudwatch.get_paginator('get_metric_data')
    for page in paginator.paginate(
        MetricDataQueries=[{
            'Id': _metric_query_id(metric_name),
            'MetricStat': {'Metric': metric, 'Period': period, 'Stat': stat},
            'ReturnData': True,
        }],
        StartTime=start,
        EndTime=end,
        ScanBy='TimestampAscending',
    ):
        for result in page.get('MetricDataResults', []):
            for stamp, value in zip(
                result.get('Timestamps', []), result.get('Values', [])
            ):
                series.append((stamp, float(value)))
    return series


def _get_metric_series_with_fallback(cloudwatch, metric_name: str, namespace: str,
                                     start: datetime, end: datetime, stat: str,
                                     dimension_candidates) -> tuple[list, list | None]:
    """First non-empty series across the candidate dimension sets.

    Returns (series, used_dimensions). Lets ClientError/BotoCoreError (and
    multi-series match errors, which are BotoCoreErrors) propagate so the
    caller records the failure against that slot alone.
    """
    last_error = None
    saw_empty = False
    for dims in dimension_candidates:
        try:
            series = _get_metric_series(
                cloudwatch, metric_name, namespace, start, end, stat, dims)
        except (ClientError, BotoCoreError) as exc:
            last_error = exc
            continue
        if series:
            return series, dims
        saw_empty = True
    if not saw_empty and last_error is not None:
        raise last_error
    return [], None


def collect_agentcore_metrics(settings, bounds: dict | None = None) -> SourceReport:
    """Runtime-level invocations, latency and errors from AgentCore metrics."""
    region = settings.region
    bounds = bounds or window_bounds(f'{settings.window_hours}h')
    start, end = bounds['start'], bounds['end']

    discovery = list_agentcore_metric_names(settings)
    if discovery['status'] != 'ok':
        return SourceReport.error(discovery['note'])
    available = discovery['data']['metric_names']

    slots = {
        slot: _match_metric(available, slot)
        for slot in ('invocations', 'latency', 'errors')
    }
    if not any(slots.values()):
        return SourceReport.unavailable(
            f"No recognised metrics in '{settings.agentcore_namespace}'. "
            f'Published names were: {", ".join(available) or "none"}. '
            'Metrics are published once the AgentCore runtime has served traffic.'
        )

    try:
        cloudwatch = _client('cloudwatch', region)
    except (ClientError, BotoCoreError) as exc:
        return SourceReport.unavailable(f'Could not create a CloudWatch client: {exc}')

    dimensions = None
    if settings.agentcore_runtime_arn:
        dimensions = [{'Name': 'Resource', 'Value': settings.agentcore_runtime_arn}]

    # AgentCore publishes some series only under aggregate dimensions (e.g.
    # Invocations under AggregateOperation=InvokeAgentRuntime carries data
    # while the Resource-scoped series is empty). Try each candidate set in
    # order and keep the first one that returns datapoints.
    dimension_candidates = []
    if dimensions:
        dimension_candidates.append(dimensions)
    dimension_candidates.append(None)
    dimension_candidates.append(
        [{'Name': 'AggregateOperation', 'Value': 'InvokeAgentRuntime'}]
    )

    collected: dict = {'resolved_metrics': slots, 'resolved_dimensions': {}}
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = {}
        for slot, metric_name in slots.items():
            if not metric_name:
                continue
            stat = 'Average' if slot == 'latency' else 'Sum'
            futures[slot] = pool.submit(
                _get_metric_series_with_fallback, cloudwatch, metric_name,
                settings.agentcore_namespace, start, end, stat, dimension_candidates,
            )
        for slot, future in futures.items():
            try:
                series, used_dims = future.result()
                collected[slot] = series
                collected['resolved_dimensions'][slot] = used_dims
            except (ClientError, BotoCoreError) as exc:
                collected[slot] = []
                collected.setdefault('notes', []).append(f'{slot}: {exc}')

    if not any(collected.get(slot) for slot in slots if slots[slot]):
        detail = ''
        notes = collected.get('notes') or []
        if notes:
            detail = ' Query notes: ' + '; '.join(str(n) for n in notes)
        return SourceReport.empty(
            f"No datapoints in '{settings.agentcore_namespace}' for {bounds['label']}.{detail}"
        )

    return SourceReport.ok(collected)


# ─────────────────────────────────────────────────────────────────────────────
# Diagnostics
# ─────────────────────────────────────────────────────────────────────────────

def diagnose(settings) -> dict:
    """Report identity and per-resource reachability, for /api/diagnose."""
    report: dict = {'region': settings.region, 'identity': None, 'checks': {}}

    try:
        identity = boto3.client('sts', region_name=settings.region,
                                config=BOTO_CONFIG).get_caller_identity()
        report['identity'] = {
            'account': identity.get('Account'),
            'arn': identity.get('Arn'),
        }
    except (ClientError, BotoCoreError) as exc:
        report['identity_error'] = str(exc)
        return report

    try:
        logs = _client('logs', settings.region)
        groups = [
            g['logGroupName']
            for g in logs.describe_log_groups().get('logGroups', [])
        ]
    except (ClientError, BotoCoreError) as exc:
        report['checks']['logs'] = {'status': 'error', 'note': str(exc)}
        groups = []

    report['checks']['agent_log_group'] = {
        'name': settings.agent_log_group,
        'exists': settings.agent_log_group in groups,
    }
    report['checks']['spans_log_group'] = {
        'name': settings.spans_log_group,
        'exists': settings.spans_log_group in groups,
    }
    report['checks']['agentcore_metrics'] = list_agentcore_metric_names(settings)
    report['guardrail_instrumentation'] = {
        'expected_log_line': (
            'GUARDRAIL policy=<Name> category=<Category> action=<BLOCK|ANONYMIZE> '
            'source=<input|output|fallback> trace=<id> (legacy 3-field lines '
            'still parsed)'
        ),
        'note': (
            'Bedrock Guardrails expose no CloudWatch metric and no AgentCore '
            'signal. This log line has to be emitted by the agent at runtime.'
        ),
    }
    return report