# =============================================================================
# Food Delivery — Shared State with DynamoDB Optimistic Locking
# =============================================================================
# Four agents (Restaurant Confirm, Driver Assign, Price Calculate,
# Status Track) update the SAME DynamoDB order record simultaneously.
# Optimistic locking (version + ConditionExpression) prevents lost
# updates; exponential backoff resolves conflicts. recover_order
# cleans partial data when the restaurant rejects an order.
# customer_memory (in-process stand-in for AgentCore Memory
# SESSION_SUMMARY) retains preferences across orders.
#
# Architecture:
#   Shared state:  order-state table (order_id PK, version field, ttl)
#   Writers:       RestaurantConfirmAgent, DriverAssignAgent,
#                  PriceCalculatorAgent, StatusTrackerAgent
#   Locking:       version-based conditional writes + retry/backoff
#   Recovery:      recover_order — reset driver/total_price, cancel
#   Memory:        customer_memory dict (preferred driver/restaurant)
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

# --- DynamoDB table ---
ORDER_TABLE = os.environ.get("ORDER_TABLE", "order-state")
dynamodb = boto3.resource("dynamodb", region_name=AWS_REGION)
order_table = dynamodb.Table(ORDER_TABLE)

# --- TTL: orders expire 2 hours after creation ---
ORDER_TTL_SECONDS = 2 * 60 * 60

# --- Pricing constants (deterministic for tests) ---
DELIVERY_FEE = 4.99
TAX_RATE = 0.08

# --- Driver pool ---
AVAILABLE_DRIVERS = [
    {"driver_id": "DRV-01", "name": "Marcus", "rating": 4.9, "vehicle": "Toyota Camry"},
    {"driver_id": "DRV-02", "name": "Sofia", "rating": 4.8, "vehicle": "Tesla Model 3"},
    {"driver_id": "DRV-03", "name": "Priya", "rating": 4.7, "vehicle": "Honda Civic"},
]

# --- Cross-session customer memory (AgentCore SESSION_SUMMARY stand-in) ---
customer_memory: dict[str, dict] = {}

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


def _record_write(order_id: str, version: int, fields: list[str]) -> None:
    global _write_log
    with _metrics_lock:
        _write_log.append({
            "order_id": order_id,
            "version": version,
            "fields": sorted(fields),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })


def _record_conflict() -> None:
    global _conflicts
    with _metrics_lock:
        _conflicts += 1


# ============================================================================
# SHARED STATE — create / read / optimistic update / recover
# ============================================================================

def create_order(order_id: str, customer_id: str, restaurant: str,
                 items: list[dict], address: str = "123 Main St",
                 distance_mi: float = 5.0,
                 simulate_rejection: bool = False) -> dict:
    """Seed a new order record at version 0 with a 2-hour TTL."""
    now = datetime.now(timezone.utc)
    item = {
        "order_id": order_id,
        "version": 0,
        "customer_id": customer_id,
        "restaurant": restaurant,
        "items": to_dynamo(items),
        "address": address,
        "distance_mi": to_dynamo(float(distance_mi)),
        "status": "pending",
        "driver": None,
        "total_price": None,
        "progress": [],
        "simulate_rejection": simulate_rejection,
        "created_at": now.isoformat(),
        # DynamoDB TTL attribute: epoch seconds, 2 hours from now
        "ttl": int(now.timestamp()) + ORDER_TTL_SECONDS,
    }
    order_table.put_item(Item=item)
    _record_write(order_id, 0, ["create"])
    return from_dynamo(item)


def get_order(order_id: str) -> dict:
    """Read the current order record (Decimal -> float)."""
    response = order_table.get_item(Key={"order_id": order_id})
    return from_dynamo(response["Item"])


