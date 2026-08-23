import boto3
import os
import sys
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------
bedrock = boto3.client("bedrock-agentcore", region_name="us-east-1")
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
            bedrock.delete_agent_runtime(agentRuntimeId=harness_id)
            print(f"Deleted harness: {harness_id}")
        except Exception as e:
            print(f"Harness deletion note: {e}")
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
