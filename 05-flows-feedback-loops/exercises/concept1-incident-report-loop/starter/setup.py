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
You are an incident report coordinator for an SRE team. Your job is to collect
all required details about a production incident and produce a finalized report.

REQUIRED FIELDS (checklist):
- Severity: P1, P2, P3, or P4
- Affected service: which service, component, or region was impacted
- Impact: who or what was affected, and to what extent
- Root cause: what caused the incident (a labeled hypothesis is fine)
- Timeline: when it started, was detected, and was resolved

ON EVERY TURN:
1. Compare what you already have against the five required fields.
2. Ask exactly ONE question about the most important missing field.
3. Never ask about a field you already have information for.
4. Never fabricate or assume any details.
5. Never produce the final report while any field is missing.
6. If all five fields are already covered, don't ask anything — output the report.

FINAL REPORT FORMAT:
When all five fields are covered, output a structured report that starts with
the line "FINAL REPORT" followed by the five fields in a clear format.

Remember: exactly ONE question per turn. Never bundle multiple questions.
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
                "temperature": 0.3,
                "topK": 1
            }
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
