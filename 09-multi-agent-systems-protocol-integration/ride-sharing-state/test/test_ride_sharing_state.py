import os
import sys
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
os.environ.setdefault("TRIP_TABLE", "trip-state")
os.environ.setdefault("MEMORY_TABLE", "rider-memory")

import ride_sharing_state as rss


def _conditional_failed():
    return ClientError(
        {"Error": {"Code": "ConditionalCheckFailedException", "Message": "The conditional request failed"}},
        "PutItem",
    )


# --- Conversion helpers ---

def test_to_dynamo_converts_float_to_decimal():
    result = rss.to_dynamo({"fare": 9.99, "nested": {"eta": 12.5}, "tags": [1.5]})
    assert isinstance(result["fare"], Decimal)
    assert isinstance(result["nested"]["eta"], Decimal)
    assert isinstance(result["tags"][0], Decimal)


def test_from_dynamo_converts_decimal_types():
    result = rss.from_dynamo({"fare": Decimal("9.99"), "version": Decimal("3")})
    assert result["fare"] == 9.99
    assert isinstance(result["fare"], float)
    assert result["version"] == 3
    assert isinstance(result["version"], int)


# --- create_trip ---

def test_create_trip_seeds_version_zero():
    mock_table = MagicMock()
    with patch.object(rss, "trip_table", mock_table), \
         patch.object(rss, "_record_write"):
        result = rss.create_trip("TRIP-001", "Alice", "Downtown", "Airport", "premium", 14.0)
    mock_table.put_item.assert_called_once()
    item = mock_table.put_item.call_args[1]["Item"]
    assert item["version"] == 0
    assert item["status"] == "requested"
    assert result["version"] == 0


# --- Optimistic locking: update_trip ---

def test_update_trip_increments_version():
    mock_table = MagicMock()
    mock_table.get_item.return_value = {
        "Item": {"trip_id": "T1", "version": 0, "status": "requested"}
    }
    with patch.object(rss, "trip_table", mock_table), \
         patch.object(rss, "_record_write"), \
         patch.object(rss, "_record_conflict"):
        result = rss.update_trip("T1", {"fare": 10.5})
    assert result["version"] == 1
    assert result["fare"] == 10.5
    put_kwargs = mock_table.put_item.call_args[1]
    assert put_kwargs["ConditionExpression"] == "version = :v"
    assert put_kwargs["ExpressionAttributeValues"][":v"] == 0


def test_update_trip_retries_on_version_conflict_then_succeeds():
    mock_table = MagicMock()
    mock_table.get_item.side_effect = [
        {"Item": {"trip_id": "T1", "version": 0}},
        {"Item": {"trip_id": "T1", "version": 1}},
    ]
    mock_table.put_item.side_effect = [_conditional_failed(), {}]

    with patch.object(rss, "trip_table", mock_table), \
         patch.object(rss, "_record_write") as mock_write, \
         patch.object(rss, "_record_conflict") as mock_conflict, \
         patch.object(rss.time, "sleep") as mock_sleep:
        result = rss.update_trip("T1", {"driver": "Marcus"})

    assert result["version"] == 2
    assert mock_table.put_item.call_count == 2
    mock_conflict.assert_called_once()
    mock_sleep.assert_called_once_with(0.1)  # first retry backoff
    mock_write.assert_called_once()


def test_update_trip_raises_after_max_retries():
    mock_table = MagicMock()
    mock_table.get_item.return_value = {"Item": {"trip_id": "T1", "version": 0}}
    mock_table.put_item.side_effect = _conditional_failed()

    with patch.object(rss, "trip_table", mock_table), \
         patch.object(rss, "_record_conflict"), \
         patch.object(rss.time, "sleep"):
        with pytest.raises(rss.VersionConflictError):
            rss.update_trip("T1", {"fare": 1.0}, max_retries=3)

    assert mock_table.put_item.call_count == 3


def test_update_trip_raises_other_client_errors_immediately():
    mock_table = MagicMock()
    mock_table.get_item.return_value = {"Item": {"trip_id": "T1", "version": 0}}
    mock_table.put_item.side_effect = ClientError(
        {"Error": {"Code": "ProvisionedThroughputExceededException", "Message": "throttled"}},
        "PutItem",
    )
    with patch.object(rss, "trip_table", mock_table), \
         patch.object(rss, "_record_write"), \
         patch.object(rss, "_record_conflict"):
        with pytest.raises(ClientError):
            rss.update_trip("T1", {"fare": 1.0})
    assert mock_table.put_item.call_count == 1


