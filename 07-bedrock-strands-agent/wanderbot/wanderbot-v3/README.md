# WanderBot v3 — Structured Outputs with Pydantic

Horizon Travel's AI travel assistant with validated, schema-conformant JSON outputs.

## Project Structure

```
wanderbot-v3/
├── src/
│   ├── main.py                    # Agent entrypoint
│   ├── datasets/
│   │   ├── flights.json
│   │   ├── hotels.json
│   │   └── exchange_rates.json
│   ├── tools/
│   │   ├── flights.py             # search_flights
│   │   ├── hotels.py              # search_hotels
│   │   └── currency.py            # get_exchange_rate
│   ├── schemas/
│   │   ├── flights.py             # FlightInput, Flight, FlightSearchResult
│   │   ├── hotels.py              # HotelInput, Hotel, HotelSearchResult
│   │   └── currency.py            # ExchangeRateInput, CurrencyRate, ExchangeResult
│   └── prompts/
│       └── system.py              # SYSTEM_PROMPT
├── pyproject.toml
└── .bedrock_agentcore.yaml        # entrypoint: src/main.py
```

## Finding Things

| What | Where | How |
|------|-------|-----|
| Tools | `src/tools/` | grep `@tool` |
| Schemas | `src/schemas/` | Pydantic `BaseModel` |
| Prompt | `src/prompts/system.py` | `SYSTEM_PROMPT` |
| Datasets | `src/datasets/` | JSON files |
| Entrypoint | `src/main.py` | `@app.entrypoint` |

## Tools

| Tool | Input | Output |
|------|-------|--------|
| `search_flights` | `FlightInput` | `FlightSearchResult` |
| `search_hotels` | `HotelInput` | `HotelSearchResult` |
| `get_exchange_rate` | `ExchangeRateInput` | `ExchangeResult` |

## Dev

```bash
agentcore dev
agentcore invoke --dev '{"message": "Find flights from BCN to FCO on 2026-03-20"}'
```

## Deploy

```bash
agentcore deploy
agentcore invoke '{"message": "Find flights from BCN to FCO on 2026-03-20"}'
```
