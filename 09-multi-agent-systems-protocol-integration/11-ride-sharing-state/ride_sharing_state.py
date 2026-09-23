# =============================================================================
# Ride Sharing — Shared State with DynamoDB Optimistic Locking
# =============================================================================
# Three agents (Driver Match, Pricing, ETA) update the SAME DynamoDB trip
# record concurrently. Optimistic locking (version + ConditionExpression)
# prevents lost updates; exponential backoff resolves conflicts.
# Rider memory (stand-in for AgentCore Memory SESSION_SUMMARY) persists
# driver preferences across separate trip sessions.
#
# Architecture:
#   Shared state:  trip-state table (trip_id PK, version field)
#   Writers:       DriverMatchAgent, PricingAgent, ETAAgent
#   Locking:       version-based conditional writes + retry/backoff
#   Memory:        rider-memory table (rider_id PK, preferred_driver)
# ============================================================================

import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from decimal import Decimal

import boto3
from botocore.exceptions import ClientError
from dotenv import load_dotenv
from strands import Agent, tool
from strands.models import BedrockModel

load_dotenv()

# --- Bedrock configuration ---
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
NOVA_LITE_MODEL = os.environ.get("NOVA_LITE_MODEL", "amazon.nova-lite-v1:0")

# --- DynamoDB tables ---
TRIP_TABLE = os.environ.get("TRIP_TABLE", "trip-state")
MEMORY_TABLE = os.environ.get("MEMORY_TABLE", "rider-memory")
dynamodb = boto3.resource("dynamodb", region_name=AWS_REGION)
trip_table = dynamodb.Table(TRIP_TABLE)
memory_table = dynamodb.Table(MEMORY_TABLE)

# --- Pricing / ETA constants (deterministic for tests) ---
BASE_FARE = 3.50
PER_MILE = 1.75
RIDE_MULTIPLIERS = {"standard": 1.0, "premium": 1.5}

# --- Driver pool (all currently available) ---
DRIVER_POOL = [
    {"name": "Marcus", "rating": 4.9, "vehicle": "Toyota Camry"},
    {"name": "Sofia", "rating": 4.8, "vehicle": "Tesla Model 3"},
    {"name": "Priya", "rating": 4.7, "vehicle": "Honda Civic"},
]

# --- Cross-process metrics (thread-safe) ---
_metrics_lock = threading.Lock()
_conflicts = 0
_write_log: list[dict] = []


class VersionConflictError(Exception):
    """Raised when optimistic locking still conflicts after all retries."""


# ============================================================================
# DYNAMO CONVERSION — DynamoDB rejects Python floats
# ============================================================================

