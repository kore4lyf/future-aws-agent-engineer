from typing import Optional
from pydantic import BaseModel, Field


class HotelSearchInput(BaseModel):
    """Validated input for a hotel search query."""
    city: str = Field(description="Name of the destination city, e.g. 'Barcelona'")
    max_price_usd: float = Field(description="Maximum price per night in USD, e.g. 200.0")


class HotelOption(BaseModel):
    """A single validated hotel result."""
    hotel_id: str = Field(description="Hotel identifier, e.g. 'HT-BCN-001'")
    name: str = Field(description="Hotel name, e.g. 'Hotel Casa Marina'")
    city: str = Field(description="City where the hotel is located, e.g. 'Barcelona'")
    star_rating: int = Field(ge=1, le=5, description="Star rating from 1 to 5")
    price_per_night_usd: float = Field(ge=0, description="Price per night in US dollars")
    available: bool = Field(description="Whether the hotel has availability")
    room_types: list[str] = Field(description="Available room types, e.g. ['Standard', 'Deluxe']")
    amenities: list[str] = Field(description="Hotel amenities, e.g. ['Pool', 'Spa']")
    check_in_time: Optional[str] = Field(default=None, description="Check-in time, e.g. '15:00'")
    check_out_time: Optional[str] = Field(default=None, description="Check-out time, e.g. '11:00'")
    cancellation_policy: Optional[str] = Field(default=None, description="Cancellation policy description")


class HotelSearchResult(BaseModel):
    hotels: list[HotelOption] = Field(description="List of matching hotels")
    total: int = Field(description="Total number of hotels found")
