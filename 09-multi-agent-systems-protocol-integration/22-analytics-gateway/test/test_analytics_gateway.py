import json
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("AWS_ACCESS_KEY_ID", "")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "")
os.environ.setdefault("AWS_SESSION_TOKEN", "")
os.environ.setdefault("AWS_REGION", "us-east-1")
os.environ.setdefault("NOVA_LITE_MODEL", "amazon.nova-lite-v1:0")

import analytics_gateway as ag


# --- LambdaGateway ---

def test_gateway_register_and_discover():
    gw = ag.LambdaGateway("test", "test gateway")
    gw.register_target("weather_lambda", "Get weather", "fn-weather")
    tools = gw.discover_tools()
    assert len(tools) == 1
    assert tools[0]["name"] == "weather_lambda"


def test_gateway_discover_filters_by_query():
    gw = ag.LambdaGateway("test", "test gateway")
    gw.register_target("weather_lambda", "Get weather", "fn-weather")
    gw.register_target("currency_lambda", "Convert currencies", "fn-currency")
    tools = gw.discover_tools(query="currency")
    assert len(tools) == 1
    assert tools[0]["name"] == "currency_lambda"


def test_gateway_invoke_tool_logs():
    gw = ag.LambdaGateway("test", "test gateway")
    gw.register_target("weather_lambda", "Get weather", "fn-weather")
    mock_lambda = MagicMock()
    mock_lambda.invoke.return_value = {"Payload": MagicMock(read=MagicMock(return_value=b'{"status": "success"}'))}
    gw._lambda_client = mock_lambda
    result = gw.invoke_tool("weather_lambda", {"city": "Tokyo"})
    assert result["status"] == "success"
    assert len(gw.invocation_log) == 1
    assert gw.invocation_log[0]["tool"] == "weather_lambda"


# --- Agent construction ---

def test_build_agent_uses_gateway_discovery():
    gw = ag.LambdaGateway("test", "test gateway")
    gw.register_target("weather_lambda", "Get weather", "fn-weather")
    gw.register_target("currency_lambda", "Convert currencies", "fn-currency")
    with patch.object(ag, "BedrockModel"):
        agent = ag.build_analytics_agent(gw)
    tool_names = list(agent.tool_registry.registry.keys())
    assert "get_weather" in tool_names
    assert "convert_currency" in tool_names


def test_agent_system_prompt_includes_gateway_discovery():
    gw = ag.LambdaGateway("test", "test gateway")
    gw.register_target("weather_lambda", "Look up weather for a city", "fn-weather")
    with patch.object(ag, "BedrockModel"):
        agent = ag.build_analytics_agent(gw)
    assert "weather_lambda" in agent.system_prompt


def test_agent_temperature_is_deterministic():
    gw = ag.LambdaGateway("test", "test gateway")
    gw.register_target("weather_lambda", "Get weather", "fn-weather")
    with patch.object(ag, "BedrockModel") as mock_bm:
        ag.build_analytics_agent(gw)
    assert mock_bm.call_args.kwargs.get("temperature") == 0.1


# --- run_agent_with_retry ---

def test_run_agent_with_retry_success():
    gw = ag.LambdaGateway("test", "test gateway")
    gw.register_target("weather_lambda", "Get weather", "fn-weather")

    fake_response = "weather in tokyo is 22c"

    def build():
        with patch.object(ag, "BedrockModel"):
            agent = ag.build_analytics_agent(gw)
        agent_mock = MagicMock(return_value=fake_response)
        return agent_mock

    result = ag.run_agent_with_retry(build, "What is the weather in Tokyo?")
    assert "tokyo" in result.lower()


def test_run_agent_with_retry_retries_on_failure():
    call_count = 0

    def flaky_build():
        nonlocal call_count
        call_count += 1
        if call_count < 2:
            raise RuntimeError("transient failure")
        with patch.object(ag, "BedrockModel"):
            return ag.build_analytics_agent(ag.LambdaGateway("test", "test"))

    result = ag.run_agent_with_retry(flaky_build, "test query", max_retries=2)
    assert call_count == 2


# --- Dynamic registration ---

def test_dynamic_tool_appears_after_registration():
    gw = ag.LambdaGateway("test", "test gateway")
    gw.register_target("weather_lambda", "Get weather", "fn-weather")
    gw.register_target("currency_lambda", "Convert currencies", "fn-currency")
    gw.register_target("news_api", "Get news", "fn-news")
    initial = {t["name"] for t in gw.discover_tools(query="")}
    assert "stock_price" not in initial
    gw.register_target("stock_price", "Get stock price", "fn-stock")
    after = {t["name"] for t in gw.discover_tools(query="")}
    assert "stock_price" in after


