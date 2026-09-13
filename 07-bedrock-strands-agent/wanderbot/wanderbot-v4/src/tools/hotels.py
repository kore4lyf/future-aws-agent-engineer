import json
import logging
from pathlib import Path

from pydantic import ValidationError
from strands import tool

from src.schemas.hotels import HotelSearchInput, HotelOption, HotelSearchResult

logger = logging.getLogger(__name__)

HOTELS_FILE = Path(__file__).parent.parent / "datasets" / "hotels_broken.json"


@tool
def search_hotels(city: str, max_price_usd: float) -> str:
    """Search available hotels in a city filtered by max price.

    Args:
        city: Name of the destination city, e.g. 'Barcelona'.
        max_price_usd: Maximum price per night in USD, e.g. 200.0.

    Returns:
        A JSON string with matching hotels and total count.
    """
    try:
        validated_input = HotelSearchInput(city=city, max_price_usd=max_price_usd)
    except ValidationError as e:
        return json.dumps({"error": "Invalid search parameters", "details": str(e)})

    with open(HOTELS_FILE, encoding="utf-8") as f:
        hotels = json.load(f)

    matches = [h for h in hotels if h.get("city", "").lower() == validated_input.city.lower()]

    validated_hotels = []
    for h in matches:
        try:
            hotel = HotelOption.model_validate(h)
            if hotel.price_per_night_usd <= validated_input.max_price_usd:
                validated_hotels.append(hotel)
        except ValidationError as e:
            logger.warning("Skipping invalid hotel record %s: %s", h.get("hotel_id", "?"), e)

    result = HotelSearchResult(hotels=validated_hotels, total=len(validated_hotels))
    return result.model_dump_json(indent=2)
