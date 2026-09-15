from typing import Literal, Optional
from pydantic import BaseModel, Field


class OrderItem(BaseModel):
    name: str
    qty: int = Field(ge=1)
    price: float = Field(ge=0)


class Order(BaseModel):
    order_id: str
    customer_id: str
    status: Literal["PROCESSING", "SHIPPED", "OUT FOR DELIVERY", "DELIVERED", "CANCELLED"]
    items: list[OrderItem]
    total: float = Field(ge=0)
    tracking_number: Optional[str] = None
    carrier: Optional[str] = None
    estimated_delivery: Optional[str] = None
    delivered_date: Optional[str] = None


class Customer(BaseModel):
    name: str
    loyalty_points: int = Field(ge=0)
    tier: Literal["Silver", "Gold", "Platinum"]
