from typing import Optional
from pydantic import BaseModel, Field


class FlightSearchInput(BaseModel):
    """Validated input for a flight search query."""
    origin: str = Field(description="IATA departure airport code, e.g. LHR")
    destination: str = Field(description="IATA arrival airport code, e.g. CDG")
    date: str = Field(description="Travel date in YYYY-MM-DD format, e.g. 2026-03-15")


class FlightOption(BaseModel):
    """A single validated flight result."""
    flight_number: str = Field(description="Flight code, e.g. HZ-101")
    origin: str = Field(description="IATA departure airport code")
    destination: str = Field(description="IATA arrival airport code")
    date: str = Field(description="Flight date in YYYY-MM-DD format")
    price_usd: float = Field(description="Ticket price in US dollars")
    available_seats: int = Field(ge=0, description="Number of seats remaining")
    status: str = Field(description="Flight status: SCHEDULED, DELAYED, or CANCELLED")
    cabin_class: Optional[str] = Field(default=None, description="Cabin class, e.g. Economy")


class FlightSearchResult(BaseModel):
    flights: list[FlightOption] = Field(description="List of matching flights")
    total: int = Field(description="Total number of flights found")
