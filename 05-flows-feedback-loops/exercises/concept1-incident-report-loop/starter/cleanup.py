import boto3
import os
import sys
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


def load_harness_arn():
    try:
        with open("harness_arn.txt", "r") as f:
            return f.read().strip()
    except FileNotFoundError:
        return None


def cleanup():
    harness_arn = load_harness_arn()

    # Delete harness
    if harness_arn:
        harness_id = harness_arn.split("/")[-1]
        try:
            bedrock_control.delete_harness(harnessId=harness_id)
            print(f"Deleted harness: {harness_id}")
        except Exception as e:
            if "not found" in str(e).lower():
                print(f"Harness already deleted: {harness_id}")
            else:
                print(f"Harness deletion note: {e}")
                print("Harness deletion is still finishing server-side — it will complete on its own.")
    else:
        print("No harness ARN found.")

    # Delete IAM roles
    try:
        roles = iam.list_roles()
        for role in roles["Roles"]:
            if role["RoleName"].startswith("incident_coordinator_role_"):
                try:
                    # Delete role policy first
                    try:
                        iam.delete_role_policy(
                            RoleName=role["RoleName"],
                            PolicyName="bedrock-invoke-policy"
                        )
                    except:
                        pass

                    iam.delete_role(RoleName=role["RoleName"])
                    print(f"Deleted IAM role {role['RoleName']}")
                except Exception as e:
                    print(f"IAM deletion note: {e}")
    except Exception as e:
        print(f"IAM listing note: {e}")

    # Remove harness_arn.txt
    if os.path.exists("harness_arn.txt"):
        os.remove("harness_arn.txt")
        print("Removed harness_arn.txt")

    print("\n=== Cleanup Complete ===")


if __name__ == "__main__":
    cleanup()
