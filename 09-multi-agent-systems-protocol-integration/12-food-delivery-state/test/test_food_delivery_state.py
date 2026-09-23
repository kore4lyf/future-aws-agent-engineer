import os
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from unittest.mock import MagicMock, patch

import boto3
import pytest
from botocore.exceptions import ClientError

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("AWS_ACCESS_KEY_ID", "")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "")
os.environ.setdefault("AWS_SESSION_TOKEN", "")
os.environ.setdefault("AWS_REGION", "us-east-1")
os.environ.setdefault("ORDER_TABLE", "order-state")

import food_delivery_state as fds


def _conditional_failed():
    return ClientError(
        {"Error": {"Code": "ConditionalCheckFailedException", "Message": "The conditional request failed"}},
        "PutItem",
    )


# --- Conversion helpers ---

def test_to_dynamo_converts_float_to_decimal():
    result = fds.to_dynamo({"total_price": 9.99, "nested": {"tax": 1.5}, "tags": [1.5]})
    assert isinstance(result["total_price"], Decimal)
    assert isinstance(result["nested"]["tax"], Decimal)
    assert isinstance(result["tags"][0], Decimal)


def test_from_dynamo_converts_decimal_types():
    result = fds.from_dynamo({"total_price": Decimal("9.99"), "version": Decimal("3")})
    assert result["total_price"] == 9.99
    assert isinstance(result["total_price"], float)
    assert result["version"] == 3
    assert isinstance(result["version"], int)


# --- create_order ---

def test_create_order_seeds_version_zero_ttl_and_pending_fields():
    mock_table = MagicMock()
    with patch.object(fds, "order_table", mock_table), \
         patch.object(fds, "_record_write"):
        result = fds.create_order(
            "ORD-001", "alice", "Tokyo Ramen House",
            [{"name": "Ramen", "price": 13.50, "qty": 2}],
            address="123 Main St",
            distance_mi=4.0,
        )
    mock_table.put_item.assert_called_once()
    item = mock_table.put_item.call_args[1]["Item"]
    assert item["version"] == 0
    assert item["status"] == "pending"
    assert item["driver"] is None
    assert item["total_price"] is None
    assert item["progress"] == []
    assert item["simulate_rejection"] is False
    assert item["ttl"] > 0
    import time
    assert abs(item["ttl"] - (int(time.time()) + 7200)) < 5
    assert result["version"] == 0


# --- Optimistic locking: update_order ---

def test_update_order_increments_version():
    mock_table = MagicMock()
    mock_table.get_item.return_value = {
        "Item": {"order_id": "O1", "version": 0, "status": "pending"}
    }
    with patch.object(fds, "order_table", mock_table), \
         patch.object(fds, "_record_write"), \
         patch.object(fds, "_record_conflict"):
        result = fds.update_order("O1", {"total_price": 25.5})
    assert result["version"] == 1
    assert result["total_price"] == 25.5
    put_kwargs = mock_table.put_item.call_args[1]
    assert put_kwargs["ConditionExpression"] == "version = :expected_ver"
    assert put_kwargs["ExpressionAttributeValues"][":expected_ver"] == 0


def test_update_order_retries_on_version_conflict_then_succeeds():
    mock_table = MagicMock()
    mock_table.get_item.side_effect = [
        {"Item": {"order_id": "O1", "version": 0}},
        {"Item": {"order_id": "O1", "version": 1}},
    ]
    mock_table.put_item.side_effect = [_conditional_failed(), {}]

    with patch.object(fds, "order_table", mock_table), \
         patch.object(fds, "_record_write") as mock_write, \
         patch.object(fds, "_record_conflict") as mock_conflict, \
         patch.object(fds.time, "sleep") as mock_sleep:
        result = fds.update_order("O1", {"driver": {"driver_id": "DRV-01", "name": "Marcus"}})

    assert result["version"] == 2
    assert mock_table.put_item.call_count == 2
    mock_conflict.assert_called_once()
    mock_sleep.assert_called_once_with(0.1)
    mock_write.assert_called_once()


