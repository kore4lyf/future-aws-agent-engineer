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
    result = fds.to_dynamo({"price": 9.99, "nested": {"total": 12.5}, "tags": [1.5]})
    assert isinstance(result["price"], Decimal)
    assert isinstance(result["nested"]["total"], Decimal)
    assert isinstance(result["tags"][0], Decimal)


def test_from_dynamo_converts_decimal_types():
    result = fds.from_dynamo({"price": Decimal("9.99"), "version": Decimal("3")})
    assert result["price"] == 9.99
    assert isinstance(result["price"], float)
    assert result["version"] == 3
    assert isinstance(result["version"], int)


# --- create_order ---

def test_create_order_seeds_version_zero_and_ttl():
    mock_table = MagicMock()
    with patch.object(fds, "order_table", mock_table), \
         patch.object(fds, "_record_write"):
        result = fds.create_order(
            "ORD-001", "Alice", "Pasta Palace",
            [{"name": "Spaghetti", "price": 12.50, "qty": 2}],
            distance_mi=6.0,
        )
    mock_table.put_item.assert_called_once()
    item = mock_table.put_item.call_args[1]["Item"]
    assert item["version"] == 0
    assert item["status"] == "placed"
    assert item["driver"] is None
    assert item["price"] is None
    assert item["ttl"] > 0
    # 2-hour TTL: ttl - created epoch ~= 7200
    import time
    assert abs(item["ttl"] - (int(time.time()) + 7200)) < 5
    assert result["version"] == 0


# --- Optimistic locking: update_order ---

def test_update_order_increments_version():
    mock_table = MagicMock()
    mock_table.get_item.return_value = {
        "Item": {"order_id": "O1", "version": 0, "status": "placed"}
    }
    with patch.object(fds, "order_table", mock_table), \
         patch.object(fds, "_record_write"), \
         patch.object(fds, "_record_conflict"):
        result = fds.update_order("O1", {"price": 25.5})
    assert result["version"] == 1
    assert result["price"] == 25.5
    put_kwargs = mock_table.put_item.call_args[1]
    assert put_kwargs["ConditionExpression"] == "version = :v"
    assert put_kwargs["ExpressionAttributeValues"][":v"] == 0


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
        result = fds.update_order("O1", {"driver": "Marcus"})

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
            fds.update_order("O1", {"price": 1.0}, max_retries=3)

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
            fds.update_order("O1", {"price": 1.0})
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
        "Item": {"order_id": "O1", "version": 2, "price": Decimal("25.5")}
    }
    with patch.object(fds, "order_table", mock_table):
        result = fds.get_order("O1")
    assert result["order_id"] == "O1"
    assert result["price"] == 25.5
    mock_table.get_item.assert_called_once_with(Key={"order_id": "O1"})


# --- recover_order ---

def test_recover_order_resets_driver_and_price_to_none():
    mock_table = MagicMock()
    mock_table.get_item.return_value = {
        "Item": {
            "order_id": "O1",
            "version": 4,
            "customer": "Carol",
            "restaurant": "Burger Barn",
            "status": "driver_assigned",
            "driver": "Marcus",
            "vehicle": "Toyota Camry",
            "price": Decimal("18.5"),
        }
    }
    with patch.object(fds, "order_table", mock_table), \
         patch.object(fds, "_record_write"):
        result = fds.recover_order("O1")
    assert result["status"] == "cancelled"
    assert result["driver"] is None
    assert result["price"] is None
    assert result["version"] == 5
    assert result["customer"] == "Carol"
    assert "cancelled_at" in result


def test_recover_already_cancelled_order_is_noop():
    mock_table = MagicMock()
    mock_table.get_item.return_value = {
        "Item": {"order_id": "O1", "version": 5, "status": "cancelled", "customer": "Carol"}
    }
    with patch.object(fds, "order_table", mock_table):
        result = fds.recover_order("O1")
    assert result["status"] == "cancelled"
    mock_table.put_item.assert_not_called()


