import boto3
import json
import time
import os
from pathlib import Path
from dotenv import load_dotenv

root_dir = Path(__file__).parent.parent
load_dotenv(root_dir / ".env")

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------
bedrock = boto3.client("bedrock-agentcore-control", region_name="us-east-1")
iam = boto3.client("iam", region_name="us-east-1")
sts = boto3.client("sts", region_name="us-east-1")

MODEL_ID = "us.amazon.nova-pro-v1:0"
HARNESS_NAME = "customer_support_chatbot"
TOOL_NAME = "create_bug_report"


def load_system_prompt():
    with open(root_dir / "system_prompt.txt", "r") as f:
        prompt = f.read()
    with open(root_dir / "online_shop_faq.md", "r") as f:
        faq = f.read()
    prompt = prompt.replace("{{FAQ}}", faq)
    return prompt


def get_harness_role_arn():
    """Get the harness execution role ARN from CloudFormation outputs."""
    cf = boto3.client("cloudformation", region_name="us-east-1")
    try:
        response = cf.describe_stacks(StackName="bug-report-tool-stack")
        outputs = response["Stacks"][0].get("Outputs", [])
        for output in outputs:
            if output["OutputKey"] == "HarnessExecutionRoleArn":
                return output["OutputValue"]
    except Exception as e:
        print(f"Error getting stack outputs: {e}")
    return None


def get_gateway_arn():
    """Get the gateway ARN."""
    try:
        gateways = bedrock.list_gateways()
        for g in gateways.get("items", []):
            if g["name"] == "customer-support-gateway":
                return f"arn:aws:bedrock-agentcore:us-east-1:{sts.get_caller_identity()['Account']}:gateway/{g['gatewayId']}"
    except Exception as e:
        print(f"Error getting gateway ARN: {e}")
    return None


def create_harness(role_arn, system_prompt):
    """Create or update the AgentCore harness."""
    gateway_arn = get_gateway_arn()
    if not gateway_arn:
        print("Error: Could not find gateway. Run setup_gateway.py first.")
        return None, None

    tool_schema = [
        {
            "type": "agentcore_gateway",
            "name": "bugreports",
            "config": {
                "agentCoreGateway": {
                    "gatewayArn": gateway_arn,
                    "outboundAuth": {
                        "awsIam": {}
                    }
                }
            }
        }
    ]

    try:
        # Try to delete existing harness first
        harnesses = bedrock.list_harnesses()
        for h in harnesses.get("harnesses", []):
            if h["harnessName"] == HARNESS_NAME:
                try:
                    bedrock.delete_harness(harnessId=h["harnessId"])
                    print(f"Deleted existing harness: {h['harnessId']}")
                    time.sleep(5)
                except:
                    pass

        # Create new harness
        harness = bedrock.create_harness(
            harnessName=HARNESS_NAME,
            executionRoleArn=role_arn,
            model={
                "bedrockModelConfig": {
                    "modelId": MODEL_ID,
                    "temperature": 0.1,
                    "topP": 0.9
                }
            },
            systemPrompt=[{"text": system_prompt}],
            tools=tool_schema,
            memory={"disabled": {}}
        )
        harness_id = harness["harness"]["harnessId"]
        harness_arn = harness["harness"]["arn"]
        print(f"Created harness: {harness_id}")
    except Exception as e:
        print(f"Error creating harness: {e}")
        return None, None

    print("Waiting for harness to reach READY status...")
    for i in range(30):
        status = bedrock.get_harness(harnessId=harness_id)["harness"]
        if status.get("status") == "READY":
            print(f"Harness is READY")
            break
        print(f"  Status: {status.get('status')}... waiting")
        time.sleep(10)
    else:
        print("Harness did not reach READY in time")

    # Save harness ARN
    with open(root_dir / "agentcore_config.json", "w") as f:
        json.dump({"harness_arn": harness_arn, "harness_id": harness_id}, f, indent=2)
    print(f"Saved harness config to agentcore_config.json")

    return harness_id, harness_arn


def main():
    print("=== Customer Support Chatbot Harness Setup ===\n")

    print("1. Loading system prompt...")
    system_prompt = load_system_prompt()
    print(f"   Loaded {len(system_prompt)} characters\n")

    print("2. Getting harness role ARN...")
    role_arn = get_harness_role_arn()
    if not role_arn:
        print("Error: Could not get harness execution role ARN. Run cloudformation deploy first.")
        return
    print(f"   Role ARN: {role_arn}\n")

    print("3. Creating harness...")
    harness_id, harness_arn = create_harness(role_arn, system_prompt)
    print()

    if harness_id:
        print("=== Setup Complete ===")
        print(f"Harness ID: {harness_id}")
        print(f"Harness ARN: {harness_arn}")
        print(f"\nRun: python chat.py")
    else:
        print("Setup failed. Check the error above.")


if __name__ == "__main__":
    main()
