# =============================================================================
# Analytics Gateway — Lesson 11 Exercise
# =============================================================================
# AI-powered analytics assistant using the gateway pattern:
#   1. LambdaGateway: register, discover, invoke tool backends
#   2. Agent builds system prompt from gateway registry at runtime
#   3. Tool shims delegate to gateway (no backend logic)
#   4. Dynamic registration: stock_price added without agent restart
# ============================================================================

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

import boto3
from dotenv import load_dotenv
from strands import Agent, tool
from strands.models import BedrockModel

load_dotenv()

sys.path.insert(0, str(Path(__file__).parent))

AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
NOVA_LITE_MODEL = os.environ.get("NOVA_LITE_MODEL", "amazon.nova-lite-v1:0")

AGENTCORE_ROLE_ARN = os.environ.get("AGENTCORE_ROLE_ARN", "").strip()

WEATHER_LAMBDA = os.environ.get("WEATHER_LAMBDA", "lesson11-exercise-weather-api")
CURRENCY_LAMBDA = os.environ.get("CURRENCY_LAMBDA", "lesson11-exercise-currency-api")
NEWS_LAMBDA = os.environ.get("NEWS_LAMBDA", "lesson11-exercise-news-api")
STOCK_PRICE_LAMBDA = os.environ.get("STOCK_PRICE_LAMBDA", "lesson11-exercise-stock-price-api")


# ============================================================================
# LambdaGateway: provided — register, discover, invoke
# ============================================================================

class LambdaGateway:
    """Centralized registry that routes tool calls to AWS Lambda backends."""

    def __init__(self, name: str, description: str):
        self.name = name
        self.description = description
        self.targets: dict[str, dict[str, str]] = {}
        self.invocation_log: list[dict[str, Any]] = []
        self._lambda_client = boto3.client("lambda", region_name=AWS_REGION)

    def register_target(self, name: str, description: str, function_name: str,
                        target_type: str = "lambda") -> None:
        self.targets[name] = {
            "description": description,
            "function_name": function_name,
            "target_type": target_type,
        }

    def discover_tools(self, query: str | None = None) -> list[dict[str, str]]:
        tools = [
            {"name": name, "description": target["description"]}
            for name, target in self.targets.items()
        ]
        if query:
            q = query.lower()
            tools = [t for t in tools if q in t["name"].lower() or q in t["description"].lower()]
        return tools

    def invoke_tool(self, tool_name: str, params: dict[str, Any]) -> dict[str, Any]:
        target = self.targets[tool_name]
        response = self._lambda_client.invoke(
            FunctionName=target["function_name"],
            InvocationType="RequestResponse",
            Payload=json.dumps(params),
        )
        result = json.loads(response["Payload"].read().decode("utf-8"))
        self.invocation_log.append({
            "tool": tool_name,
            "params": params,
            "result_status": result.get("status"),
        })
        return result


# ============================================================================
# Build analytics agent — system prompt from gateway registry
# ============================================================================

def build_analytics_agent(gateway: LambdaGateway) -> Agent:
    """Build agent whose tool catalog comes from the gateway."""
    model = BedrockModel(model_id=NOVA_LITE_MODEL, region_name=AWS_REGION, temperature=0.0)

    tool_list = "\n".join(
        f"  - {t['name']}: {t['description']}"
        for t in gateway.discover_tools()
    )

    system_prompt = f"""You are an AI-powered analytics assistant.
You have access to the following tools via AgentCore Gateway:

{tool_list}

Use the appropriate tool for each query. When a user asks about weather,
currency conversion, news, or stock prices, route the query to the correct
backend and present the result clearly."""

    @tool
    def get_weather(city: str) -> str:
        """Get current weather conditions for a city."""
        result = gateway.invoke_tool("weather_api", {"city": city})
        return json.dumps(result, indent=2)

    @tool
    def convert_currency(from_currency: str, to_currency: str, amount: float = 1.0) -> str:
        """Convert an amount from one currency to another."""
        result = gateway.invoke_tool("currency_api", {
            "from_currency": from_currency,
            "to_currency": to_currency,
            "amount": amount,
        })
        return json.dumps(result, indent=2)

    @tool
    def get_news(category: str = "") -> str:
        """Get latest news articles, optionally filtered by category."""
        params = {"category": category} if category else {}
        result = gateway.invoke_tool("news_api", params)
        return json.dumps(result, indent=2)

    @tool
    def get_stock_price(symbol: str) -> str:
        """Get current stock price and change percentage for a symbol."""
        result = gateway.invoke_tool("stock_price_api", {"symbol": symbol})
        return json.dumps(result, indent=2)

    return Agent(
        model=model,
        system_prompt=system_prompt,
        tools=[get_weather, convert_currency, get_news, get_stock_price],
    )


# ============================================================================
# MAIN
# ============================================================================

def main() -> None:
    print("=" * 70)
    print("Lesson 11 Exercise — Analytics Gateway")
    print("=" * 70)

    gateway = LambdaGateway(name="analytics-gateway",
                           description="Central registry for analytics tool backends")

    # Register initial backends
    print("\n[1] Registering initial backends...")
    gateway.register_target("weather_api", "Get current weather conditions for a city", WEATHER_LAMBDA)
    gateway.register_target("currency_api", "Convert between currencies with live rates", CURRENCY_LAMBDA)
    gateway.register_target("news_api", "Get latest news articles by category", NEWS_LAMBDA)
    print(f"  Registered: {list(gateway.targets.keys())}")

    # Build agent from registry
    print("\n[2] Building analytics agent from gateway...")
    agent = build_analytics_agent(gateway)
    tools = gateway.discover_tools()
    print(f"  Tools discovered: {[t['name'] for t in tools]}")

    # Initial queries
    queries = [
        ("Weather", "What is the weather in Tokyo?"),
        ("Currency", "Convert 100 USD to EUR."),
        ("News", "Show me the latest market news."),
    ]

    for label, query in queries:
        print(f"\n[3] Query ({label}): {query}")
        response = str(agent(query))
        print(f"  Output: {response[:250]}...")

    # Dynamic registration: add stock_price at runtime
    print("\n[4] Dynamically registering stock_price_api...")
    gateway.register_target("stock_price_api", "Get current stock price and change for a symbol", STOCK_PRICE_LAMBDA)
    print(f"  Registered: {list(gateway.targets.keys())}")

    # Rebuild agent so it discovers the new tool
    agent = build_analytics_agent(gateway)
    print(f"  Tools discovered: {[t['name'] for t in gateway.discover_tools()]}")

    # Query using the dynamically added tool
    print("\n[5] Query (stock price, dynamic tool): What is the stock price of AAPL?")
    response = str(agent("What is the stock price of AAPL?"))
    print(f"  Output: {response[:250]}...")

    # Invocation log
    print("\n[6] Invocation log:")
    for entry in gateway.invocation_log:
        print(f"  {entry['tool']:20s} params={entry['params']}  status={entry['result_status']}")

    print("\n" + "=" * 70)
    print("Analytics gateway demo complete")
    print("=" * 70)


if __name__ == "__main__":
    main()
