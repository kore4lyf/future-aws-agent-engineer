"""
Inspect an AgentCore Gateway and all its Targets in detail.

Usage:
    python inspect_gateway.py <gateway-name-or-id>
    python inspect_gateway.py demo3-gateway
"""

import json
import sys

from _common import client


def main(identifier: str) -> None:
    control = client("bedrock-agentcore-control")

    # Find gateway
    gateways = control.list_gateways().get("items", [])
    gw = next(
        (g for g in gateways if g["name"] == identifier or g["gatewayId"] == identifier),
        None,
    )
    if not gw:
        print(f"Gateway '{identifier}' not found.")
        sys.exit(1)

    gid = gw["gatewayId"]
    full = control.get_gateway(gatewayIdentifier=gid)
    print(f"### Gateway: {gw['name']} ({gid})")
    print(json.dumps(full.get("gateway", full), default=str, indent=2))

    targets = control.list_gateway_targets(gatewayIdentifier=gid).get("items", [])
    for t in targets:
        tid = t.get("targetId")
        full_t = control.get_gateway_target(gatewayIdentifier=gid, targetId=tid)
        print(f"\n### Target: {t.get('name')} ({tid})")
        print(json.dumps(full_t, default=str, indent=2))


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(1)
    main(sys.argv[1])
