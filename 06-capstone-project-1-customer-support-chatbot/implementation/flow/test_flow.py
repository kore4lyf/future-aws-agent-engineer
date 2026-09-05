"""
Customer Support Flow – Test

Invokes the Bedrock Flow with test cases and prints the response.
"""

import boto3
import json
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

root_dir = Path(__file__).parent.parent.parent
load_dotenv(root_dir / ".env")

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------
bedrock_runtime = boto3.client("bedrock-agent-runtime", region_name="us-east-1")
FLOW_ALIAS_ARN = os.getenv("CUSTOMER_SUPPORT_FLOW_ALIAS_ARN")

if not FLOW_ALIAS_ARN:
    print("Error: CUSTOMER_SUPPORT_FLOW_ALIAS_ARN not found in .env. Run create_flow.py first.")
    sys.exit(1)

FLOW_ID = FLOW_ALIAS_ARN.split("/")[-3]

TEST_CASES = [
    ("Bug report", "The checkout page crashes every time I click Pay."),
    ("FAQ shipping", "How long does shipping take?"),
    ("Other request", "Can you help me write an essay?"),
]


def invoke_flow(flow_id, alias_arn, user_message):
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
                content = event["flowOutputEvent"].get("content", {})
                if isinstance(content, dict) and "document" in content:
                    full_response = content["document"]
            elif "flowErrorEvent" in event:
                return f"[error: {event['flowErrorEvent']['message']}]"

        return full_response or "[no output]"

    except Exception as e:
        return f"[error: {e}]"


def main():
    print("=== Customer Support Flow – Test ===\n")

    for label, message in TEST_CASES:
        print(f"{'-' * 60}")
        print(f"Test: {label}")
        print(f"Input: {message}")
        print(f"{'-' * 60}")

        response = invoke_flow(FLOW_ID, FLOW_ALIAS_ARN, message)
        print(f"Response:\n{response}\n")


if __name__ == "__main__":
    main()
