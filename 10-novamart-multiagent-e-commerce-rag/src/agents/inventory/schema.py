"""
agents/inventory/schema.py
===========================
Pydantic models for Inventory Agent tool inputs and outputs.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class CheckOrderStatusInput(BaseModel):
    customer_id: str = Field(description="The customer's unique identifier (e.g. CUST-001)")
    order_id: str = Field(description="The order identifier (e.g. ORD-27176)")


class OrderItem(BaseModel):
    order_id: str
    status: str
    product_name: str
    order_date: str
    price: str


class CheckOrderStatusOutput(BaseModel):
    found: bool
    order: OrderItem | None = None
    message: str | None = None
    error: str | None = None


class GetCustomerTierInput(BaseModel):
    customer_id: str = Field(description="The customer's unique identifier")


class CustomerProfile(BaseModel):
    customer_id: str
    name: str
    email: str
    tier: str
    account_created: str
    total_orders: int
    preferred_contact: str | None = None


class GetCustomerTierOutput(BaseModel):
    found: bool
    customer: CustomerProfile | None = None
    message: str | None = None
    error: str | None = None


class ListCustomerOrdersInput(BaseModel):
    customer_id: str = Field(description="The customer's unique identifier")


class OrderSummary(BaseModel):
    order_id: str
    status: str
    order_date: str
    price: str


class ListCustomerOrdersOutput(BaseModel):
    found: bool
    orders: list[OrderSummary] = []
    count: int = 0
    error: str | None = None
