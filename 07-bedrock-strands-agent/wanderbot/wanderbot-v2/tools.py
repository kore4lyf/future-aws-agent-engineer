import json
from pathlib import Path

from strands import tool

DATASETS_DIR = Path(__file__).parent / "datasets"


@tool
def search_flights(origin: str, destination: str, date: str) -> str:
    """Search available flights by origin, destination, and date.

    Args:
        origin: IATA airport code for departure city (e.g., "BCN", "FCO", "LHR").
        destination: IATA airport code for arrival city (e.g., "FCO", "LHR", "CDG").
        date: Travel date in YYYY-MM-DD format (e.g., "2026-03-20").

    Returns:
        A list of matching flights with airline, times, price, and status.
    """
    with open(DATASETS_DIR / "flights.json") as f:
        flights = json.load(f)

    results = [
        flight for flight in flights
        if flight["origin"] == origin
        and flight["destination"] == destination
        and flight["departure"].startswith(date)
    ]

    if not results:
        return f"No flights found from {origin} to {destination} on {date}."

    return json.dumps(results, indent=2)


@tool
def search_hotels(city: str, max_price_usd: float = None) -> str:
    """Search available hotels in a city, optionally filtered by max price.

    Args:
        city: City name (e.g., "Rome", "Barcelona", "London", "Paris", "Tokyo").
        max_price_usd: Optional maximum price per night in USD. If omitted, all hotels in the city are returned.

    Returns:
        A list of matching hotels with name, rating, price, and amenities.
    """
    with open(DATASETS_DIR / "hotels.json") as f:
        hotels = json.load(f)

    results = [hotel for hotel in hotels if hotel["city"] == city]

    if max_price_usd is not None:
        results = [hotel for hotel in results if hotel["price_usd"] <= max_price_usd]

    if not results:
        return f"No hotels found in {city}" + (f" under ${max_price_usd}/night" if max_price_usd else "") + "."

    return json.dumps(results, indent=2)


@tool
def get_exchange_rate(amount_usd: float, target_currency: str) -> str:
    """Convert an amount from USD to a target currency.

    Args:
        amount_usd: Amount in US dollars to convert.
        target_currency: ISO 4217 currency code (e.g., "EUR", "GBP", "JPY", "CAD").

    Returns:
        The converted amount with the exchange rate used.
    """
    with open(DATASETS_DIR / "exchange_rates.json") as f:
        rates = json.load(f)

    for rate in rates:
        if rate["currency_code"] == target_currency.upper():
            converted = amount_usd * rate["rate_to_usd"]
            return f"${amount_usd:.2f} USD = {converted:.2f} {target_currency.upper()} (rate: 1 USD = {rate['rate_to_usd']} {target_currency.upper()})"

    return f"Currency {target_currency} not found. Available: {', '.join(r['currency_code'] for r in rates)}"