def update_order(order_id: str, updates: dict, max_retries: int = 3) -> dict:
    """Optimistic locking with retry: READ version -> MODIFY -> WRITE with condition.

    Every agent reads the current version, applies its slice locally,
    bumps the version, and writes back only if the version is unchanged.
    On ConditionalCheckFailedException, re-read and retry with
    exponential backoff (0.1s, 0.2s, 0.4s).
    """
    for attempt in range(max_retries):
        # READ: fetch current record and capture its version
        current = order_table.get_item(Key={"order_id": order_id})["Item"]
        expected_version = int(current["version"])

        # MODIFY: apply updates locally and bump the version
        current.update(to_dynamo(updates))
        current["version"] = expected_version + 1

        try:
            # WRITE: put the record back, conditional on version unchanged
            order_table.put_item(
                Item=current,
                ConditionExpression="version = :expected_ver",
                ExpressionAttributeValues={":expected_ver": expected_version},
            )
            _record_write(order_id, expected_version + 1, list(updates.keys()))
            return from_dynamo(current)
        except ClientError as e:
            if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
                # CONFLICT: another agent wrote first — back off and re-READ
                _record_conflict()
                if attempt < max_retries - 1:
                    time.sleep(0.1 * (2 ** attempt))  # 0.1s, 0.2s, 0.4s
                else:
                    raise VersionConflictError(
                        f"Version conflict after {max_retries} retries"
                    )
            else:
                raise
    raise VersionConflictError(f"Version conflict after {max_retries} retries")


def recover_order(order_id: str) -> dict:
    """State recovery: clean partial agent writes after restaurant rejection.

    Resets driver and total_price to None, marks the order cancelled, and
    appends progress entries explaining what happened — through the same
    optimistic-locking path so a concurrent writer cannot clobber cleanup.
    """
    return update_order(order_id, {
        "driver": None,
        "total_price": None,
        "status": "cancelled",
        "progress": ["Order rejected by restaurant", "Partial updates cleaned up"],
    })


# ============================================================================
# PURE HELPERS — deterministic logic shared by tools and tests
# ============================================================================

def confirm_restaurant(order: dict) -> dict:
    """Restaurant accepts unless simulate_rejection is set on the order."""
    if order.get("simulate_rejection"):
        return {
            "confirmed": False,
            "status": "rejected",
            "reason": "Restaurant is closed for new orders",
        }
    return {
        "confirmed": True,
        "status": "confirmed",
        "reason": "Restaurant accepted the order",
    }


def select_driver(customer_id: str) -> dict:
    """Prefer the customer's remembered driver; else highest-rated available.

    Also writes back preferred_driver / favorite_restaurant / usual_address
    into customer_memory (AgentCore SESSION_SUMMARY stand-in).
    """
    memory = customer_memory.get(customer_id, {})
    preferred = memory.get("preferred_driver")

    if preferred and any(d["driver_id"] == preferred for d in AVAILABLE_DRIVERS):
        best = next(d for d in AVAILABLE_DRIVERS if d["driver_id"] == preferred)
        source = "memory"
    else:
        best = max(AVAILABLE_DRIVERS, key=lambda d: d["rating"])
        source = "highest_rated"

    customer_memory.setdefault(customer_id, {})["preferred_driver"] = best["driver_id"]
    return {**best, "source": source}


def compute_price(items: list[dict]) -> dict:
    """Deterministic price: subtotal + 8% tax + $4.99 delivery fee."""
    subtotal = round(sum(float(i["price"]) * int(i["qty"]) for i in items), 2)
    tax = round(subtotal * TAX_RATE, 2)
    total_price = round(subtotal + tax + DELIVERY_FEE, 2)
    return {
        "subtotal": subtotal,
        "tax": tax,
        "delivery_fee": DELIVERY_FEE,
        "total_price": total_price,
    }


def append_progress(order: dict, entry: str) -> list[str]:
    progress = order.get("progress") or []
    return [*progress, entry]


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


