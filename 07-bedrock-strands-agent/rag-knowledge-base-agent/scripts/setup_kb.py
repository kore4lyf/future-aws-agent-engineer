"""
Setup S3 + Bedrock Knowledge Base with S3 Vectors + Titan Text Embeddings v2.
Run: uv run python scripts/setup_kb.py --bucket <unique-bucket> --kb-name horizon-kb
Requires: bedrock:CreateKnowledgeBase, s3:CreateBucket, iam:CreateRole (or pre-made role).
Lab IAM may deny — alternative: create via Console following NOTES.md steps.
"""
import argparse
import boto3
import pathlib
import time

REGION = "us-east-1"
EMBEDDING_MODEL = "amazon.titan-embed-text-v2:0"

DOCS_DIR = pathlib.Path(__file__).parent.parent / "docs"

def create_bucket(s3, bucket):
    try:
        s3.create_bucket(Bucket=bucket)
        print(f"Bucket created: {bucket}")
    except s3.exceptions.BucketAlreadyOwnedByYou:
        print(f"Bucket exists: {bucket}")
    for p in DOCS_DIR.glob("*.txt"):
        s3.upload_file(str(p), bucket, f"horizon-docs/{p.name}")
        print(f"Uploaded {p.name}")
    return f"s3://{bucket}/horizon-docs/"

def create_kb(bedrock_agent, bucket_arn_prefix, role_arn, kb_name):
    resp = bedrock_agent.create_knowledge_base(
        name=kb_name,
        roleArn=role_arn,
        knowledgeBaseConfiguration={
            "type": "VECTOR",
            "vectorKnowledgeBaseConfiguration": {"embeddingModelArn": f"arn:aws:bedrock:{REGION}::foundation-model/{EMBEDDING_MODEL}"}
        },
        storageConfiguration={
            "type": "S3_VECTORS",
            "s3VectorsConfiguration": {
                "indexArn": f"{bucket_arn_prefix}/index/horizon-index"
            }
        },
    )
    kb_id = resp["knowledgeBase"]["knowledgeBaseId"]
    print(f"KB created: {kb_id}")
    return kb_id

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--bucket", required=True, help="Unique S3 bucket name")
    p.add_argument("--kb-name", default="horizon-travel-kb")
    p.add_argument("--role-arn", default="", help="Pre-created KB role ARN (if lab denies iam:CreateRole)")
    args = p.parse_args()

    s3 = boto3.client("s3", region_name=REGION)
    prefix = create_bucket(s3, args.bucket)
    print(f"\nNext: create Knowledge Base in Console if IAM denied.")
    print(f"  S3 prefix: {prefix}")
    print(f"  Embedding: {EMBEDDING_MODEL} -> S3 Vectors")
    print(f"  After KB sync, set KNOWLEDGE_BASE_ID env var.")
