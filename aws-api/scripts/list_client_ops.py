"""
List all public operations on a boto3 client.

Usage:
    python list_client_ops.py <client-name>
    python list_client_ops.py bedrock-agentcore-control
    python list_client_ops.py bedrock-agent
    python list_client_ops.py bedrock-agentcore
    python list_client_ops.py bedrock-runtime
    python list_client_ops.py bedrock
"""

import sys

from _common import client, REGION


def main(client_name: str) -> None:
    c = client(client_name)
    ops = sorted(
        m
        for m in dir(c)
        if not m.startswith("_")
        and callable(getattr(c, m, None))
        and not m.startswith("get_")
        or m.startswith(("create_", "update_", "delete_", "list_", "invoke_", "prepare_"))
    )
    # Filter to a tidy list of likely public operations
    public = [
        m
        for m in ops
        if not m.startswith(("can_", "close", "exceptions", "generate_", "get_paginator",
                            "get_waiter", "meta", "waiter_"))
    ]
    print(f"Client: {client_name} (region={REGION})")
    print(f"Public operations: {len(public)}")
    for op in public:
        print(f"  {op}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(1)
    main(sys.argv[1])
