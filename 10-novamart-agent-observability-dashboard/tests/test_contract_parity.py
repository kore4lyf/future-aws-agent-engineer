"""
Tests for the shared telemetry contract.

The agent project (src/telemetry/contract.py, canonical) and this
dashboard (contract.py, mirror) must stay byte-identical. If this test
fails, edit the canonical file first, then copy it over verbatim.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path


DASHBOARD_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(DASHBOARD_DIR))

import contract as dashboard_contract  # noqa: E402

CANONICAL = (
    DASHBOARD_DIR.parent
    / "10-novamart-multiagent-e-commerce-rag"
    / "src" / "telemetry" / "contract.py"
)


class TestContractParity(unittest.TestCase):
    def test_mirror_matches_canonical(self):
        if not CANONICAL.is_file():
            self.skipTest(f"canonical contract not found at {CANONICAL}")
        mirror = (DASHBOARD_DIR / "contract.py").read_bytes()
        canonical = CANONICAL.read_bytes()
        self.assertEqual(
            mirror, canonical,
            "dashboard contract.py diverged from the canonical "
            "src/telemetry/contract.py — copy the canonical file over verbatim",
        )

    def test_guardrail_lines_parse(self):
        canonical = dashboard_contract.format_guardrail_line(
            policy="CompetitorBlock", action="BLOCK",
            trace_id="trace-1", category="DENIED_TOPIC", source="input",
        )
        parsed = dashboard_contract.parse_guardrail_line(canonical)
        self.assertEqual(parsed["policy"], "CompetitorBlock")
        self.assertEqual(parsed["action"], "BLOCK")
        # Legacy 3-field line must still parse.
        legacy = "GUARDRAIL policy=Unknown action=BLOCK trace=abc123"
        parsed_legacy = dashboard_contract.parse_guardrail_line(legacy)
        self.assertIsNotNone(parsed_legacy)
        self.assertEqual(parsed_legacy["policy"], "Unknown")

    def test_kb_spans_aggregate_to_single_rag_row(self):
        rows = dashboard_contract.aggregate_spans_for_display({
            "KnowledgeBase:returns": {"calls": 4, "avg_ms": 200, "p95_ms": 300},
            "KnowledgeBase:shipping": {"calls": 2, "avg_ms": 400, "p95_ms": 500},
            "InventoryAgent": {"calls": 6, "avg_ms": 100, "p95_ms": 150},
        })
        rag_rows = [r for r in rows if r["name"] == "RAG Agent"]
        self.assertEqual(len(rag_rows), 1)
        self.assertEqual(rag_rows[0]["invocations"], 6)

    def test_tool_map_has_no_invented_nodes(self):
        nodes = set(dashboard_contract.AGENT_NODE_FOR_TOOL.values())
        self.assertTrue(
            nodes <= set(dashboard_contract.NODE_LABELS),
            f"tool map points at unknown nodes: {nodes - set(dashboard_contract.NODE_LABELS)}",
        )


if __name__ == "__main__":
    unittest.main()
