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
os.environ.setdefault("CHECKOUT_TABLE", "checkout-saga")

import ecommerce_checkout_saga as ecs


def _conditional_failed():
    return ClientError(
        {"Error": {"Code": "ConditionalCheckFailedException", "Message": "The conditional request failed"}},
        "UpdateItem",
    )


# --- Conversion helpers ---

def test_to_dynamo_converts_float_to_decimal():
    from decimal import Decimal
    result = ecs.to_dynamo({"price": 9.99, "nested": {"tax": 1.5}})
    assert isinstance(result["price"], Decimal)
    assert isinstance(result["nested"]["tax"], Decimal)


def test_from_dynamo_converts_decimal_types():
    from decimal import Decimal
    result = ecs.from_dynamo({"fee": Decimal("9.99"), "compensations_completed": Decimal("3")})
    assert result["fee"] == 9.99
    assert isinstance(result["fee"], float)
    assert result["compensations_completed"] == 3
    assert isinstance(result["compensations_completed"], int)


# --- create_saga / get_saga ---

def test_create_saga_seeds_pending_steps_and_zeroed_barrier():
    mock_table = MagicMock()
    with patch.object(ecs, "checkout_table", mock_table):
        result = ecs.create_saga(
            "CHECKOUT-001",
            {"checkout_id": "CHECKOUT-001", "customer": "Alice"},
        )
    mock_table.put_item.assert_called_once()
    item = mock_table.put_item.call_args[1]["Item"]
    assert item["checkout_id"] == "CHECKOUT-001"
    assert item["overall_status"] == "running"
    assert item["current_phase"] == "forward"
    assert item["locked"] is False
    assert item["compensations_needed"] == 0
    assert item["compensations_completed"] == 0
    assert item["refund_total"] == 0
    assert [s["name"] for s in item["steps"]] == ["inventory", "payment", "shipping"]
    assert all(s["status"] == "pending" for s in item["steps"])
    assert all(s["booking_ref"] is None for s in item["steps"])
    assert all(s["compensation_ref"] is None for s in item["steps"])
    assert result["overall_status"] == "running"


def test_get_saga_returns_item():
    mock_table = MagicMock()
    mock_table.get_item.return_value = {
        "Item": {
            "checkout_id": "C1",
            "compensations_completed": 2,
            "compensations_needed": 2,
            "locked": False,
        }
    }
    with patch.object(ecs, "checkout_table", mock_table):
        result = ecs.get_saga("C1")
    assert result["compensations_completed"] == 2
    mock_table.get_item.assert_called_once_with(Key={"checkout_id": "C1"})


# --- update_step ---

def test_update_step_patches_one_step():
    mock_table = MagicMock()
    mock_table.get_item.return_value = {
        "Item": {
            "checkout_id": "C1",
            "overall_status": "running",
            "steps": [
                {"name": "inventory", "status": "pending", "detail": None},
                {"name": "payment", "status": "pending", "detail": None},
                {"name": "shipping", "status": "pending", "detail": None},
            ],
        }
    }
    with patch.object(ecs, "checkout_table", mock_table):
        result = ecs.update_step("C1", 1, {"status": "executing"})
    assert result["steps"][1]["status"] == "executing"
    assert result["steps"][0]["status"] == "pending"
    saved = mock_table.put_item.call_args[1]["Item"]
    assert saved["steps"][1]["status"] == "executing"


# --- Distributed lock ---

def test_acquire_lock_succeeds_when_free():
    mock_table = MagicMock()
    with patch.object(ecs, "checkout_table", mock_table), \
         patch.object(ecs.time, "sleep"):
        assert ecs.acquire_lock("C1") is True
    kwargs = mock_table.update_item.call_args[1]
    assert kwargs["ConditionExpression"] == "locked = :want"
    assert kwargs["ExpressionAttributeValues"][":want"] is False
    assert kwargs["ExpressionAttributeValues"][":expected"] is True


def test_acquire_lock_retries_then_fails_when_held():
    mock_table = MagicMock()
    mock_table.update_item.side_effect = _conditional_failed()
    with patch.object(ecs, "checkout_table", mock_table), \
         patch.object(ecs.time, "sleep") as mock_sleep:
        assert ecs.acquire_lock("C1", max_retries=3) is False
    assert mock_table.update_item.call_count == 3
    assert mock_sleep.call_count == 3


