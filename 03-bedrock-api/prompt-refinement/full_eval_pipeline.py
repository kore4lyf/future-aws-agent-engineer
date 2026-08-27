"""
Full Bedrock Evaluation Pipeline — No UI Required

This script:
1. Creates a prompt in Bedrock Prompt Management
2. Publishes version 1
3. Generates responses for all test cases
4. Writes JSONL file
5. Uploads to S3
6. Creates and runs an evaluation job

Usage:
    python full_eval_pipeline.py
"""

import boto3
import json
import time
import os
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------
bedrock = boto3.client("bedrock", region_name="us-east-1")
bedrock_runtime = boto3.client("bedrock-runtime", region_name="us-east-1")
s3 = boto3.client("s3", region_name="us-east-1")
iam = boto3.client("iam", region_name="us-east-1")
sts = boto3.client("sts", region_name="us-east-1")

REGION = "us-east-1"
ACCOUNT_ID = sts.get_caller_identity()["Account"]
MODEL_ID = "amazon.nova-pro-v1:0"
BUCKET_NAME = f"faq-eval-bucket-{ACCOUNT_ID}"
OUTPUT_KEY = "eval_responses.jsonl"

# ---------------------------------------------------------------------------
# Product FAQ
# ---------------------------------------------------------------------------
PRODUCT_FAQ = """\
Product FAQ

Pricing:
- Individual plan: $29 per month
- Team plan: $99 per month (up to 10 users)
- Enterprise: contact sales for custom pricing

Free Trial:
- 14-day free trial available for all plans
- No credit card required to start

Features:
- Task management with priority levels and due dates
- Time tracking built into each task
- Gantt chart view for project timelines
- Integrations: Slack and Google Workspace only

Storage:
- Individual plan: 10 GB per user
- Team plan: 100 GB shared across the team

Supported Platforms:
- Web browsers (Chrome, Firefox, Safari, Edge)
- iOS and Android mobile apps

Security:
- SOC 2 Type II certified
- All data encrypted at rest and in transit

Support:
- Email support for all plans
- Live chat support for Team and Enterprise plans only\
"""

# ---------------------------------------------------------------------------
# Eval dataset
# ---------------------------------------------------------------------------
EVAL_QUESTIONS = [
    # Answerable questions
    {"prompt": "What is the price of the team plan?",
     "referenceResponse": "The team plan is $99 per month and supports up to 10 users."},
    {"prompt": "Does the product offer a free trial?",
     "referenceResponse": "Yes, a 14-day free trial is available for all plans with no credit card required."},
    {"prompt": "How much storage does the individual plan include?",
     "referenceResponse": "The individual plan includes 10 GB of storage per user."},
    {"prompt": "What integrations does the product support?",
     "referenceResponse": "The product integrates with Slack and Google Workspace only."},
    # Unanswerable questions
    {"prompt": "Does the product integrate with Microsoft Teams?",
     "referenceResponse": "That information is not available in the FAQ. The FAQ mentions Slack and Google Workspace integrations only."},
    {"prompt": "Is the product HIPAA compliant?",
     "referenceResponse": "That information is not available in the FAQ. The FAQ mentions SOC 2 Type II certification only."},
]

# Prompt template
PROMPT_TEMPLATE = """\
You are a helpful product assistant for a SaaS company. Answer the customer's question using ONLY the FAQ below. If the answer is not in the FAQ, say "That information is not available in the FAQ." Do not make up information.

FAQ:
{faq}

Customer question: {question}

Answer:"""


# ---------------------------------------------------------------------------
# Step 1: Create Prompt in Bedrock Prompt Management
# ---------------------------------------------------------------------------
def create_prompt():
    print("Step 1: Creating prompt in Bedrock Prompt Management...")

    prompt_name = "FAQ-Assistant-Eval"

    # Check if prompt exists
    try:
        response = bedrock.list_prompts(maxResults=100)
        for prompt in response.get("promptSummaries", []):
            if prompt["name"] == prompt_name:
                print(f"  Prompt already exists: {prompt['id']}")
                return prompt["id"]
    except Exception as e:
        print(f"  List prompts note: {e}")

    # Create new prompt
    try:
        response = bedrock.create_prompt(
            name=prompt_name,
            description="FAQ assistant for evaluation",
            customerEncryptionKeyArn=None,
            tags={}
        )
        prompt_id = response["id"]
        print(f"  Created prompt: {prompt_id}")
        return prompt_id
    except Exception as e:
        print(f"  Error creating prompt: {e}")
        return None


