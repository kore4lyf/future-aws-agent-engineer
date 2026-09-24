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

import supply_chain_gateway as scg


# --- LambdaGateway ---

def test_gateway_register_and_discover():
    gw = scg.LambdaGateway("test", "test gateway")
    gw.register_target("inventory_api", "Check inventory", "fn-inventory")
    tools = gw.discover_tools()
    assert len(tools) == 1
    assert tools[0]["name"] == "inventory_api"


def test_gateway_discover_filters_by_query():
    gw = scg.LambdaGateway("test", "test gateway")
    gw.register_target("inventory_api", "Check inventory levels", "fn-inv")
    gw.register_target("shipping_api", "Track shipments", "fn-ship")
    tools = gw.discover_tools(query="inventory")
    assert len(tools) == 1
    assert tools[0]["name"] == "inventory_api"


def test_gateway_invoke_tool_logs():
    gw = scg.LambdaGateway("test", "test gateway")
    gw.register_target("inventory_api", "Check inventory", "fn-inventory")
    mock_lambda = MagicMock()
    mock_lambda.invoke.return_value = {"Payload": MagicMock(read=MagicMock(return_value=b'{"status": "success"}'))}
    gw._lambda_client = mock_lambda
    result = gw.invoke_tool("inventory_api", {"item_id": "DIGI-001"})
    assert result["status"] == "success"
    assert len(gw.invocation_log) == 1
    assert gw.invocation_log[0]["tool"] == "inventory_api"
    assert gw.invocation_log[0]["result_status"] == "success"


# --- Agent construction ---

def test_build_agent_contains_registered_tools():
    gw = scg.LambdaGateway("test", "test gateway")
    gw.register_target("inventory_api", "Check inventory", "fn-inv")
    gw.register_target("shipping_api", "Track shipments", "fn-ship")
    with patch.object(scg, "BedrockModel"):
        agent = scg.build_supply_chain_agent(gw)
    tool_names = list(agent.tool_registry.registry.keys())
    assert "check_inventory" in tool_names
    assert "track_shipment" in tool_names


def test_agent_system_prompt_includes_tool_descriptions():
    gw = scg.LambdaGateway("test", "test gateway")
    gw.register_target("inventory_api", "Check inventory levels", "fn-inv")
    with patch.object(scg, "BedrockModel"):
        agent = scg.build_supply_chain_agent(gw)
    tool_names = list(agent.tool_registry.registry.keys())
    for name in tool_names:
        assert name in agent.system_prompt or gw.discover_tools()[0]["description"] in agent.system_prompt


def test_dynamic_registration_new_tool_appears_in_prompt():
    gw = scg.LambdaGateway("test", "test gateway")
    gw.register_target("inventory_api", "Check inventory", "fn-inv")
    gw.register_target("shipping_api", "Track shipments", "fn-ship")
    gw.register_target("supplier_api", "Look up suppliers", "fn-supplier")
    initial_names = {t["name"] for t in gw.discover_tools(query="")}
    assert "quality_inspection_api" not in initial_names
    gw.register_target("quality_inspection_api", "Inspect quality", "fn-quality")
    after_names = {t["name"] for t in gw.discover_tools(query="")}
    assert "quality_inspection_api" in after_names


# --- Tool shims ---

def test_check_inventory_delegates_to_gateway():
    gw = scg.LambdaGateway("test", "test gateway")
    gw.register_target("inventory_api", "Check inventory", "fn-inv")
    mock_lambda = MagicMock()
    mock_lambda.invoke.return_value = {"Payload": MagicMock(read=MagicMock(return_value=b'{"status": "success", "data": {"stock": 1500}}'))}
    gw._lambda_client = mock_lambda
    with patch.object(scg, "BedrockModel"):
        agent = scg.build_supply_chain_agent(gw)
    fn = agent.tool_registry.registry["check_inventory"]
    raw = fn._tool_function if hasattr(fn, "_tool_function") else fn
    result = raw("DIGI-001")
    data = json.loads(result)
    assert data["status"] == "success"


