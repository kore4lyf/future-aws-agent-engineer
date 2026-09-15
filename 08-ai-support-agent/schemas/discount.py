from typing import Literal
from pydantic import BaseModel, Field


class DiscountInput(BaseModel):
    loyalty_points: int = Field(ge=0)
    tier: Literal["Silver", "Gold", "Platinum"]
    order_total: float = Field(gt=0)
    product_category: Literal["standard", "device", "fresh"] = "standard"


class DiscountResult(BaseModel):
    points_redeemed: int = Field(ge=0)
    tier_discount_pct: int = Field(ge=0, le=100)
    tier_discount: float = Field(ge=0)
    final_total: float = Field(ge=0)
    total_savings: float = Field(ge=0)
    points_earned: int = Field(ge=0)
    remaining_points: int = Field(ge=0)
