"""
Shared helpers for AWS API discovery scripts.

Loads credentials from the project-root .env (two levels above this file),
resolves the region/model, and creates boto3 clients on demand.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# aws-api/scripts/_common.py -> ../../..
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
load_dotenv(ROOT_DIR / ".env")

REGION = os.getenv("AWS_REGION", "us-east-1")
MODEL_ID = os.getenv("MODEL_ID", "amazon.nova-lite-v1:0")


def account_id() -> str:
    import boto3

    return boto3.client("sts", region_name=REGION).get_caller_identity()["Account"]


def client(name: str):
    import boto3

    return boto3.client(name, region_name=REGION)
