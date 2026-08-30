"""
Create Bedrock Evaluation Job for the Customer Support Chatbot.

Reads eval-job-config.json and creates the evaluation job.
"""

import boto3
import json
import sys
from pathlib import Path
from dotenv import load_dotenv

root_dir = Path(__file__).parent.parent
load_dotenv(root_dir / ".env")

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------
bedrock = boto3.client("bedrock", region_name="us-east-1")
CONFIG_PATH = root_dir / "eval-job-config.json"


def main():
    if not CONFIG_PATH.exists():
        print(f"Error: {CONFIG_PATH} not found.")
        sys.exit(1)

    with open(CONFIG_PATH, "r") as f:
        config = json.load(f)

    print("=== Creating Bedrock Evaluation Job ===\n")
    print(f"Job name: {config['jobName']}")
    print(f"Role ARN: {config['roleArn']}")
    print(f"Dataset: {config['evaluationConfig']['automated']['datasetMetricConfigs'][0]['dataset']['datasetLocation']['s3Uri']}")
    print(f"Output: {config['outputDataConfig']['s3Uri']}")
    print()

    try:
        response = bedrock.create_evaluation_job(**config)
        job_arn = response.get("jobArn", "N/A")
        print(f"Evaluation job created: {job_arn}")
        print(f"\nCheck status:")
        print(f"  aws bedrock describe-evaluation-job --job-name {config['jobName']} --region us-east-1")
    except Exception as e:
        print(f"Error creating evaluation job: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
