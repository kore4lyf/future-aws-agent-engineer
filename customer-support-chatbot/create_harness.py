import boto3
import json
import time
import os
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------
bedrock = boto3.client("bedrock-agentcore", region_name="us-east-1")
iam = boto3.client("iam", region_name="us-east-1")
sts = boto3.client("sts", region_name="us-east-1")

MODEL_ID = "us.amazon.nova-pro-v1:0"
HARNESS_NAME = "customer-support-chatbot"
TOOL_NAME = "create_bug_report"


def load_system_prompt():
    with open("system_prompt.txt", "r") as f:
        return f.read()


def get_gateway_role_arn():
    """Get the gateway role ARN from CloudFormation outputs."""
    cf = boto3.client("cloudformation", region_name="us-east-1")
    try:
        response = cf.describe_stacks(StackName="bug-report-tool-stack")
        outputs = response["Stacks"][0].get("Outputs", [])
        for output in outputs:
            if output["OutputKey"] == "GatewayRoleArn":
                return output["OutputValue"]
    except Exception as e:
        print(f"Error getting stack outputs: {e}")
    return None


def create_harness(role_arn, system_prompt):
    """Create or update the AgentCore harness."""
    tool_schema = [
        {
            "toolSpec": {
                "name": TOOL_NAME,
                "description": "Creates a bug report ticket in the system. Use this when the customer has provided all required bug report details: description, steps to reproduce, and environment.",
                "inputSchema": {
                    "json": {
                        "type": "object",
                        "properties": {
                            "bug_description": {
                                "type": "string",
                                "description": "Description of the bug or issue the customer reported"
                            },
                            "steps_to_reproduce": {
                                "type": "string",
                                "description": "Steps the customer took to reproduce the issue"
                            },
                            "environment": {
                                "type": "string",
                                "description": "Customer's environment: browser, device, OS, app version"
                            },
                            "customer_id": {
                                "type": "string",
                                "description": "Customer identifier if available"
                            }
                        },
                        "required": ["bug_description", "steps_to_reproduce", "environment"]
                    }
                }
            }
        }
    ]

    try:
        # Try to delete existing harness first
        harnesses = bedrock.list_agent_runtimes()
        for h in harnesses.get("items", []):
            if h["name"] == HARNESS_NAME:
                try:
                    bedrock.delete_agent_runtime(agentRuntimeId=h["agentRuntimeId"])
                    print(f"Deleted existing harness: {h['agentRuntimeId']}")
                    time.sleep(5)
                except:
                    pass

        # Create new harness
        harness = bedrock.create_agent_runtime(
            name=HARNESS_NAME,
            description="Customer support chatbot with bug reporting and FAQ",
            modelId=MODEL_ID,
            instructionPrompt=system_prompt,
            tools=tool_schema,
            roleArn=role_arn,
            inferenceConfig={
                "temperature": 0.3,
                "topK": 1
            },
            memory={"disabled": {}}
        )
        harness_id = harness["agentRuntimeId"]
        harness_arn = harness.get("agentRuntimeArn", f"arn:aws:bedrock-agentcore:us-east-1:{sts.get_caller_identity()['Account']}:agent-runtime/{harness_id}")
        print(f"Created harness: {harness_id}")
    except Exception as e:
        print(f"Error creating harness: {e}")
        return None, None

    print("Waiting for harness to reach READY status...")
    for i in range(30):
        status = bedrock.get_agent_runtime(agentRuntimeId=harness_id)
        if status.get("status") == "READY":
            print(f"Harness is READY")
            break
        print(f"  Status: {status.get('status')}... waiting")
        time.sleep(10)
    else:
        print("Harness did not reach READY in time")

    # Save harness ARN
    with open("agentcore_config.json", "w") as f:
        json.dump({"harness_arn": harness_arn, "harness_id": harness_id}, f, indent=2)
    print(f"Saved harness config to agentcore_config.json")

    return harness_id, harness_arn


def main():
    print("=== Customer Support Chatbot Harness Setup ===\n")

    print("1. Loading system prompt...")
    system_prompt = load_system_prompt()
    print(f"   Loaded {len(system_prompt)} characters\n")

    print("2. Getting gateway role ARN...")
    role_arn = get_gateway_role_arn()
    if not role_arn:
        print("Error: Could not get gateway role ARN. Run setup_gateway.py first.")
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