def test_update_order_raises_after_max_retries():
    mock_table = MagicMock()
    mock_table.get_item.return_value = {"Item": {"order_id": "O1", "version": 0}}
    mock_table.put_item.side_effect = _conditional_failed()

    with patch.object(fds, "order_table", mock_table), \
         patch.object(fds, "_record_conflict"), \
         patch.object(fds.time, "sleep"):
        with pytest.raises(fds.VersionConflictError):
            fds.update_order("O1", {"total_price": 1.0}, max_retries=3)

    assert mock_table.put_item.call_count == 3


def test_update_order_raises_other_client_errors_immediately():
    mock_table = MagicMock()
    mock_table.get_item.return_value = {"Item": {"order_id": "O1", "version": 0}}
    mock_table.put_item.side_effect = ClientError(
        {"Error": {"Code": "ProvisionedThroughputExceededException", "Message": "throttled"}},
        "PutItem",
    )
    with patch.object(fds, "order_table", mock_table), \
         patch.object(fds, "_record_write"), \
         patch.object(fds, "_record_conflict"):
        with pytest.raises(ClientError):
            fds.update_order("O1", {"total_price": 1.0})
    assert mock_table.put_item.call_count == 1


def test_update_order_uses_exponential_backoff_delays():
    mock_table = MagicMock()
    mock_table.get_item.side_effect = [
        {"Item": {"order_id": "O1", "version": 0}},
        {"Item": {"order_id": "O1", "version": 1}},
        {"Item": {"order_id": "O1", "version": 2}},
    ]
    mock_table.put_item.side_effect = [
        _conditional_failed(),
        _conditional_failed(),
        {},
    ]
    with patch.object(fds, "order_table", mock_table), \
         patch.object(fds, "_record_write"), \
         patch.object(fds, "_record_conflict"), \
         patch.object(fds.time, "sleep") as mock_sleep:
        fds.update_order("O1", {"status": "confirmed"})
    delays = [call.args[0] for call in mock_sleep.call_args_list]
    assert delays == [0.1, 0.2]


# --- get_order ---

def test_get_order_returns_item():
    mock_table = MagicMock()
    mock_table.get_item.return_value = {
        "Item": {"order_id": "O1", "version": 2, "total_price": Decimal("25.5")}
    }
    with patch.object(fds, "order_table", mock_table):
        result = fds.get_order("O1")
    assert result["order_id"] == "O1"
    assert result["total_price"] == 25.5
    mock_table.get_item.assert_called_once_with(Key={"order_id": "O1"})


# --- recover_order ---

def test_recover_order_resets_driver_and_total_price_via_update_order():
    mock_table = MagicMock()
    mock_table.get_item.return_value = {
        "Item": {
            "order_id": "O1",
            "version": 4,
            "customer_id": "carlos",
            "status": "confirmed",
            "driver": {"driver_id": "DRV-01", "name": "Marcus"},
            "total_price": Decimal("22.66"),
        }
    }
    with patch.object(fds, "order_table", mock_table), \
         patch.object(fds, "_record_write"):
        result = fds.recover_order("O1")
    assert result["status"] == "cancelled"
    assert result["driver"] is None
    assert result["total_price"] is None
    assert result["version"] == 5
    assert result["progress"] == [
        "Order rejected by restaurant",
        "Partial updates cleaned up",
    ]
    put_kwargs = mock_table.put_item.call_args[1]
    assert put_kwargs["ConditionExpression"] == "version = :expected_ver"


