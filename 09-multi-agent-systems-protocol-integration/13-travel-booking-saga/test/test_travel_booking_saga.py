import os
import sys
from unittest.mock import MagicMock, patch

import boto3
import pytest
from botocore.exceptions import ClientError

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("AWS_ACCESS_KEY_ID", "")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "")
os.environ.setdefault("AWS_SESSION_TOKEN", "")
os.environ.setdefault("AWS_REGION", "us-east-1")
os.environ.setdefault("SAGA_TABLE", "saga-state")

import travel_booking_saga as tbs


def _conditional_failed():
    return ClientError(
        {"Error": {"Code": "ConditionalCheckFailedException", "Message": "The conditional request failed"}},
        "UpdateItem",
    )


# --- Conversion helpers ---

def test_to_dynamo_converts_float_to_decimal():
    from decimal import Decimal
    result = tbs.to_dynamo({"price": 9.99, "nested": {"tax": 1.5}})
    assert isinstance(result["price"], Decimal)
    assert isinstance(result["nested"]["tax"], Decimal)


def test_from_dynamo_converts_decimal_types():
    from decimal import Decimal
    result = tbs.from_dynamo({"fee": Decimal("9.99"), "compensations_done": Decimal("3")})
    assert result["fee"] == 9.99
    assert isinstance(result["fee"], float)
    assert result["compensations_done"] == 3
    assert isinstance(result["compensations_done"], int)


# --- create_saga / get_saga ---

def test_create_saga_seeds_three_pending_steps():
    mock_table = MagicMock()
    with patch.object(tbs, "saga_table", mock_table):
        result = tbs.create_saga("SAGA-001", {"package_id": "PKG-001", "customer": "Alice"})
    mock_table.put_item.assert_called_once()
    item = mock_table.put_item.call_args[1]["Item"]
    assert item["saga_id"] == "SAGA-001"
    assert item["status"] == "running"
    assert item["current_phase"] == "forward"
    assert item["lock"] is False
    assert item["compensations_done"] == 0
    assert item["compensations_needed"] == 0
    assert item["refund_total"] == 0
    assert [s["name"] for s in item["steps"]] == ["flight", "hotel", "car"]
    assert all(s["status"] == "pending" for s in item["steps"])
    assert all(s["booking_ref"] is None for s in item["steps"])
    assert all(s["compensation_ref"] is None for s in item["steps"])
    assert result["status"] == "running"


def test_get_saga_returns_item():
    mock_table = MagicMock()
    mock_table.get_item.return_value = {
        "Item": {"saga_id": "S1", "compensations_done": 2, "lock": False}
    }
    with patch.object(tbs, "saga_table", mock_table):
        result = tbs.get_saga("S1")
    assert result["compensations_done"] == 2
    mock_table.get_item.assert_called_once_with(Key={"saga_id": "S1"})


# --- update_step ---

def test_update_step_patches_one_step():
    mock_table = MagicMock()
    mock_table.get_item.return_value = {
        "Item": {
            "saga_id": "S1",
            "status": "running",
            "steps": [
                {"name": "flight", "status": "pending", "detail": None},
                {"name": "hotel", "status": "pending", "detail": None},
                {"name": "car", "status": "pending", "detail": None},
            ],
        }
    }
    with patch.object(tbs, "saga_table", mock_table):
        result = tbs.update_step("S1", 1, {"status": "executing"})
    assert result["steps"][1]["status"] == "executing"
    assert result["steps"][0]["status"] == "pending"
    saved = mock_table.put_item.call_args[1]["Item"]
    assert saved["steps"][1]["status"] == "executing"


# --- Distributed lock ---

def test_acquire_lock_succeeds_when_free():
    mock_table = MagicMock()
    with patch.object(tbs, "saga_table", mock_table), \
         patch.object(tbs.time, "sleep"):
        assert tbs.acquire_lock("S1") is True
    kwargs = mock_table.update_item.call_args[1]
    assert kwargs["ConditionExpression"] == "#lk = :want"
    assert kwargs["ExpressionAttributeNames"]["#lk"] == "lock"
    assert kwargs["ExpressionAttributeValues"][":want"] is False
    assert kwargs["ExpressionAttributeValues"][":expected"] is True


