"""
Customer Support Flow – Create and Deploy

Creates a Bedrock Flow:
  FlowInput (user_message)
      │
      ▼
  [Classifier Prompt]
      │
      ▼
  [Condition: route by category]
      │
      ├── bug_report ──► [Bug Report Prompt] ──► FlowOutput
      │
      ├── platform_question ──► [FAQ Prompt] ──► FlowOutput
      │
      └── other ──► [Other Request Prompt] ──► FlowOutput
"""

import boto3
import json
import os
import time
from pathlib import Path
from dotenv import load_dotenv
from botocore.exceptions import ClientError

root_dir = Path(__file__).parent.parent.parent
load_dotenv(root_dir / ".env")

# ---------------------------------------------------------------------------
# Clients
# ---------------------------------------------------------------------------
bedrock_agent = boto3.client("bedrock-agent", region_name="us-east-1")

# ---------------------------------------------------------------------------
# Flow metadata
# ---------------------------------------------------------------------------
FLOW_NAME = "customer-support-flow"
FLOW_DESCRIPTION = "Customer support chatbot flow: classifies messages and routes to bug report, FAQ, or redirect"
EXECUTION_ROLE_ARN = os.getenv("EXECUTION_ROLE_ARN")
MODEL_ID = os.getenv("MODEL_ID", "amazon.nova-pro-v1:0")

if not EXECUTION_ROLE_ARN:
    raise ValueError("EXECUTION_ROLE_ARN not found in .env")

# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------
CLASSIFIER_PROMPT = """You are a message classifier for a customer support chatbot.

Classify the customer's message into exactly ONE of these categories:
- bug_report: The customer is reporting a problem, error, or issue with the platform.
- platform_question: The customer is asking about orders, shipping, returns, or payments.
- other: The request does not fit either category above.

Respond with ONLY one of these words:
bug_report
platform_question
other

Do not include any other text, explanations, or formatting. Just the word.

Customer message:
{{input}}"""

BUG_REPORT_PROMPT = """You are a customer support chatbot for an online shop.

The customer has reported a bug. Your job is to collect all required details before filing a ticket.

Required fields:
- description: What is the problem?
- stepsToReproduce: How can we reproduce this issue?
- environment: Browser, device, operating system, app version

CRITICAL RULES:
1. A single sentence like "The checkout page crashes" is ONLY a description. It is NOT steps or environment.
2. You must have explicit answers for ALL THREE fields before calling the tool.
3. If any field is missing, ask for exactly ONE missing field per turn.
4. NEVER call the tool with missing fields. NEVER make up or infer missing fields.
5. After collecting all three, call the tool, then respond: "Ticket filed: <ticket_id>"

Customer message:
{{input}}"""

FAQ_PROMPT = """You are a customer support chatbot for an online shop.

The customer is asking about orders, shipping, returns, or payments.

Answer using ONLY the FAQ document below. Do not make up answers or add information not in the FAQ.

FAQ Document:
{{FAQ}}

If the FAQ does not cover the customer's question, politely tell them you don't have that information and offer to connect them with human support.

Customer message:
{{input}}"""

OTHER_PROMPT = """You are a customer support chatbot for an online shop.

The customer's request does not fit bug reports or platform questions.

1. Politely acknowledge the message.
2. Explain that you can help with bug reports or platform questions (orders, shipping, returns, payments).
3. Offer to connect them with human support for other inquiries.
4. Keep the response under 50 words.

Customer message:
{{input}}"""

# Load FAQ
with open(root_dir / "online_shop_faq.md", "r") as f:
    FAQ_CONTENT = f.read()