def test_recover_order_retries_on_conflict():
    mock_table = MagicMock()
    mock_table.get_item.side_effect = [
        {"Item": {"order_id": "O1", "version": 4, "status": "confirmed",
                  "driver": {"name": "Marcus"}, "total_price": Decimal("10")}},
        {"Item": {"order_id": "O1", "version": 5, "status": "confirmed",
                  "driver": {"name": "Marcus"}, "total_price": Decimal("10")}},
    ]
    mock_table.put_item.side_effect = [_conditional_failed(), {}]
    with patch.object(fds, "order_table", mock_table), \
         patch.object(fds, "_record_write"), \
         patch.object(fds, "_record_conflict") as mock_conflict, \
         patch.object(fds.time, "sleep"):
        result = fds.recover_order("O1")
    assert result["status"] == "cancelled"
    assert result["version"] == 6
    mock_conflict.assert_called_once()


# --- Pure helpers ---

def test_confirm_restaurant_accepts_normal_order():
    order = {"restaurant": "Tokyo Ramen House", "simulate_rejection": False}
    result = fds.confirm_restaurant(order)
    assert result["confirmed"] is True
    assert result["status"] == "confirmed"


def test_confirm_restaurant_rejects_when_flag_set():
    order = {"restaurant": "Green Garden", "simulate_rejection": True}
    result = fds.confirm_restaurant(order)
    assert result["confirmed"] is False
    assert result["status"] == "rejected"
    assert result["reason"]


def test_select_driver_highest_rated_when_no_memory():
    fds.customer_memory.clear()
    driver = fds.select_driver("alice")
    assert driver["driver_id"] == "DRV-01"
    assert driver["name"] == "Marcus"
    assert driver["rating"] == 4.9
    assert driver["source"] == "highest_rated"
    assert fds.customer_memory["alice"]["preferred_driver"] == "DRV-01"


def test_select_driver_prefers_memory():
    fds.customer_memory.clear()
    fds.customer_memory["bob"] = {"preferred_driver": "DRV-03"}
    driver = fds.select_driver("bob")
    assert driver["driver_id"] == "DRV-03"
    assert driver["source"] == "memory"


def test_select_driver_falls_back_when_preferred_unavailable():
    fds.customer_memory.clear()
    fds.customer_memory["alice"] = {"preferred_driver": "DRV-99"}
    driver = fds.select_driver("alice")
    assert driver["driver_id"] == "DRV-01"
    assert driver["source"] == "highest_rated"


def test_compute_price_with_tax_and_delivery_fee():
    items = [
        {"name": "Ramen", "price": 13.50, "qty": 2},  # 27.00
        {"name": "Gyoza", "price": 6.00, "qty": 1},    # 6.00
    ]
    # subtotal=33.00, tax=2.64, delivery=4.99, total=40.63
    result = fds.compute_price(items)
    assert result["subtotal"] == 33.00
    assert result["tax"] == 2.64
    assert result["delivery_fee"] == 4.99
    assert result["total_price"] == 40.63


def test_append_progress_appends_entry():
    assert fds.append_progress({"progress": ["a"]}, "b") == ["a", "b"]
    assert fds.append_progress({}, "x") == ["x"]


# --- Concurrent writes through ThreadPoolExecutor ---

def test_concurrent_updates_do_not_lose_fields():
    """Four writers race on the same record; no field may be lost."""
    store = {
        "order_id": "O1", "version": 0, "status": "pending",
        "driver": None, "total_price": None, "progress": [],
    }
    lock = threading.Lock()

    class FakeTable:
        def get_item(self, Key):
            import copy
            with lock:
                return {"Item": copy.deepcopy(store)}

        def put_item(self, Item, ConditionExpression=None, ExpressionAttributeValues=None):
            with lock:
                if ExpressionAttributeValues and store["version"] != ExpressionAttributeValues[":expected_ver"]:
                    raise _conditional_failed()
                store.clear()
                store.update(Item)

    with patch.object(fds, "order_table", FakeTable()), \
         patch.object(fds, "_record_write"), \
         patch.object(fds, "_record_conflict"):

        def write_slice(updates):
            return fds.update_order("O1", updates, max_retries=20)

        slices = [
            {"status": "confirmed", "restaurant_confirmed": True,
             "progress": ["Restaurant: confirmed"]},
            {"driver": {"driver_id": "DRV-01", "name": "Marcus"},
             "progress": ["Driver assigned: Marcus"]},
            {"total_price": 40.63, "currency": "USD",
             "progress": ["Price calculated"]},
            {"status": "out_for_delivery",
             "progress": ["Status: out_for_delivery"]},
        ]
        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = [pool.submit(write_slice, s) for s in slices]
            for f in futures:
                f.result()

    # Last successful write of each key wins — none may be missing
    assert store["restaurant_confirmed"] is True
    assert store["driver"]["name"] == "Marcus"
    assert float(store["total_price"]) == 40.63
    assert store["currency"] == "USD"
    assert store["version"] == 4


