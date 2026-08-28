from dotenv import load_dotenv
import os
from pathlib import Path

# Load from root .env (one level up from this folder)
root_dir = Path(__file__).parent.parent
load_dotenv(root_dir / ".env")

SYSTEM_PROMPT = """You are a Helpful Home AI travel assistant. You help users plan trips and find things to do.

RULES:
- Always use the available tools to get weather and attraction information.
- Never make up information about weather or attractions.
- Prioritize indoor attractions when the weather is poor.
- Tailor suggestions to stated preferences (family-friendly, budget, etc.).
- Include practical details like opening hours, costs, and travel tips.

"""

import boto3
import json
import time

REGION = os.getenv("AWS_REGION", "us-east-1")
MODEL_ID = os.getenv("MODEL_ID", "amazon.nova-lite-v1:0")
ACCOUNT_ID = boto3.client("sts", region_name=REGION).get_caller_identity()["Account"]
ROLE_NAME = "demo3-agentcore-harness-role"
GATEWAY_NAME = "demo3-gateway"
WEATHER_TARGET = "weather"
ATTRACTIONS_TARGET = "attractions"
WEATHER_LAMBDA = "demo3-get-weather"
ATTRACTIONS_LAMBDA = "demo3-get-top-attractions"
HARNESS_NAME = "demo3_harness_v2"

iam = boto3.client("iam", region_name=REGION)
lambda_client = boto3.client("lambda", region_name=REGION)
bedrock_control = boto3.client("bedrock-agentcore-control", region_name=REGION)

def create_iam_role():
    trust_policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Principal": {
                    "Service": ["bedrock-agentcore.amazonaws.com", "lambda.amazonaws.com"]
                },
                "Action": "sts:AssumeRole"
            }
        ]
    }

    try:
        role = iam.create_role(
            RoleName=ROLE_NAME,
            AssumeRolePolicyDocument=json.dumps(trust_policy),
            Description="Role for AgentCore Harness demo"
        )
        role_arn = role["Role"]["Arn"]
    except iam.exceptions.EntityAlreadyExistsException:
        role = iam.get_role(RoleName=ROLE_NAME)
        role_arn = role["Role"]["Arn"]

    policy_document = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Action": "lambda:InvokeFunction",
                "Resource": [
                    f"arn:aws:lambda:{REGION}:{ACCOUNT_ID}:function:{WEATHER_LAMBDA}",
                    f"arn:aws:lambda:{REGION}:{ACCOUNT_ID}:function:{ATTRACTIONS_LAMBDA}"
                ]
            }
        ]
    }

    try:
        iam.put_role_policy(
            RoleName=ROLE_NAME,
            PolicyName="lambda-invoke-policy",
            PolicyDocument=json.dumps(policy_document)
        )
    except Exception as e:
        print(f"Policy update note: {e}")

    return role_arn

def create_lambda(function_name, handler_file):
    zip_path = f"{handler_file}.zip"

    import zipfile
    with zipfile.ZipFile(zip_path, 'w') as zf:
        zf.write(f"lambda/{handler_file}/lambda_function.py", "lambda_function.py")

    with open(zip_path, 'rb') as f:
        zipped_code = f.read()

    try:
        response = lambda_client.create_function(
            FunctionName=function_name,
            Runtime="python3.11",
            Role=f"arn:aws:iam::{ACCOUNT_ID}:role/{ROLE_NAME}",
            Handler="lambda_function.lambda_handler",
            Code={"ZipFile": zipped_code},
            Timeout=30,
            MemorySize=128
        )
        lambda_arn = response["FunctionArn"]
        print(f"Created Lambda: {function_name}")
    except lambda_client.exceptions.ResourceConflictException:
        response = lambda_client.get_function(FunctionName=function_name)
        lambda_arn = response["Configuration"]["FunctionArn"]
        print(f"Lambda already exists: {function_name}")

    os.remove(zip_path)
    return lambda_arn

