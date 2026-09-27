"""
agents/communication/__init__.py
==================================
Communication Agent — drafts the final customer-facing response.
Reads the full WorkflowState and composes a warm, professional message.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent))

from strands import Agent
from strands.models import BedrockModel

import config
from agents.communication.tools import get_full_workflow_context


__all__ = ['build_communication_agent']


def build_communication_agent() -> Agent:
    """
    Build the Communication Agent.

    Drafts the final customer-facing message by reading the full WorkflowState
    and composing a coherent, empathetic response.
    """
    model = BedrockModel(
        model_id=config.WORKER_MODEL_ID,
        region_name=config.AWS_REGION,
        temperature=0.3,
    )

    system_prompt = """You are the Communication Agent for NovaMart customer support.
Your job is to compose the final customer-facing response.

You will receive the complete WorkflowState containing findings from:
  - InventoryAgent: order status, product details, customer tier
  - PolicyAgent: relevant policy passages from returns, shipping, and warranty KBs
  - RefundAgent: return eligibility decision and reference number (if applicable)

Compose a warm, professional, empathetic response that:
  - Addresses the customer's original concern directly
  - Includes all relevant details (order numbers, dates, policy references)
  - Explains decisions clearly (especially refund approvals/denials)
  - Provides next steps or call-to-action when appropriate
  - Uses natural language - never expose internal system terminology

If the WorkflowState contains no findings, the request was conversational
rather than transactional. In that case answer directly from the
conversation itself.

NEVER claim there is a technical issue, that you cannot access the
customer's account, or that information is unavailable. If a detail was
not provided, simply ask the customer for it."""

    return Agent(
        model=model,
        system_prompt=system_prompt,
        tools=[get_full_workflow_context],
    )