def test_release_lock_clears_flag():
    mock_table = MagicMock()
    with patch.object(ecs, "checkout_table", mock_table):
        ecs.release_lock("C1")
    kwargs = mock_table.update_item.call_args[1]
    assert kwargs["ExpressionAttributeValues"][":no"] is False


# --- Atomic barrier ---

def test_set_barrier_target_sets_needed():
    mock_table = MagicMock()
    with patch.object(ecs, "checkout_table", mock_table):
        ecs.set_barrier_target("C1", needed=2)
    kwargs = mock_table.update_item.call_args[1]
    assert kwargs["ExpressionAttributeValues"][":val"] == 2


def test_increment_barrier_uses_add_expression():
    mock_table = MagicMock()
    mock_table.update_item.return_value = {
        "Attributes": {"compensations_completed": 1, "compensations_needed": 2}
    }
    with patch.object(ecs, "checkout_table", mock_table):
        completed, needed = ecs.increment_barrier("C1")
    assert (completed, needed) == (1, 2)
    kwargs = mock_table.update_item.call_args[1]
    assert kwargs["UpdateExpression"] == "ADD compensations_completed :one"
    assert kwargs["ExpressionAttributeValues"][":one"] == 1
    assert kwargs["ReturnValues"] == "ALL_NEW"


# --- Pure checkout logics ---

def test_reserve_items_success():
    result = ecs.reserve_items_logic({
        "checkout_id": "CHECKOUT-001",
        "items": ["Pro Laptop", "Laptop Sleeve"],
    })
    assert result["confirmation"] == "INV-001"
    assert result["item_count"] == 2


def test_charge_card_raises_when_fail_at_payment():
    with pytest.raises(RuntimeError, match="Insufficient funds"):
        ecs.charge_card_logic({"checkout_id": "CHECKOUT-002", "simulate_failure": "payment"})


def test_schedule_delivery_raises_when_fail_at_shipping():
    with pytest.raises(RuntimeError, match="Address is undeliverable"):
        ecs.schedule_delivery_logic({
            "checkout_id": "CHECKOUT-003",
            "simulate_failure": "shipping",
        })


def test_cancel_logics_refs_and_refunds():
    package = {
        "checkout_id": "CHECKOUT-002",
        "total": 1196,
    }
    released = ecs.release_items_logic(package)
    refunded = ecs.refund_card_logic(package)
    cancelled = ecs.cancel_delivery_logic(package)

    assert released["confirmation"] == "REL-002"
    assert released["refund_amount"] == 0
    assert refunded["confirmation"] == "RFND-002"
    assert refunded["comp_ref"] == "RFND-002"
    assert refunded["refund_amount"] == 1196
    assert cancelled["confirmation"] == "CAN-002"
    assert cancelled["refund_amount"] == 0


# --- Agent builders flip tools via cancel_mode ---

def test_builders_attach_forward_tool_by_default():
    for builder in (ecs.build_inventory_agent, ecs.build_payment_agent, ecs.build_shipping_agent):
        with patch.object(ecs, "BedrockModel"):
            agent = builder(cancel_mode=False, checkout_id="C1")
        names = list(agent.tool_registry.registry)
        assert len(names) == 1
        assert names[0] in ("reserve_items", "charge_card", "schedule_delivery")


def test_builders_attach_cancel_tool_when_cancel_mode():
    for builder in (ecs.build_inventory_agent, ecs.build_payment_agent, ecs.build_shipping_agent):
        with patch.object(ecs, "BedrockModel"):
            agent = builder(cancel_mode=True, checkout_id="C1")
        names = list(agent.tool_registry.registry)
        assert len(names) == 1
        assert names[0] in ("release_items", "refund_card", "cancel_delivery")


# --- Orchestrator: reverse compensation ordering (pure) ---

def test_completed_steps_reverse_for_compensation():
    """The core rule: compensate in reverse completion order."""
    steps = [
        {"name": "inventory", "status": "completed"},
        {"name": "payment", "status": "completed"},
        {"name": "shipping", "status": "failed"},
    ]
    completed = [(i, s) for i, s in enumerate(steps) if s["status"] == "completed"]
    completed.reverse()
    assert [s["name"] for _, s in completed] == ["payment", "inventory"]


