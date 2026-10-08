"""
server.py
=========
Local telemetry proxy for the observability dashboard.

Why a server exists
-------------------
The browser cannot query CloudWatch Logs Insights: there is no SigV4 signer in
plain JavaScript, and the API rejects cross-origin requests. AWS credentials
also must never be handed to a page. So this process holds the boto3 client,
runs the queries, and returns plain JSON over loopback.

Routes
------
GET /                 the dashboard (index.html)
GET /api/telemetry    assembled payload; optional ?window=24h|7d|1w|3m... and
                      ?year=YYYY to scope queries (year overrides window)
GET /api/diagnose     identity, reachable resources, published metric names
GET /api/health       liveness plus source status, without running queries
"""

from __future__ import annotations

import json
import sys
import threading
import time
import traceback
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import aws_sources
import settings as settings_module
import telemetry


__all__ = ['run']


BASE_DIR = Path(__file__).resolve().parent
INDEX_FILE = BASE_DIR / 'index.html'

_cache_lock = threading.Lock()
_cache: dict = {}


def _query_params(raw_query: str) -> tuple[str, int | None]:
    """Extract (window, year) from a query string, both optional."""
    params = parse_qs(raw_query)
    window = (params.get('window') or [''])[0].strip().lower()
    year_raw = (params.get('year') or [''])[0].strip()
    year = int(year_raw) if year_raw.isdigit() else None
    return window, year


def _cached_payload(active: settings_module.Settings, window: str, year: int | None) -> dict:
    key = (window, year)
    if active.cache_ttl_seconds <= 0:
        return telemetry.build_payload(active, window=window, year=year)
    now = time.monotonic()
    with _cache_lock:
        entry = _cache.get(key)
        if entry is not None and now < entry['expires_at']:
            return entry['payload']
    payload = telemetry.build_payload(active, window=window, year=year)
    with _cache_lock:
        if len(_cache) >= 32:
            _cache.clear()
        _cache[key] = {'payload': payload, 'expires_at': now + active.cache_ttl_seconds}
    return payload


class DashboardHandler(BaseHTTPRequestHandler):
    """Serve the dashboard and the telemetry API."""

    server_version = 'NovaMartObservability/1.0'
    settings: settings_module.Settings = None

    def log_message(self, fmt: str, *args) -> None:
        sys.stderr.write(f'  {self.address_string()} {fmt % args}\n')

    def _send(self, status: HTTPStatus, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, status: HTTPStatus, payload: dict) -> None:
        body = json.dumps(payload, default=str).encode('utf-8')
        self._send(status, body, 'application/json; charset=utf-8')

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path.rstrip('/') or '/'
        try:
            if path == '/':
                self._serve_index()
            elif path == '/api/telemetry':
                self._serve_telemetry(parsed.query)
            elif path == '/api/telemetry-debug':
                window, year = _query_params(parsed.query)
                raw = telemetry.build_payload(self.settings, window=window, year=year)
                self._send_json(HTTPStatus.OK, {
                    'raw_source': raw.get('sources', {}).get('agent_log', {}),
                    'invocations_count': len(raw.get('invocations', [])),
                    'stats': raw.get('stats', {}),
                    'raw_agents': raw.get('agents', []),
                })
            elif path == '/api/telemetry-debug2':
                import telemetry as telemetry_module
                from contract import NODE_LABELS
                window, year = _query_params(parsed.query)
                raw = telemetry_module.build_payload(self.settings, window=window, year=year)
                log_report = raw.get('sources', {}).get('agent_log', {})
                log_data = log_report.get('data', {})
                merged = telemetry_module._merge_nodes({}, log_data.get('tool_latency', {}))
                self._send_json(HTTPStatus.OK, {
                    'tool_latency_keys': list(log_data.get('tool_latency', {}).keys())[:10],
                    'merged_nodes': list(merged.keys()),
                    'node_labels': list(NODE_LABELS.keys()),
                    'raw_stats': raw.get('stats', {}),
                })
            elif path == '/api/diagnose':
                self._send_json(HTTPStatus.OK, aws_sources.diagnose(self.settings))
            elif path == '/api/health':
                self._serve_health()
            else:
                self._send_json(HTTPStatus.NOT_FOUND, {'error': f'no route for {path}'})
        except Exception as exc:
            traceback.print_exc()
            self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {
                'error': type(exc).__name__,
                'message': str(exc),
            })

    def _serve_index(self) -> None:
        if not INDEX_FILE.is_file():
            self._send_json(
                HTTPStatus.NOT_FOUND,
                {'error': 'index.html not found next to server.py'},
            )
            return
        self._send(HTTPStatus.OK, INDEX_FILE.read_bytes(), 'text/html; charset=utf-8')

    def _serve_telemetry(self, raw_query: str = '') -> None:
        window, year = _query_params(raw_query)
        payload = _cached_payload(self.settings, window, year)
        self._send_json(HTTPStatus.OK, payload)

    def _serve_health(self) -> None:
        report = aws_sources.diagnose(self.settings)
        self._send_json(HTTPStatus.OK, {
            'ok': report.get('identity') is not None,
            'identity': report.get('identity'),
            'identity_error': report.get('identity_error'),
            'region': self.settings.region,
            'settings': self.settings.public_dict(),
            'checks': report.get('checks', {}),
        })


def run() -> int:
    """Load settings, bind loopback, and serve until interrupted."""
    active = settings_module.load_settings()

    print('AI Agent Observability Dashboard')
    print(f'  Region          : {active.region}')
    print(f'  Agent log group : {active.agent_log_group}')
    print(f'  Spans log group : {active.spans_log_group}')
    print(f'  Namespace       : {active.agentcore_namespace}')
    print(f'  Window          : {active.window_hours}h (cache {active.cache_ttl_seconds}s)')
    print(f'  Mock fallback   : {"on" if active.allow_mock_fallback else "off"}')
    print(f'  Env file        : {"loaded" if active.env_file_loaded else "absent"}')

    try:
        identity = aws_sources.diagnose(active).get('identity')
    except Exception:
        identity = None
    if identity:
        print(f'  AWS identity    : {identity["arn"]} (account {identity["account"]})')
    else:
        print('  AWS identity    : UNAVAILABLE - set credentials, then open /api/diagnose')

    url = f'http://{active.host}:{active.port}'
    print(f'\n  Serving {url}\n')

    handler = type('BoundHandler', (DashboardHandler,), {'settings': active})
    server = ThreadingHTTPServer((active.host, active.port), handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\n  Stopped.')
    finally:
        server.server_close()
    return 0


if __name__ == '__main__':
    raise SystemExit(run())