# ---------------------------------------------------------------------------
# Step 2: Create Prompt Version
# ---------------------------------------------------------------------------
def create_prompt_version(prompt_id):
    print("\nStep 2: Creating prompt version...")

    try:
        response = bedrock.create_prompt_version(
            promptIdentifier=prompt_id,
            description="Version 1 - FAQ assistant"
        )
        version = response["version"]
        prompt_arn = response["arn"]
        print(f"  Created version: {version}")
        print(f"  Prompt ARN: {prompt_arn}")
        return version, prompt_arn
    except Exception as e:
        print(f"  Error creating version: {e}")
        return None, None


# ---------------------------------------------------------------------------
# Step 3: Generate Responses
# ---------------------------------------------------------------------------
def generate_responses(prompt_arn):
    print("\nStep 3: Generating responses for test cases...")

    responses = []

    for i, item in enumerate(EVAL_QUESTIONS, 1):
        question = item["prompt"]
        reference = item["referenceResponse"]

        # Format the prompt
        full_prompt = PROMPT_TEMPLATE.format(
            faq=PRODUCT_FAQ,
            question=question
        )

        # Invoke model
        try:
            body = {
                "messages": [{"role": "user", "content": [{"text": full_prompt}]}],
                "inferenceConfig": {"maxTokens": 512, "temperature": 0.0},
            }

            response = bedrock_runtime.invoke_model(
                modelId=MODEL_ID,
                body=json.dumps(body),
                contentType="application/json",
                accept="application/json",
            )

            result = json.loads(response["body"].read())
            model_response = result["output"]["message"]["content"][0]["text"]

            print(f"  [{i}/{len(EVAL_QUESTIONS)}] {question[:50]}...")
            print(f"      Response: {model_response[:80]}...")

            responses.append({
                "prompt": question,
                "referenceResponse": reference,
                "modelResponses": [
                    {
                        "response": model_response,
                        "modelIdentifier": "faq-assistant-v1",
                    }
                ],
            })
        except Exception as e:
            print(f"  Error on question {i}: {e}")
            responses.append({
                "prompt": question,
                "referenceResponse": reference,
                "modelResponses": [
                    {
                        "response": f"Error: {str(e)}",
                        "modelIdentifier": "faq-assistant-v1",
                    }
                ],
            })

    return responses


# ---------------------------------------------------------------------------
# Step 4: Write JSONL File
# ---------------------------------------------------------------------------
def write_jsonl(responses):
    print("\nStep 4: Writing JSONL file...")

    output_file = "eval_responses.jsonl"

    with open(output_file, "w") as f:
        for record in responses:
            f.write(json.dumps(record) + "\n")

    print(f"  Wrote {len(responses)} records to {output_file}")
    return output_file


# ---------------------------------------------------------------------------
# Step 5: Create S3 Bucket and Upload
# ---------------------------------------------------------------------------
def upload_to_s3(file_path):
    print("\nStep 5: Uploading to S3...")

    # Create bucket if it doesn't exist
    try:
        if REGION == "us-east-1":
            s3.create_bucket(Bucket=BUCKET_NAME)
        else:
            s3.create_bucket(
                Bucket=BUCKET_NAME,
                CreateBucketConfiguration={"LocationConstraint": REGION}
            )
        print(f"  Created bucket: {BUCKET_NAME}")
    except s3.exceptions.BucketAlreadyOwnedByYou:
        print(f"  Bucket already exists: {BUCKET_NAME}")
    except Exception as e:
        print(f"  Bucket note: {e}")

    # Upload file
    s3.upload_file(file_path, BUCKET_NAME, OUTPUT_KEY)
    s3_uri = f"s3://{BUCKET_NAME}/{OUTPUT_KEY}"
    print(f"  Uploaded to: {s3_uri}")
    return s3_uri