def test_rebuilt_agent_sees_new_tool():
    gw = ag.LambdaGateway("test", "test gateway")
    gw.register_target("weather_lambda", "Get weather", "fn-weather")
    with patch.object(ag, "BedrockModel"):
        agent1 = ag.build_analytics_agent(gw)
    tools_v1_gateway = {t["name"] for t in gw.discover_tools(query="")}
    assert "stock_price" not in tools_v1_gateway
    gw.register_target("stock_price", "Get stock price", "fn-stock")
    with patch.object(ag, "BedrockModel"):
        agent2 = ag.build_analytics_agent(gw)
    tools_v2_gateway = {t["name"] for t in gw.discover_tools(query="")}
    assert "stock_price" in tools_v2_gateway
    assert "stock_price" in agent2.tool_registry.registry


# --- Tool shims delegate to gateway ---

def test_weather_tool_delegates_to_gateway():
    gw = ag.LambdaGateway("test", "test gateway")
    gw.register_target("weather_lambda", "Get weather", "fn-weather")
    mock_lambda = MagicMock()
    mock_lambda.invoke.return_value = {"Payload": MagicMock(read=MagicMock(return_value=b'{"status": "success", "data": {"city": "tokyo", "temp_c": 22}}'))}
    gw._lambda_client = mock_lambda
    with patch.object(ag, "BedrockModel"):
        agent = ag.build_analytics_agent(gw)
    fn = agent.tool_registry.registry["get_weather"]
    raw = fn._tool_function if hasattr(fn, "_tool_function") else fn
    result = json.loads(raw("Tokyo"))
    assert result["status"] == "success"
    assert result["data"]["temp_c"] == 22


def test_currency_tool_delegates_to_gateway():
    gw = ag.LambdaGateway("test", "test gateway")
    gw.register_target("currency_lambda", "Convert currencies", "fn-currency")
    mock_lambda = MagicMock()
    mock_lambda.invoke.return_value = {"Payload": MagicMock(read=MagicMock(return_value=b'{"status": "success", "data": {"converted": 92.0}}'))}
    gw._lambda_client = mock_lambda
    with patch.object(ag, "BedrockModel"):
        agent = ag.build_analytics_agent(gw)
    fn = agent.tool_registry.registry["convert_currency"]
    raw = fn._tool_function if hasattr(fn, "_tool_function") else fn
    result = json.loads(raw("USD", "EUR", 100))
    assert result["status"] == "success"


def test_news_tool_delegates_to_gateway():
    gw = ag.LambdaGateway("test", "test gateway")
    gw.register_target("news_api", "Get news", "fn-news")
    mock_lambda = MagicMock()
    mock_lambda.invoke.return_value = {"Payload": MagicMock(read=MagicMock(return_value=b'{"status": "success", "data": {"articles": []}}'))}
    gw._lambda_client = mock_lambda
    with patch.object(ag, "BedrockModel"):
        agent = ag.build_analytics_agent(gw)
    fn = agent.tool_registry.registry["get_news"]
    raw = fn._tool_function if hasattr(fn, "_tool_function") else fn
    result = json.loads(raw("Markets"))
    assert result["status"] == "success"


# --- Invocation log ---

def test_invocation_log_records_all_calls():
    gw = ag.LambdaGateway("test", "test gateway")
    gw.register_target("weather_lambda", "Get weather", "fn-weather")
    gw.register_target("currency_lambda", "Convert currencies", "fn-currency")
    mock_lambda = MagicMock()
    mock_lambda.invoke.return_value = {"Payload": MagicMock(read=MagicMock(return_value=b'{"status": "success"}'))}
    gw._lambda_client = mock_lambda
    gw.invoke_tool("weather_lambda", {"city": "Tokyo"})
    gw.invoke_tool("currency_lambda", {"from_currency": "USD", "to_currency": "EUR"})
    assert len(gw.invocation_log) == 2
    assert gw.invocation_log[0]["tool"] == "weather_lambda"
    assert gw.invocation_log[1]["params"]["to_currency"] == "EUR"


# --- Test input narrative ---

def test_demo_covers_four_tools_after_dynamic_registration():
    gw = ag.LambdaGateway("test", "test gateway")
    gw.register_target("weather_lambda", "Get weather", "fn-weather")
    gw.register_target("currency_lambda", "Convert currencies", "fn-currency")
    gw.register_target("news_api", "Get news", "fn-news")
    tools_before = {t["name"] for t in gw.discover_tools(query="")}
    assert "stock_price" not in tools_before
    gw.register_target("stock_price", "Get stock price", "fn-stock")
    tools_after = {t["name"] for t in gw.discover_tools(query="")}
    assert tools_after == {"weather_lambda", "currency_lambda", "news_api", "stock_price"}
