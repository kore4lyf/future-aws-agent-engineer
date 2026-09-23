# =============================================================================
# Travel Booking — Saga Pattern with Orchestrated Compensation
# =============================================================================
# A Python orchestrator (not an LLM) drives three LLM booking agents —
# Flight, Hotel, Car — through a forward path. On any failure it runs
# compensating cancel_* tools in REVERSE order. DynamoDB is the state
# machine (step statuses), distributed lock, and atomic barrier so the
# saga survives crashes and cannot resolve while rollbacks are in flight.
#
# Architecture:
#   State:     saga-state table (saga_id PK)
#   Steps:     pending -> executing -> completed
#              failed path: compensating -> compensated
#   Lock:      lock flag via conditional write
#   Barrier:   compensations_done ADD vs compensations_needed
#   Agents:    one builder per service; cancel_mode flips tool book/cancel
# ============================================================================

import json
import os
import threading
import time
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

# --- DynamoDB table ---
SAGA_TABLE = os.environ.get("SAGA_TABLE", "saga-state")
dynamodb = boto3.resource("dynamodb", region_name=AWS_REGION)
saga_table = dynamodb.Table(SAGA_TABLE)

# --- Step / saga status vocabulary ---
STEP_STATUSES = (
    "pending", "executing", "completed",
    "failed", "compensating", "compensated",
)

# --- Forward agent config (order matters: compensation reverses it) ---
AGENTS_CONFIG = [
    {"name": "flight", "index": 0, "builder": "build_flight_agent",
     "prompt": "Book the flight for this travel package."},
    {"name": "hotel", "index": 1, "builder": "build_hotel_agent",
     "prompt": "Book the hotel stay for this travel package."},
    {"name": "car", "index": 2, "builder": "build_car_agent",
     "prompt": "Book the rental car for this travel package."},
]

# --- Cross-process metrics (thread-safe) ---
_metrics_lock = threading.Lock()
_compensation_order: list[str] = []
_forward_log: list[str] = []


class SagaError(Exception):
    """Raised when the saga cannot proceed (lock failure, bad state)."""


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
    """Recursively convert Decimal back to Python types."""
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
# METRICS
# ============================================================================

def reset_metrics() -> None:
    global _compensation_order, _forward_log
    with _metrics_lock:
        _compensation_order = []
        _forward_log = []


def get_metrics() -> dict:
    with _metrics_lock:
        return {
            "compensation_order": list(_compensation_order),
            "forward": list(_forward_log),
        }


def _record_forward(name: str) -> None:
    global _forward_log
    with _metrics_lock:
        _forward_log.append(name)


def _record_compensation(name: str) -> None:
    global _compensation_order
    with _metrics_lock:
        _compensation_order.append(name)


# ============================================================================
# SHARED STATE — saga record + step updates
# ============================================================================