def test_acquire_lock_retries_then_fails_when_held():
    mock_table = MagicMock()
    mock_table.update_item.side_effect = _conditional_failed()
    with patch.object(tbs, "saga_table", mock_table), \
         patch.object(tbs.time, "sleep") as mock_sleep:
        assert tbs.acquire_lock("S1", max_retries=3) is False
    assert mock_table.update_item.call_count == 3
    assert mock_sleep.call_count == 3


def test_release_lock_clears_flag():
    mock_table = MagicMock()
    with patch.object(tbs, "saga_table", mock_table):
        tbs.release_lock("S1")
    kwargs = mock_table.update_item.call_args[1]
    assert kwargs["ExpressionAttributeNames"]["#lk"] == "lock"
    assert kwargs["ExpressionAttributeValues"][":no"] is False


# --- Atomic barrier ---

def test_initialize_barrier_sets_counts():
    mock_table = MagicMock()
    with patch.object(tbs, "saga_table", mock_table):
        tbs.initialize_barrier("S1", needed=2)
    kwargs = mock_table.update_item.call_args[1]
    assert kwargs["ExpressionAttributeValues"][":n"] == 2
    assert kwargs["ExpressionAttributeValues"][":z"] == 0


def test_increment_barrier_uses_add_expression():
    mock_table = MagicMock()
    mock_table.update_item.return_value = {
        "Attributes": {"compensations_done": 1, "compensations_needed": 2}
    }
    with patch.object(tbs, "saga_table", mock_table):
        done, needed = tbs.increment_barrier("S1")
    assert (done, needed) == (1, 2)
    kwargs = mock_table.update_item.call_args[1]
    assert kwargs["UpdateExpression"] == "ADD compensations_done :one"
    assert kwargs["ExpressionAttributeValues"][":one"] == 1
    assert kwargs["ReturnValues"] == "ALL_NEW"


# --- Pure booking logics ---

def test_book_flight_success():
    result = tbs.book_flight_logic({"package_id": "PKG-001", "origin": "SFO", "destination": "NYC"})
    assert result["confirmation"] == "FLT-001"
    assert result["route"] == "SFO->NYC"


def test_book_flight_raises_when_fail_at_flight():
    with pytest.raises(RuntimeError, match="Airline inventory"):
        tbs.book_flight_logic({"package_id": "PKG-001", "fail_at": "flight"})


def test_book_hotel_raises_when_fail_at_hotel():
    with pytest.raises(RuntimeError, match="No rooms available"):
        tbs.book_hotel_logic({"package_id": "PKG-003", "fail_at": "hotel"})


def test_book_car_raises_when_fail_at_car():
    with pytest.raises(RuntimeError, match="No cars available at destination"):
        tbs.book_car_logic({"package_id": "PKG-002", "fail_at": "car"})


def test_cancel_logics_return_refund_amounts():
    package = {
        "package_id": "PKG-001",
        "flight_price": 1200,
        "hotel_price": 900,
        "car_price": 210,
    }
    flight = tbs.cancel_flight_logic(package)
    hotel = tbs.cancel_hotel_logic(package)
    car = tbs.cancel_car_logic(package)
    assert flight["cancelled"] is True
    assert flight["confirmation"] == "FLT-001"
    assert flight["refund_amount"] == 1200
    assert hotel["confirmation"] == "HTL-001"
    assert hotel["refund_amount"] == 900
    assert car["refund_amount"] == 210


def test_book_hotel_uses_htl_prefix():
    result = tbs.book_hotel_logic({"package_id": "PKG-001", "nights": 5})
    assert result["confirmation"] == "HTL-001"
    assert result["nights"] == 5


# --- Agent builders flip tools via cancel_mode ---

def test_builders_attach_forward_tool_by_default():
    for builder in (tbs.build_flight_agent, tbs.build_hotel_agent, tbs.build_car_agent):
        with patch.object(tbs, "BedrockModel"):
            agent = builder(cancel_mode=False, saga_id="S1")
        names = list(agent.tool_registry.registry)
        assert len(names) == 1
        assert names[0].startswith("book_")


def test_builders_attach_cancel_tool_when_cancel_mode():
    for builder in (tbs.build_flight_agent, tbs.build_hotel_agent, tbs.build_car_agent):
        with patch.object(tbs, "BedrockModel"):
            agent = builder(cancel_mode=True, saga_id="S1")
        names = list(agent.tool_registry.registry)
        assert len(names) == 1
        assert names[0].startswith("cancel_")


# --- Orchestrator: reverse compensation ordering (pure) ---