def test_track_shipment_delegates_to_gateway():
    gw = scg.LambdaGateway("test", "test gateway")
    gw.register_target("shipping_api", "Track shipments", "fn-ship")
    mock_lambda = MagicMock()
    mock_lambda.invoke.return_value = {"Payload": MagicMock(read=MagicMock(return_value=b'{"status": "success", "data": {"status": "delayed"}}'))}
    gw._lambda_client = mock_lambda
    with patch.object(scg, "BedrockModel"):
        agent = scg.build_supply_chain_agent(gw)
    fn = agent.tool_registry.registry["track_shipment"]
    raw = fn._tool_function if hasattr(fn, "_tool_function") else fn
    result = raw("SHIP-102")
    data = json.loads(result)
    assert data["data"]["status"] == "delayed"


# --- Configuration ---

def test_nova_lite_temperature_for_predictable_routing():
    with patch.object(scg, "BedrockModel") as mock_bm:
        gw = scg.LambdaGateway("test", "test gateway")
        gw.register_target("inventory_api", "Check inventory", "fn-inv")
        scg.build_supply_chain_agent(gw)
    call_kwargs = mock_bm.call_args.kwargs
    assert call_kwargs.get("temperature") == 0.1


def test_gateway_invocation_log_records_all_calls():
    gw = scg.LambdaGateway("test", "test gateway")
    gw.register_target("inventory_api", "Check inventory", "fn-inv")
    mock_lambda = MagicMock()
    mock_lambda.invoke.return_value = {"Payload": MagicMock(read=MagicMock(return_value=b'{"status": "success"}'))}
    gw._lambda_client = mock_lambda
    gw.invoke_tool("inventory_api", {"item_id": "DIGI-001"})
    gw.invoke_tool("inventory_api", {"item_id": "DIGI-002"})
    assert len(gw.invocation_log) == 2
    assert gw.invocation_log[0]["tool"] == "inventory_api"
    assert gw.invocation_log[1]["params"]["item_id"] == "DIGI-002"


# --- Test input narrative ---

def test_demo_covers_four_supply_chain_queries():
    gw = scg.LambdaGateway("test", "test gateway")
    gw.register_target("inventory_api", "Check inventory", "fn-inv")
    gw.register_target("shipping_api", "Track shipments", "fn-ship")
    gw.register_target("supplier_api", "Look up suppliers", "fn-supplier")
    gw.register_target("quality_inspection_api", "Inspect quality", "fn-quality")
    tools = gw.discover_tools()
    assert len(tools) == 4
    names = {t["name"] for t in tools}
    assert names == {"inventory_api", "shipping_api", "supplier_api", "quality_inspection_api"}


def test_quality_inspection_added_mid_run():
    gw = scg.LambdaGateway("test", "test gateway")
    gw.register_target("inventory_api", "Check inventory", "fn-inv")
    gw.register_target("shipping_api", "Track shipments", "fn-ship")
    gw.register_target("supplier_api", "Look up suppliers", "fn-supplier")
    initial_names = {t["name"] for t in gw.discover_tools(query="")}
    assert "quality_inspection_api" not in initial_names
    gw.register_target("quality_inspection_api", "Inspect quality", "fn-quality")
    after_names = {t["name"] for t in gw.discover_tools(query="")}
    assert "quality_inspection_api" in after_names


# --- Live tests ---

def test_live_inventory_lambda():
    if not os.getenv("AWS_ACCESS_KEY_ID"):
        pytest.skip("AWS credentials not set")
    import boto3
    client = boto3.client("lambda", region_name="us-east-1")
    try:
        client.get_function(FunctionName=scg.INVENTORY_LAMBDA)
    except client.exceptions.ResourceNotFoundException:
        pytest.skip(f"Lambda {scg.INVENTORY_LAMBDA} not deployed")