def test_update_trip_uses_exponential_backoff_delays():
    mock_table = MagicMock()
    mock_table.get_item.side_effect = [
        {"Item": {"trip_id": "T1", "version": 0}},
        {"Item": {"trip_id": "T1", "version": 1}},
        {"Item": {"trip_id": "T1", "version": 2}},
    ]
    mock_table.put_item.side_effect = [
        _conditional_failed(),
        _conditional_failed(),
        {},
    ]
    with patch.object(rss, "trip_table", mock_table), \
         patch.object(rss, "_record_write"), \
         patch.object(rss, "_record_conflict"), \
         patch.object(rss.time, "sleep") as mock_sleep:
        rss.update_trip("T1", {"eta_minutes": 20})
    delays = [call.args[0] for call in mock_sleep.call_args_list]
    assert delays == [0.1, 0.2]  # 0.1 * 2**0, 0.1 * 2**1


# --- State recovery ---

def test_recover_incomplete_trip_resets_partial_fields():
    mock_table = MagicMock()
    mock_table.get_item.return_value = {
        "Item": {
            "trip_id": "T1",
            "version": 2,
            "rider": "Bob",
            "pickup": "A",
            "dropoff": "B",
            "ride_type": "standard",
            "distance_mi": Decimal("8.0"),
            "status": "driver_matched",
            "driver": "Marcus",
            "fare": Decimal("20.0"),
        }
    }
    with patch.object(rss, "trip_table", mock_table), \
         patch.object(rss, "_record_write"):
        result = rss.recover_incomplete_trip("T1")
    assert result["status"] == "requested"
    assert result["version"] == 3
    assert "driver" not in result
    assert "fare" not in result
    assert result["rider"] == "Bob"


def test_recover_confirmed_trip_is_noop():
    mock_table = MagicMock()
    mock_table.get_item.return_value = {
        "Item": {"trip_id": "T1", "version": 3, "status": "confirmed", "rider": "Alice"}
    }
    with patch.object(rss, "trip_table", mock_table):
        result = rss.recover_incomplete_trip("T1")
    assert result["status"] == "confirmed"
    mock_table.put_item.assert_not_called()


# --- Pure helpers: driver selection + memory ---

def test_select_driver_highest_rated_when_no_memory():
    mock_memory = MagicMock()
    mock_memory.get_item.return_value = {}
    with patch.object(rss, "memory_table", mock_memory):
        driver, source = rss.select_driver_for_rider("Bob")
    assert driver["name"] == "Marcus"  # highest rating in pool
    assert driver["rating"] == 4.9
    assert source == "highest_rated"
    mock_memory.put_item.assert_called_once()
    saved = mock_memory.put_item.call_args[1]["Item"]
    assert saved["rider_id"] == "Bob"
    assert saved["preferred_driver"] == "Marcus"


def test_select_driver_uses_preferred_from_memory():
    mock_memory = MagicMock()
    mock_memory.get_item.return_value = {"Item": {"rider_id": "Alice", "preferred_driver": "Priya"}}
    with patch.object(rss, "memory_table", mock_memory):
        driver, source = rss.select_driver_for_rider("Alice")
    assert driver["name"] == "Priya"
    assert source == "memory"
    mock_memory.put_item.assert_not_called()


def test_select_driver_falls_back_when_preferred_unavailable():
    mock_memory = MagicMock()
    mock_memory.get_item.return_value = {"Item": {"rider_id": "Alice", "preferred_driver": "RetiredDriver"}}
    with patch.object(rss, "memory_table", mock_memory):
        driver, source = rss.select_driver_for_rider("Alice")
    assert driver["name"] == "Marcus"
    assert source == "highest_rated"
    mock_memory.put_item.assert_called_once()


# --- Pure helpers: fare + ETA ---

def test_compute_fare_standard():
    # 3.50 + 1.75 * 8 * 1.0 = 17.50
    assert rss.compute_fare("standard", 8.0) == 17.50


def test_compute_fare_premium():
    # 3.50 + 1.75 * 14 * 1.5 = 32.00 + wait: 1.75*14=24.5; 24.5*1.5=36.75; +3.50=40.25
    assert rss.compute_fare("premium", 14.0) == 40.25


def test_compute_eta_minutes():
    # 5 + 1.2 * 10 = 17
    assert rss.compute_eta_minutes(10.0) == 17


