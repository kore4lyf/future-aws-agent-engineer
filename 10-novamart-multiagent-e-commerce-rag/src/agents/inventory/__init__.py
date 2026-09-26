"""
agents/inventory/__init__.py
=============================
Inventory Agent — retrieves order and customer facts from DynamoDB.
No decisions, no customer-facing output.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent))

from strands import Agent
from strands.models import BedrockModel

import config
from agents.inventory.tools import check_order_status, get_customer_tier, list_customer_orders


__all__ = ['build_inventory_agent']


def build_inventory_agent() -> Agent:
    """
    Build the Inventory Agent.

    Gathers order and customer facts from DynamoDB. Does NOT make decisions -
    only retrieves data for the OrchestratorAgent to share with downstream agents.
    """
    model = BedrockModel(
        model_id=config.WORKER_MODEL_ID,
        region_name=config.AWS_REGION,
        temperature=0.1,
    )

    system_prompt = """You are the Inventory Agent for NovaMart customer support.
Your ONLY job is to retrieve factual data from DynamoDB - you must NEVER make
eligibility decisions or compose customer-facing responses.

When asked for order or customer information, use your tools to look up the
exact data and report it accurately. If a record is not found, say so clearly."""

    return Agent(
        model=model,
        system_prompt=system_prompt,
        tools=[check_order_status, get_customer_tier, list_customer_orders],
    )
