import json
from pathlib import Path
from strands import tool

DATA_DIR = Path(__file__).parent.parent.parent / "datasets"

@tool
def search_flights(origin: str, destination: str) -> str:
    """Search available flights between two cities."""
    flights = json.loads((DATA_DIR / "flights.json").read_text())
    matches = [
        f for f in flights
        if f.get("origin", "").upper() == origin.upper()
        and f.get("destination", "").upper() == destination.upper()
        and f.get("status") != "CANCELLED"
    ]
    if not matches:
        return f"No flights found from {origin} to {destination}."
    return json.dumps(matches[:5], indent=2)

@tool
def search_hotels(city: str, max_price: float = 500.0) -> str:
    """Search available hotels in a city with an optional maximum price."""
    hotels = json.loads((DATA_DIR / "hotels.json").read_text())
    matches = [
        h for h in hotels
        if (h.get("city", h.get("location", ""))).lower() == city.lower()
        and h.get("available", h.get("availability", True))
        and h.get("price_per_night_usd", h.get("price_usd", 0)) <= max_price
    ]
    if not matches:
        return f"No hotels found in {city} under ${max_price}/night."
    return json.dumps(matches[:5], indent=2)
