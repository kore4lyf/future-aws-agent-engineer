from dotenv import load_dotenv
import os
from pathlib import Path

# Load from root .env (one level up from this folder)
root_dir = Path(__file__).parent.parent
load_dotenv(root_dir / ".env")

import boto3
import json

def load_config():
    if not os.path.exists("demo_config.json"):
        print("No demo_config.json found. Nothing to clean up.")
        return None
    with open("demo_config.json", "r") as f:
        return json.load(f)

def cleanup():
    config = load_config()
    if config is None:
        return

    region = config["region"]
    bedrock = boto3.client("bedrock-agentcore", region_name=region)
    bedrock_control = boto3.client("bedrock-agentcore-control", region_name=region)
    lambda_client = boto3.client("lambda", region_name=region)
    iam = boto3.client("iam", region_name=region)

    print("=== Cleaning up resources ===\n")

    # Delete harness
    try:
        bedrock.delete_agent_runtime(agentRuntimeId=config["harness_id"])
        print(f"Deleted harness: {config['harness_id']}")
    except Exception as e:
        print(f"Harness deletion note: {e}")

    # Delete gateway
    try:
        bedrock_control.delete_gateway(gatewayId=config["gateway_id"])
        print(f"Deleted gateway: {config['gateway_id']}")
    except Exception as e:
        print(f"Gateway deletion note: {e}")

    # Delete Lambda functions
    for lambda_name in ["demo3-get-weather", "demo3-get-top-attractions"]:
        try:
            lambda_client.delete_function(FunctionName=lambda_name)
            print(f"Deleted Lambda: {lambda_name}")
        except Exception as e:
            print(f"Lambda deletion note: {e}")

    # Delete IAM role
    try:
        iam.delete_role_policy(RoleName="demo3-agentcore-harness-role", PolicyName="lambda-invoke-policy")
        iam.delete_role(RoleName="demo3-agentcore-harness-role")
        print(f"Deleted IAM role: demo3-agentcore-harness-role")
    except Exception as e:
        print(f"IAM deletion note: {e}")

    # Remove config file
    os.remove("demo_config.json")
    print("\nRemoved demo_config.json")
    print("\n=== Cleanup Complete ===")

if __name__ == "__main__":
    cleanup()