def create_gateway(role_arn, weather_arn, attractions_arn):
    try:
        gateway = bedrock_control.create_gateway(
            name=GATEWAY_NAME,
            roleArn=role_arn,
            authorizerType="NONE",
            protocolType="MCP",
            description="Demo gateway for weather and attractions tools"
        )
        gateway_id = gateway["gatewayId"]
        print(f"Created Gateway: {gateway_id}")
    except Exception as e:
        if "already exists" in str(e).lower():
            gateways = bedrock_control.list_gateways()
            gateway_id = next(g["gatewayId"] for g in gateways.get("items", []) if g["name"] == GATEWAY_NAME)
            print(f"Gateway already exists: {gateway_id}")
        else:
            raise

    credential_config = [
        {
            "credentialProviderType": "GATEWAY_IAM_ROLE"
        }
    ]

    try:
        bedrock_control.create_gateway_target(
            gatewayIdentifier=gateway_id,
            name=WEATHER_TARGET,
            description="Weather lookup tool",
            credentialProviderConfigurations=credential_config,
            targetConfiguration={
                "mcp": {
                    "lambda": {
                        "lambdaArn": weather_arn,
                        "toolSchema": {
                            "inlinePayload": [
                                {
                                    "name": "get_weather",
                                    "description": "Get current weather for a city on a specific date",
                                    "inputSchema": {
                                        "type": "object",
                                        "properties": {
                                            "city": {"type": "string", "description": "The city name"},
                                            "date": {"type": "string", "description": "The date in YYYY-MM-DD format"}
                                        },
                                        "required": ["city", "date"]
                                    }
                                }
                            ]
                        }
                    }
                }
            }
        )
        print(f"Created weather target")
    except Exception as e:
        if "already exists" in str(e).lower():
            print("Weather target already exists")
        else:
            print(f"Weather target note: {e}")

    try:
        bedrock_control.create_gateway_target(
            gatewayIdentifier=gateway_id,
            name=ATTRACTIONS_TARGET,
            description="Top attractions lookup tool",
            credentialProviderConfigurations=credential_config,
            targetConfiguration={
                "mcp": {
                    "lambda": {
                        "lambdaArn": attractions_arn,
                        "toolSchema": {
                            "inlinePayload": [
                                {
                                    "name": "get_top_attractions",
                                    "description": "Get top attractions for a city",
                                    "inputSchema": {
                                        "type": "object",
                                        "properties": {
                                            "city": {"type": "string", "description": "The city name"}
                                        },
                                        "required": ["city"]
                                    }
                                }
                            ]
                        }
                    }
                }
            }
        )
        print(f"Created attractions target")
    except Exception as e:
        if "already exists" in str(e).lower():
            print("Attractions target already exists")
        else:
            print(f"Attractions target note: {e}")

    return gateway_id

def get_gateway_arn(gateway_id):
    gateway = bedrock_control.get_gateway(gatewayIdentifier=gateway_id)
    return gateway["gatewayArn"]

def create_harness(gateway_id, role_arn):
    gateway_arn = get_gateway_arn(gateway_id)

    tools = [
        {
            "type": "agentcore_gateway",
            "name": "weather___get_weather",
            "config": {
                "agentCoreGateway": {
                    "gatewayArn": gateway_arn,
                    "outboundAuth": {"none": {}}
                }
            }
        },
        {
            "type": "agentcore_gateway",
            "name": "attractions___get_top_attractions",
            "config": {
                "agentCoreGateway": {
                    "gatewayArn": gateway_arn,
                    "outboundAuth": {"none": {}}
                }
            }
        }
    ]

    try:
        harness = bedrock_control.create_harness(
            harnessName=HARNESS_NAME,
            executionRoleArn=role_arn,
            model={"bedrockModelConfig": {"modelId": MODEL_ID}},
            systemPrompt=[{"text": SYSTEM_PROMPT}],
            tools=tools
        )
        harness_id = harness["harness"]["harnessId"]
        harness_arn = harness["harness"]["arn"]
        print(f"Created harness: {harness_arn}")
    except Exception as e:
        if "already exists" in str(e).lower():
            harnesses = bedrock_control.list_harnesses()
            existing = next(h for h in harnesses.get("items", []) if h["harnessName"] == HARNESS_NAME)
            harness_id = existing["harnessId"]
            harness_arn = existing["arn"]
            print(f"Harness already exists: {harness_arn}")
        else:
            raise

    print("Waiting for harness to reach READY status...")
    for i in range(30):
        status = bedrock_control.get_harness(harnessId=harness_id)
        if status.get("harness", {}).get("status") == "READY":
            print("Harness is READY")
            break
        print(f"  Status: {status.get('harness', {}).get('status')}... waiting")
        time.sleep(10)
    else:
        print("Harness did not reach READY in time")

    return harness_arn

def main():
    print("=== AgentCore Harness Demo Setup ===\n")

    print("1. Creating IAM role...")
    role_arn = create_iam_role()
    print(f"   Role ARN: {role_arn}\n")

    print("2. Creating Lambda functions...")
    weather_arn = create_lambda(WEATHER_LAMBDA, "get_weather")
    attractions_arn = create_lambda(ATTRACTIONS_LAMBDA, "get_top_attractions")
    print()

    print("3. Creating Gateway with targets...")
    gateway_id = create_gateway(role_arn, weather_arn, attractions_arn)
    print()

    print("4. Creating harness...")
    harness_arn = create_harness(gateway_id, role_arn)
    print()

    config = {
        "harness_arn": harness_arn,
        "gateway_id": gateway_id,
        "role_arn": role_arn,
        "weather_lambda_arn": weather_arn,
        "attractions_lambda_arn": attractions_arn,
        "region": REGION,
        "model": MODEL_ID
    }

    with open("demo_config.json", "w") as f:
        json.dump(config, f, indent=2)
    print("Saved demo_config.json")

    print("\n" + "="*60)
    print("SETUP COMPLETE")
    print("="*60)
    print(f"\nHarness ARN: {harness_arn}")
    print(f"Run: python chat.py \"I'll be in London this Saturday with my family. What should we do?\"")

if __name__ == "__main__":
    main()
