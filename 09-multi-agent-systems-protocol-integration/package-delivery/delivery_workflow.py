# =============================================================================
# Package Delivery — Multi-Agent Orchestration Exercise
# =============================================================================
# Demonstrates three orchestration patterns in a single workflow:
#   Phase 1 (Gate):        validate address before anything else
#   Phase 2 (Parallel):    label, insurance, carrier run concurrently
#   Phase 3 (Conditional): route to domestic or international shipping
# ============================================================================

import json
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from dotenv import load_dotenv
from strands import Agent, tool
from strands.models import BedrockModel

load_dotenv()

# --- Bedrock configuration ---
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
NOVA_LITE_MODEL = os.environ.get("NOVA_LITE_MODEL", "amazon.nova-lite-v1:0")

# --- Test packages ---
# PKG-001: valid US → US (domestic route)
# PKG-002: valid US → UK (international route)
# PKG-003: invalid address, halt at gate
PACKAGES = [
    {
        "id": "PKG-001",
        "sender": {"name": "Alice", "address": "123 Main St", "city": "Seattle", "state": "WA", "zip": "98101", "country": "US"},
        "recipient": {"name": "Bob", "address": "456 Oak Ave", "city": "Portland", "state": "OR", "zip": "97201", "country": "US"},
        "weight_kg": 2.5,
        "value": 150.00,
    },
    {
        "id": "PKG-002",
        "sender": {"name": "Carol", "address": "789 Pine Ln", "city": "San Francisco", "state": "CA", "zip": "94105", "country": "US"},
        "recipient": {"name": "Dave", "address": "10 Downing St", "city": "London", "state": "", "zip": "SW1A 2AA", "country": "UK"},
        "weight_kg": 5.0,
        "value": 800.00,
    },
    {
        "id": "PKG-003",
        "sender": {"name": "Eve", "address": "", "city": "", "state": "", "zip": "", "country": ""},
        "recipient": {"name": "Frank", "address": "321 Elm St", "city": "Chicago", "state": "IL", "zip": "60601", "country": "US"},
        "weight_kg": 1.0,
        "value": 50.00,
    },
]

# --- Shared workflow state ---
# Each agent writes its result here so downstream agents can read it.
workflow_state = {}


def clean_response(text: str) -> str:
    """Strip <thinking> tags from model output."""
    return re.sub(r"<thinking>.*?</thinking>", "", str(text), flags=re.DOTALL).strip()


def run_agent_with_retry(agent_builder, prompt: str, max_retries: int = 3) -> str:
    """Wrap an agent invocation with exponential backoff (1s, 2s, 4s).

    Catches transient Bedrock errors and retries without crashing the phase.
    """
    for attempt in range(max_retries):
        try:
            agent = agent_builder()
            result = agent(prompt)
            return clean_response(result)
        except Exception as error:
            if attempt < max_retries - 1:
                wait = 2 ** attempt
                print(f"[Retry {attempt + 1}/{max_retries}] ({error.__class__.__name__}), waiting {wait}s...")
                time.sleep(wait)
                continue
            print(f"[Failed] ({error.__class__.__name__}) after {max_retries} attempts")
            raise


def _get_package(package_id: str) -> dict:
    """Look up a package dict by ID from the PACKAGES roster."""
    return next(p for p in PACKAGES if p["id"] == package_id)


# ============================================================================
# TODO 1-6: AGENT PROMPTS
# Write a focused, single-purpose system prompt for each worker agent.
# Each prompt must instruct the agent to call its designated tool with the
# given package ID and specify exactly what the agent should report back.
# ============================================================================

# TODO 1: Address Validator — validates sender/recipient addresses
def build_address_validator() -> Agent:
    """Validate that the package has a complete, non-empty address.

    Writes to workflow_state["validation"].
    """
    model = BedrockModel(model_id=NOVA_LITE_MODEL, region_name=AWS_REGION, temperature=0.0)

    # TODO 1: Write the system prompt
    system_prompt = """You are an address validation agent. Your ONLY job:
1. Call validate_address with the package_id
2. Report in exactly 2 lines:
   Valid: <YES|NO>
   Reason: <one-sentence>
Do NOT add any other commentary."""

    @tool
    def validate_address(package_id: str) -> str:
        pkg = _get_package(package_id)
        sender = pkg["sender"]
        # Check that sender has all required fields filled in
        valid = all([sender["address"], sender["city"], sender["state"], sender["zip"], sender["country"]])
        reason = "Address is complete" if valid else "Missing required address fields"
        result = {"package_id": package_id, "valid": valid, "reason": reason}
        workflow_state["validation"] = result
        return json.dumps(result, indent=2)

    return Agent(model=model, system_prompt=system_prompt, tools=[validate_address])


