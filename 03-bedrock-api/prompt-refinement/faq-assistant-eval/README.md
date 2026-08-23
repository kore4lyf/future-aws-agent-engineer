# Exercise: FAQ Assistant with Evaluation

Build and evaluate an FAQ assistant that answers customer questions strictly from a curated FAQ document.

## Overview

This exercise demonstrates:
- Bedrock Prompt Management with template variables
- Bedrock Evaluations with LLM-as-a-judge
- Prompt iteration and refinement

## Files

| File | Purpose |
|------|---------|
| `faq_assistant.py` | Main script to generate eval responses |
| `template.yaml` | CloudFormation template for S3 bucket |

## Setup

### Step 1: Create the Prompt Template

1. Open Amazon Bedrock console → Prompt Management → Create prompt
2. Select model: Amazon Nova Pro
3. Write a prompt with two template variables: `{{faq}}` and `{{customer_question}}`
4. Save and publish version 1
5. Copy the Prompt version ARN

### Step 2: Configure the Script

Update `PROMPT_VERSION_ARN` in `faq_assistant.py` with your ARN.

### Step 3: Deploy S3 Bucket

```bash
aws cloudformation deploy \
  --template-file template.yaml \
  --stack-name faq-assistant-eval \
  --region us-east-1
```

### Step 4: Run the Script

```bash
python faq_assistant.py
```

### Step 5: Upload to S3

```bash
BUCKET=$(aws cloudformation describe-stacks --stack-name faq-assistant-eval \
  --query "Stacks[0].Outputs[?OutputKey=='BucketName'].OutputValue" \
  --region us-east-1 \
  --output text)

aws s3 cp eval_responses.jsonl s3://$BUCKET/eval_responses.jsonl
```

### Step 6: Run Bedrock Evaluation

1. Open Amazon Bedrock console → Evaluations → Create
2. Select "Automatic: LLM as a judge"
3. Select Amazon Nova Pro as evaluator model
4. Set Inference source to "Bring your own inference responses"
5. Select Correctness metric
6. Point to your S3 JSONL file
7. Create the job

## Test Dataset

**Answerable questions (5):**
- Team plan pricing
- Free trial duration
- Supported integrations
- Storage limits
- Security certifications

**Unanswerable questions (2):**
- Nonprofit discounts
- Jira/Trello integrations

## Expected Output

```
Running FAQ Assistant Eval
============================================================
Question:  What is the price of the team plan?
Expected:  The team plan is $99 per month for up to 10 users.
Response:  The team plan is priced at $99 per month and supports up to 10 users.
------------------------------------------------------------
...
Wrote 7 records to eval_responses.jsonl
```

## Cleanup

- Delete the Bedrock prompt from the console
- Delete the JSONL file and evaluation results from S3
- Delete the CloudFormation stack: `aws cloudformation delete-stack --stack-name faq-assistant-eval`
