"""
List existing AgentCore resources (gateways, targets, agent runtimes, harnesses).

Usage:
    python list_agentcore_resources.py
"""

import json

from _common import client, REGION


def show(label: str, items) -> None:
    print(f"\n=== {label} ({len(items)}) ===")
    for it in items:
        print(json.dumps(it, default=str))


def main() -> None:
    control = client("bedrock-agentcore-control")

    gateways = control.list_gateways().get("items", [])
    show("Gateways", gateways)

    for g in gateways:
        gid = g["gatewayId"]
        targets = control.list_gateway_targets(gatewayIdentifier=gid).get("items", [])
        show(f"  Targets in {g['name']}", targets)

    runtimes = control.list_agent_runtimes().get("items", [])
    show("Agent Runtimes", runtimes)

    harnesses = control.list_harnesses().get("items", [])
    show("Harnesses", harnesses)


if __name__ == "__main__":
    main()