def build_restaurant_confirm_agent() -> Agent:
    """Confirm or reject the order; writes status via update_order."""
    model = BedrockModel(model_id=NOVA_LITE_MODEL, region_name=AWS_REGION, temperature=0.0)
    system_prompt = (
        "You are a restaurant-confirmation agent for a food delivery platform. "
        "Call confirm_restaurant exactly ONCE with the order_id. "
        "Return ONLY the JSON result from the tool. Do NOT add commentary."
    )

    @tool
    def confirm_restaurant_tool(order_id: str) -> str:
        order = get_order(order_id)
        result = confirm_restaurant(order)
        update_order(order_id, {
            "status": result["status"],
            "restaurant_confirmed": result["confirmed"],
            "reject_reason": None if result["confirmed"] else result["reason"],
            "progress": append_progress(order, f"Restaurant: {result['status']}"),
        })
        memory = customer_memory.setdefault(order["customer_id"], {})
        memory["favorite_restaurant"] = order["restaurant"]
        return json.dumps({"order_id": order_id, **result}, indent=2)

    return Agent(model=model, system_prompt=system_prompt, tools=[confirm_restaurant_tool])


def build_driver_assign_agent() -> Agent:
    """Assign a driver (memory-aware); writes driver via update_order."""
    model = BedrockModel(model_id=NOVA_LITE_MODEL, region_name=AWS_REGION, temperature=0.0)
    system_prompt = (
        "You are a driver-assignment agent for a food delivery platform. "
        "Call assign_driver exactly ONCE with the order_id. "
        "Return ONLY the JSON result from the tool. Do NOT add commentary."
    )

    @tool
    def assign_driver_tool(order_id: str) -> str:
        order = get_order(order_id)
        cust_id = order["customer_id"]
        preferred = customer_memory.get(cust_id, {}).get("preferred_driver")

        if preferred and any(d["driver_id"] == preferred for d in AVAILABLE_DRIVERS):
            best = next(d for d in AVAILABLE_DRIVERS if d["driver_id"] == preferred)
            source = "memory"
        else:
            best = max(AVAILABLE_DRIVERS, key=lambda d: d["rating"])
            source = "highest_rated"

        update_order(order_id, {
            "driver": {"driver_id": best["driver_id"], "name": best["name"],
                       "vehicle": best["vehicle"], "source": source},
            "progress": append_progress(order, f"Driver assigned: {best['name']}"),
        })
        memory = customer_memory.setdefault(cust_id, {})
        memory["preferred_driver"] = best["driver_id"]
        memory["favorite_restaurant"] = order["restaurant"]
        memory["usual_address"] = order["address"]
        return json.dumps({
            "order_id": order_id,
            "driver": best["name"],
            "driver_id": best["driver_id"],
            "source": source,
        }, indent=2)

    return Agent(model=model, system_prompt=system_prompt, tools=[assign_driver_tool])


def build_price_calculator_agent() -> Agent:
    """Calculate total with tax + delivery fee; writes total_price via update_order."""
    model = BedrockModel(model_id=NOVA_LITE_MODEL, region_name=AWS_REGION, temperature=0.0)
    system_prompt = (
        "You are a price-calculation agent for a food delivery platform. "
        "Call calculate_price exactly ONCE with the order_id. "
        "Return ONLY the JSON result from the tool. Do NOT add commentary."
    )

    @tool
    def calculate_price_tool(order_id: str) -> str:
        order = get_order(order_id)
        pricing = compute_price(from_dynamo(order["items"]))
        update_order(order_id, {
            "total_price": pricing["total_price"],
            "price_breakdown": pricing,
            "currency": "USD",
            "progress": append_progress(
                order,
                f"Price calculated: subtotal ${pricing['subtotal']:.2f} "
                f"+ 8% tax + ${DELIVERY_FEE:.2f} delivery",
            ),
        })
        return json.dumps({"order_id": order_id, **pricing}, indent=2)

    return Agent(model=model, system_prompt=system_prompt, tools=[calculate_price_tool])


