import boto3
import json
import os
import sys
import time
from dotenv import load_dotenv

load_dotenv()

def load_config():
    if not os.path.exists("demo_config.json"):
        print("No demo_config.json found. Nothing to clean up.")
        return None
    with open("demo_config.json", "r") as f:
        return json.load(f)

def cleanup(keep_stack=False):
    """Clean up all created resources."""
    config = load_config()
    if config is None:
        return

    region = config["region"]
    bedrock = boto3.client("bedrock-agentcore", region_name=region)

    print("=== Cleaning up resources ===\n")

    # Delete harness
    try:
        bedrock.delete_agent_runtime(agentRuntimeId=config["harness_id"])
        print(f"Deleted harness: {config['harness_id']}")
        print("Waiting for harness memory to delete...")
        time.sleep(10)
    except Exception as e:
        print(f"Harness deletion note: {e}")

    # Delete gateway
    try:
        bedrock.delete_gateway(gatewayId=config["gateway_id"])
        print(f"Deleted gateway: {config['gateway_id']}")
    except Exception as e:
        print(f"Gateway deletion note: {e}")

    # Delete CloudFormation stack (unless keeping it)
    if not keep_stack:
        try:
            cf = boto3.client("cloudformation", region_name=region)
            cf.delete_stack(StackName=config["stack_name"])
            print(f"Deleted CloudFormation stack: {config['stack_name']}")
            print("Waiting for stack deletion to complete...")
            waiter = cf.get_waiter("stack_delete_complete")
            waiter.wait(StackName=config["stack_name"], WaiterConfig={"Delay": 10, "MaxAttempts": 60})
            print("Stack deletion complete")
        except Exception as e:
            print(f"Stack deletion note: {e}")
    else:
        print("Keeping CloudFormation stack (--keep-stack)")

    # Remove config file
    if os.path.exists("demo_config.json"):
        os.remove("demo_config.json")
        print("\nRemoved demo_config.json")

    print("\n=== Cleanup Complete ===")

def main():
    keep_stack = "--keep-stack" in sys.argv
    cleanup(keep_stack)

if __name__ == "__main__":
    main()