# TODO 2: Label Generator — generates shipping label
def build_label_generator() -> Agent:
    """Generate a shipping label from package details.

    Writes to workflow_state["label"].
    """
    model = BedrockModel(model_id=NOVA_LITE_MODEL, region_name=AWS_REGION, temperature=0.0)

    # TODO 2: Write the system prompt
    system_prompt = """You are a label generation agent. Your ONLY job:
1. Call generate_label with the package_id
2. Report: Label created for <package_id> (<sender_city> → <recipient_city>)
Do NOT add any other commentary."""

    @tool
    def generate_label(package_id: str) -> str:
        pkg = _get_package(package_id)
        result = {
            "package_id": package_id,
            "label_id": f"LBL-{package_id}",
            "from": f"{pkg['sender']['city']}, {pkg['sender']['country']}",
            "to": f"{pkg['recipient']['city']}, {pkg['recipient']['country']}",
        }
        workflow_state["label"] = result
        return json.dumps(result, indent=2)

    return Agent(model=model, system_prompt=system_prompt, tools=[generate_label])


# TODO 3: Insurance Calculator — calculates insurance cost
def build_insurance_calculator() -> Agent:
    """Calculate insurance based on package value.

    Writes to workflow_state["insurance"].
    """
    model = BedrockModel(model_id=NOVA_LITE_MODEL, region_name=AWS_REGION, temperature=0.0)

    # TODO 3: Write the system prompt
    system_prompt = """You are an insurance calculation agent. Your ONLY job:
1. Call calculate_insurance with the package_id
2. Report: Insurance calculated for <package_id> ($<amount> coverage)
Do NOT add any other commentary."""

    @tool
    def calculate_insurance(package_id: str) -> str:
        pkg = _get_package(package_id)
        # 2% of package value, minimum $5
        insurance_cost = max(pkg["value"] * 0.02, 5.00)
        result = {
            "package_id": package_id,
            "coverage": pkg["value"],
            "cost": round(insurance_cost, 2),
        }
        workflow_state["insurance"] = result
        return json.dumps(result, indent=2)

    return Agent(model=model, system_prompt=system_prompt, tools=[calculate_insurance])


# TODO 4: Carrier Selector — selects best carrier
def build_carrier_selector() -> Agent:
    """Select a carrier based on destination and weight.

    Writes to workflow_state["carrier"].
    """
    model = BedrockModel(model_id=NOVA_LITE_MODEL, region_name=AWS_REGION, temperature=0.0)

    # TODO 4: Write the system prompt
    system_prompt = """You are a carrier selection agent. Your ONLY job:
1. Call select_carrier with the package_id
2. Report: Carrier selected for <package_id> (<carrier_name>)
Do NOT add any other commentary."""

    @tool
    def select_carrier(package_id: str) -> str:
        pkg = _get_package(package_id)
        is_international = pkg["sender"]["country"] != pkg["recipient"]["country"]
        # Select carrier based on domestic vs international
        carrier = "USPS Priority" if not is_international else "DHL Express"
        result = {"package_id": package_id, "carrier": carrier, "international": is_international}
        workflow_state["carrier"] = result
        return json.dumps(result, indent=2)

    return Agent(model=model, system_prompt=system_prompt, tools=[select_carrier])


# ============================================================================
# TODO 9: CONDITIONAL SHIPPING AGENTS
# ============================================================================

# TODO 5: Domestic Shipping Agent
def build_domestic_shipping() -> Agent:
    """Process domestic shipping. Writes to workflow_state["shipping"].

    Routes here when sender.country == recipient.country.
    """
    model = BedrockModel(model_id=NOVA_LITE_MODEL, region_name=AWS_REGION, temperature=0.0)

    # TODO 5: Write the system prompt
    system_prompt = """You are a domestic shipping agent. Your ONLY job:
1. Call process_domestic with the package_id
2. Report: Domestic shipping initiated for <package_id> via <carrier>
Do NOT add any other commentary."""

    @tool
    def process_domestic(package_id: str) -> str:
        carrier = workflow_state.get("carrier", {}).get("carrier", "USPS")
        result = {"package_id": package_id, "shipping_type": "domestic", "carrier": carrier, "status": "initiated"}
        workflow_state["shipping"] = result
        return json.dumps(result, indent=2)

    return Agent(model=model, system_prompt=system_prompt, tools=[process_domestic])


# TODO 6: International Shipping Agent
def build_international_shipping() -> Agent:
    """Process international shipping. Writes to workflow_state["shipping"].

    Routes here when sender.country != recipient.country.
    """
    model = BedrockModel(model_id=NOVA_LITE_MODEL, region_name=AWS_REGION, temperature=0.0)

    # TODO 6: Write the system prompt
    system_prompt = """You are an international shipping agent. Your ONLY job:
1. Call process_international with the package_id
2. Report: International shipping initiated for <package_id> via <carrier> with customs forms
Do NOT add any other commentary."""

    @tool
    def process_international(package_id: str) -> str:
        carrier = workflow_state.get("carrier", {}).get("carrier", "DHL")
        result = {"package_id": package_id, "shipping_type": "international", "carrier": carrier, "customs_forms": True, "status": "initiated"}
        workflow_state["shipping"] = result
        return json.dumps(result, indent=2)

    return Agent(model=model, system_prompt=system_prompt, tools=[process_international])


