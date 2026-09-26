"""
agents/refund/schema.py
========================
Pydantic models for Refund Agent tool inputs and outputs.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class GetInventoryContextInput(BaseModel):
    session_id: str = Field(description="The current session identifier")


class GetInventoryContextOutput(BaseModel):
    inventory_agent: str | None = None
    error: str | None = None


class InitiateRefundInput(BaseModel):
    customer_id: str = Field(description="The customer's unique identifier")
    order_id: str = Field(description="The order to return")
    reason: str = Field(description="Customer-provided reason for the return")


class InitiateRefundOutput(BaseModel):
    success: bool
    return_reference: str | None = None
    message: str | None = None
    error: str | None = None