# --- Agent builders attach the correct tool ---

def test_agent_builders_return_agents_with_one_tool():
    for builder in (
        fds.build_restaurant_confirm_agent,
        fds.build_driver_assign_agent,
        fds.build_price_calculator_agent,
        fds.build_status_tracker_agent,
    ):
        with patch.object(fds, "BedrockModel"):
            agent = builder()
        assert len(agent.tool_registry.registry) == 1


# --- Live tests: real DynamoDB with AWS credentials ---

def test_live_optimistic_locking_roundtrip():
    if not os.getenv("AWS_ACCESS_KEY_ID"):
        pytest.skip("AWS credentials are not set")

    table = boto3.resource("dynamodb", region_name="us-east-1").Table("order-state")
    order_id = "LIVE-001"
    try:
        table.put_item(Item={
            "order_id": order_id, "version": 0,
            "customer_id": "test", "restaurant": "TestResto",
            "items": [{"name": "Burger", "price": Decimal("10.0"), "qty": 1}],
            "address": "1 Test St", "distance_mi": Decimal("5.0"),
            "status": "pending", "driver": None, "total_price": None,
            "progress": [], "simulate_rejection": False,
        })
        r1 = fds.update_order(order_id, {
            "driver": {"driver_id": "DRV-01", "name": "Marcus"},
        })
        assert r1["version"] == 1
        r2 = fds.update_order(order_id, {"total_price": 17.79, "currency": "USD"})
        assert r2["version"] == 2
        assert r2["driver"]["name"] == "Marcus"
        assert r2["total_price"] == 17.79

        item = table.get_item(Key={"order_id": order_id})["Item"]
        assert int(item["version"]) == 2
        assert item["driver"]["name"] == "Marcus"
    finally:
        table.delete_item(Key={"order_id": order_id})


def test_live_recover_order_cancels():
    if not os.getenv("AWS_ACCESS_KEY_ID"):
        pytest.skip("AWS credentials are not set")

    table = boto3.resource("dynamodb", region_name="us-east-1").Table("order-state")
    order_id = "LIVE-002"
    try:
        table.put_item(Item={
            "order_id": order_id, "version": 0,
            "customer_id": "test", "restaurant": "TestResto",
            "items": [{"name": "Burger", "price": Decimal("10.0"), "qty": 1}],
            "address": "1 Test St", "distance_mi": Decimal("5.0"),
            "status": "pending", "driver": None, "total_price": None,
            "progress": [], "simulate_rejection": True,
        })
        fds.update_order(order_id, {
            "driver": {"driver_id": "DRV-02", "name": "Sofia"},
            "status": "confirmed",
        })
        fds.update_order(order_id, {"total_price": 17.79})

        final = fds.recover_order(order_id)
        assert final["status"] == "cancelled"
        assert final["driver"] is None
        assert final["total_price"] is None
        assert final["progress"] == [
            "Order rejected by restaurant",
            "Partial updates cleaned up",
        ]
    finally:
        table.delete_item(Key={"order_id": order_id})
