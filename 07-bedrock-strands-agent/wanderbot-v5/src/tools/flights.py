import json
import logging
from pathlib import Path

from pydantic import ValidationError
from strands import tool

from src.schemas.flights import FlightSearchInput, FlightOption, FlightSearchResult

logger = logging.getLogger(__name__)

FLIGHTS_FILE = Path(__file__).parent.parent / "datasets" / "flights.json"


@tool
def search_flights(origin: str, destination: str, date: str) -> str:
    """Search available flights by origin, destination, and date.

    Args:
        origin: IATA airport code for departure city (e.g., "BCN", "FCO", "LHR").
        destination: IATA airport code for arrival city (e.g., "FCO", "LHR", "CDG").
        date: Travel date in YYYY-MM-DD format (e.g., "2026-03-20").

    Returns:
        A JSON string with matching flights and total count.
    """
    try:
        validated_input = FlightSearchInput(origin=origin, destination=destination, date=date)
    except ValidationError as e:
        return json.dumps({"error": "Invalid search parameters", "details": str(e)})

    with open(FLIGHTS_FILE, encoding="utf-8") as f:
        flights = json.load(f)

    matches = [
        fl for fl in flights
        if fl.get("origin", "").upper() == validated_input.origin.upper()
        and fl.get("destination", "").upper() == validated_input.destination.upper()
        and fl.get("date", "") == validated_input.date
    ]

    validated_flights = []
    for fl in matches:
        try:
            validated_flights.append(FlightOption.model_validate(fl))
        except ValidationError as e:
            logger.warning("Skipping invalid flight record: %s", e)

    result = FlightSearchResult(flights=validated_flights, total=len(validated_flights))
    return result.model_dump_json(indent=2)
