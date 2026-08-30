import boto3
import json
import time
from pathlib import Path
from dotenv import load_dotenv

root_dir = Path(__file__).parent.parent
load_dotenv(root_dir / ".env")

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------
bedrock = boto3.client("bedrock-agentcore-control", region_name="us-east-1")
sts = boto3.client("sts", region_name="us-east-1")
cf = boto3.client("cloudformation", region_name="us-east-1")

GATEWAY_NAME = "customer-support-gateway"
TARGET_NAME = "bugreports"
LAMBDA_NAME = "bug-report-tool-stack-create-bug-report"


def get_gateway_role_arn():
    """Get the gateway role ARN from CloudFormation outputs."""
    try:
        response = cf.describe_stacks(StackName="bug-report-tool-stack")
        outputs = response["Stacks"][0].get("Outputs", [])
        for output in outputs:
            if output["OutputKey"] == "GatewayRoleArn":
                return output["OutputValue"]
    except Exception as e:
        print(f"Error getting stack outputs: {e}")
    return None


def get_lambda_arn():
    """Get the Lambda function ARN."""
    lambda_client = boto3.client("lambda", region_name="us-east-1")
    try:
        response = lambda_client.get_function(FunctionName=LAMBDA_NAME)
        return response["Configuration"]["FunctionArn"]
    except Exception as e:
        print(f"Error getting Lambda ARN: {e}")
    return None


def create_gateway(role_arn):
    """Create AgentCore Gateway."""
    try:
        gateway = bedrock.create_gateway(
            name=GATEWAY_NAME,
            roleArn=role_arn,
            protocolType="MCP",
            authorizerType="NONE",
            description="Gateway for customer support tools"
        )
        gateway_id = gateway["gatewayId"]
        print(f"Created Gateway: {gateway_id}")
    except Exception as e:
        if "already exists" in str(e).lower():
            gateways = bedrock.list_gateways()
            gateway_id = next(g["gatewayId"] for g in gateways.get("items", []) if g["name"] == GATEWAY_NAME)
            print(f"Gateway already exists: {gateway_id}")
        else:
            raise

    return gateway_id


def create_target(gateway_id, lambda_arn):
    """Create Gateway target for the Lambda."""
    tool_schema = [
        {
            "name": "create_bug_report",
            "description": "Creates a bug report ticket in the system. Use this when the customer has provided all required bug report details: description, steps to reproduce, and environment.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "description": {
                        "type": "string",
                        "description": "Description of the bug or issue the customer reported"
                    },
                    "stepsToReproduce": {
                        "type": "string",
                        "description": "Steps the customer took to reproduce the issue"
                    },
                    "environment": {
                        "type": "string",
                        "description": "Customer's environment: browser, device, OS, app version"
                    }
                },
                "required": ["description", "stepsToReproduce", "environment"]
            }
        }
    ]

    try:
        bedrock.create_gateway_target(
            gatewayIdentifier=gateway_id,
            name=TARGET_NAME,
            description="Bug report creation tool",
            targetConfiguration={
                "mcp": {
                    "lambda": {
                        "lambdaArn": lambda_arn,
                        "toolSchema": {
                            "inlinePayload": tool_schema
                        }
                    }
                }
            },
            credentialProviderConfigurations=[
                {"credentialProviderType": "GATEWAY_IAM_ROLE"}
            ]
        )
        print(f"Created target: {TARGET_NAME}")
    except Exception as e:
        if "already exists" in str(e).lower():
            print(f"Target already exists: {TARGET_NAME}")
        else:
            print(f"Target note: {e}")


def main():
    print("=== Customer Support Gateway Setup ===\n")

    print("1. Getting gateway role ARN...")
    role_arn = get_gateway_role_arn()
    if not role_arn:
        print("Error: Could not get gateway role ARN. Run cloudformation deploy first.")
        return
    print(f"   Role ARN: {role_arn}\n")

    print("2. Getting Lambda ARN...")
    lambda_arn = get_lambda_arn()
    if not lambda_arn:
        print("Error: Could not get Lambda ARN. Run cloudformation deploy first.")
        return
    print(f"   Lambda ARN: {lambda_arn}\n")

    print("3. Creating Gateway...")
    gateway_id = create_gateway(role_arn)
    print()

    print("4. Creating target...")
    create_target(gateway_id, lambda_arn)
    print()

    print("=== Gateway Setup Complete ===")
    print(f"Gateway ID: {gateway_id}")
    print(f"Target: {TARGET_NAME}")


if __name__ == "__main__":
    main()
