import boto3
import os
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------
bedrock = boto3.client("bedrock-agentcore", region_name="us-east-1")
iam = boto3.client("iam", region_name="us-east-1")

GATEWAY_NAME = "customer-support-gateway"
TARGET_NAME = "bug_report"
HARNESS_NAME = "customer-support-chatbot"


def cleanup():
    print("=== Cleaning up resources ===\n")

    # Delete harness
    try:
        harnesses = bedrock.list_agent_runtimes()
        for h in harnesses.get("items", []):
            if h["name"] == HARNESS_NAME:
                bedrock.delete_agent_runtime(agentRuntimeId=h["agentRuntimeId"])
                print(f"Deleted harness: {h['agentRuntimeId']}")
    except Exception as e:
        print(f"Harness cleanup note: {e}")

    # Delete gateway
    try:
        gateways = bedrock.list_gateways()
        for g in gateways.get("items", []):
            if g["gatewayName"] == GATEWAY_NAME:
                bedrock.delete_gateway(gatewayId=g["gatewayId"])
                print(f"Deleted gateway: {g['gatewayId']}")
    except Exception as e:
        print(f"Gateway cleanup note: {e}")

    # Remove harness_arn.txt
    if os.path.exists("harness_arn.txt"):
        os.remove("harness_arn.txt")
        print("Removed harness_arn.txt")

    print("\n=== Cleanup Complete ===")
    print("Note: CloudFormation stack and Lambda function were not deleted.")
    print("To delete them: aws cloudformation delete-stack --stack-name customer-support-tools")


if __name__ == "__main__":
    cleanup()