def test_completed_steps_reverse_for_compensation():
    """The core rule: compensate in reverse completion order."""
    steps = [
        {"name": "flight", "status": "completed"},
        {"name": "hotel", "status": "completed"},
        {"name": "car", "status": "failed"},
    ]
    completed = [(i, s) for i, s in enumerate(steps) if s["status"] == "completed"]
    completed.reverse()
    assert [s["name"] for _, s in completed] == ["hotel", "flight"]


def test_only_completed_steps_are_compensated():
    steps = [
        {"name": "flight", "status": "completed"},
        {"name": "hotel", "status": "failed"},
        {"name": "car", "status": "pending"},
    ]
    completed = [s for s in steps if s["status"] == "completed"]
    assert [s["name"] for s in completed] == ["flight"]


# --- Live tests ---

def test_live_lock_and_barrier_roundtrip():
    if not os.getenv("AWS_ACCESS_KEY_ID"):
        pytest.skip("AWS credentials are not set")

    table = boto3.resource("dynamodb", region_name="us-east-1").Table("saga-state")
    saga_id = "LIVE-SAGA-001"
    try:
        table.put_item(Item={
            "saga_id": saga_id, "status": "running",
            "package": {"package_id": "PKG-LIVE"},
            "steps": [
                {"name": "flight", "status": "completed", "detail": None},
                {"name": "hotel", "status": "completed", "detail": None},
                {"name": "car", "status": "failed", "detail": "No cars"},
            ],
            "lock": False,
            "compensations_done": 0, "compensations_needed": 0,
            "failed_step": 2,
        })

        assert tbs.acquire_lock(saga_id) is True
        tbs.initialize_barrier(saga_id, needed=2)
        done1, needed1 = tbs.increment_barrier(saga_id)
        assert (done1, needed1) == (1, 2)
        done2, needed2 = tbs.increment_barrier(saga_id)
        assert (done2, needed2) == (2, 2)

        tbs.release_lock(saga_id)
        item = table.get_item(Key={"saga_id": saga_id})["Item"]
        assert item["lock"] is False
        assert int(item["compensations_done"]) == 2
    finally:
        table.delete_item(Key={"saga_id": saga_id})


def test_live_full_rollback_state_machine():
    if not os.getenv("AWS_ACCESS_KEY_ID"):
        pytest.skip("AWS credentials are not set")

    table = boto3.resource("dynamodb", region_name="us-east-1").Table("saga-state")
    saga_id = "LIVE-SAGA-002"
    try:
        tbs.reset_metrics()
        package = {
            "package_id": "PKG-LIVE2", "customer": "Test",
            "origin": "SFO", "destination": "NYC",
            "fail_at": "car",
        }
        # Seed flight+hotel completed, car failed — then run compensation phase
        # through pure step updates (no Bedrock required).
        from travel_booking_saga import create_saga, get_saga, update_step, update_saga
        from travel_booking_saga import acquire_lock, release_lock, initialize_barrier, increment_barrier

        create_saga(saga_id, package)
        update_step(saga_id, 0, {"status": "completed", "detail": {"confirmation": "FLT-002"}})
        update_step(saga_id, 1, {"status": "completed", "detail": {"confirmation": "HOT-002"}})
        update_step(saga_id, 2, {"status": "failed", "detail": "No cars available at counter"})
        update_saga(saga_id, {"status": "compensating", "failed_step": 2})

        assert acquire_lock(saga_id) is True
        saga = get_saga(saga_id)
        completed = [(i, s) for i, s in enumerate(saga["steps"]) if s["status"] == "completed"]
        completed.reverse()
        initialize_barrier(saga_id, needed=len(completed))
        assert [s["name"] for _, s in completed] == ["hotel", "flight"]

        for idx, step in completed:
            update_step(saga_id, idx, {"status": "compensating"})
            update_step(saga_id, idx, {"status": "compensated"})
            increment_barrier(saga_id)

        final = update_saga(saga_id, {"status": "failed"})
        release_lock(saga_id)
        final = get_saga(saga_id)

        assert final["status"] == "failed"
        assert final["compensations_done"] == 2
        assert final["compensations_needed"] == 2
        statuses = [s["status"] for s in final["steps"]]
        assert statuses == ["compensated", "compensated", "failed"]
        assert final["lock"] is False
    finally:
        table.delete_item(Key={"saga_id": saga_id})