def test_recover_order_retries_on_conflict():
    mock_table = MagicMock()
    mock_table.get_item.side_effect = [
        {"Item": {"order_id": "O1", "version": 4, "status": "placed", "driver": "Marcus", "price": Decimal("10")}},
        {"Item": {"order_id": "O1", "version": 5, "status": "placed", "driver": "Marcus", "price": Decimal("10")}},
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

def test_confirm_restaurant_always_accepts():
    order = {"restaurant": "Pasta Palace", "distance_mi": 6.0}
    result = fds.confirm_restaurant(order)
    assert result["confirmed"] is True
    assert result["restaurant"] == "Pasta Palace"
    # 25 + round(6 * 1.5) = 25 + 9 = 34
    assert result["eta_minutes"] == 34


def test_select_driver_picks_highest_rated():
    driver = fds.select_driver("ORD-001")
    assert driver["name"] == "Marcus"
    assert driver["rating"] == 4.9


def test_compute_price_standard_order():
    items = [
        {"name": "Spaghetti", "price": 12.50, "qty": 2},  # 25.00
        {"name": "Tiramisu", "price": 7.00, "qty": 1},     # 7.00
    ]
    # subtotal=32.00, delivery=2.99, service=3.20, tax=2.56, total=40.75
    result = fds.compute_price(items, 6.0)
    assert result["subtotal"] == 32.00
    assert result["delivery_fee"] == 2.99
    assert result["service_fee"] == 3.20
    assert result["tax"] == 2.56
    assert result["total"] == 40.75


def test_next_status_pipeline():
    assert fds.next_status("placed") == "confirmed"
    assert fds.next_status("confirmed") == "driver_assigned"
    assert fds.next_status("driver_assigned") == "out_for_delivery"
    assert fds.next_status("out_for_delivery") == "delivered"
    assert fds.next_status("delivered") == "delivered"


# --- Concurrent writes through ThreadPoolExecutor ---

def test_concurrent_updates_do_not_lose_fields():
    """Four writers race on the same record; no field may be lost."""
    store = {"order_id": "O1", "version": 0, "status": "placed", "driver": None, "price": None}
    lock = threading.Lock()

    class FakeTable:
        def get_item(self, Key):
            import copy
            with lock:
                return {"Item": copy.deepcopy(store)}

        def put_item(self, Item, ConditionExpression=None, ExpressionAttributeValues=None):
            with lock:
                if ExpressionAttributeValues and store["version"] != ExpressionAttributeValues[":v"]:
                    raise _conditional_failed()
                store.clear()
                store.update(Item)

    with patch.object(fds, "order_table", FakeTable()), \
         patch.object(fds, "_record_write"), \
         patch.object(fds, "_record_conflict"):

        def write_slice(updates):
            return fds.update_order("O1", updates, max_retries=20)

        slices = [
            {"restaurant_confirmed": True, "status": "confirmed"},
            {"driver": "Marcus", "vehicle": "Toyota Camry", "status": "driver_assigned"},
            {"price": 40.75, "currency": "USD"},
            {"status": "delivered"},
        ]
        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = [pool.submit(write_slice, s) for s in slices]
            for f in futures:
                f.result()

    assert store["restaurant_confirmed"] is True
    assert store["driver"] == "Marcus"
    assert store["price"] == 40.75
    assert store["status"] == "delivered"
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
            "customer": "TestCustomer", "restaurant": "TestResto",
            "items": [{"name": "Burger", "price": Decimal("10.0"), "qty": 1}],
            "distance_mi": Decimal("5.0"),
            "status": "placed", "driver": None, "price": None,
        })
        r1 = fds.update_order(order_id, {"driver": "Marcus", "vehicle": "Toyota Camry"})
        assert r1["version"] == 1
        r2 = fds.update_order(order_id, {"price": 18.5, "currency": "USD"})
        assert r2["version"] == 2
        assert r2["driver"] == "Marcus"
        assert r2["price"] == 18.5

        item = table.get_item(Key={"order_id": order_id})["Item"]
        assert int(item["version"]) == 2
        assert item["driver"] == "Marcus"
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
            "customer": "TestCustomer", "restaurant": "TestResto",
            "items": [{"name": "Burger", "price": Decimal("10.0"), "qty": 1}],
            "distance_mi": Decimal("5.0"),
            "status": "placed", "driver": None, "price": None,
        })
        fds.update_order(order_id, {"driver": "Sofia", "status": "driver_assigned"})
        fds.update_order(order_id, {"price": 22.0})

        final = fds.recover_order(order_id)
        assert final["status"] == "cancelled"
        assert final["driver"] is None
        assert final["price"] is None
    finally:
        table.delete_item(Key={"order_id": order_id})