def create_saga(saga_id: str, package: dict) -> dict:
    """Seed a saga with three pending steps at version/lock defaults."""
    steps = [
        {
            "name": cfg["name"],
            "status": "pending",
            "booking_ref": None,
            "compensation_ref": None,
            "detail": None,
        }
        for cfg in AGENTS_CONFIG
    ]
    item = {
        "saga_id": saga_id,
        "status": "running",
        "current_phase": "forward",
        "package": to_dynamo(package),
        "steps": to_dynamo(steps),
        "lock": False,
        "compensations_done": 0,
        "compensations_needed": 0,
        "failed_step": None,
        "refund_total": 0,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    saga_table.put_item(Item=item)
    return from_dynamo(item)


def get_saga(saga_id: str) -> dict:
    response = saga_table.get_item(Key={"saga_id": saga_id})
    return from_dynamo(response["Item"])


def update_step(saga_id: str, index: int, updates: dict) -> dict:
    """Read-modify-write one step inside the saga record (single-writer orchestrator)."""
    current = saga_table.get_item(Key={"saga_id": saga_id})["Item"]
    current = from_dynamo(current)
    current["steps"][index].update(updates)
    saga_table.put_item(Item=to_dynamo(current))
    return current


def update_saga(saga_id: str, updates: dict) -> dict:
    """Read-modify-write top-level saga fields (orchestrator only)."""
    current = from_dynamo(saga_table.get_item(Key={"saga_id": saga_id})["Item"])
    current.update(updates)
    saga_table.put_item(Item=to_dynamo(current))
    return current


# ============================================================================
# DISTRIBUTED LOCK — conditional flag acquire/release
# ============================================================================

def acquire_lock(saga_id: str, max_retries: int = 5) -> bool:
    """Try to flip lock False -> True with a ConditionExpression.

    Uses ExpressionAttributeNames because `lock` is a DynamoDB reserved
    keyword. Returns True if this caller owns the lock. Retries briefly if
    another process holds it; returns False after max_retries (orchestrator
    then leaves compensation to the lock holder).
    """
    for attempt in range(max_retries):
        try:
            saga_table.update_item(
                Key={"saga_id": saga_id},
                UpdateExpression="SET #lk = :expected",
                ConditionExpression="#lk = :want",
                ExpressionAttributeNames={"#lk": "lock"},
                ExpressionAttributeValues={":expected": True, ":want": False},
            )
            return True
        except ClientError as e:
            if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
                time.sleep(0.05 * (2 ** attempt))
                continue
            raise
    return False


def release_lock(saga_id: str) -> None:
    saga_table.update_item(
        Key={"saga_id": saga_id},
        UpdateExpression="SET #lk = :no",
        ExpressionAttributeNames={"#lk": "lock"},
        ExpressionAttributeValues={":no": False},
    )


# ============================================================================
# ATOMIC BARRIER — DynamoDB ADD (never read-modify-write the counter)
# ============================================================================

def initialize_barrier(saga_id: str, needed: int) -> None:
    saga_table.update_item(
        Key={"saga_id": saga_id},
        UpdateExpression="SET compensations_needed = :n, compensations_done = :z",
        ExpressionAttributeValues={":n": int(needed), ":z": 0},
    )


def increment_barrier(saga_id: str) -> tuple[int, int]:
    """Atomically increment compensations_done and return (done, needed).

    DynamoDB's ADD expression cannot lose increments under contention;
    a read-modify-write would.
    """
    response = saga_table.update_item(
        Key={"saga_id": saga_id},
        UpdateExpression="ADD compensations_done :one",
        ExpressionAttributeValues={":one": 1},
        ReturnValues="ALL_NEW",
    )
    attrs = from_dynamo(response["Attributes"])
    return (
        int(attrs.get("compensations_done", 0)),
        int(attrs.get("compensations_needed", 0)),
    )


# ============================================================================
# PURE HELPERS — deterministic booking logic (tests never call Bedrock)
# ============================================================================

def book_flight_logic(package: dict) -> dict:
    if package.get("simulate_failure") == "flight" or package.get("fail_at") == "flight":
        raise RuntimeError("Airline inventory unavailable")
    return {
        "confirmation": f"FLT-{package['package_id'][-3:]}",
        "route": f"{package['origin']}->{package['destination']}",
        "cabin": package.get("cabin", "economy"),
        "price": package.get("flight_price", 0),
    }


def cancel_flight_logic(package: dict) -> dict:
    return {
        "cancelled": True,
        "confirmation": f"FLT-{package['package_id'][-3:]}",
        "refund_amount": package.get("flight_price", 0),
    }


def book_hotel_logic(package: dict) -> dict:
    if package.get("simulate_failure") == "hotel" or package.get("fail_at") == "hotel":
        raise RuntimeError("No rooms available")
    return {
        "confirmation": f"HTL-{package['package_id'][-3:]}",
        "nights": package.get("nights", 3),
        "property": package.get("hotel", "City Suites"),
        "price": package.get("hotel_price", 0),
    }


def cancel_hotel_logic(package: dict) -> dict:
    return {
        "cancelled": True,
        "confirmation": f"HTL-{package['package_id'][-3:]}",
        "refund_amount": package.get("hotel_price", 0),
    }


def book_car_logic(package: dict) -> dict:
    if package.get("simulate_failure") == "car" or package.get("fail_at") == "car":
        raise RuntimeError("No cars available at destination")
    return {
        "confirmation": f"CAR-{package['package_id'][-3:]}",
        "class": package.get("car_class", "midsize"),
        "price": package.get("car_price", 0),
    }


def cancel_car_logic(package: dict) -> dict:
    return {
        "cancelled": True,
        "confirmation": f"CAR-{package['package_id'][-3:]}",
        "refund_amount": package.get("car_price", 0),
    }


BOOK_LOGICS = {
    "flight": book_flight_logic,
    "hotel": book_hotel_logic,
    "car": book_car_logic,
}
CANCEL_LOGICS = {
    "flight": cancel_flight_logic,
    "hotel": cancel_hotel_logic,
    "car": cancel_car_logic,
}


# ============================================================================
# AGENT BUILDERS — cancel_mode flips book_* <-> cancel_* on the same builder
# ============================================================================

def run_agent_with_retry(agent_builder, prompt: str, max_retries: int = 3,
                         **builder_kwargs) -> str:
    """Wrap an agent invocation with exponential backoff (1s, 2s, 4s)."""
    for attempt in range(max_retries):
        try:
            agent = agent_builder(**builder_kwargs)
            return str(agent(prompt))
        except Exception as error:
            if attempt < max_retries - 1:
                wait = 2 ** attempt
                print(f"[Retry {attempt + 1}/{max_retries}] ({error.__class__.__name__}), waiting {wait}s...")
                time.sleep(wait)
                continue
            print(f"[Failed] ({error.__class__.__name__}) after {max_retries} attempts")
            raise


def _booking_tool(service: str, saga_id: str, cancel_mode: bool):
    """Build the @tool that either books or cancels one service."""
    index = next(c["index"] for c in AGENTS_CONFIG if c["name"] == service)

    if cancel_mode:
        def cancel_fn(package_id: str) -> str:
            saga = get_saga(saga_id)
            package = from_dynamo(saga["package"])
            result = CANCEL_LOGICS[service](package)
            refund = int(result.get("refund_amount", 0))
            update_step(saga_id, index, {
                "compensation_ref": result.get("confirmation"),
                "refund_amount": refund,
            })
            if refund:
                current = int(saga.get("refund_total", 0))
                update_saga(saga_id, {"refund_total": current + refund})
            _record_compensation(service)
            return json.dumps({
                "service": service,
                "action": "cancel",
                "saga_id": saga_id,
                **result,
            }, indent=2)

        cancel_fn.__name__ = f"cancel_{service}"
        return tool(cancel_fn)

    def book_fn(package_id: str) -> str:
        saga = get_saga(saga_id)
        package = from_dynamo(saga["package"])
        try:
            result = BOOK_LOGICS[service](package)
        except Exception as error:
            # Tool records failure so the orchestrator can break without
            # relying on the LLM to surface exceptions.
            update_step(saga_id, index, {
                "status": "failed",
                "detail": str(error),
            })
            return json.dumps({
                "service": service,
                "action": "book",
                "success": False,
                "error": str(error),
            }, indent=2)

        update_step(saga_id, index, {
            "status": "completed",
            "booking_ref": result.get("confirmation"),
            "detail": result,
        })
        _record_forward(service)
        return json.dumps({
            "service": service,
            "action": "book",
            "success": True,
            **result,
        }, indent=2)

    book_fn.__name__ = f"book_{service}"
    return tool(book_fn)


def _build_service_agent(service: str, cancel_mode: bool, saga_id: str) -> Agent:
    model = BedrockModel(model_id=NOVA_LITE_MODEL, region_name=AWS_REGION, temperature=0.0)
    action = "cancel" if cancel_mode else "book"
    system_prompt = (
        f"You are a travel {service}-booking agent. "
        f"The user message includes package_id. "
        f"Call {'cancel' if cancel_mode else 'book'}_{service} exactly ONCE "
        f"with that package_id. "
        "Return ONLY the JSON result from the tool. Do NOT add commentary."
    )
    agent_tool = _booking_tool(service, saga_id, cancel_mode)
    return Agent(model=model, system_prompt=system_prompt, tools=[agent_tool])


def build_flight_agent(cancel_mode: bool = False, saga_id: str = "") -> Agent:
    return _build_service_agent("flight", cancel_mode, saga_id)


def build_hotel_agent(cancel_mode: bool = False, saga_id: str = "") -> Agent:
    return _build_service_agent("hotel", cancel_mode, saga_id)


def build_car_agent(cancel_mode: bool = False, saga_id: str = "") -> Agent:
    return _build_service_agent("car", cancel_mode, saga_id)


BUILDERS = {
    "flight": build_flight_agent,
    "hotel": build_hotel_agent,
    "car": build_car_agent,
}


# ============================================================================
# ORCHESTRATOR — forward path + reverse compensation + barrier resolve
# ============================================================================

def run_saga(saga_id: str) -> dict:
    """Drive forward booking agents; on failure compensate in reverse order.

    Reverse order is required: later steps may depend on earlier ones, so
    unwinding from the most recent completed step prevents orphans.
    """
    print("\n" + "=" * 70)
    print(f"Saga {saga_id} - forward path")
    print("=" * 70)

    saga = get_saga(saga_id)
    package = from_dynamo(saga["package"])
    package_id = package["package_id"]
    failed_step: int | None = None

    for cfg in AGENTS_CONFIG:
        update_saga(saga_id, {"current_phase": cfg["name"]})
        update_step(saga_id, cfg["index"], {"status": "executing"})
        builder = BUILDERS[cfg["name"]]
        prompt = f"{cfg['prompt']} Use package_id={package_id}."
        try:
            run_agent_with_retry(
                builder,
                prompt,
                cancel_mode=False,
                saga_id=saga_id,
            )
        except Exception:
            update_step(saga_id, cfg["index"], {"status": "failed", "detail": "agent error"})
            failed_step = cfg["index"]
            break

        step = get_saga(saga_id)["steps"][cfg["index"]]
        print(f"  forward {cfg['name']:8s} -> {step['status']}"
              + (f"  ref={step.get('booking_ref')}" if step.get("booking_ref") else ""))
        if step["status"] == "failed":
            failed_step = cfg["index"]
            print(f"  step failed: {step.get('detail')}")
            break
        if step["status"] != "completed":
            update_step(saga_id, cfg["index"], {
                "status": "failed",
                "detail": "agent did not complete booking",
            })
            failed_step = cfg["index"]
            break

    if failed_step is None:
        result = update_saga(saga_id, {"status": "completed", "current_phase": "done"})
        print("  saga status: completed")
        return result

    # --- Compensation phase ---
    print("\n" + "=" * 70)
    print(f"Saga {saga_id} - compensation (reverse order)")
    print("=" * 70)

    update_saga(saga_id, {
        "status": "compensating",
        "failed_step": failed_step,
        "current_phase": "compensation",
    })

    if not acquire_lock(saga_id):
        raise SagaError(f"Could not acquire lock for saga {saga_id}")

    try:
        saga = get_saga(saga_id)
        completed = [
            (i, s) for i, s in enumerate(saga["steps"])
            if s["status"] == "completed"
        ]
        completed.reverse()  # compensate in reverse order
        initialize_barrier(saga_id, needed=len(completed))
        print(f"  compensating {len(completed)} step(s): "
              f"{[s['name'] for _, s in completed]}")

        for idx, step in completed:
            update_step(saga_id, idx, {"status": "compensating"})
            builder = BUILDERS[step["name"]]
            run_agent_with_retry(
                builder,
                f"Cancel {step['name']} for saga {saga_id} package_id={package_id}",
                cancel_mode=True,
                saga_id=saga_id,
            )
            update_step(saga_id, idx, {"status": "compensated"})
            done, needed = increment_barrier(saga_id)
            refreshed = get_saga(saga_id)["steps"][idx]
            print(f"  compensate {step['name']:8s} -> {step['status']}"
                  f"  ref={refreshed.get('compensation_ref')}"
                  f"  barrier {done}/{needed}")

        # Barrier gates resolution: only fail once every compensation reports back
        saga = get_saga(saga_id)
        done = int(saga["compensations_done"])
        needed = int(saga["compensations_needed"])
        if done < needed:
            raise SagaError(
                f"Barrier not satisfied: {done}/{needed} compensations done"
            )
        update_saga(saga_id, {"status": "failed", "current_phase": "resolved"})
        saga = get_saga(saga_id)
        print(f"  saga status: failed (barrier {done}/{needed})")
        print(f"  total refund: ${int(saga.get('refund_total', 0))}")
    finally:
        release_lock(saga_id)

    return get_saga(saga_id)


# ============================================================================
# SCENARIOS
# ============================================================================

def run_scenario_success(saga_id: str = "SAGA-001") -> dict:
    """Scenario 1: all three bookings succeed. No compensation."""
    print("\n" + "=" * 70)
    print("Scenario 1 - Success (flight + hotel + car all complete)")
    print("=" * 70)

    package = {
        "package_id": "PKG-001",
        "customer": "Alice",
        "origin": "New York",
        "destination": "Paris",
        "cabin": "business",
        "nights": 5,
        "hotel": "Rive Gauche Hotel",
        "car_class": "midsize",
        "flight_price": 1200,
        "hotel_price": 900,
        "car_price": 210,
        "simulate_failure": None,
        "fail_at": None,
    }
    create_saga(saga_id, package)
    print(f"Created {saga_id} (Alice New York->Paris, no failure injected)")

    final = run_saga(saga_id)
    metrics = get_metrics()
    print(f"Forward order: {metrics['forward']}")
    print(f"Compensations: {metrics['compensation_order'] or 'none'}")
    _print_saga(final)
    return final


def run_scenario_rollback(saga_id: str = "SAGA-002") -> dict:
    """Scenario 2: car booking fails -> compensate hotel then flight (reverse)."""
    print("\n" + "=" * 70)
    print("Scenario 2 - Rollback (car fails, reverse compensation)")
    print("=" * 70)

    package = {
        "package_id": "PKG-002",
        "customer": "Bob",
        "origin": "LAX",
        "destination": "Tokyo",
        "cabin": "economy",
        "nights": 4,
        "hotel": "Shinjuku Grand",
        "car_class": "compact",
        "flight_price": 950,
        "hotel_price": 640,
        "car_price": 180,
        "simulate_failure": "car",
        "fail_at": "car",
    }
    create_saga(saga_id, package)
    print(f"Created {saga_id} (Bob LAX->Tokyo, simulate_failure=car)")

    final = run_saga(saga_id)
    metrics = get_metrics()
    print(f"Forward order: {metrics['forward']}")
    print(f"Compensation order: {metrics['compensation_order']} "
          f"(reverse of forward - last success undone first)")
    _print_saga(final)
    return final


def run_scenario_mid_failure(saga_id: str = "SAGA-003") -> dict:
    """Scenario 3: hotel fails after flight -> only flight is compensated."""
    print("\n" + "=" * 70)
    print("Scenario 3 - Mid-path failure (hotel fails, only flight rolls back)")
    print("=" * 70)

    package = {
        "package_id": "PKG-003",
        "customer": "Carol",
        "origin": "ORD",
        "destination": "London",
        "cabin": "economy",
        "nights": 3,
        "hotel": "Thames View",
        "car_class": "suv",
        "flight_price": 780,
        "hotel_price": 540,
        "car_price": 240,
        "simulate_failure": "hotel",
        "fail_at": "hotel",
    }
    create_saga(saga_id, package)
    print(f"Created {saga_id} (Carol ORD->London, simulate_failure=hotel)")

    final = run_saga(saga_id)
    metrics = get_metrics()
    print(f"Forward order: {metrics['forward']}")
    print(f"Compensation order: {metrics['compensation_order']}")
    _print_saga(final)
    return final


def _print_saga(saga: dict) -> None:
    steps = ", ".join(
        f"{s['name']}={s['status']}"
        + (f"({s.get('booking_ref')})" if s.get("booking_ref") else "")
        for s in saga["steps"]
    )
    print(f"Final: status={saga['status']}  lock={saga['lock']}  "
          f"barrier={saga['compensations_done']}/{saga['compensations_needed']}  "
          f"failed_step={saga.get('failed_step')}  "
          f"refund_total=${int(saga.get('refund_total', 0))}")
    print(f"  steps: {steps}")


# ============================================================================
# MAIN
# ============================================================================

def _print_insights() -> None:
    print("\n" + "=" * 70)
    print("Key insights")
    print("=" * 70)
    insights = [
        "Saga pattern - every step has a compensating action",
        "Compensating transactions - undo completed work on failure",
        "Reverse order - unwind from the most recent completed step",
        "State machine - DynamoDB step statuses make progress explicit",
        "Distributed lock - only one compensator runs a saga at a time",
        "Barrier counter - resolution waits for all compensations",
        "Idempotency - cancel tools are safe to retry",
        "Crash recovery - durable state resumes after restart",
    ]
    for i, text in enumerate(insights, 1):
        print(f"  {i}. {text}")


def main() -> None:
    """CLI entrypoint. Runs all three saga scenarios and prints the report."""
    print("=" * 70)
    print("Travel Booking - Saga Pattern with Orchestrated Compensation")
    print("=" * 70)

    reset_metrics()
    saga1 = run_scenario_success("SAGA-001")
    reset_metrics()
    saga2 = run_scenario_rollback("SAGA-002")
    reset_metrics()
    saga3 = run_scenario_mid_failure("SAGA-003")

    print("\n" + "=" * 70)
    print("Summary")
    print("=" * 70)
    for saga in (saga1, saga2, saga3):
        steps = {s["name"]: s["status"] for s in saga["steps"]}
        print(f"  {saga['saga_id']}: status={saga['status']}  "
              f"barrier={saga['compensations_done']}/{saga['compensations_needed']}  "
              f"refund=${int(saga.get('refund_total', 0))}  "
              f"steps={steps}")

    _print_insights()
    print("\nWhy reverse order? Later steps may depend on earlier ones; "
          "unwinding from the most recent completed step prevents orphans.")


if __name__ == "__main__":
    main()
