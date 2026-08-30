# Customer Support Chatbot with Amazon Bedrock AgentCore

A customer support chatbot that handles bug reports, platform questions, and other requests using the Bedrock AgentCore managed harness.

## Architecture

```
User → chat.py → AgentCore Harness → ReAct Loop → Lambda Tool → DynamoDB
                                    ↓
                          ┌─────────┴─────────┐
                          │                   │
                     Bug Report          Platform FAQ
                     (Lambda + DDB)      (Embedded in prompt)
```

## Features

- **Bug Reports**: Collects details over conversation, then files a ticket
- **Platform Questions**: Answers using embedded FAQ (orders, shipping, returns, payments)
- **Other Requests**: Politely redirects to human support

## Project Structure

```
customer-support-chatbot/
├── .env                          # AWS credentials
├── system_prompt.txt             # Main deliverable: chatbot prompt
├── online_shop_faq.md            # FAQ document for platform questions
├── harness-tests.json            # Test cases for evaluation
├── harness-tests-template.json   # Template for test cases
├── output_eval_dataset.jsonl     # Generated evaluation dataset
├── eval-job-config.json          # Bedrock Evaluation job config
├── requirements.txt
├── README.md
│
├── scripts/
│   ├── aws/
│   │   ├── setup_gateway.py      # Creates AgentCore Gateway + Target
│   │   ├── create_harness.py     # Creates/updates the managed harness
│   │   ├── chat.py               # Interactive chat client
│   │   ├── cleanup_agentcore.py  # Deletes harness, gateway, target
│   │   ├── debug_target.py       # Debug gateway target payload
│   │   └── debug_tools.py        # Debug available tools
│   └── bedrock/
│       └── generate-eval-dataset.py  # Runs harness → JSONL for Evaluations
│
├── infrastructure/
│   ├── cloudformation-tool.yaml       # DynamoDB, Lambda, IAM roles
│   ├── cloudformation-testing.yaml    # S3 bucket + eval IAM role
│   └── lambda/
│       └── create_bug_report.py       # Lambda function code
│
└── docs/
    └── submission-checklist.md        # Rubric evidence checklist
```

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Deploy CloudFormation stack
aws cloudformation deploy \
  --template-file infrastructure/cloudformation-tool.yaml \
  --stack-name bug-report-tool-stack \
  --capabilities CAPABILITY_NAMED_IAM \
  --region us-east-1

# 3. Create Gateway
python scripts/aws/setup_gateway.py

# 4. Create Harness
python scripts/aws/create_harness.py

# 5. Chat
python scripts/aws/chat.py

# 6. Cleanup
python scripts/aws/cleanup_agentcore.py
```

## System Prompt Design

The system prompt handles three categories:

### Bug Reports
- Collects: description, steps to reproduce, environment
- Asks ONE question per turn
- Files ticket via `create_bug_report` tool

### Platform Questions
- Answers from embedded FAQ only
- Covers: orders, shipping, returns, payments
- Redirects to human support if FAQ doesn't cover the question

### Other Requests
- Politely acknowledges
- Offers to connect with human support
- Keeps response under 50 words

## Evaluation

```bash
# 1. Copy test template and add your test cases
cp harness-tests-template.json harness-tests.json

# 2. Generate evaluation dataset
python scripts/bedrock/generate-eval-dataset.py --tests-json harness-tests.json

# 3. Deploy testing stack
aws cloudformation deploy \
  --template-file infrastructure/cloudformation-testing.yaml \
  --stack-name bug-report-testing-stack \
  --capabilities CAPABILITY_NAMED_IAM \
  --region us-east-1

# 4. Get stack outputs
aws cloudformation describe-stacks \
  --stack-name bug-report-testing-stack \
  --query 'Stacks[0].Outputs' \
  --output table \
  --region us-east-1

# 5. Upload to S3
aws s3 cp output_eval_dataset.jsonl \
  s3://<EvalDatasetBucketName>/output_eval_dataset.jsonl \
  --region us-east-1

# 6. Create Bedrock Evaluation job
aws bedrock create-evaluation-job \
  --job-name support-chatbot-eval-run-1 \
  --role-arn <BedrockEvalRoleArn> \
  --evaluation-config file://eval-job-config.json \
  --region us-east-1
```
