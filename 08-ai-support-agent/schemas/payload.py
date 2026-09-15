from typing import Optional
from pydantic import BaseModel, Field


class InvokePayload(BaseModel):
    prompt: str = Field(default="Hello!", min_length=1)
    customer_id: str = Field(default="CUST-123", min_length=1)
    session_id: Optional[str] = None


class AgentResponse(BaseModel):
    response: str = Field(min_length=1)
