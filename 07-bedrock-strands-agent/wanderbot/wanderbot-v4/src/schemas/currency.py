from pydantic import BaseModel, Field


class ExchangeRateInput(BaseModel):
    """Validated input for currency conversion."""
    amount_usd: float = Field(description="Amount in US dollars to convert")
    target_currency: str = Field(description="ISO 4217 currency code, e.g. EUR, GBP, JPY")


class CurrencyRate(BaseModel):
    """Validated currency rate record."""
    currency_code: str = Field(description="ISO 4217 code, e.g. EUR")
    currency_name: str = Field(description="Currency name, e.g. Euro")
    rate_to_usd: float = Field(description="Conversion rate: 1 USD = X target currency")


class ExchangeResult(BaseModel):
    amount_usd: float = Field(description="Original amount in USD")
    target_currency: str = Field(description="Target currency code")
    converted_amount: float = Field(description="Converted amount in target currency")
    rate_used: float = Field(description="Exchange rate applied")
