"""
agents/policy/schema.py
========================
Pydantic models for Policy Agent tool inputs and outputs.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class RetrievePolicyInput(BaseModel):
    query: str = Field(description="The policy question to search for")


class RetrievePolicyOutput(BaseModel):
    domain: str
    passages: list[str] = []
    scores: list[float] = []


class SearchAllPoliciesOutput(BaseModel):
    returns: str = ""
    shipping: str = ""
    warranty: str = ""
    synthesis: str = ""
