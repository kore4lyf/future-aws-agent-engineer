# =============================================================================
# Analytics Gateway — Lesson 11 Exercise
# =============================================================================
# AI-powered analytics assistant using the gateway pattern:
#   - LambdaGateway: register, discover, invoke tool backends
#   - Agent builds system prompt from gateway.discover_tools() at runtime
#   - @tool shims are thin pass-throughs to gateway.invoke_tool()
#   - stock_price registered dynamically; agent picks it up on rebuild
# =============================================================================

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
# LambdaGateway (provided — do not modify)
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
# Retry helper
# ============================================================================

def run_agent_with_retry(build_fn, query: str, max_retries: int = 2) -> str:
    """Build a fresh agent, run a query, retry on transient failure."""
    for attempt in range(1, max_retries + 1):
        try:
            agent = build_fn()
            return str(agent(query))
        except Exception as exc:
            if attempt == max_retries:
                raise
            print(f"  [retry {attempt}/{max_retries}] {exc}")


# ============================================================================
# Build analytics agent — system prompt from gateway registry
# ============================================================================

def build_analytics_agent(gateway: LambdaGateway) -> Agent:
    """Construct agent whose tool catalog is derived from the gateway."""
    model = BedrockModel(
        model_id=NOVA_LITE_MODEL,
        region_name=AWS_REGION,
        temperature=0.1,
    )

    available = gateway.discover_tools()
    tool_list = "\n".join(
        f"  - {t['name']}: {t['description']}" for t in available
    )

    system_prompt = f"""You are a data analytics agent. You have access to the following
tools via AgentCore Gateway:

{tool_list}

Use the appropriate tool for each query. Report results concisely."""

    @tool
    def get_weather(city: str) -> str:
        return json.dumps(gateway.invoke_tool("weather_lambda", {"city": city}))

    @tool
    def convert_currency(from_currency: str, to_currency: str, amount: float = 1.0) -> str:
        return json.dumps(gateway.invoke_tool("currency_lambda", {
            "from_currency": from_currency,
            "to_currency": to_currency,
            "amount": amount,
        }))

    @tool
    def get_news(category: str = "") -> str:
        params = {"category": category} if category else {}
        return json.dumps(gateway.invoke_tool("news_api", params))

    @tool
    def stock_price(symbol: str) -> str:
        return json.dumps(gateway.invoke_tool("stock_price", {"symbol": symbol}))

    return Agent(
        model=model,
        system_prompt=system_prompt,
        tools=[get_weather, convert_currency, get_news, stock_price],
    )


# ============================================================================
# MAIN
# ============================================================================

def main() -> None:
    print("=" * 70)
    print("Lesson 11 Exercise — Analytics Gateway")
    print("=" * 70)

    gateway = LambdaGateway(
        name="analytics-gateway",
        description="Central registry for analytics tool backends",
    )

    print("\n[1] Registering initial backends...")
    gateway.register_target(
        "weather_lambda",
        "Look up current weather conditions for a given city, including temperature, humidity, and wind.",
        WEATHER_LAMBDA,
    )
    gateway.register_target(
        "currency_lambda",
        "Convert an amount between two currencies using live exchange rates.",
        CURRENCY_LAMBDA,
    )
    gateway.register_target(
        "news_api",
        "Get the latest news headlines, optionally filtered by category.",
        NEWS_LAMBDA,
    )
    print(f"  Registered: {list(gateway.targets.keys())}")

    queries = [
        "What is the weather in Tokyo?",
        "Convert 500 USD to EUR.",
        "What are the latest AI news headlines?",
    ]

    for q in queries:
        print(f"\n[2] Query: {q}")
        response = run_agent_with_retry(build_analytics_agent, q)
        print(f"  Output: {response[:250]}")

    print("\n[3] Dynamically registering stock_price...")
    gateway.register_target(
        "stock_price",
        "Get current stock price for any ticker symbol.",
        STOCK_PRICE_LAMBDA,
    )
    print(f"  Registered: {list(gateway.targets.keys())}")

    q = "What is the current stock price of AMZN?"
    print(f"\n[4] Query (dynamic tool): {q}")
    response = run_agent_with_retry(build_analytics_agent, q)
    print(f"  Output: {response[:250]}")

    print("\n[5] Invocation log:")
    for entry in gateway.invocation_log:
        print(f"  {entry['tool']:20s}  params={entry['params']}  status={entry['result_status']}")

    print("\n" + "=" * 70)
    print("Analytics gateway demo complete")
    print("=" * 70)


if __name__ == "__main__":
    main()
