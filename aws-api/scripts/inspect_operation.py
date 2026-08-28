"""
Print the input/output structure of a boto3 operation from the service model.

Usage:
    python inspect_operation.py <client-name> <OperationName>
    python inspect_operation.py bedrock-agentcore-control CreateHarness
    python inspect_operation.py bedrock-agentcore-control CreateGateway
    python inspect_operation.py bedrock-agentcore-control CreateGatewayTarget
    python inspect_operation.py bedrock-agentcore-control GetHarness
    python inspect_operation.py bedrock-agentcore InvokeHarness
"""

import sys

from _common import client


def shape(name: str, sh, indent: int = 0) -> None:
    pad = "  " * indent
    t = sh.type_name
    if t == "structure":
        print(f"{pad}{name}: structure")
        for sn, sm in sh.members.items():
            shape(sn, sm, indent + 1)
    elif t == "list":
        print(f"{pad}{name}: list<{sh.member.type_name}>")
        if hasattr(sh.member, "members"):
            for sn, sm in sh.member.members.items():
                shape(sn, sm, indent + 1)
    elif t == "map":
        print(f"{pad}{name}: map<{sh.key.type_name},{sh.value.type_name}>")
    else:
        print(f"{pad}{name}: {t}")


def main(client_name: str, operation: str) -> None:
    c = client(client_name)
    sm = c._service_model
    op = sm.operation_model(operation)
    print(f"### {client_name} -> {operation}")
    req = op.input_shape.metadata.get("required", []) if op.input_shape else []
    print(f"Required input: {req}")
    if op.input_shape:
        print("Input members:")
        for n, m in op.input_shape.members.items():
            marker = " (required)" if n in req else ""
            print(f"  {n}{marker}")
            shape(n, m, indent=2)
    if op.output_shape:
        print()
        print("Output members:")
        for n, m in op.output_shape.members.items():
            print(f"  {n}")
            shape(n, m, indent=2)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(1)
    main(sys.argv[1], sys.argv[2])