# ============================================================================
# ORCHESTRATOR
# ============================================================================

def orchestrate_delivery(package_id: str) -> dict:
    """Run the full delivery workflow for a single package.

    Phase 1 (Gate):        validate address — if invalid, halt immediately
    Phase 2 (Parallel):    label, insurance, carrier run concurrently
    Phase 3 (Conditional): route to domestic or international shipping
    """
    pkg = _get_package(package_id)

    # Clear state from any previous run
    workflow_state.clear()

    # --- TODO 7: PHASE 1 — SEQUENTIAL GATE (address validation) ---
    # Invoke address validator, read validation result from workflow_state.
    # If address is invalid, halt immediately and return early failure dict.
    run_agent_with_retry(build_address_validator, f"Validate address for {package_id}")
    validation = workflow_state.get("validation", {})
    if not validation.get("valid", False):
        # Return early failure — do NOT continue to Phase 2 or 3
        return {
            "package_id": package_id,
            "status": "HALTED",
            "reason": validation.get("reason", "Address validation failed"),
            "phases_completed": ["gate"],
        }

    # --- TODO 8: PHASE 2 — PARALLEL DISPATCH ---
    # Run label generator, insurance calculator, and carrier selector
    # simultaneously. Store timing results in workflow_state.
    phase2_start = time.perf_counter()
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {
            executor.submit(run_agent_with_retry, build_label_generator, f"Generate label for {package_id}"): "label",
            executor.submit(run_agent_with_retry, build_insurance_calculator, f"Calculate insurance for {package_id}"): "insurance",
            executor.submit(run_agent_with_retry, build_carrier_selector, f"Select carrier for {package_id}"): "carrier",
        }
        for f in as_completed(futures):
            f.result()
    phase2_end = time.perf_counter()
    # Store timing in workflow_state so orchestrator can access it
    workflow_state["phase2_seconds"] = round(phase2_end - phase2_start, 4)

    # --- TODO 9: PHASE 3 — CONDITIONAL ROUTING ---
    # Evaluate sender's country against destination country.
    # Use workflow_state["carrier"]["international"] to route.
    carrier_result = workflow_state.get("carrier", {})
    if carrier_result.get("international", False):
        run_agent_with_retry(build_international_shipping, f"Process international shipping for {package_id}")
    else:
        run_agent_with_retry(build_domestic_shipping, f"Process domestic shipping for {package_id}")

    return build_delivery_summary(package_id)


def build_delivery_summary(package_id: str) -> dict:
    """Assemble all workflow_state entries into a single summary dict."""
    pkg = _get_package(package_id)
    validation = workflow_state.get("validation", {})
    label = workflow_state.get("label", {})
    insurance = workflow_state.get("insurance", {})
    carrier = workflow_state.get("carrier", {})
    shipping = workflow_state.get("shipping", {})

    return {
        "package": {
            "id": package_id,
            "sender": pkg["sender"],
            "recipient": pkg["recipient"],
            "weight_kg": pkg["weight_kg"],
            "value": pkg["value"],
        },
        "validation": validation,
        "label": label,
        "insurance": insurance,
        "carrier": carrier,
        "shipping": shipping,
        "timing": {
            "phase2_seconds": workflow_state.get("phase2_seconds", 0),
        },
    }


def main() -> None:
    """CLI entrypoint. Delivers all packages (or a single one via --package-id)."""
    import argparse
    parser = argparse.ArgumentParser(description="Package Delivery Orchestrator")
    parser.add_argument("--package-id", default=None, help="Deliver specific package")
    args = parser.parse_args()

    # Filter to single package if --package-id is provided
    if args.package_id:
        packages = [p for p in PACKAGES if p["id"] == args.package_id]
        if not packages:
            print(f"Error: Package {args.package_id} not found")
            return
    else:
        packages = PACKAGES

    # Run the orchestrator for each package and print the summary
    for pkg in packages:
        summary = orchestrate_delivery(pkg["id"])
        print(f"\n{'=' * 70}")
        print(f"DELIVERY: {summary['package']['id']}")
        print(f"From: {summary['package']['sender']['name']} ({summary['package']['sender']['city']}, {summary['package']['sender']['country']})")
        print(f"To: {summary['package']['recipient']['name']} ({summary['package']['recipient']['city']}, {summary['package']['recipient']['country']})")
        print(f"Status: {summary['shipping'].get('status', summary.get('status', 'unknown'))}")
        print(f"{'=' * 70}")
        print(f"Validation: {summary['validation']}")
        print(f"Label: {summary['label']}")
        print(f"Insurance: {summary['insurance']}")
        print(f"Carrier: {summary['carrier']}")
        print(f"Shipping: {summary['shipping']}")
        print(f"Phase 2 Time: {summary['timing']['phase2_seconds']}s")


if __name__ == "__main__":
    main()
