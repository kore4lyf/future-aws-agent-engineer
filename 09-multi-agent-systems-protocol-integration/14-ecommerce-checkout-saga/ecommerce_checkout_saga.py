# =============================================================================
# E-commerce Checkout — Saga Pattern with Tool-Owned Barrier Increments
# =============================================================================
# Three agents (Inventory, Payment, Shipping) run in forward order.
# On failure, compensating tools run in REVERSE under a distributed lock.
# Structural improvement over the demo: each compensation tool owns its
# increment_barrier call, so concurrent compensations are safe and the
# orchestrator only checks the barrier after the lock is released.
#
# Architecture:
#   State:     checkout-saga table (checkout_id PK)
#   Steps:     pending -> executing -> completed
#              failed path: compensating -> compensated
#   Lock:      locked flag via conditional write
#   Barrier:   compensations_completed ADD vs compensations_needed
#   Agents:    cancel_mode flips reserve/charge/schedule <-> release/refund/cancel
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
CHECKOUT_TABLE = os.environ.get("CHECKOUT_TABLE", "checkout-saga")
dynamodb = boto3.resource("dynamodb", region_name=AWS_REGION)
checkout_table = dynamodb.Table(CHECKOUT_TABLE)

# --- Step / saga status vocabulary ---
STEP_STATUSES = (
    "pending", "executing", "completed",
    "failed", "compensating", "compensated",
)

