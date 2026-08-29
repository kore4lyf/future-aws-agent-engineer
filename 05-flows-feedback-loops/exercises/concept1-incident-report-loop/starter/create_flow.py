"""
Incident Report Flow – Create and Deploy

Creates a Bedrock Flow:
  FlowInput (incident_report)
      │
      ▼
  [Prompt node: IncidentCoordinator]
      │
      ▼
  FlowOutput

The Prompt node carries the same system prompt as the harness, giving a
single-shot view of the agent that can be tested from the Bedrock Flow
console.  For the multi-turn feedback loop, use the harness in chat.py.
"""

import boto3
import json
import os
import time
from pathlib import Path
from dotenv import load_dotenv
from botocore.exceptions import ClientError

root_dir = Path(__file__).parent.parent.parent.parent.parent
load_dotenv(root_dir / ".env")

# ---------------------------------------------------------------------------
# Clients
# ---------------------------------------------------------------------------
bedrock_agent = boto3.client("bedrock-agent", region_name="us-east-1")

# ---------------------------------------------------------------------------
# Flow metadata
# ---------------------------------------------------------------------------
FLOW_NAME = "incident-report-flow"
FLOW_DESCRIPTION = "Single-turn incident report coordinator using a prompt node"
EXECUTION_ROLE_ARN = os.getenv("EXECUTION_ROLE_ARN")
MODEL_ID = os.getenv("MODEL_ID", "amazon.nova-pro-v1:0")

if not EXECUTION_ROLE_ARN:
    raise ValueError("EXECUTION_ROLE_ARN not found in .env")

# ---------------------------------------------------------------------------
# System prompt (same as harness)
# ---------------------------------------------------------------------------
COORDINATOR_PROMPT = """\
You are an incident report coordinator for an SRE team. An engineer will
submit an incident report that may be incomplete. Your job is to collect
every required detail before the report can be filed.

A report can only be filed when you have specific answers for all five of
these required fields:
- Severity: P1 / P2 / P3 / P4
- Affected service: which service, component, or region was impacted
- Impact: who or what was affected, and to what extent
- Root cause: what caused the incident (a hypothesis is acceptable if
  labeled as such)
- Timeline: when the incident started, when it was detected, and when it
  was resolved

On every turn:
1. Compare everything the engineer has told you so far against the five
   required fields. Any concrete answer the engineer has given counts as
   covered — including a labeled hypothesis for the root cause. Never ask
   the engineer to confirm, refine, or quantify something they have
   already told you.
2. If a field has not been addressed at all, or is too vague to write a
   sentence about, ask about the single most important missing field —
   phrased as ONE single, short question. Never ask two questions in a
   turn, not even two phrasings of the same question, and never re-ask
   about a field you already have an answer for.
3. Do not fabricate or assume any details. The report may only contain
   details the engineer actually gave — never add specifics they did not
   mention. Do not produce the final report while any field is still
   missing.
4. If all five fields are covered — even in the engineer's very first
   message — do not ask anything; immediately output the report.

Only when you have specific answers for all five fields, output the report
in exactly this format — plain text, no XML tags or wrappers — and nothing
else:

FINAL REPORT
- Severity: [value]
- Affected service: [value]
- Impact: [value]
- Root cause: [value]
- Timeline: [value]

User message:
{{input}}"""

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
        # 2. Prompt node (the agent)
        {
            "name": "IncidentCoordinator",
            "type": "Prompt",
            "configuration": {
                "prompt": {
                    "sourceConfiguration": {
                        "inline": {
                            "templateType": "TEXT",
                            "templateConfiguration": {
                                "text": {
                                    "text": COORDINATOR_PROMPT,
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
        # 3. FlowOutput
        {
            "name": "FlowOutput",
            "type": "Output",
            "configuration": {"output": {}},
            "inputs": [
                {
                    "name": "document",
                    "type": "String",
                    "expression": "$.data",
                }
            ],
            "outputs": [],
        },
    ],
    "connections": [
        # FlowInput -> IncidentCoordinator
        {
            "type": "Data",
            "name": "input_to_agent",
            "source": "FlowInput",
            "target": "IncidentCoordinator",
            "configuration": {
                "data": {"sourceOutput": "document", "targetInput": "input"}
            },
        },
        # IncidentCoordinator -> FlowOutput
        {
            "type": "Data",
            "name": "agent_to_output",
            "source": "IncidentCoordinator",
            "target": "FlowOutput",
            "configuration": {
                "data": {
                    "sourceOutput": "modelCompletion",
                    "targetInput": "document",
                }
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
    for attempt in range(6):
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
            f.write(f"\nINCIDENT_FLOW_ALIAS_ARN={alias_arn}\n")
        print(f"  Saved INCIDENT_FLOW_ALIAS_ARN to .env")

        return alias_arn
    except ClientError as e:
        print(f"Error creating alias: {e.response['Error']['Message']}")
        raise


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print("=== Incident Report Flow Setup ===\n")

    flow_id, flow_arn = create_flow()
    prepare_flow(flow_id)
    alias_arn = create_alias(flow_id)

    print(f"\n=== Setup Complete ===")
    print(f"Flow ID:       {flow_id}")
    print(f"Flow ARN:      {flow_arn}")
    print(f"Alias ARN:     {alias_arn}")
    print(f"\nNext: run python test_flow.py")
