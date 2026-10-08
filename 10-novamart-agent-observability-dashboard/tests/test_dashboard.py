"""
Tests for the observability dashboard server.

Covers:
- server starts and responds on loopback
- /api/health reports AWS identity
- /api/telemetry returns non-empty data when CloudWatch logs exist
"""

from __future__ import annotations

import json
import sys
import threading
import time
import unittest
from http.client import HTTPConnection
from pathlib import Path

import boto3

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

import server  # noqa: E402


HOST = "127.0.0.1"
PORT = 18787  # test-only port


class TestDashboardTelemetry(unittest.TestCase):
    """Run against live AWS (no mocks)."""

    @classmethod
    def setUpClass(cls):
        settings = server.settings_module.load_settings()
        handler_base = server.DashboardHandler
        handler = type(
            "TestHandler",
            (handler_base,),
            {"settings": settings},
        )
        cls.server = server.ThreadingHTTPServer((HOST, PORT), handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        time.sleep(1)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def _get(self, path: str) -> tuple[int, dict]:
        conn = HTTPConnection(HOST, PORT, timeout=30)
        try:
            conn.request("GET", path)
            resp = conn.getresponse()
            body = json.loads(resp.read().decode("utf-8"))
            return resp.status, body
        finally:
            conn.close()

    def test_health_ok(self):
        status, body = self._get("/api/health")
        self.assertEqual(status, 200)
        self.assertIn("identity", body)

    def test_telemetry_returns_data(self):
        """Regression: dashboard must surface CloudWatch log data."""
        status, body = self._get("/api/telemetry?window=24h")
        self.assertEqual(status, 200)
        self.assertNotIn(
            "error", body,
            f"telemetry endpoint returned error: {body.get('error')}",
        )
        sources = body.get("sources", {})
        agent_log = sources.get("agent_log", {})
        self.assertNotEqual(
            agent_log.get("status"),
            "empty",
            "CloudWatch log group has data but dashboard reports empty — "
            "check _QUERY_INVOCATIONS filter and _bucket_map timestamp parsing",
        )

    def test_diagnose_reachable(self):
        status, body = self._get("/api/diagnose")
        self.assertEqual(status, 200)
        self.assertIn("checks", body)


if __name__ == "__main__":
    unittest.main()