def build_status_tracker_agent() -> Agent:
    """Advance order status and append progress via update_order."""
    model = BedrockModel(model_id=NOVA_LITE_MODEL, region_name=AWS_REGION, temperature=0.0)
    system_prompt = (
        "You are a status-tracking agent for a food delivery platform. "
        "Call track_status exactly ONCE with the order_id. "
        "Return ONLY the JSON result from the tool. Do NOT add commentary."
    )

    @tool
    def track_status_tool(order_id: str) -> str:
        order = get_order(order_id)
        if order.get("status") in ("rejected", "cancelled"):
            status = order["status"]
        else:
            status = "out_for_delivery"
        update_order(order_id, {
            "status": status,
            "progress": append_progress(order, f"Status: {status}"),
        })
        return json.dumps({"order_id": order_id, "status": status}, indent=2)

    return Agent(model=model, system_prompt=system_prompt, tools=[track_status_tool])


# ============================================================================
# SCENARIOS
# ============================================================================

def run_scenario_sequential(order_id: str = "ORD-001") -> dict:
    """Scenario 1: four agents one at a time. No conflicts expected."""
    print("\n" + "=" * 70)
    print("Scenario 1 - Sequential (one agent at a time)")
    print("=" * 70)

    create_order(
        order_id, customer_id="alice",
        restaurant="Tokyo Ramen House",
        items=[{"name": "Ramen", "price": 13.50, "qty": 2},
               {"name": "Gyoza", "price": 6.00, "qty": 1}],
        address="123 Main St",
        distance_mi=4.0,
    )
    print(f"Created {order_id} v0 (Alice, Tokyo Ramen House, ttl+2h)")

    builders = [
        ("RestaurantConfirmAgent", build_restaurant_confirm_agent),
        ("DriverAssignAgent", build_driver_assign_agent),
        ("PriceCalculatorAgent", build_price_calculator_agent),
        ("StatusTrackerAgent", build_status_tracker_agent),
    ]
    conflicts_before = get_metrics()["conflicts"]

    for name, builder in builders:
        run_agent_with_retry(builder, f"Process order {order_id}")
        state = get_order(order_id)
        print(f"  {name:24s} -> version {state['version']}  status={state['status']}")

    conflicts_after = get_metrics()["conflicts"]
    final = get_order(order_id)
    print(f"Conflicts this scenario: {conflicts_after - conflicts_before}")
    _print_final_state(final)
    return final


def run_scenario_concurrent(order_id: str = "ORD-002") -> dict:
    """Scenario 2: all four agents run in parallel (ThreadPoolExecutor)."""
    print("\n" + "=" * 70)
    print("Scenario 2 - Concurrent (ThreadPoolExecutor, 4 agents in parallel)")
    print("=" * 70)

    create_order(
        order_id, customer_id="bob",
        restaurant="Bella Italia",
        items=[{"name": "Margherita Pizza", "price": 15.00, "qty": 1},
               {"name": "Tiramisu", "price": 7.50, "qty": 1}],
        address="456 Oak Ave",
        distance_mi=6.0,
    )
    print(f"Created {order_id} v0 (Bob, Bella Italia, ttl+2h)")

    builders = [
        build_restaurant_confirm_agent,
        build_driver_assign_agent,
        build_price_calculator_agent,
        build_status_tracker_agent,
    ]
    conflicts_before = get_metrics()["conflicts"]

    # Build agents INSIDE worker threads so each has its own client state
    def _worker(builder):
        agent = builder()
        return agent(f"Process order {order_id}")

    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(_worker, b) for b in builders]
        for future in as_completed(futures):
            future.result()  # propagate any agent/tool errors

    conflicts_after = get_metrics()["conflicts"]
    final = get_order(order_id)
    print(
        f"Conflicts this scenario: {conflicts_after - conflicts_before} "
        f"(resolved via optimistic locking)"
    )
    _print_final_state(final)
    return final


