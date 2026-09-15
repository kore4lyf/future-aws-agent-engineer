from typing import Optional
from pydantic import BaseModel, Field


class RefundRequest(BaseModel):
    order_id: str = Field(min_length=1)
    reason: Optional[str] = None
    amount: Optional[float] = Field(default=None, ge=0)


class RefundResult(BaseModel):
    refund_id: str
    order_id: Optional[str] = None
    status: str
    amount: Optional[float] = None
    message: Optional[str] = None
