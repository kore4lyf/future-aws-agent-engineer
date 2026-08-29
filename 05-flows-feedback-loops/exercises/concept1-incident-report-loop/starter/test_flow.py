"""
Incident Report Flow – Test

Invokes the Bedrock Flow with test cases and prints the response.
"""

import boto3
import json
import os
import sys
import time
from pathlib import Path
from dotenv import load_dotenv

root_dir = Path(__file__).parent.parent.parent.parent.parent
load_dotenv(root_dir / ".env")

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------
bedrock_runtime = boto3.client("bedrock-agent-runtime", region_name="us-east-1")
FLOW_ALIAS_ARN = os.getenv("INCIDENT_FLOW_ALIAS_ARN")

if not FLOW_ALIAS_ARN:
    print("Error: INCIDENT_FLOW_ALIAS_ARN not found in .env. Run create_flow.py first.")
    sys.exit(1)

# Extract flow ID from alias ARN: arn:aws:bedrock:...:flow/{flow_id}/alias/...
FLOW_ID = FLOW_ALIAS_ARN.split("/")[-3]

TEST_CASES = [
    ("Minimal report", "Database went down around 3pm. Fixed it."),
    (
        "Partial report",
        "Incident: API gateway returning 503 errors\n"
        "Started at 14:32 UTC, resolved 15:18 UTC\n"
        "Affected: checkout service in us-east-1\n"
        "Root cause: misconfigured load balancer after deploy at 14:28 UTC\n"
        "Action taken: rolled back the deployment",
    ),
    (
        "Complete report",
        "Severity: P1\n"
        "Affected systems: checkout-api (us-east-1), payment-processor integration\n"
        "Timeline: Started 14:32 UTC, detected 14:35 UTC, resolved 15:18 UTC\n"
        "Root cause: Load balancer misconfiguration introduced in deploy v2.4.1 at 14:28 UTC\n"
        "Impact: ~1,200 failed checkout attempts, estimated $34k in lost transactions\n"
        "Remediation: Rolled back to v2.4.0, confirmed 503 rate dropped to zero at 15:18 UTC",
    ),
]


def invoke_flow(flow_id, alias_arn, user_message):
    """Invoke the flow with a user message and return the response."""
    try:
        response = bedrock_runtime.invoke_flow(
            flowIdentifier=flow_id,
            flowAliasIdentifier=alias_arn,
            inputs=[
                {
                    "nodeName": "FlowInput",
                    "nodeOutputName": "document",
                    "content": {"document": user_message},
                }
            ],
        )

        full_response = ""
        for event in response.get("responseStream", []):
            if "flowOutputEvent" in event:
                output = event["flowOutputEvent"]
                content = output.get("content", {})
                if isinstance(content, dict) and "document" in content:
                    full_response = content["document"]
            elif "flowErrorEvent" in event:
                return f"[error: {event['flowErrorEvent']['message']}]"

        return full_response or "[no output]"

    except Exception as e:
        return f"[error: {e}]"


def main():
    print("=== Incident Report Flow – Test ===\n")

    for label, message in TEST_CASES:
        print(f"{'-' * 60}")
        print(f"Test: {label}")
        print(f"Input: {message[:80]}...")
        print(f"{'-' * 60}")

        response = invoke_flow(FLOW_ID, FLOW_ALIAS_ARN, message)
        print(f"Response:\n{response}\n")


if __name__ == "__main__":
    main()