# ---------------------------------------------------------------------------
# Step 6: Create Evaluation Job
# ---------------------------------------------------------------------------
def create_evaluation_job(s3_uri):
    print("\nStep 6: Creating evaluation job...")

    # Create IAM role for evaluation
    role_name = f"bedrock-eval-role-{ACCOUNT_ID[:8]}"
    trust_policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Principal": {"Service": "bedrock.amazonaws.com"},
                "Action": "sts:AssumeRole"
            }
        ]
    }

    try:
        role = iam.create_role(
            RoleName=role_name,
            AssumeRolePolicyDocument=json.dumps(trust_policy),
            Description="Role for Bedrock evaluation"
        )
        role_arn = role["Role"]["Arn"]

        # Attach policies
        iam.attach_role_policy(
            RoleName=role_name,
            PolicyArn="arn:aws:iam::aws:policy/AmazonS3FullAccess"
        )
        iam.attach_role_policy(
            RoleName=role_name,
            PolicyArn="arn:aws:iam::aws:policy/AmazonBedrockFullAccess"
        )

        print(f"  Created IAM role: {role_name}")
        time.sleep(10)  # Wait for role to propagate
    except iam.exceptions.EntityAlreadyExistsException:
        role = iam.get_role(RoleName=role_name)
        role_arn = role["Role"]["Arn"]
        print(f"  Using existing role: {role_name}")
    except Exception as e:
        print(f"  Role creation error: {e}")
        return None

    # Create evaluation job
    try:
        response = bedrock.create_evaluation_job(
            jobName="faq-assistant-eval-job",
            roleArn=role_arn,
            evaluationConfig={
                "automated": {
                    "evalMetricConfigurations": [
                        {
                            "metricGroups": [
                                {
                                    "name": "correctness",
                                    "metricParams": [
                                        {
                                            "name": "correctness",
                                            "ratingModel": {
                                                "providerModels": [
                                                    {
                                                        "providerName": "amazon",
                                                        "modelId": MODEL_ID
                                                    }
                                                ]
                                            }
                                        }
                                    ]
                                }
                            ]
                        }
                    ]
                }
            },
            inferenceConfig={
                "models": [
                    {
                        "modelIdentifier": MODEL_ID
                    }
                ]
            },
            datasets=[
                {
                    "name": "faq-eval-dataset",
                    "dataSource": {
                        "s3Uri": s3_uri
                    }
                }
            ],
            outputConfig={
                "s3Uri": f"s3://{BUCKET_NAME}/evaluation-output/"
            }
        )

        job_arn = response["evaluationJobArn"]
        print(f"  Created evaluation job: {job_arn}")
        return job_arn
    except Exception as e:
        print(f"  Error creating evaluation job: {e}")
        print(f"  Note: You may need to create this job manually in the console.")
        return None


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print("=" * 60)
    print("BEDROCK EVALUATION PIPELINE — FULL AUTOMATION")
    print("=" * 60)

    # Step 1: Create prompt
    prompt_id = create_prompt()
    if not prompt_id:
        print("\nFailed to create prompt. Exiting.")
        exit(1)

    # Step 2: Create prompt version
    version, prompt_arn = create_prompt_version(prompt_id)
    if not version:
        print("\nFailed to create version. Exiting.")
        exit(1)

    # Step 3: Generate responses
    responses = generate_responses(prompt_arn)

    # Step 4: Write JSONL
    jsonl_file = write_jsonl(responses)

    # Step 5: Upload to S3
    s3_uri = upload_to_s3(jsonl_file)

    # Step 6: Create evaluation job
    job_arn = create_evaluation_job(s3_uri)

    print("\n" + "=" * 60)
    print("PIPELINE COMPLETE")
    print("=" * 60)
    print(f"\nPrompt ID:      {prompt_id}")
    print(f"Prompt Version: {version}")
    print(f"Prompt ARN:     {prompt_arn}")
    print(f"JSONL File:     {jsonl_file}")
    print(f"S3 URI:         {s3_uri}")
    if job_arn:
        print(f"Evaluation Job: {job_arn}")
    print("\nCheck results in Bedrock Console → Evaluations")