# ---------------------------------------------------------------------------
# Flow definition
# ---------------------------------------------------------------------------
flow_definition = {
    "nodes": [
        # 1. FlowInput
        {
            "name": "FlowInput",
            "type": "Input",
            "configuration": {"input": {}},
            "inputs": [],
            "outputs": [{"name": "document", "type": "String"}],
        },
        # 2. Classifier Prompt
        {
            "name": "Classifier",
            "type": "Prompt",
            "configuration": {
                "prompt": {
                    "sourceConfiguration": {
                        "inline": {
                            "templateType": "TEXT",
                            "templateConfiguration": {
                                "text": {
                                    "text": CLASSIFIER_PROMPT,
                                    "inputVariables": [{"name": "input"}],
                                }
                            },
                            "modelId": MODEL_ID,
                        }
                    }
                }
            },
            "inputs": [
                {"name": "input", "type": "String", "expression": "$.data"}
            ],
            "outputs": [{"name": "modelCompletion", "type": "String"}],
        },
        # 3. Condition Node
        {
            "name": "RouteByCategory",
            "type": "Condition",
            "configuration": {
                "condition": {
                    "conditions": [
                        {"name": "bug_report", "expression": "conditionInput == \"bug_report\""},
                        {"name": "platform_question", "expression": "conditionInput == \"platform_question\""},
                        {"name": "default"},
                    ]
                }
            },
            "inputs": [
                {"name": "conditionInput", "type": "String", "expression": "$.data"}
            ],
            "outputs": [],
        },
        # 4. Bug Report Prompt
        {
            "name": "BugReportHandler",
            "type": "Prompt",
            "configuration": {
                "prompt": {
                    "sourceConfiguration": {
                        "inline": {
                            "templateType": "TEXT",
                            "templateConfiguration": {
                                "text": {
                                    "text": BUG_REPORT_PROMPT,
                                    "inputVariables": [{"name": "input"}],
                                }
                            },
                            "modelId": MODEL_ID,
                        }
                    }
                }
            },
            "inputs": [
                {"name": "input", "type": "String", "expression": "$.data"}
            ],
            "outputs": [{"name": "modelCompletion", "type": "String"}],
        },
        # 5. FAQ Prompt
        {
            "name": "FAQHandler",
            "type": "Prompt",
            "configuration": {
                "prompt": {
                    "sourceConfiguration": {
                        "inline": {
                            "templateType": "TEXT",
                            "templateConfiguration": {
                                "text": {
                                    "text": FAQ_PROMPT.replace("{{FAQ}}", FAQ_CONTENT),
                                    "inputVariables": [{"name": "input"}],
                                }
                            },
                            "modelId": MODEL_ID,
                        }
                    }
                }
            },
            "inputs": [
                {"name": "input", "type": "String", "expression": "$.data"}
            ],
            "outputs": [{"name": "modelCompletion", "type": "String"}],
        },
        # 6. Other Request Prompt
        {
            "name": "OtherHandler",
            "type": "Prompt",
            "configuration": {
                "prompt": {
                    "sourceConfiguration": {
                        "inline": {
                            "templateType": "TEXT",
                            "templateConfiguration": {
                                "text": {
                                    "text": OTHER_PROMPT,
                                    "inputVariables": [{"name": "input"}],
                                }
                            },
                            "modelId": MODEL_ID,
                        }
                    }
                }
            },
            "inputs": [
                {"name": "input", "type": "String", "expression": "$.data"}
            ],
            "outputs": [{"name": "modelCompletion", "type": "String"}],
        },
        # 7. Output nodes (one per branch)
        {
            "name": "BugReportOutput",
            "type": "Output",
            "configuration": {"output": {}},
            "inputs": [
                {"name": "document", "type": "String", "expression": "$.data"}
            ],
            "outputs": [],
        },
        {
            "name": "FAQOutput",
            "type": "Output",
            "configuration": {"output": {}},
            "inputs": [
                {"name": "document", "type": "String", "expression": "$.data"}
            ],
            "outputs": [],
        },
        {
            "name": "OtherOutput",
            "type": "Output",
            "configuration": {"output": {}},
            "inputs": [
                {"name": "document", "type": "String", "expression": "$.data"}
            ],
            "outputs": [],
        },
    ],
    "connections": [
        # FlowInput -> Classifier
        {
            "type": "Data",
            "name": "input_to_classifier",
            "source": "FlowInput",
            "target": "Classifier",
            "configuration": {
                "data": {"sourceOutput": "document", "targetInput": "input"}
            },
        },
        # Classifier -> Condition
        {
            "type": "Data",
            "name": "classifier_to_condition",
            "source": "Classifier",
            "target": "RouteByCategory",
            "configuration": {
                "data": {"sourceOutput": "modelCompletion", "targetInput": "conditionInput"}
            },
        },
        # Condition -> BugReportHandler (conditional)
        {
            "type": "Conditional",
            "name": "route_to_bug_report",
            "source": "RouteByCategory",
            "target": "BugReportHandler",
            "configuration": {"conditional": {"condition": "bug_report"}},
        },
        # Condition -> FAQHandler (conditional)
        {
            "type": "Conditional",
            "name": "route_to_faq",
            "source": "RouteByCategory",
            "target": "FAQHandler",
            "configuration": {"conditional": {"condition": "platform_question"}},
        },
        # Condition -> OtherHandler (conditional, default)
        {
            "type": "Conditional",
            "name": "route_to_other",
            "source": "RouteByCategory",
            "target": "OtherHandler",
            "configuration": {"conditional": {"condition": "default"}},
        },
        # FlowInput -> BugReportHandler (data)
        {
            "type": "Data",
            "name": "input_to_bug_report",
            "source": "FlowInput",
            "target": "BugReportHandler",
            "configuration": {
                "data": {"sourceOutput": "document", "targetInput": "input"}
            },
        },
        # FlowInput -> FAQHandler (data)
        {
            "type": "Data",
            "name": "input_to_faq",
            "source": "FlowInput",
            "target": "FAQHandler",
            "configuration": {
                "data": {"sourceOutput": "document", "targetInput": "input"}
            },
        },
        # FlowInput -> OtherHandler (data)
        {
            "type": "Data",
            "name": "input_to_other",
            "source": "FlowInput",
            "target": "OtherHandler",
            "configuration": {
                "data": {"sourceOutput": "document", "targetInput": "input"}
            },
        },
        # BugReportHandler -> BugReportOutput
        {
            "type": "Data",
            "name": "bug_report_to_output",
            "source": "BugReportHandler",
            "target": "BugReportOutput",
            "configuration": {
                "data": {"sourceOutput": "modelCompletion", "targetInput": "document"}
            },
        },
        # FAQHandler -> FAQOutput
        {
            "type": "Data",
            "name": "faq_to_output",
            "source": "FAQHandler",
            "target": "FAQOutput",
            "configuration": {
                "data": {"sourceOutput": "modelCompletion", "targetInput": "document"}
            },
        },
        # OtherHandler -> OtherOutput
        {
            "type": "Data",
            "name": "other_to_output",
            "source": "OtherHandler",
            "target": "OtherOutput",
            "configuration": {
                "data": {"sourceOutput": "modelCompletion", "targetInput": "document"}
            },
        },
    ],
}


