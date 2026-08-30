"""
Customer Support Flow – Cleanup

Deletes the Bedrock Flow and its alias.
"""

import boto3
import os
import time
from pathlib import Path
from dotenv import load_dotenv
from botocore.exceptions import ClientError

root_dir = Path(__file__).parent.parent
load_dotenv(root_dir / ".env")

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------
bedrock_agent = boto3.client("bedrock-agent", region_name="us-east-1")
FLOW_ALIAS_ARN = os.getenv("CUSTOMER_SUPPORT_FLOW_ALIAS_ARN")
FLOW_NAME = "customer-support-flow"

if FLOW_ALIAS_ARN:
    FLOW_ID = FLOW_ALIAS_ARN.split("/")[-3]
else:
    try:
        flows = bedrock_agent.list_flows()
        for flow in flows.get("flowSummaries", []):
            if flow["name"] == FLOW_NAME:
                FLOW_ID = flow["id"]
                break
        else:
            FLOW_ID = None
    except ClientError:
        FLOW_ID = None


def cleanup():
    if not FLOW_ID:
        print("No flow found to delete.")
        return

    print(f"Cleaning up flow: {FLOW_ID}")

    # Delete aliases first
    try:
        aliases = bedrock_agent.list_flow_aliases(flowIdentifier=FLOW_ID)
        for alias in aliases.get("flowAliasSummaries", []):
            try:
                bedrock_agent.delete_flow_alias(
                    flowIdentifier=FLOW_ID, aliasIdentifier=alias["id"]
                )
                print(f"  Deleted alias: {alias['name']}")
            except ClientError as e:
                print(f"  Alias deletion note: {e}")
    except ClientError as e:
        print(f"  Alias listing note: {e}")

    # Delete versions
    try:
        versions = bedrock_agent.list_flow_versions(flowIdentifier=FLOW_ID)
        for version in versions.get("flowVersionSummaries", []):
            try:
                bedrock_agent.delete_flow_version(
                    flowIdentifier=FLOW_ID, flowVersionIdentifier=version["version"]
                )
            except ClientError:
                pass
    except ClientError as e:
        print(f"  Version listing note: {e}")

    # Delete the flow
    try:
        bedrock_agent.delete_flow(flowIdentifier=FLOW_ID)
        print(f"  Deleted flow: {FLOW_ID}")
    except ClientError as e:
        print(f"  Flow deletion note: {e}")

    # Remove from .env
    env_path = root_dir / ".env"
    if env_path.exists():
        with open(env_path, "r") as f:
            lines = f.readlines()
        with open(env_path, "w") as f:
            for line in lines:
                if not line.startswith("CUSTOMER_SUPPORT_FLOW_ALIAS_ARN="):
                    f.write(line)
        print("  Removed CUSTOMER_SUPPORT_FLOW_ALIAS_ARN from .env")

    print("\n=== Flow Cleanup Complete ===")


if __name__ == "__main__":
    cleanup()
