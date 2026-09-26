"""
agents/orchestrator/schema.py
===============================
Pydantic models for Orchestrator Agent tool inputs and outputs.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class InitializeSessionInput(BaseModel):
    session_id: str = Field(description="A unique identifier for this session")
    customer_id: str = Field(description="The customer's identifier")


class InitializeSessionOutput(BaseModel):
    session_id: str
    customer_id: str
    version: int
    message: str


class RouteToInventoryAgentInput(BaseModel):
    session_id: str = Field(description="The current session identifier")
    customer_id: str = Field(description="The customer's unique identifier")
    request: str = Field(description="The customer's original request")


class RouteToPolicyAgentInput(BaseModel):
    session_id: str = Field(description="The current session identifier")
    request: str = Field(description="The customer's policy question")


class RouteToRefundAgentInput(BaseModel):
    session_id: str = Field(description="The current session identifier")
    customer_id: str = Field(description="The customer's unique identifier")
    request: str = Field(description="The return/refund request")


class RouteToCommunicationAgentInput(BaseModel):
    session_id: str = Field(description="The current session identifier")
    customer_id: str = Field(description="The customer's unique identifier")
    original_request: str = Field(description="The customer's original message")
