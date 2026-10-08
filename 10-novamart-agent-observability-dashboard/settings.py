"""
settings.py
===========
Configuration for the observability dashboard backend.

Credentials are read only in this process. They are never returned by any
endpoint and never embedded in the HTML, which is the whole reason this runs
behind a local proxy instead of talking to AWS from the browser.

Resolution order for every value:
    1. process environment
    2. a .env file next to this module
    3. the DEFAULT below

AWS credentials themselves are deliberately absent from this module. They are
resolved by boto3's normal provider chain (environment, shared config, SSO,
instance role), so the dashboard inherits whatever identity the rest of the
agent project already uses.
"""

from __future__ import annotations

import os
from pathlib import Path


__all__ = ['DEFAULT', 'Settings', 'load_settings']


BASE_DIR = Path(__file__).resolve().parent
ENV_FILE = BASE_DIR / '.env'


DEFAULT = {
    'AWS_REGION': 'us-east-1',
    'AGENT_LOG_GROUP': '/aws/bedrock/agentcore/novamart-agentcore',
    'SPANS_LOG_GROUP': 'aws/spans',
    'AGENTCORE_NAMESPACE': 'AWS/Bedrock-AgentCore',
    'AGENTCORE_RUNTIME_ARN': '',
    'WINDOW_HOURS': '24',
    'QUERY_TIMEOUT_SECONDS': '30',
    'CACHE_TTL_SECONDS': '60',
    'SPAN_DURATION_DIVISOR': '1000000',
    'ALLOW_MOCK_FALLBACK': 'true',
    'HOST': '127.0.0.1',
    'PORT': '8787',
}

_TRUTHY = {'1', 'true', 'yes', 'on'}


def _parse_env_file(path: Path) -> dict:
    """Read KEY=VALUE pairs from a .env file, ignoring blanks and comments."""
    values: dict = {}
    if not path.is_file():
        return values
    for raw in path.read_text(encoding='utf-8').splitlines():
        line = raw.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        if line.lower().startswith('export '):
            line = line[7:].strip()
        key, _, value = line.partition('=')
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
            value = value[1:-1]
        values[key.strip()] = value
    return values


def _flag(raw: str) -> bool:
    return raw.strip().lower() in _TRUTHY


def _int(raw: str, minimum: int) -> int:
    try:
        return max(minimum, int(raw))
    except (TypeError, ValueError):
        return minimum


class Settings:
    """Resolved dashboard settings."""

    __slots__ = (
        'region', 'agent_log_group', 'spans_log_group',
        'agentcore_namespace', 'agentcore_runtime_arn',
        'window_hours', 'query_timeout_seconds', 'cache_ttl_seconds',
        'span_duration_divisor', 'allow_mock_fallback', 'host', 'port',
        'env_file_loaded',
    )

    def __init__(self, **values) -> None:
        self.region = values['region']
        self.agent_log_group = values['agent_log_group']
        self.spans_log_group = values['spans_log_group']
        self.agentcore_namespace = values['agentcore_namespace']
        self.agentcore_runtime_arn = values['agentcore_runtime_arn']
        self.window_hours = values['window_hours']
        self.query_timeout_seconds = values['query_timeout_seconds']
        self.cache_ttl_seconds = values['cache_ttl_seconds']
        self.span_duration_divisor = values['span_duration_divisor']
        self.allow_mock_fallback = values['allow_mock_fallback']
        self.host = values['host']
        self.port = values['port']
        self.env_file_loaded = values['env_file_loaded']

    def public_dict(self) -> dict:
        """Settings safe to return to the browser. Contains no credentials."""
        return {
            'region': self.region,
            'agent_log_group': self.agent_log_group,
            'spans_log_group': self.spans_log_group,
            'agentcore_namespace': self.agentcore_namespace,
            'agentcore_runtime_arn_configured': bool(self.agentcore_runtime_arn),
            'window_hours': self.window_hours,
            'span_duration_divisor': self.span_duration_divisor,
            'env_file_loaded': self.env_file_loaded,
        }


def load_settings() -> Settings:
    """Build Settings from the environment, then .env, then DEFAULT."""
    from_file = _parse_env_file(ENV_FILE)

    def get(key: str) -> str:
        raw = os.environ.get(key)
        if raw is not None and raw.strip() != '':
            return raw.strip()
        return from_file.get(key, DEFAULT[key]).strip() or DEFAULT[key]

    return Settings(
        region=os.environ.get('AWS_REGION') or get('AWS_REGION'),
        agent_log_group=get('AGENT_LOG_GROUP'),
        spans_log_group=get('SPANS_LOG_GROUP'),
        agentcore_namespace=get('AGENTCORE_NAMESPACE'),
        agentcore_runtime_arn=get('AGENTCORE_RUNTIME_ARN'),
        window_hours=_int(get('WINDOW_HOURS'), 1),
        query_timeout_seconds=_int(get('QUERY_TIMEOUT_SECONDS'), 5),
        cache_ttl_seconds=_int(get('CACHE_TTL_SECONDS'), 0),
        span_duration_divisor=_int(get('SPAN_DURATION_DIVISOR'), 1),
        allow_mock_fallback=_flag(get('ALLOW_MOCK_FALLBACK')),
        host=get('HOST'),
        port=_int(get('PORT'), 1024),
        env_file_loaded=ENV_FILE.is_file(),
    )