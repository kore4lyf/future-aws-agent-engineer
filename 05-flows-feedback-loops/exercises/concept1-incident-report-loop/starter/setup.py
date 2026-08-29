import boto3
import json
import time
import os
import uuid
from pathlib import Path
from dotenv import load_dotenv

root_dir = Path(__file__).parent.parent.parent.parent.parent
load_dotenv(root_dir / ".env")

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------
bedrock = boto3.client("bedrock-agentcore", region_name="us-east-1")
bedrock_control = boto3.client("bedrock-agentcore-control", region_name="us-east-1")
iam = boto3.client("iam", region_name="us-east-1")

MODEL_ID = os.getenv("MODEL_ID", "amazon.nova-pro-v1:0")

# ---------------------------------------------------------------------------
# SYSTEM_PROMPT — Write your incident report coordinator prompt here
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = """\
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
"""


# ---------------------------------------------------------------------------
# Create IAM role
# ---------------------------------------------------------------------------
def create_iam_role():
    role_name = f"incident_coordinator_role_{uuid.uuid4().hex[:8]}"

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
            RoleName=role_name,
            AssumeRolePolicyDocument=json.dumps(trust_policy),
            Description="Role for incident report coordinator harness"
        )
        role_arn = role["Role"]["Arn"]
    except iam.exceptions.EntityAlreadyExistsException:
        role = iam.get_role(RoleName=role_name)
        role_arn = role["Role"]["Arn"]

    # Grant the role permissions needed by the harness
    policy_document = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Action": "bedrock-agentcore:*",
                "Resource": "*"
            },
            {
                "Effect": "Allow",
                "Action": [
                    "bedrock:InvokeModel",
                    "bedrock:InvokeModelWithResponseStream"
                ],
                "Resource": "arn:aws:bedrock:*::foundation-model/*"
            }
        ]
    }

    try:
        iam.put_role_policy(
            RoleName=role_name,
            PolicyName="incident-coordinator-policy",
            PolicyDocument=json.dumps(policy_document)
        )
    except Exception as e:
        print(f"Policy update note: {e}")

    print(f"Created IAM role {role_name}")
    return role_arn


# ---------------------------------------------------------------------------
# Create harness
# ---------------------------------------------------------------------------
def create_harness(role_arn):
    harness_name = f"incident_coordinator_{uuid.uuid4().hex[:8]}"

    try:
        harness = bedrock_control.create_harness(
            harnessName=harness_name,
            executionRoleArn=role_arn,
            model={"bedrockModelConfig": {"modelId": MODEL_ID}},
            systemPrompt=[{"text": SYSTEM_PROMPT}],
            memory={"disabled": {}}
        )
        harness_id = harness["harness"]["harnessId"]
        harness_arn = harness["harness"]["arn"]
        print(f"Created harness: {harness_arn}")
    except Exception as e:
        print(f"Error creating harness: {e}")
        return None, None

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

    # Save harness ARN for chat.py
    with open("harness_arn.txt", "w") as f:
        f.write(harness_arn)
    print(f"Saved harness ARN to harness_arn.txt")

    return harness_id, harness_arn


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print("=== Incident Report Coordinator Setup ===\n")

    role_arn = "arn:aws:iam::708026873259:role/AmazonBedrockExecutionRoleForFlows"
    print(f"Using existing role: {role_arn}")

    print("2. Creating harness...")
    harness_id, harness_arn = create_harness(role_arn)
    print()

    if harness_id:
        print("=== Setup Complete ===")
        print(f"Harness ID: {harness_id}")
        print(f"Harness ARN: {harness_arn}")
        print(f"\nRun: python chat.py")
    else:
        print("Setup failed. Check the error above.")
