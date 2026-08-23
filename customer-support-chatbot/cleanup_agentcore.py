import boto3
import os
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------
bedrock = boto3.client("bedrock-agentcore-control", region_name="us-east-1")
iam = boto3.client("iam", region_name="us-east-1")

GATEWAY_NAME = "customer-support-gateway"
TARGET_NAME = "bugreports"
HARNESS_NAME = "customer-support-chatbot"


def cleanup():
    print("=== Cleaning up resources ===\n")

    # Delete harness
    try:
        harnesses = bedrock.list_harnesses()
        for h in harnesses.get("items", []):
            if h["name"] == HARNESS_NAME:
                bedrock.delete_harness(harnessId=h["harnessId"])
                print(f"Deleted harness: {h['harnessId']}")
    except Exception as e:
        print(f"Harness cleanup note: {e}")

    # Delete gateway
    try:
        gateways = bedrock.list_gateways()
        for g in gateways.get("items", []):
            if g["name"] == GATEWAY_NAME:
                bedrock.delete_gateway(gatewayId=g["gatewayId"])
                print(f"Deleted gateway: {g['gatewayId']}")
    except Exception as e:
        print(f"Gateway cleanup note: {e}")

    # Remove agentcore_config.json
    if os.path.exists("agentcore_config.json"):
        os.remove("agentcore_config.json")
        print("Removed agentcore_config.json")

    print("\n=== Cleanup Complete ===")
    print("Note: CloudFormation stack and Lambda function were not deleted.")
    print("To delete them: aws cloudformation delete-stack --stack-name bug-report-tool-stack")


if __name__ == "__main__":
    cleanup()