def test_only_completed_steps_are_compensated():
    steps = [
        {"name": "inventory", "status": "completed"},
        {"name": "payment", "status": "failed"},
        {"name": "shipping", "status": "pending"},
    ]
    completed = [s for s in steps if s["status"] == "completed"]
    assert [s["name"] for s in completed] == ["inventory"]


def test_payment_failure_compensates_only_inventory():
    """Checkout-002: payment fails -> only inventory needs release (REL-002)."""
    steps = [
        {"name": "inventory", "status": "completed"},
        {"name": "payment", "status": "failed"},
        {"name": "shipping", "status": "pending"},
    ]
    completed = [(i, s) for i, s in enumerate(steps) if s["status"] == "completed"]
    completed.reverse()
    assert [s["name"] for _, s in completed] == ["inventory"]


# --- Live tests ---

def test_live_lock_and_barrier_roundtrip():
    if not os.getenv("AWS_ACCESS_KEY_ID"):
        pytest.skip("AWS credentials are not set")

    table = boto3.resource("dynamodb", region_name="us-east-1").Table("checkout-saga")
    checkout_id = "LIVE-CHECKOUT-001"
    try:
        table.put_item(Item={
            "checkout_id": checkout_id, "overall_status": "running",
            "package": {"checkout_id": checkout_id},
            "steps": [
                {"name": "inventory", "status": "completed", "detail": None},
                {"name": "payment", "status": "completed", "detail": None},
                {"name": "shipping", "status": "failed", "detail": "undeliverable"},
            ],
            "locked": False,
            "compensations_completed": 0, "compensations_needed": 0,
            "failed_step": 2,
        })

        assert ecs.acquire_lock(checkout_id) is True
        ecs.set_barrier_target(checkout_id, needed=2)
        done1, needed1 = ecs.increment_barrier(checkout_id)
        assert (done1, needed1) == (1, 2)
        done2, needed2 = ecs.increment_barrier(checkout_id)
        assert (done2, needed2) == (2, 2)

        ecs.release_lock(checkout_id)
        item = table.get_item(Key={"checkout_id": checkout_id})["Item"]
        assert item["locked"] is False
        assert int(item["compensations_completed"]) == 2
    finally:
        table.delete_item(Key={"checkout_id": checkout_id})


def test_live_full_rollback_state_machine():
    if not os.getenv("AWS_ACCESS_KEY_ID"):
        pytest.skip("AWS credentials are not set")

    table = boto3.resource("dynamodb", region_name="us-east-1").Table("checkout-saga")
    checkout_id = "LIVE-CHECKOUT-002"
    try:
        ecs.reset_metrics()
        package = {
            "checkout_id": checkout_id, "customer": "Test",
            "items": ["Widget"], "total": 50,
            "simulate_failure": "payment",
        }
        from ecommerce_checkout_saga import (
            create_saga, get_saga, update_step, update_saga,
            acquire_lock, release_lock, set_barrier_target, increment_barrier,
        )

        create_saga(checkout_id, package)
        update_step(checkout_id, 0, {
            "status": "completed",
            "booking_ref": "INV-002",
            "detail": {"confirmation": "INV-002"},
        })
        update_step(checkout_id, 1, {"status": "failed", "detail": "Insufficient funds"})
        update_saga(checkout_id, {"overall_status": "compensating", "failed_step": 1})

        assert acquire_lock(checkout_id) is True
        saga = get_saga(checkout_id)
        completed = [
            (i, s) for i, s in enumerate(saga["steps"]) if s["status"] == "completed"
        ]
        completed.reverse()
        set_barrier_target(checkout_id, needed=len(completed))
        assert [s["name"] for _, s in completed] == ["inventory"]

        for idx, step in completed:
            update_step(checkout_id, idx, {
                "status": "compensated",
                "compensation_ref": "REL-002",
            })
            done, needed = increment_barrier(checkout_id)
            assert (done, needed) == (1, 1)

        release_lock(checkout_id)
        final = get_saga(checkout_id)

        assert final["overall_status"] == "compensating"
        assert final["compensations_completed"] >= final["compensations_needed"]
        statuses = [s["status"] for s in final["steps"]]
        assert statuses == ["compensated", "failed", "pending"]
        assert final["steps"][0]["compensation_ref"] == "REL-002"
        assert final["locked"] is False
    finally:
        table.delete_item(Key={"checkout_id": checkout_id})
