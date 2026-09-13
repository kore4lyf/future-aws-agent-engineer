import json
import logging
from pathlib import Path

from pydantic import ValidationError
from strands import tool

from src.schemas.currency import ExchangeRateInput, CurrencyRate, ExchangeResult

logger = logging.getLogger(__name__)

DATASETS_DIR = Path(__file__).parent.parent / "datasets"


@tool
def get_exchange_rate(amount_usd: float, target_currency: str) -> str:
    """Convert an amount from USD to a target currency.

    Args:
        amount_usd: Amount in US dollars to convert.
        target_currency: ISO 4217 currency code (e.g., "EUR", "GBP", "JPY", "CAD").

    Returns:
        A JSON string with conversion details and rate used.
    """
    try:
        validated_input = ExchangeRateInput(amount_usd=amount_usd, target_currency=target_currency)
    except ValidationError as e:
        return json.dumps({"error": "Invalid conversion parameters", "details": str(e)})

    with open(DATASETS_DIR / "exchange_rates.json", encoding="utf-8") as f:
        rates = json.load(f)

    for rate in rates:
        if rate.get("currency_code", "").upper() == validated_input.target_currency.upper():
            try:
                CurrencyRate.model_validate(rate)
            except ValidationError as e:
                logger.warning("Skipping invalid rate record: %s", e)
                continue
            converted = validated_input.amount_usd * rate["rate_to_usd"]
            result = ExchangeResult(
                amount_usd=validated_input.amount_usd,
                target_currency=validated_input.target_currency.upper(),
                converted_amount=round(converted, 2),
                rate_used=rate["rate_to_usd"],
            )
            return result.model_dump_json(indent=2)

    available = [r.get("currency_code", "") for r in rates]
    return json.dumps({"error": f"Currency {target_currency} not found", "available": available})
