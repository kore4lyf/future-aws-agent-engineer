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
├── requirements.txt
├── README.md
│
├── implementation/
│   ├── harness/                  # AgentCore managed harness (working agent)
│   │   ├── agentcore_config.json
│   │   ├── create_harness.py
│   │   ├── chat.py
│   │   ├── cleanup_agentcore.py
│   │   ├── debug_tools.py
│   │   └── debug_target.py
│   │
│   └── flow/                     # Bedrock Flow (rubric compliance)
│       ├── create_flow.py
│       ├── test_flow.py
│       └── cleanup_flow.py
│
├── tests/
│   ├── harness-tests.json        # Test suite (7 tests)
│   ├── harness-tests-template.json
│   ├── output_eval_dataset.jsonl # Eval dataset (7 records)
│   └── eval-job-config.json
│
├── infrastructure/
│   ├── cloudformation-tool.yaml
│   ├── cloudformation-testing.yaml
│   └── lambda/
│       └── create_bug_report.py
│
├── docs/
│   ├── submission-notes.md       # Rubric mapping + architecture note
│   ├── submission-checklist.md
│   └── eval-observations.md
│
└── evidence/
     ├── rubric-1-routing/        # Flow diagram, classifier, condition nodes
     ├── rubric-2-bug-report/     # Bug report transcript + DynamoDB
     ├── rubric-3-faq-other/      # FAQ transcript + other request
     └── rubric-4-evaluation/     # Eval screenshots + observations
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
python implementation/harness/setup_gateway.py

# 4. Create Harness
python implementation/harness/create_harness.py

# 5. Chat
python implementation/harness/chat.py

# 6. Cleanup
python implementation/harness/cleanup_agentcore.py
```

## Evaluation

```bash
# 1. Generate eval dataset
python tests/generate-eval-dataset.py --tests-json tests/harness-tests.json

# 2. Deploy testing stack
aws cloudformation deploy \
  --template-file infrastructure/cloudformation-testing.yaml \
  --stack-name bug-report-testing-stack \
  --capabilities CAPABILITY_NAMED_IAM \
  --region us-east-1

# 3. Upload to S3
aws s3 cp tests/output_eval_dataset.jsonl \
  s3://<EvalDatasetBucketName>/output_eval_dataset.jsonl \
  --region us-east-1

# 4. Create Bedrock Evaluation job
python tests/create_eval_job.py
```