# ---------------------------------------------------------------------------
# Create flow
# ---------------------------------------------------------------------------
def create_flow():
    print(f"\n{'=' * 60}")
    print(f"Creating Bedrock Flow: {FLOW_NAME}")
    print(f"{'=' * 60}")

    # Delete existing flow with the same name
    try:
        existing = bedrock_agent.list_flows()
        for flow in existing.get("flowSummaries", []):
            if flow["name"] == FLOW_NAME:
                print(f"Deleting existing flow: {flow['id']}")
                bedrock_agent.delete_flow(flowIdentifier=flow["id"])
                time.sleep(5)
                break
    except ClientError as e:
        print(f"Error listing flows: {e.response['Error']['Message']}")

    try:
        response = bedrock_agent.create_flow(
            name=FLOW_NAME,
            description=FLOW_DESCRIPTION,
            executionRoleArn=EXECUTION_ROLE_ARN,
            definition=flow_definition,
        )
        flow_id = response["id"]
        flow_arn = response["arn"]
        print(f"Flow created: {flow_id}")
        return flow_id, flow_arn
    except ClientError as e:
        print(f"Error creating flow: {e.response['Error']['Message']}")
        raise


# ---------------------------------------------------------------------------
# Prepare flow
# ---------------------------------------------------------------------------
def prepare_flow(flow_id):
    print(f"\nPreparing flow {flow_id}...")
    for attempt in range(12):
        try:
            resp = bedrock_agent.prepare_flow(flowIdentifier=flow_id)
            status = resp.get("status", "UNKNOWN")
            print(f"  Prepare status: {status}")
            if status == "PREPARED":
                return
        except ClientError as e:
            print(f"  Prepare note: {e.response['Error']['Message']}")
        time.sleep(15)
    print("  Flow preparation still in progress — check the console.")


# ---------------------------------------------------------------------------
# Create alias
# ---------------------------------------------------------------------------
def create_alias(flow_id):
    print(f"\nCreating alias 'latest' for flow {flow_id}...")
    try:
        version_resp = bedrock_agent.create_flow_version(
            flowIdentifier=flow_id, description="Initial version"
        )
        version = version_resp["version"]
        print(f"  Version: {version}")

        alias_resp = bedrock_agent.create_flow_alias(
            flowIdentifier=flow_id,
            name="latest",
            routingConfiguration=[{"flowVersion": version}],
        )
        alias_arn = alias_resp["arn"]
        print(f"  Alias ARN: {alias_arn}")

        # Persist alias ARN
        env_path = root_dir / ".env"
        with open(env_path, "a") as f:
            f.write(f"\nCUSTOMER_SUPPORT_FLOW_ALIAS_ARN={alias_arn}\n")
        print(f"  Saved CUSTOMER_SUPPORT_FLOW_ALIAS_ARN to .env")

        return alias_arn
    except ClientError as e:
        print(f"Error creating alias: {e.response['Error']['Message']}")
        raise


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print("=== Customer Support Flow Setup ===\n")

    flow_id, flow_arn = create_flow()
    prepare_flow(flow_id)
    alias_arn = create_alias(flow_id)

    print(f"\n=== Setup Complete ===")
    print(f"Flow ID:       {flow_id}")
    print(f"Flow ARN:      {flow_arn}")
    print(f"Alias ARN:     {alias_arn}")
    print(f"\nTest the flow in the AWS Bedrock console.")
