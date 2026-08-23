import boto3
import json
import time
import os
from dotenv import load_dotenv

load_dotenv()

# ============================================================
# TODO 1: SYSTEM_PROMPT
# Write an instruction prompt that:
# - Describes the agent as a restaurant recommendation assistant for a single city
# - Tells it to always use the tools before making suggestions
# - Tells it to base its recommendation only on tool results
# - Tells it to confirm availability before recommending
# - Tells it to try the next best option if a restaurant is unavailable
# ============================================================

SYSTEM_PROMPT = """You are a helpful restaurant recommendation assistant for a single city — the
one the user is in — so never ask for their location.

Always ground every answer in tool results. When the user asks for a
restaurant recommendation:
1. First call get_cuisines to discover which cuisine types exist.
2. Then call search_restaurants to find matching restaurants.
3. Before recommending a restaurant, call get_availability to confirm it has
   a table tonight. If it is not available, check the next best option from
   the search results.

Never invent, guess, or embellish restaurants, ratings, or availability —
mention only restaurants the tools returned, with the ratings the tools
reported. If no matching restaurant is available, say so honestly instead of
making something up."""

# ============================================================
# TODO 2: TOOL DESCRIPTIONS
# Fill in each tool's description and parameters for the three
# Lambda functions exposed through the Gateway.
# ============================================================

TOOLS = [
    {
        # Tool 1: get_cuisines
        "name": "cuisines___get_cuisines",
        "description": "Returns the list of cuisine types available for restaurant search. Use this first to understand what options exist.",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        # Tool 2: search_restaurants
        "name": "restaurants___search_restaurants",
        "description": "Searches for restaurants by cuisine type. Returns all restaurants if no cuisine is specified. Use this after get_cuisines to find restaurants matching the user's preferred cuisine.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "cuisine": {
                    "type": "string",
                    "description": "The cuisine type to filter by (e.g., Italian, Japanese, Mexican, Indian, American). Optional - omit to get all restaurants."
                }
            },
            "required": []
        }
    },
    {
        # Tool 3: get_availability
        "name": "availability___get_availability",
        "description": "Checks whether a specific restaurant has availability for tonight. Use this after search_restaurants to confirm the restaurant can seat the user tonight.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "restaurant_id": {
                    "type": "string",
                    "description": "The unique ID of the restaurant (e.g., r1, r2, r3). Get this from search_restaurants results."
                }
            },
            "required": ["restaurant_id"]
        }
    }
]

# ============================================================
# CONFIGURATION
# ============================================================

REGION = "us-east-1"
STACK_NAME = "restaurant-agent"
HARNESS_NAME = "restaurant-recommendation-agent"
MODEL_ID = "amazon.nova-pro-v1:0"
GATEWAY_NAME = "restaurant-agent-gateway"

def get_stack_outputs():
    """Get CloudFormation stack outputs for IAM roles."""
    cf = boto3.client("cloudformation", region_name=REGION)
    response = cf.describe_stacks(StackName=STACK_NAME)
    outputs = response["Stacks"][0].get("Outputs", [])
    return {o["OutputKey"]: o["OutputValue"] for o in outputs}

def create_gateway(role_arn):
    """Create AgentCore Gateway with three tool targets."""
    bedrock = boto3.client("bedrock-agentcore", region_name=REGION)

    try:
        gateway = bedrock.create_gateway(
            gatewayName=GATEWAY_NAME,
            roleArn=role_arn,
            description="Gateway for restaurant recommendation agent tools"
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

    # Create targets for each Lambda
    targets = [
        {
            "targetName": "cuisines",
            "description": "Cuisine types lookup",
            "functionName": "restaurant-agent-get-cuisines",
            "toolSchema": TOOLS[0]["inputSchema"]
        },
        {
            "targetName": "restaurants",
            "description": "Restaurant search",
            "functionName": "restaurant-agent-search-restaurants",
            "toolSchema": TOOLS[1]["inputSchema"]
        },
        {
            "targetName": "availability",
            "description": "Availability check",
            "functionName": "restaurant-agent-get-availability",
            "toolSchema": TOOLS[2]["inputSchema"]
        }
    ]

    account_id = boto3.client("sts").get_caller_identity()["Account"]

    for target in targets:
        try:
            bedrock.create_gateway_target(
                gatewayId=gateway_id,
                targetName=target["targetName"],
                targetDescription=target["description"],
                targetUri=f"arn:aws:lambda:{REGION}:{account_id}:function:{target['functionName']}",
                protocolType="MCP",
                toolSchema=[
                    {
                        "name": target["functionName"].replace("restaurant-agent-", ""),
                        "description": target["description"],
                        "inputSchema": target["toolSchema"]
                    }
                ]
            )
            print(f"Created target: {target['targetName']}")
        except Exception as e:
            if "already exists" in str(e).lower():
                print(f"Target already exists: {target['targetName']}")
            else:
                print(f"Target note: {e}")

    return gateway_id

def create_harness(gateway_id, role_arn):
    """Create the AgentCore harness with the model, prompt, and tools."""
    bedrock = boto3.client("bedrock-agentcore", region_name=REGION)

    try:
        harness = bedrock.create_agent_runtime(
            name=HARNESS_NAME,
            description="Restaurant recommendation agent using ReAct pattern",
            modelId=MODEL_ID,
            instructionPrompt=SYSTEM_PROMPT,
            tools=TOOLS,
            roleArn=role_arn,
            inferenceConfig={
                "temperature": 0.0,
                "topK": 1
            }
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
    """Save configuration for other scripts."""
    with open("demo_config.json", "w") as f:
        json.dump(config, f, indent=2)
    print("Saved demo_config.json")

def main():
    print("=== Restaurant Recommendation Agent Setup ===\n")

    print("1. Getting stack outputs...")
    try:
        outputs = get_stack_outputs()
        gateway_role_arn = outputs.get("GatewayRoleArn")
        harness_role_arn = outputs.get("HarnessExecutionRoleArn")
        print(f"   Gateway Role: {gateway_role_arn}")
        print(f"   Harness Role: {harness_role_arn}\n")
    except Exception as e:
        print(f"Error getting stack outputs: {e}")
        print("Make sure you ran: aws cloudformation deploy --template-file template.yaml --stack-name restaurant-agent --capabilities CAPABILITY_NAMED_IAM --region us-east-1")
        return

    print("2. Creating Gateway with targets...")
    gateway_id = create_gateway(gateway_role_arn)
    print()

    print("3. Creating harness...")
    harness_id = create_harness(gateway_id, harness_role_arn)
    print()

    config = {
        "harness_id": harness_id,
        "gateway_id": gateway_id,
        "gateway_role_arn": gateway_role_arn,
        "harness_role_arn": harness_role_arn,
        "region": REGION,
        "model": MODEL_ID,
        "stack_name": STACK_NAME
    }
    save_config(config)

    print("\n=== Setup Complete ===")
    print(f"Harness ID: {harness_id}")
    print(f"Run: python invoke_agent.py \"Find me an Italian restaurant for tonight.\"")

if __name__ == "__main__":
    main()
