"""Seed Drug Interactions + Clinical Guidelines documents into the exercise S3 bucket."""

import os
from pathlib import Path

import boto3
from dotenv import load_dotenv

load_dotenv()

AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
STACK_NAME = os.environ.get("RAG_STACK_NAME", "lesson-08-exercise-rag")
PREFIXES = ("drugs", "guidelines")


def get_bucket_name() -> str:
    cfn = boto3.client("cloudformation", region_name=AWS_REGION)
    stacks = cfn.describe_stacks(StackName=STACK_NAME)["Stacks"]
    for out in stacks[0].get("Outputs", []):
        if out["OutputKey"] == "SourceBucketName":
            return out["OutputValue"]
    raise SystemExit(f"Output SourceBucketName not found on stack {STACK_NAME}")


def seed(bucket: str) -> int:
    s3 = boto3.client("s3", region_name=AWS_REGION)
    root = Path(__file__).parent / "documents"
    count = 0
    for prefix in PREFIXES:
        folder = root / prefix
        if not folder.is_dir():
            print(f"  skip missing folder: {folder}")
            continue
        for path in sorted(folder.iterdir()):
            if not path.is_file():
                continue
            key = f"{prefix}/{path.name}"
            s3.upload_file(str(path), bucket, key)
            print(f"  s3://{bucket}/{key}")
            count += 1
    return count


def main() -> None:
    if not os.getenv("AWS_ACCESS_KEY_ID"):
        raise SystemExit("AWS credentials not set — load them into .env first")
    bucket = get_bucket_name()
    print(f"Seeding bucket: {bucket}")
    n = seed(bucket)
    print(f"Uploaded {n} documents")


if __name__ == "__main__":
    main()