# --- Concurrent writes through ThreadPoolExecutor ---

def test_concurrent_updates_do_not_lose_fields():
    """Simulate concurrent updates against an in-memory fake table.

    Three writers race on the same record; optimistic locking must
    preserve every field in the final state (no lost updates).
    """
    store = {"trip_id": "T1", "version": 0, "status": "requested"}

    class FakeTable:
        def get_item(self, Key):
            import copy
            return {"Item": copy.deepcopy(store)}

        def put_item(self, Item, ConditionExpression=None, ExpressionAttributeValues=None):
            import threading
            # Emulate DynamoDB atomic conditional put with a process-wide lock
            fake_lock = getattr(FakeTable, "_lock", None)
            if fake_lock is None:
                FakeTable._lock = threading.Lock()
                fake_lock = FakeTable._lock
            with fake_lock:
                if ExpressionAttributeValues and store["version"] != ExpressionAttributeValues[":v"]:
                    raise _conditional_failed()
                store.clear()
                store.update(Item)

    import copy
    mock_table = FakeTable()
    with patch.object(rss, "trip_table", mock_table), \
         patch.object(rss, "_record_write"), \
         patch.object(rss, "_record_conflict"):

        def write_slice(updates):
            return rss.update_trip("T1", updates, max_retries=10)

        with ThreadPoolExecutor(max_workers=3) as pool:
            futures = [
                pool.submit(write_slice, {"driver": "Marcus", "vehicle": "Toyota Camry"}),
                pool.submit(write_slice, {"fare": 17.5, "currency": "USD"}),
                pool.submit(write_slice, {"eta_minutes": 14, "status": "confirmed"}),
            ]
            for f in futures:
                f.result()

    assert store["driver"] == "Marcus"
    assert store["fare"] == 17.5
    assert store["eta_minutes"] == 14
    assert store["status"] == "confirmed"
    assert store["version"] == 3


# --- Live tests: real DynamoDB with AWS credentials ---

def test_live_optimistic_locking_roundtrip():
    if not os.getenv("AWS_ACCESS_KEY_ID"):
        pytest.skip("AWS credentials are not set")

    table = boto3.resource("dynamodb", region_name="us-east-1").Table("trip-state")
    trip_id = "LIVE-001"
    try:
        table.put_item(Item={
            "trip_id": trip_id, "version": 0,
            "rider": "TestRider", "pickup": "A", "dropoff": "B",
            "ride_type": "standard", "distance_mi": Decimal("5.0"),
            "status": "requested",
        })
        r1 = rss.update_trip(trip_id, {"driver": "Marcus", "vehicle": "Toyota Camry"})
        assert r1["version"] == 1
        r2 = rss.update_trip(trip_id, {"fare": 12.25, "currency": "USD"})
        assert r2["version"] == 2
        assert r2["driver"] == "Marcus"  # prior write preserved
        assert r2["fare"] == 12.25

        item = table.get_item(Key={"trip_id": trip_id})["Item"]
        assert int(item["version"]) == 2
        assert item["driver"] == "Marcus"
    finally:
        table.delete_item(Key={"trip_id": trip_id})


def test_live_concurrent_updates_all_apply():
    if not os.getenv("AWS_ACCESS_KEY_ID"):
        pytest.skip("AWS credentials are not set")

    table = boto3.resource("dynamodb", region_name="us-east-1").Table("trip-state")
    trip_id = "LIVE-002"
    try:
        table.put_item(Item={
            "trip_id": trip_id, "version": 0,
            "rider": "TestRider", "pickup": "A", "dropoff": "B",
            "ride_type": "standard", "distance_mi": Decimal("5.0"),
            "status": "requested",
        })
        slices = [
            {"driver": "Marcus", "vehicle": "Toyota Camry"},
            {"fare": 12.25, "currency": "USD"},
            {"eta_minutes": 11, "status": "confirmed"},
        ]
        with ThreadPoolExecutor(max_workers=3) as pool:
            futures = [pool.submit(rss.update_trip, trip_id, s, 10) for s in slices]
            for f in futures:
                f.result()

        final = rss.get_trip(trip_id)
        assert final["driver"] == "Marcus"
        assert final["fare"] == 12.25
        assert final["eta_minutes"] == 11
        assert final["status"] == "confirmed"
        assert final["version"] >= 3
    finally:
        table.delete_item(Key={"trip_id": trip_id})
