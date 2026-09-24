#!/usr/bin/env python3
"""Deploy the Lesson 11 exercise infrastructure stack."""
import sys
import subprocess
from pathlib import Path

import boto3
from botocore.exceptions import ClientError

STACK_NAME = "lesson-11-exercise-gateway"
TEMPLATE_PATH = Path(__file__).parent / "template.yaml"
REGION = __import__("os").environ.get("AWS_REGION", "us-east-1")


def _aws_cmd(*args):
    return ["uvx", "--from", "awscli", "aws"] + list(args)


def deploy():
    if not TEMPLATE_PATH.exists():
        print(f"ERROR: template not found: {TEMPLATE_PATH}")
        sys.exit(1)

    print(f"Deploying stack {STACK_NAME} in {REGION}...")
    subprocess.run(
        _aws_cmd(
            "cloudformation", "deploy",
            "--template-file", str(TEMPLATE_PATH),
            "--stack-name", STACK_NAME,
            "--region", REGION,
            "--capabilities", "CAPABILITY_NAMED_IAM",
        ),
        check=True,
    )

    cf = boto3.client("cloudformation", region_name=REGION)
    stacks = cf.describe_stacks(StackName=STACK_NAME)["Stacks"]
    outputs = {o["OutputKey"]: o["OutputValue"] for o in stacks[0].get("Outputs", [])}

    print("\n=== Stack outputs ===")
    for key, value in outputs.items():
        print(f"  {key}: {value}")

    return outputs


if __name__ == "__main__":
    deploy()