# --- Forward agent config (order matters: compensation reverses it) ---
AGENTS_CONFIG = [
    {"name": "inventory", "index": 0,
     "prompt": "Reserve the items for this checkout order."},
    {"name": "payment", "index": 1,
     "prompt": "Charge the card for this checkout order."},
    {"name": "shipping", "index": 2,
     "prompt": "Schedule the delivery for this checkout order."},
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
# SHARED STATE — checkout record + step updates
# ============================================================================

def create_saga(checkout_id: str, package: dict) -> dict:
    """Seed a checkout with three pending steps and zeroed barrier counters.

    compensations_needed / compensations_completed live on the record from
    day one (cleaner than the demo's later initialize_barrier call).
    """
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
        "checkout_id": checkout_id,
        "overall_status": "running",
        "current_phase": "forward",
        "package": to_dynamo(package),
        "steps": to_dynamo(steps),
        "locked": False,
        "compensations_needed": 0,
        "compensations_completed": 0,
        "failed_step": None,
        "refund_total": 0,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    checkout_table.put_item(Item=item)
    return from_dynamo(item)


def get_saga(checkout_id: str) -> dict:
    response = checkout_table.get_item(Key={"checkout_id": checkout_id})
    return from_dynamo(response["Item"])


def update_step(checkout_id: str, index: int, updates: dict) -> dict:
    """Read-modify-write one step inside the checkout record (single-writer orchestrator)."""
    current = from_dynamo(checkout_table.get_item(Key={"checkout_id": checkout_id})["Item"])
    current["steps"][index].update(updates)
    checkout_table.put_item(Item=to_dynamo(current))
    return current


def update_saga(checkout_id: str, updates: dict) -> dict:
    """Read-modify-write top-level checkout fields (orchestrator only)."""
    current = from_dynamo(checkout_table.get_item(Key={"checkout_id": checkout_id})["Item"])
    current.update(updates)
    checkout_table.put_item(Item=to_dynamo(current))
    return current


# ============================================================================
# DISTRIBUTED LOCK — conditional flag acquire/release
# ============================================================================

def acquire_lock(checkout_id: str, max_retries: int = 5) -> bool:
    """Try to flip locked False -> True with a ConditionExpression.

    Returns True if this caller owns the lock. Retries briefly if another
    process holds it; returns False after max_retries.
    """
    for attempt in range(max_retries):
        try:
            checkout_table.update_item(
                Key={"checkout_id": checkout_id},
                UpdateExpression="SET locked = :expected",
                ConditionExpression="locked = :want",
                ExpressionAttributeValues={":expected": True, ":want": False},
            )
            return True
        except ClientError as e:
            if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
                time.sleep(0.05 * (2 ** attempt))
                continue
            raise
    return False


def release_lock(checkout_id: str) -> None:
    checkout_table.update_item(
        Key={"checkout_id": checkout_id},
        UpdateExpression="SET locked = :no",
        ExpressionAttributeValues={":no": False},
    )


# ============================================================================
# ATOMIC BARRIER — DynamoDB ADD, owned by each compensation tool
# ============================================================================

def increment_barrier(checkout_id: str) -> tuple[int, int]:
    """Increment barrier counter. Returns (completed, needed).

    DynamoDB's ADD expression cannot lose increments under contention;
    a read-modify-write would.
    """
    response = checkout_table.update_item(
        Key={"checkout_id": checkout_id},
        UpdateExpression="ADD compensations_completed :one",
        ExpressionAttributeValues={":one": 1},
        ReturnValues="ALL_NEW",
    )
    item = from_dynamo(response["Attributes"])
    return int(item["compensations_completed"]), int(item["compensations_needed"])


def set_barrier_target(checkout_id: str, needed: int) -> None:
    """Set compensations_needed when entering the compensation phase."""
    checkout_table.update_item(
        Key={"checkout_id": checkout_id},
        UpdateExpression="SET compensations_needed = :val",
        ExpressionAttributeValues={":val": int(needed)},
    )


# ============================================================================
# PURE HELPERS — deterministic checkout logic (tests never call Bedrock)
# ============================================================================

def reserve_items_logic(package: dict) -> dict:
    if package.get("simulate_failure") == "inventory":
        raise RuntimeError("Insufficient stock for one or more items")
    items = package.get("items", [])
    return {
        "confirmation": f"INV-{package['checkout_id'].split('-')[1]}",
        "item_count": len(items),
        "items": items,
    }


def release_items_logic(package: dict) -> dict:
    suffix = package["checkout_id"].split("-")[1]
    return {
        "cancelled": True,
        "confirmation": f"REL-{suffix}",
        "refund_amount": 0,
    }


def charge_card_logic(package: dict) -> dict:
    if package.get("simulate_failure") == "payment":
        raise RuntimeError("Insufficient funds")
    total = int(package.get("total", 0))
    return {
        "confirmation": f"PAY-{package['checkout_id'].split('-')[1]}",
        "amount": total,
        "last4": package.get("card_last4", "4242"),
    }


def refund_card_logic(package: dict) -> dict:
    suffix = package["checkout_id"].split("-")[1]
    total = int(package.get("total", 0))
    return {
        "cancelled": True,
        "confirmation": f"RFND-{suffix}",
        "comp_ref": f"RFND-{suffix}",
        "amount": total,
        "refund_amount": total,
    }


def schedule_delivery_logic(package: dict) -> dict:
    if package.get("simulate_failure") == "shipping":
        raise RuntimeError("Address is undeliverable")
    return {
        "confirmation": f"SHP-{package['checkout_id'].split('-')[1]}",
        "address": package.get("address", ""),
        "carrier": package.get("carrier", "Standard"),
    }


def cancel_delivery_logic(package: dict) -> dict:
    suffix = package["checkout_id"].split("-")[1]
    return {
        "cancelled": True,
        "confirmation": f"CAN-{suffix}",
        "refund_amount": 0,
    }


BOOK_LOGICS = {
    "inventory": reserve_items_logic,
    "payment": charge_card_logic,
    "shipping": schedule_delivery_logic,
}
CANCEL_LOGICS = {
    "inventory": release_items_logic,
    "payment": refund_card_logic,
    "shipping": cancel_delivery_logic,
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


FORWARD_TOOLS = {
    "inventory": "reserve_items",
    "payment": "charge_card",
    "shipping": "schedule_delivery",
}
CANCEL_TOOLS = {
    "inventory": "release_items",
    "payment": "refund_card",
    "shipping": "cancel_delivery",
}


def _checkout_tool(step_name: str, checkout_id: str, cancel_mode: bool):
    """Build the @tool that either performs or compensates one step.

    Compensation tools own their barrier increment so parallel compensations
    cannot lose counts under DynamoDB ADD.
    """
    index = next(c["index"] for c in AGENTS_CONFIG if c["name"] == step_name)

    if cancel_mode:
        def cancel_fn(checkout_id: str) -> str:
            saga = get_saga(checkout_id)
            package = from_dynamo(saga["package"])
            result = CANCEL_LOGICS[step_name](package)
            comp_ref = result.get("confirmation")
            update_step(checkout_id, index, {
                "status": "compensated",
                "compensation_ref": comp_ref,
                "refund_amount": int(result.get("refund_amount", 0)),
            })
            refund = int(result.get("refund_amount", 0))
            if refund:
                current = int(saga.get("refund_total", 0))
                update_saga(checkout_id, {"refund_total": current + refund})
            completed, needed = increment_barrier(checkout_id)
            print(f"      [Barrier] {completed}/{needed} compensations done")
            _record_compensation(step_name)
            payload = {
                "checkout_id": checkout_id,
                "action": CANCEL_TOOLS[step_name],
                **result,
            }
            if step_name == "payment":
                payload["amount"] = result.get("amount", 0)
                payload["comp_ref"] = result.get("comp_ref")
            return json.dumps(payload, indent=2)

        cancel_fn.__name__ = CANCEL_TOOLS[step_name]
        return tool(cancel_fn)

    def book_fn(checkout_id: str) -> str:
        saga = get_saga(checkout_id)
        package = from_dynamo(saga["package"])
        try:
            result = BOOK_LOGICS[step_name](package)
        except Exception as error:
            update_step(checkout_id, index, {
                "status": "failed",
                "detail": str(error),
            })
            return json.dumps({
                "checkout_id": checkout_id,
                "action": FORWARD_TOOLS[step_name],
                "success": False,
                "error": str(error),
            }, indent=2)

        update_step(checkout_id, index, {
            "status": "completed",
            "booking_ref": result.get("confirmation"),
            "detail": result,
        })
        _record_forward(step_name)
        return json.dumps({
            "checkout_id": checkout_id,
            "action": FORWARD_TOOLS[step_name],
            "success": True,
            **result,
        }, indent=2)

    book_fn.__name__ = FORWARD_TOOLS[step_name]
    return tool(book_fn)


def _build_service_agent(step_name: str, cancel_mode: bool, checkout_id: str) -> Agent:
    model = BedrockModel(model_id=NOVA_LITE_MODEL, region_name=AWS_REGION, temperature=0.0)
    tool_name = CANCEL_TOOLS[step_name] if cancel_mode else FORWARD_TOOLS[step_name]
    system_prompt = (
        f"You are an e-commerce {step_name} agent. "
        f"The user message includes checkout_id. "
        f"Call {tool_name} exactly ONCE with that checkout_id. "
        "Return ONLY the JSON result from the tool. Do NOT add commentary."
    )
    agent_tool = _checkout_tool(step_name, checkout_id, cancel_mode)
    return Agent(model=model, system_prompt=system_prompt, tools=[agent_tool])


def build_inventory_agent(cancel_mode: bool = False, checkout_id: str = "") -> Agent:
    return _build_service_agent("inventory", cancel_mode, checkout_id)


def build_payment_agent(cancel_mode: bool = False, checkout_id: str = "") -> Agent:
    return _build_service_agent("payment", cancel_mode, checkout_id)


def build_shipping_agent(cancel_mode: bool = False, checkout_id: str = "") -> Agent:
    return _build_service_agent("shipping", cancel_mode, checkout_id)


BUILDERS = {
    "inventory": build_inventory_agent,
    "payment": build_payment_agent,
    "shipping": build_shipping_agent,
}


# ============================================================================
# ORCHESTRATOR — forward path + reverse compensation + barrier resolve
# ============================================================================

def run_saga(checkout_id: str) -> dict:
    """Drive forward agents; on failure compensate in reverse under a lock.

    Tools already incremented compensations_completed, so after releasing
    the lock the orchestrator only compares completed vs needed.
    """
    print("\n" + "=" * 70)
    print(f"Checkout {checkout_id} - forward path")
    print("=" * 70)

    saga = get_saga(checkout_id)
    package = from_dynamo(saga["package"])
    failed_step: int | None = None

    for cfg in AGENTS_CONFIG:
        update_saga(checkout_id, {"current_phase": cfg["name"]})
        update_step(checkout_id, cfg["index"], {"status": "executing"})
        builder = BUILDERS[cfg["name"]]
        prompt = f"{cfg['prompt']} Use checkout_id={checkout_id}."
        try:
            run_agent_with_retry(
                builder,
                prompt,
                cancel_mode=False,
                checkout_id=checkout_id,
            )
        except Exception:
            update_step(checkout_id, cfg["index"], {"status": "failed", "detail": "agent error"})
            failed_step = cfg["index"]
            break

        step = get_saga(checkout_id)["steps"][cfg["index"]]
        print(f"  forward {cfg['name']:10s} -> {step['status']}"
              + (f"  ref={step.get('booking_ref')}" if step.get("booking_ref") else ""))
        if step["status"] == "failed":
            failed_step = cfg["index"]
            print(f"  step failed: {step.get('detail')}")
            break
        if step["status"] != "completed":
            update_step(checkout_id, cfg["index"], {
                "status": "failed",
                "detail": "agent did not complete step",
            })
            failed_step = cfg["index"]
            break

    if failed_step is None:
        result = update_saga(checkout_id, {"overall_status": "completed", "current_phase": "done"})
        print("  overall_status: completed")
        return result

    # --- Compensation phase ---
    print("\n" + "=" * 70)
    print(f"Checkout {checkout_id} - compensation (reverse order)")
    print("=" * 70)

    saga = get_saga(checkout_id)
    completed_steps = [
        (i, s) for i, s in enumerate(saga["steps"])
        if s["status"] == "completed"
    ]
    completed_steps.reverse()  # reverse completion order

    update_saga(checkout_id, {
        "overall_status": "compensating",
        "failed_step": failed_step,
        "current_phase": "compensation",
    })
    set_barrier_target(checkout_id, needed=len(completed_steps))

    print(f"  compensating {len(completed_steps)} step(s): "
          f"{[s['name'] for _, s in completed_steps]}")

    if not acquire_lock(checkout_id):
        raise SagaError(f"Could not acquire lock for checkout {checkout_id}")

    try:
        for idx, step in completed_steps:
            update_step(checkout_id, idx, {"status": "compensating"})
            builder = BUILDERS[step["name"]]
            run_agent_with_retry(
                builder,
                f"Cancel {step['name']} for checkout {checkout_id}",
                cancel_mode=True,
                checkout_id=checkout_id,
            )
            refreshed = get_saga(checkout_id)["steps"][idx]
            print(f"  compensate {step['name']:10s} -> {refreshed['status']}"
                  f"  ref={refreshed.get('compensation_ref')}")
    finally:
        release_lock(checkout_id)

    # Tools already incremented the barrier — orchestrator only checks it.
    saga_final = get_saga(checkout_id)
    completed = int(saga_final["compensations_completed"])
    needed = int(saga_final["compensations_needed"])
    if completed >= needed:
        update_saga(checkout_id, {"overall_status": "failed", "current_phase": "resolved"})
        print(f"  overall_status: failed (barrier {completed}/{needed})")
        print(f"  total refund: ${int(saga_final.get('refund_total', 0))}")
    else:
        # Stay in compensating so an operator can investigate stuck reversals.
        print(f"  overall_status: compensating (barrier {completed}/{needed}) "
              f"- waiting for operator review")
        update_saga(checkout_id, {"current_phase": "stalled"})

    return get_saga(checkout_id)


# ============================================================================
# SCENARIOS
# ============================================================================

def run_scenario_success(checkout_id: str = "CHECKOUT-001") -> dict:
    """Scenario 1: Alice's laptop order — all three steps succeed."""
    print("\n" + "=" * 70)
    print("Scenario 1 - Success (inventory + payment + shipping all complete)")
    print("=" * 70)

    package = {
        "checkout_id": checkout_id,
        "customer": "Alice",
        "items": ["Pro Laptop", "Laptop Sleeve"],
        "total": 1499,
        "card_last4": "4242",
        "address": "123 Main St, Springfield",
        "carrier": "Express",
        "simulate_failure": None,
    }
    create_saga(checkout_id, package)
    print(f"Created {checkout_id} (Alice Pro Laptop + Sleeve, no failure)")

    final = run_saga(checkout_id)
    metrics = get_metrics()
    print(f"Forward order: {metrics['forward']}")
    print(f"Compensations: {metrics['compensation_order'] or 'none'}")
    _print_saga(final)
    return final


def run_scenario_payment_failure(checkout_id: str = "CHECKOUT-002") -> dict:
    """Scenario 2: Bob's phone order — payment fails, only inventory compensates."""
    print("\n" + "=" * 70)
    print("Scenario 2 - Payment fails (only inventory released)")
    print("=" * 70)

    package = {
        "checkout_id": checkout_id,
        "customer": "Bob",
        "items": ["Smartphone x2", "X-Device", "Wireless Chargers"],
        "total": 1196,
        "card_last4": "0002",
        "address": "456 Oak Ave, Metropolis",
        "carrier": "Standard",
        "simulate_failure": "payment",
    }
    create_saga(checkout_id, package)
    print(f"Created {checkout_id} (Bob phones + accessories, simulate_failure=payment)")

    final = run_saga(checkout_id)
    metrics = get_metrics()
    print(f"Forward order: {metrics['forward']}")
    print(f"Compensation order: {metrics['compensation_order']} "
          f"(reverse of forward - last success undone first)")
    _print_saga(final)
    return final


def run_scenario_shipping_failure(checkout_id: str = "CHECKOUT-003") -> dict:
    """Scenario 3: Carol's desk order — shipping fails, payment+inventory compensate."""
    print("\n" + "=" * 70)
    print("Scenario 3 - Shipping fails (refund payment, then release inventory)")
    print("=" * 70)

    package = {
        "checkout_id": checkout_id,
        "customer": "Carol",
        "items": ["Standing Desk", "4K Monitor"],
        "total": 899,
        "card_last4": "1881",
        "address": "Undeliverable Island",
        "carrier": "Freight",
        "simulate_failure": "shipping",
    }
    create_saga(checkout_id, package)
    print(f"Created {checkout_id} (Carol desk + monitor, simulate_failure=shipping)")

    final = run_saga(checkout_id)
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
    print(f"Final: overall_status={saga['overall_status']}  "
          f"locked={saga['locked']}  "
          f"barrier={saga['compensations_completed']}/{saga['compensations_needed']}  "
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
        "Identical to demo - Saga pattern, compensating transactions, reverse order, state machine",
        "New - Barrier coordination via atomic DynamoDB ADD inside each compensation tool",
        "Each compensation tool owns increment_barrier, enabling safe parallel compensation",
        "Only completed forward steps are compensated (failed/pending are not undone)",
        "Compensations run in exact reverse order to unwind dependencies cleanly",
        "Distributed lock still serializes who may run compensation for a checkout",
        "Saga resolves to failed only when compensations_completed >= compensations_needed",
        "If the barrier stalls, overall_status stays compensating for operator review",
    ]
    for i, text in enumerate(insights, 1):
        print(f"  {i}. {text}")


def main() -> None:
    """CLI entrypoint. Runs all three checkout scenarios and prints the report."""
    print("=" * 70)
    print("E-commerce Checkout - Saga Pattern with Tool-Owned Barrier")
    print("=" * 70)

    reset_metrics()
    saga1 = run_scenario_success("CHECKOUT-001")
    reset_metrics()
    saga2 = run_scenario_payment_failure("CHECKOUT-002")
    reset_metrics()
    saga3 = run_scenario_shipping_failure("CHECKOUT-003")

    print("\n" + "=" * 70)
    print("Summary")
    print("=" * 70)
    for saga in (saga1, saga2, saga3):
        steps = {s["name"]: s["status"] for s in saga["steps"]}
        print(f"  {saga['checkout_id']}: overall_status={saga['overall_status']}  "
              f"barrier={saga['compensations_completed']}/{saga['compensations_needed']}  "
              f"refund=${int(saga.get('refund_total', 0))}  "
              f"steps={steps}")

    _print_insights()
    print("\nWhy reverse order? Later steps may depend on earlier ones; "
          "unwinding from the most recent completed step prevents orphans.")


if __name__ == "__main__":
    main()
