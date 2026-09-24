# =============================================================================
# Supply Chain Gateway — Lesson 11 Demo
# =============================================================================
# Plugin-architecture supply chain agent using a centralized gateway:
#   1. LambdaGateway: register, discover, invoke tool backends
#   2. Dynamic discovery: agent builds system prompt from registry at runtime
#   3. Thin @tool shims delegate to gateway
#   4. Mid-run registration: quality_inspection_api added without agent restart
#   5. Centralized observability: invocation_log
# ============================================================================

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

import boto3
from dotenv import load_dotenv
from strands import Agent, tool
from strands.models import BedrockModel

load_dotenv()

sys.path.insert(0, str(Path(__file__).parent))

AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
NOVA_LITE_MODEL = os.environ.get("NOVA_LITE_MODEL", "amazon.nova-lite-v1:0")

AGENTCORE_ROLE_ARN = os.environ.get("AGENTCORE_ROLE_ARN", "").strip()

INVENTORY_LAMBDA = os.environ.get("INVENTORY_LAMBDA", "lesson11-demo-inventory-api")
SHIPPING_LAMBDA = os.environ.get("SHIPPING_LAMBDA", "lesson11-demo-shipping-api")
SUPPLIER_LAMBDA = os.environ.get("SUPPLIER_LAMBDA", "lesson11-demo-supplier-api")
QUALITY_LAMBDA = os.environ.get("QUALITY_LAMBDA", "lesson11-demo-quality-inspection-api")


# ============================================================================
# LambdaGateway: register, discover, invoke
# ============================================================================

class LambdaGateway:
    """Centralized registry that routes tool calls to AWS Lambda backends."""

    def __init__(self, name: str, description: str):
        self.name = name
        self.description = description
        self.targets: dict[str, dict[str, str]] = {}
        self.invocation_log: list[dict[str, Any]] = []
        self._lambda_client = boto3.client("lambda", region_name=AWS_REGION)

    def register_target(self, name: str, description: str, function_name: str,
                        target_type: str = "lambda") -> None:
        """Register a new tool backend."""
        self.targets[name] = {
            "description": description,
            "function_name": function_name,
            "target_type": target_type,
        }

    def discover_tools(self, query: str | None = None) -> list[dict[str, str]]:
        """Return registered tools, optionally filtered by semantic query."""
        tools = [
            {"name": name, "description": target["description"]}
            for name, target in self.targets.items()
        ]
        if query:
            q = query.lower()
            tools = [t for t in tools if q in t["name"].lower() or q in t["description"].lower()]
        return tools

    def invoke_tool(self, tool_name: str, params: dict[str, Any]) -> dict[str, Any]:
        """Resolve target Lambda and invoke it."""
        target = self.targets[tool_name]
        response = self._lambda_client.invoke(
            FunctionName=target["function_name"],
            InvocationType="RequestResponse",
            Payload=json.dumps(params),
        )
        result = json.loads(response["Payload"].read().decode("utf-8"))
        self.invocation_log.append({
            "tool": tool_name,
            "params": params,
            "result_status": result.get("status"),
        })
        return result


# ============================================================================
# Supply chain agent — discovers tools via gateway
# ============================================================================

def build_supply_chain_agent(gateway: LambdaGateway) -> Agent:
    """Build agent whose system prompt is generated from the gateway registry."""
    model = BedrockModel(model_id=NOVA_LITE_MODEL, region_name=AWS_REGION, temperature=0.1)

    tool_list = "\n".join(
        f"  - {t['name']}: {t['description']}"
        for t in gateway.discover_tools()
    )

    system_prompt = f"""You are a supply chain management agent.
You have access to the following tools via AgentCore Gateway:

{tool_list}

Use the appropriate tool for each query. When summarizing, include relevant
details from the tool output (stock levels, status, ETA, ratings, etc.)."""

    @tool
    def check_inventory(item_id: str) -> str:
        """Check inventory level and reorder status for an item."""
        result = gateway.invoke_tool("inventory_api", {"item_id": item_id})
        return json.dumps(result, indent=2)

    @tool
    def track_shipment(shipment_id: str) -> str:
        """Track shipping status and ETA for a shipment."""
        result = gateway.invoke_tool("shipping_api", {"shipment_id": shipment_id})
        return json.dumps(result, indent=2)

    @tool
    def lookup_supplier(supplier_id: str = "") -> str:
        """Look up supplier information by ID, or list all suppliers."""
        params = {"supplier_id": supplier_id} if supplier_id else {}
        result = gateway.invoke_tool("supplier_api", params)
        return json.dumps(result, indent=2)

    @tool
    def inspect_quality(item_id: str) -> str:
        """Inspect quality status and defect rate for an item."""
        result = gateway.invoke_tool("quality_inspection_api", {"item_id": item_id})
        return json.dumps(result, indent=2)

    return Agent(
        model=model,
        system_prompt=system_prompt,
        tools=[check_inventory, track_shipment, lookup_supplier, inspect_quality],
    )


# ============================================================================
# MAIN
# ============================================================================

def main() -> None:
    print("=" * 70)
    print("Lesson 11 Demo — Supply Chain Gateway")
    print("=" * 70)

    # Create gateway and register core tools
    gateway = LambdaGateway(name="supply-chain-gateway",
                           description="Central registry for supply chain tool backends")

    print("\n[1] Registering core tools...")
    gateway.register_target("inventory_api", "Check inventory levels and reorder points", INVENTORY_LAMBDA)
    gateway.register_target("shipping_api", "Track shipment status and ETA", SHIPPING_LAMBDA)
    gateway.register_target("supplier_api", "Look up supplier info by ID or list all", SUPPLIER_LAMBDA)
    print(f"  Registered: {list(gateway.targets.keys())}")

    # Build agent from registry
    print("\n[2] Building agent from gateway registry...")
    agent = build_supply_chain_agent(gateway)
    print(f"  Tools in prompt: {[t['name'] for t in gateway.discover_tools()]}")

    # Queries 1-3: core tools
    queries = [
        ("Inventory check", "What is the inventory level for DIGI-002 copper wire?"),
        ("Shipment tracking", "What is the status of shipment SHIP-102?"),
        ("Supplier list", "List all available suppliers and their lead times."),
    ]

    for label, query in queries:
        print(f"\n[3] Query: {label}")
        print(f"  Input: {query}")
        response = str(agent(query))
        print(f"  Output: {response[:200]}...")

    # Dynamic registration: add quality inspection mid-run
    print("\n[4] Dynamically registering quality_inspection_api...")
    gateway.register_target("quality_inspection_api", "Inspect quality status and defect rate for items", QUALITY_LAMBDA)
    print(f"  Registered: {list(gateway.targets.keys())}")

    # Rebuild agent so it discovers the new tool
    agent = build_supply_chain_agent(gateway)
    print(f"  Tools in prompt: {[t['name'] for t in gateway.discover_tools()]}")

    # Query 4: uses the dynamically added tool
    print("\n[5] Query: Quality inspection (dynamic tool)")
    query = "What is the quality inspection result for Widget 002?"
    print(f"  Input: {query}")
    response = str(agent(query))
    print(f"  Output: {response[:200]}...")

    # Invocation log
    print("\n[6] Invocation log (centralized observability):")
    for entry in gateway.invocation_log:
        print(f"  {entry['tool']:25s} params={entry['params']} status={entry['result_status']}")

    print("\n" + "=" * 70)
    print("Gateway demo complete")
    print("=" * 70)


if __name__ == "__main__":
    main()