def run_scenario_recovery(order_id: str = "ORD-003") -> dict:
    """Scenario 3: driver + price first, restaurant rejects, recover_order cleans up."""
    print("\n" + "=" * 70)
    print("Scenario 3 - State recovery (restaurant rejects after partial writes)")
    print("=" * 70)

    create_order(
        order_id, customer_id="carlos",
        restaurant="Green Garden",
        items=[{"name": "Buddha Bowl", "price": 12.00, "qty": 1},
               {"name": "Smoothie", "price": 5.50, "qty": 2}],
        address="789 Pine Rd",
        distance_mi=3.0,
        simulate_rejection=True,
    )
    print(f"Created {order_id} v0 (Carlos, Green Garden, simulate_rejection=True)")

    # Driver and price write first — order looks partially complete
    run_agent_with_retry(build_driver_assign_agent, f"Process order {order_id}")
    run_agent_with_retry(build_price_calculator_agent, f"Process order {order_id}")
    partial = get_order(order_id)
    print(f"  Partial state: status={partial['status']}  "
          f"driver={partial.get('driver', {}).get('name') if isinstance(partial.get('driver'), dict) else partial.get('driver')}  "
          f"total_price={partial.get('total_price')}  version={partial['version']}")

    # Restaurant rejects — clean up orphan driver + price
    run_agent_with_retry(build_restaurant_confirm_agent, f"Process order {order_id}")
    rejected = get_order(order_id)
    print(f"  Restaurant rejected: status={rejected['status']}  "
          f"reason={rejected.get('reject_reason')}")

    final = recover_order(order_id)
    print(f"  recover_order -> status={final['status']}  "
          f"driver={final.get('driver')}  total_price={final.get('total_price')}  "
          f"version={final['version']}")
    print(f"  progress: {final.get('progress')}")
    _print_final_state(final)
    return final


def _print_final_state(order: dict) -> None:
    driver = order.get("driver")
    driver_name = driver.get("name") if isinstance(driver, dict) else driver
    print(f"Final state: status={order.get('status')}  "
          f"driver={driver_name}  "
          f"total_price={order.get('total_price')}  "
          f"version={order.get('version')}  "
          f"ttl={order.get('ttl')}")


# ============================================================================
# MAIN
# ============================================================================

def main() -> None:
    """CLI entrypoint. Runs all three scenarios and prints the report."""
    print("=" * 70)
    print("Food Delivery - Shared State with DynamoDB Optimistic Locking")
    print("=" * 70)

    reset_metrics()
    customer_memory.clear()

    order1 = run_scenario_sequential("ORD-001")
    order2 = run_scenario_concurrent("ORD-002")
    order3 = run_scenario_recovery("ORD-003")

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
    print(f"  {'order_id':10s} {'version':>8s}  fields")
    for entry in writes:
        print(f"  {entry['order_id']:10s} {entry['version']:>8d}  {', '.join(entry['fields'])}")

    # --- Customer memory ---
    print("\n" + "=" * 70)
    print("Customer Memory (AgentCore SESSION_SUMMARY stand-in)")
    print("=" * 70)
    for cust_id, mem in sorted(customer_memory.items()):
        print(f"  {cust_id}: preferred_driver={mem.get('preferred_driver')}  "
              f"favorite_restaurant={mem.get('favorite_restaurant')}  "
              f"usual_address={mem.get('usual_address')}")

    # --- Scenario outcomes ---
    print("\n" + "=" * 70)
    print("Scenario outcomes")
    print("=" * 70)
    print(f"  ORD-001 sequential: status={order1.get('status')} "
          f"driver={_driver_name(order1)} total_price={order1.get('total_price')} "
          f"version={order1.get('version')}")
    print(f"  ORD-002 concurrent: status={order2.get('status')} "
          f"driver={_driver_name(order2)} total_price={order2.get('total_price')} "
          f"version={order2.get('version')} "
          f"(conflicts resolved via optimistic locking)")
    print(f"  ORD-003 recovered:  status={order3.get('status')} "
          f"driver={order3.get('driver')} total_price={order3.get('total_price')} "
          f"version={order3.get('version')}")


def _driver_name(order: dict) -> str | None:
    driver = order.get("driver")
    if isinstance(driver, dict):
        return driver.get("name")
    return driver


if __name__ == "__main__":
    main()
