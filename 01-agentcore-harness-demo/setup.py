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
import os

REGION = "us-east-1"
ACCOUNT_ID = boto3.client("sts").get_caller_identity()["Account"]
ROLE_NAME = "demo3-agentcore-harness-role"
GATEWAY_NAME = "demo3-gateway"
WEATHER_TARGET = "weather"
ATTRACTIONS_TARGET = "attractions"
WEATHER_LAMBDA = "demo3-get-weather"
ATTRACTIONS_LAMBDA = "demo3-get-top-attractions"
HARNESS_NAME = "demo3-harness"
MODEL_ID = "amazon.nova-pro-v1:0"

iam = boto3.client("iam", region_name=REGION)
lambda_client = boto3.client("lambda", region_name=REGION)
bedrock = boto3.client("bedrock-agentcore", region_name=REGION)

def create_iam_role():
    trust_policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Principal": {"Service": "bedrock-agentcore.amazonaws.com"},
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
        gateway = bedrock.create_gateway(
            gatewayName=GATEWAY_NAME,
            roleArn=role_arn,
            description="Demo gateway for weather and attractions tools"
        )
        gateway_id = gateway["gatewayId"]
        print(f"Created Gateway: {gateway_id}")
    except Exception as e:
        if "already exists" in str(e).lower():
            gateways = bedrock.list_gateways()
            gateway_id = next(g["gatewayId"] for g in gateways.get("items", []) if g["gatewayName"] == GATEWAY_NAME)
            print(f"Gateway already exists: {gateway_id}")
        else:
            raise

    try:
        bedrock.create_gateway_target(
            gatewayId=gateway_id,
            targetName=WEATHER_TARGET,
            targetDescription="Weather lookup tool",
            targetUri=weather_arn,
            protocolType="MCP",
            toolSchema=[
                {
                    "name": "get_weather",
                    "description": "Get current weather for a city on a specific date",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "city": {
                                "type": "string",
                                "description": "The city name"
                            },
                            "date": {
                                "type": "string",
                                "description": "The date in YYYY-MM-DD format"
                            }
                        },
                        "required": ["city", "date"]
                    }
                }
            ]
        )
        print(f"Created weather target")
    except Exception as e:
        if "already exists" in str(e).lower():
            print("Weather target already exists")
        else:
            print(f"Weather target note: {e}")

    try:
        bedrock.create_gateway_target(
            gatewayId=gateway_id,
            targetName=ATTRACTIONS_TARGET,
            targetDescription="Top attractions lookup tool",
            targetUri=attractions_arn,
            protocolType="MCP",
            toolSchema=[
                {
                    "name": "get_top_attractions",
                    "description": "Get top attractions for a city",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "city": {
                                "type": "string",
                                "description": "The city name"
                            }
                        },
                        "required": ["city"]
                    }
                }
            ]
        )
        print(f"Created attractions target")
    except Exception as e:
        if "already exists" in str(e).lower():
            print("Attractions target already exists")
        else:
            print(f"Attractions target note: {e}")

    return gateway_id

def create_harness(gateway_id, role_arn):
    import datetime
    today = datetime.date.today().isoformat()
    full_prompt = SYSTEM_PROMPT + f"\nToday's date is {today}."

    tools = [
        {
            "name": "weather___get_weather",
            "description": "Get current weather for a city on a specific date",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "city": {"type": "string", "description": "The city name"},
                    "date": {"type": "string", "description": "The date in YYYY-MM-DD format"}
                },
                "required": ["city", "date"]
            }
        },
        {
            "name": "attractions___get_top_attractions",
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

    try:
        harness = bedrock.create_agent_runtime(
            name=HARNESS_NAME,
            description="Demo travel assistant harness",
            modelId=MODEL_ID,
            instructionPrompt=full_prompt,
            tools=tools,
            roleArn=role_arn
        )
        harness_id = harness["agentRuntimeId"]
        print(f"Created harness: {harness_id}")
    except Exception as e:
        if "already exists" in str(e).lower():
            harnesses = bedrock.list_agent_runtimes()
            harness_id = next(h["agentRuntimeId"] for h in harnesses.get("items", []) if h["name"] == HARNESS_NAME)
            print(f"Harness already exists: {harness_id}")
        else:
            raise

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

    return harness_id

def save_config(config):
    with open("demo_config.json", "w") as f:
        json.dump(config, f, indent=2)
    print("Saved demo_config.json")

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
    harness_id = create_harness(gateway_id, role_arn)
    print()

    config = {
        "harness_id": harness_id,
        "gateway_id": gateway_id,
        "role_arn": role_arn,
        "weather_lambda_arn": weather_arn,
        "attractions_lambda_arn": attractions_arn,
        "region": REGION,
        "model": MODEL_ID
    }
    save_config(config)

    print("\n=== Setup Complete ===")
    print(f"Harness ID: {harness_id}")
    print(f"Run: python chat.py \"I'll be in London this Saturday with my family. What should we do?\"")

if __name__ == "__main__":
    main()
