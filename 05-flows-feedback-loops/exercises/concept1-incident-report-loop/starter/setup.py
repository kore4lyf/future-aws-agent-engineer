import boto3
import json
import time
import os
import uuid
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------
bedrock = boto3.client("bedrock-agentcore", region_name="us-east-1")
iam = boto3.client("iam", region_name="us-east-1")

MODEL_ID = "amazon.nova-pro-v1:0"

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

    role = iam.create_role(
        RoleName=role_name,
        AssumeRolePolicyDocument=json.dumps(trust_policy),
        Description="Role for incident report coordinator harness"
    )

    print(f"Created IAM role {role_name}")
    return role["Role"]["Arn"]


# ---------------------------------------------------------------------------
# Create harness
# ---------------------------------------------------------------------------
def create_harness(role_arn):
    harness_name = f"incident-coordinator-{uuid.uuid4().hex[:8]}"

    try:
        harness = bedrock.create_agent_runtime(
            name=harness_name,
            description="Incident report coordinator with feedback loop",
            modelId=MODEL_ID,
            instructionPrompt=SYSTEM_PROMPT,
            roleArn=role_arn,
            inferenceConfig={
                "temperature": 0.0,
                "topK": 1
            },
            memory={"disabled": {}}
        )
        harness_id = harness["agentRuntimeId"]
        harness_arn = harness.get("agentRuntimeArn", f"arn:aws:bedrock-agentcore:us-east-1:{boto3.client('sts').get_caller_identity()['Account']}:agent-runtime/{harness_id}")
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

    print("1. Creating IAM role...")
    role_arn = create_iam_role()
    print()

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