def to_dynamo(obj):
    """Recursively convert floats to Decimal for DynamoDB."""
    if isinstance(obj, dict):
        return {k: to_dynamo(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [to_dynamo(v) for v in obj]
    if isinstance(obj, float):
        return Decimal(str(obj))
    return obj


def from_dynamo(obj):
    """Recursively convert Decimal back to Python types.

    Whole Decimals (e.g. version) become int; fractional Decimals become float.
    """
    if isinstance(obj, dict):
        return {k: from_dynamo(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [from_dynamo(v) for v in obj]
    if isinstance(obj, Decimal):
        if obj == obj.to_integral_value():
            return int(obj)
        return float(obj)
    return obj


# ============================================================================
# METRICS — write log + conflict counter
# ============================================================================

def reset_metrics() -> None:
    global _conflicts, _write_log
    with _metrics_lock:
        _conflicts = 0
        _write_log = []


def get_metrics() -> dict:
    with _metrics_lock:
        return {"conflicts": _conflicts, "writes": list(_write_log)}


def _record_write(trip_id: str, version: int, fields: list[str]) -> None:
    global _write_log
    with _metrics_lock:
        _write_log.append({
            "trip_id": trip_id,
            "version": version,
            "fields": sorted(fields),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })


def _record_conflict() -> None:
    global _conflicts
    with _metrics_lock:
        _conflicts += 1


# ============================================================================
# SHARED STATE — create / read / optimistic update
# ============================================================================

def create_trip(trip_id: str, rider: str, pickup: str, dropoff: str,
                ride_type: str = "standard", distance_mi: float = 10.0) -> dict:
    """Seed a new trip record at version 0."""
    item = {
        "trip_id": trip_id,
        "version": 0,
        "rider": rider,
        "pickup": pickup,
        "dropoff": dropoff,
        "ride_type": ride_type,
        "distance_mi": to_dynamo(float(distance_mi)),
        "status": "requested",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    trip_table.put_item(Item=item)
    _record_write(trip_id, 0, ["create"])
    return from_dynamo(item)


def get_trip(trip_id: str) -> dict:
    """Read the current trip record (Decimal → float)."""
    response = trip_table.get_item(Key={"trip_id": trip_id})
    return from_dynamo(response["Item"])


def update_trip(trip_id: str, updates: dict, max_retries: int = 3) -> dict:
    """Optimistic locking: read → modify locally → conditional write.

    Every agent reads the current version, applies its slice locally,
    bumps the version, and writes back only if the version is unchanged.
    On ConditionalCheckFailedException, re-read and retry with
    exponential backoff (0.1s, 0.2s, 0.4s).
    """
    for attempt in range(max_retries):
        # READ: capture the current version (our "lock token")
        current = trip_table.get_item(Key={"trip_id": trip_id})["Item"]
        expected_version = int(current["version"])

        # MODIFY locally and bump the version
        current.update(to_dynamo(updates))
        current["version"] = expected_version + 1

        try:
            # WRITE with a condition on the original version
            trip_table.put_item(
                Item=current,
                ConditionExpression="version = :v",
                ExpressionAttributeValues={":v": expected_version},
            )
            _record_write(trip_id, expected_version + 1, list(updates.keys()))
            return from_dynamo(current)
        except ClientError as e:
            if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
                _record_conflict()
                if attempt < max_retries - 1:
                    time.sleep(0.1 * (2 ** attempt))  # 0.1s, 0.2s, 0.4s
                else:
                    raise VersionConflictError(
                        f"Version conflict on {trip_id} after {max_retries} retries"
                    )
            else:
                raise


def recover_incomplete_trip(trip_id: str, max_retries: int = 3) -> dict:
    """State recovery: reset a trip that never reached 'confirmed'.

    Clears partial agent-written fields and returns status to 'requested'
    so the pipeline can reprocess it. Uses the same optimistic lock so a
    concurrent agent write is never silently overwritten.
    """
    identity_fields = (
        "trip_id", "version", "rider", "pickup", "dropoff",
        "ride_type", "distance_mi", "status", "created_at",
    )
    for attempt in range(max_retries):
        current = trip_table.get_item(Key={"trip_id": trip_id})["Item"]
        expected_version = int(current["version"])

        if current.get("status") == "confirmed":
            return from_dynamo(current)

        recovered = {k: current[k] for k in identity_fields if k in current}
        recovered["status"] = "requested"
        recovered["recovered_at"] = datetime.now(timezone.utc).isoformat()
        recovered["version"] = expected_version + 1

        try:
            trip_table.put_item(
                Item=recovered,
                ConditionExpression="version = :v",
                ExpressionAttributeValues={":v": expected_version},
            )
            _record_write(trip_id, expected_version + 1, ["recover"])
            return from_dynamo(recovered)
        except ClientError as e:
            if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
                _record_conflict()
                if attempt < max_retries - 1:
                    time.sleep(0.1 * (2 ** attempt))
                else:
                    raise VersionConflictError(
                        f"Version conflict recovering {trip_id} after {max_retries} retries"
                    )
            else:
                raise


# ============================================================================
# PURE HELPERS — deterministic logic shared by tools and tests
# ============================================================================

def select_driver_for_rider(rider_id: str) -> tuple[dict, str]:
    """Pick a driver using rider memory (AgentCore SESSION_SUMMARY stand-in).

    If a returning rider has a saved preferred driver who is available,
    use that driver; otherwise pick the highest-rated one and save it.
    Returns (driver, source) where source is "memory" or "highest_rated".
    """
    memory_item = memory_table.get_item(Key={"rider_id": rider_id}).get("Item")
    preferred = memory_item.get("preferred_driver") if memory_item else None
    available_names = {d["name"] for d in DRIVER_POOL}

    if preferred and preferred in available_names:
        driver = next(d for d in DRIVER_POOL if d["name"] == preferred)
        return driver, "memory"

    driver = max(DRIVER_POOL, key=lambda d: d["rating"])
    memory_table.put_item(
        Item={
            "rider_id": rider_id,
            "preferred_driver": driver["name"],
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    return driver, "highest_rated"


def compute_fare(ride_type: str, distance_mi: float) -> float:
    """Deterministic fare: base + per-mile * distance * ride multiplier."""
    multiplier = RIDE_MULTIPLIERS.get(ride_type, 1.0)
    return round(BASE_FARE + PER_MILE * distance_mi * multiplier, 2)


def compute_eta_minutes(distance_mi: float) -> int:
    """Deterministic ETA: 5 min base + 1.2 min per mile."""
    return int(round(5 + distance_mi * 1.2))


# ============================================================================
# AGENT BUILDERS — Nova Lite + single tool (same shape, different tool body)
# ============================================================================

def run_agent_with_retry(agent_builder, prompt: str, max_retries: int = 3) -> str:
    """Wrap an agent invocation with exponential backoff (1s, 2s, 4s)."""
    for attempt in range(max_retries):
        try:
            agent = agent_builder()
            return str(agent(prompt))
        except Exception as error:
            if attempt < max_retries - 1:
                wait = 2 ** attempt
                print(f"[Retry {attempt + 1}/{max_retries}] ({error.__class__.__name__}), waiting {wait}s...")
                time.sleep(wait)
                continue
            print(f"[Failed] ({error.__class__.__name__}) after {max_retries} attempts")
            raise


def build_driver_match_agent() -> Agent:
    """Match a driver to the trip; writes driver/vehicle via update_trip."""
    model = BedrockModel(model_id=NOVA_LITE_MODEL, region_name=AWS_REGION, temperature=0.0)
    system_prompt = (
        "You are a driver-matching agent for a ride-sharing platform. "
        "Call match_driver exactly ONCE with the trip_id. "
        "Return ONLY the JSON result from the tool. Do NOT add commentary."
    )

    @tool
    def match_driver(trip_id: str) -> str:
        trip = get_trip(trip_id)
        driver, source = select_driver_for_rider(trip["rider"])
        update_trip(trip_id, {
            "driver": driver["name"],
            "vehicle": driver["vehicle"],
            "driver_rating": driver["rating"],
            "driver_source": source,
        })
        return json.dumps({
            "trip_id": trip_id,
            "driver": driver["name"],
            "vehicle": driver["vehicle"],
            "source": source,
        })

    return Agent(model=model, system_prompt=system_prompt, tools=[match_driver])


def build_pricing_agent() -> Agent:
    """Calculate the fare; writes fare via update_trip."""
    model = BedrockModel(model_id=NOVA_LITE_MODEL, region_name=AWS_REGION, temperature=0.0)
    system_prompt = (
        "You are a pricing agent for a ride-sharing platform. "
        "Call calculate_fare exactly ONCE with the trip_id. "
        "Return ONLY the JSON result from the tool. Do NOT add commentary."
    )

    @tool
    def calculate_fare(trip_id: str) -> str:
        trip = get_trip(trip_id)
        fare = compute_fare(trip["ride_type"], float(trip["distance_mi"]))
        update_trip(trip_id, {"fare": fare, "currency": "USD"})
        return json.dumps({"trip_id": trip_id, "fare": fare, "currency": "USD"})

    return Agent(model=model, system_prompt=system_prompt, tools=[calculate_fare])


def build_eta_agent() -> Agent:
    """Estimate arrival time; writes eta + confirms via update_trip."""
    model = BedrockModel(model_id=NOVA_LITE_MODEL, region_name=AWS_REGION, temperature=0.0)
    system_prompt = (
        "You are an ETA agent for a ride-sharing platform. "
        "Call estimate_eta exactly ONCE with the trip_id. "
        "Return ONLY the JSON result from the tool. Do NOT add commentary."
    )

    @tool
    def estimate_eta(trip_id: str) -> str:
        trip = get_trip(trip_id)
        eta = compute_eta_minutes(float(trip["distance_mi"]))
        update_trip(trip_id, {"eta_minutes": eta, "status": "confirmed"})
        return json.dumps({"trip_id": trip_id, "eta_minutes": eta, "status": "confirmed"})

    return Agent(model=model, system_prompt=system_prompt, tools=[estimate_eta])


# ============================================================================
# SCENARIOS
# ============================================================================

def run_scenario_sequential(trip_id: str = "TRIP-001") -> dict:
    """Scenario 1: agents run one at a time. No conflicts expected."""
    print("\n" + "=" * 70)
    print("Scenario 1 — Sequential (one agent at a time)")
    print("=" * 70)

    create_trip(
        trip_id, rider="Alice",
        pickup="Downtown", dropoff="Airport",
        ride_type="premium", distance_mi=14.0,
    )
    print(f"Created {trip_id} at version 0 (Alice, Downtown -> Airport, premium)")

    builders = [
        ("DriverMatchAgent", build_driver_match_agent),
        ("PricingAgent", build_pricing_agent),
        ("ETAAgent", build_eta_agent),
    ]
    conflicts_before = get_metrics()["conflicts"]

    for name, builder in builders:
        run_agent_with_retry(builder, f"Process trip {trip_id}")
        state = get_trip(trip_id)
        print(f"  {name:20s} -> version {state['version']}")

    conflicts_after = get_metrics()["conflicts"]
    final = get_trip(trip_id)
    print(f"Conflicts this scenario: {conflicts_after - conflicts_before}")
    _print_final_state(final)
    return final


def run_scenario_concurrent(trip_id: str = "TRIP-002") -> dict:
    """Scenario 2: all three agents run in parallel (ThreadPoolExecutor)."""
    print("\n" + "=" * 70)
    print("Scenario 2 — Concurrent (ThreadPoolExecutor, 3 agents in parallel)")
    print("=" * 70)

    create_trip(
        trip_id, rider="Bob",
        pickup="University", dropoff="Tech Park",
        ride_type="standard", distance_mi=8.0,
    )
    print(f"Created {trip_id} at version 0 (Bob, University -> Tech Park, standard)")

    builders = [
        build_driver_match_agent,
        build_pricing_agent,
        build_eta_agent,
    ]
    conflicts_before = get_metrics()["conflicts"]

    # Build agents INSIDE worker threads so each has its own client state
    def _worker(builder):
        agent = builder()
        return agent(f"Process trip {trip_id}")

    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = [pool.submit(_worker, b) for b in builders]
        for future in as_completed(futures):
            future.result()  # propagate any agent/tool errors

    conflicts_after = get_metrics()["conflicts"]
    final = get_trip(trip_id)
    print(f"Conflicts this scenario: {conflicts_after - conflicts_before} (resolved via optimistic locking)")
    _print_final_state(final)
    return final


def run_scenario_memory(trip_id: str = "TRIP-003") -> dict:
    """Scenario 3: same rider as Scenario 1 — tests cross-session memory."""
    print("\n" + "=" * 70)
    print("Scenario 3 — Cross-session memory (Alice returns)")
    print("=" * 70)

    create_trip(
        trip_id, rider="Alice",
        pickup="Airport", dropoff="Downtown",
        ride_type="premium", distance_mi=14.0,
    )
    print(f"Created {trip_id} at version 0 (Alice, Airport -> Downtown, premium)")

    run_agent_with_retry(build_driver_match_agent, f"Process trip {trip_id}")
    run_agent_with_retry(build_pricing_agent, f"Process trip {trip_id}")
    run_agent_with_retry(build_eta_agent, f"Process trip {trip_id}")

    final = get_trip(trip_id)
    print(f"Driver source: {final.get('driver_source', 'n/a')} "
          f"(expected 'memory' — same driver as TRIP-001)")
    _print_final_state(final)
    return final


def _print_final_state(trip: dict) -> None:
    print(f"Final state: status={trip.get('status')}  "
          f"driver={trip.get('driver')} ({trip.get('vehicle')})  "
          f"fare=${trip.get('fare')}  "
          f"eta={trip.get('eta_minutes')}min  "
          f"version={trip.get('version')}")


def get_rider_memory(rider_id: str) -> dict | None:
    item = memory_table.get_item(Key={"rider_id": rider_id}).get("Item")
    return from_dynamo(item) if item else None


# ============================================================================
# MAIN
# ============================================================================

def main() -> None:
    """CLI entrypoint. Runs all three scenarios and prints the report."""
    print("=" * 70)
    print("Ride Sharing — Shared State with DynamoDB Optimistic Locking")
    print("=" * 70)

    reset_metrics()

    trip1 = run_scenario_sequential("TRIP-001")
    trip2 = run_scenario_concurrent("TRIP-002")
    trip3 = run_scenario_memory("TRIP-003")

    # --- Summary ---
    metrics = get_metrics()
    writes = metrics["writes"]
    conflicts = metrics["conflicts"]
    attempts = len(writes) + conflicts
    conflict_rate = (conflicts / attempts) if attempts else 0.0

    print("\n" + "=" * 70)
    print("Summary")
    print("=" * 70)
    print(f"  Total writes:     {len(writes)}")
    print(f"  Total conflicts:  {conflicts}")
    print(f"  Conflict rate:    {conflict_rate:.2%}  (all resolved via optimistic locking + retry)")

    # --- Write log ---
    print("\n" + "=" * 70)
    print("Write Log (every DynamoDB write)")
    print("=" * 70)
    print(f"  {'trip_id':10s} {'version':>8s}  fields")
    for entry in writes:
        print(f"  {entry['trip_id']:10s} {entry['version']:>8d}  {', '.join(entry['fields'])}")

    # --- Rider memory ---
    print("\n" + "=" * 70)
    print("Rider Memory (AgentCore SESSION_SUMMARY stand-in)")
    print("=" * 70)
    for rider in ("Alice", "Bob"):
        memory = get_rider_memory(rider)
        if memory:
            print(f"  {rider}: preferred_driver={memory['preferred_driver']}")
        else:
            print(f"  {rider}: (no memory)")

    # --- Cross-session check ---
    print("\n" + "=" * 70)
    print("Cross-session check")
    print("=" * 70)
    same_driver = trip1.get("driver") == trip3.get("driver")
    print(f"  TRIP-001 driver: {trip1.get('driver')}")
    print(f"  TRIP-003 driver: {trip3.get('driver')}")
    print(f"  Remembered preference: {'YES' if same_driver else 'NO'} "
          f"(source={trip3.get('driver_source')})")
    print(f"  TRIP-002 (concurrent) conflicts resolved; final version={trip2.get('version')}")


if __name__ == "__main__":
    main()
