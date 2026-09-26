"""
agents/refund/__init__.py
=========================
Refund Agent — makes return/refund eligibility decisions.
Reads WorkflowState for inventory context; writes decision back.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent))

from strands import Agent
from strands.models import BedrockModel

import config
from agents.refund.tools import get_inventory_context, initiate_refund


def build_refund_agent() -> Agent:
    """
    Build the Refund Agent.

    Makes return/refund eligibility decisions based on order facts from
    WorkflowState and applies the correct policy window per customer tier.
    """
    model = BedrockModel(
        model_id=config.WORKER_MODEL_ID,
        region_name=config.AWS_REGION,
        temperature=0.1,
    )

    system_prompt = """You are the Refund Agent for NovaMart customer support.
Your job is to decide whether a return or refund is eligible.

Rules:
  - Standard customers: 30-day return window from order date
  - Premium customers: 60-day return window from order date
  - Always read the inventory context FIRST to get the order date and customer tier
  - Calculate days elapsed from order_date to today
  - If within the window: approve the return and generate a reference number
  - If outside the window: deny with a clear explanation
  - When initiating a refund, update the order status in DynamoDB to 'returned'
  - Be fair but firm - follow the policy exactly"""

    return Agent(
        model=model,
        system_prompt=system_prompt,
        tools=[get_inventory_context, initiate_refund],
    )
