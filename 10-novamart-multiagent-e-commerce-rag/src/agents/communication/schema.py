"""
agents/communication/schema.py
================================
Pydantic models for Communication Agent tool inputs and outputs.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class GetFullWorkflowContextInput(BaseModel):
    session_id: str = Field(description="The current session identifier")


class GetFullWorkflowContextOutput(BaseModel):
    inventory_agent: str | None = None
    policy_agent: str | None = None
    refund_agent: str | None = None
    error: str | None = None
