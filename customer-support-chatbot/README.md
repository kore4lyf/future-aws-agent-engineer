# Customer Support Chatbot with Amazon Bedrock AgentCore

A customer support chatbot that handles bug reports, platform questions, and other requests using the Bedrock AgentCore managed harness.

## Architecture

```
User → Bedrock Flow → Classifier → Condition → Paths
                        │
          ┌─────────────┼─────────────┐
          │             │             │
     Bug Report    Platform Q    Other Request
     (Harness)     (FAQ)         (Redirect)
          │
     AgentCore Harness → Lambda Tool → DynamoDB
```

## Features

- **Bug Reports**: Collects details over conversation, then files a ticket
- **Platform Questions**: Answers using embedded FAQ (orders, shipping, returns, payments)
- **Other Requests**: Politely redirects to human support

## Files

| File | Purpose |
|------|---------|
| `system_prompt.txt` | System prompt for bug report collection (used by harness) |
| `cloudformation-flow.yaml` | Bedrock Flow with classifier, condition, and 3 paths |
| `cloudformation-tool.yaml` | Deploys DynamoDB, Lambda, and IAM roles |
| `create_bug_report.py` | Lambda function code |
| `setup_gateway.py` | Creates AgentCore Gateway |
| `create_harness.py` | Creates the managed harness |
| `chat.py` | Terminal chat client |
| `online_shop_faq.md` | FAQ document |
| `cleanup_agentcore.py` | Deletes resources |
| `requirements.txt` | Dependencies |

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Deploy CloudFormation stack (Lambda, DynamoDB, IAM)
aws cloudformation deploy \
  --template-file cloudformation-tool.yaml \
  --stack-name bug-report-tool-stack \
  --capabilities CAPABILITY_NAMED_IAM \
  --region us-east-1

# 3. Deploy Bedrock Flow
aws cloudformation deploy \
  --template-file cloudformation-flow.yaml \
  --stack-name bug-report-flow-stack \
  --capabilities CAPABILITY_NAMED_IAM \
  --region us-east-1

# 4. Create Gateway
python setup_gateway.py

# 5. Create Harness
python create_harness.py

# 6. Chat (using harness directly)
python chat.py

# 7. Test Flow in Bedrock console
# - Go to Bedrock → Flows → customer-support-flow
# - Test with: "The checkout page is broken"
# - Test with: "How long does shipping take?"
# - Test with: "Can you help me with my homework?"

# 8. Cleanup
python cleanup_agentcore.py
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

## Test Cases

**Bug Report:**
```
You: The checkout page is broken
Assistant: I'm sorry to hear that. Can you describe what happens when you try to checkout?
You: It shows an error message
Assistant: What does the error message say?
You: "Payment failed" but I didn't enter any payment info
Assistant: What browser and device are you using?
You: Chrome on Windows 10
Assistant: Thank you. Let me file a bug report for you. [files ticket]
```

**Platform Question:**
```
You: How long does shipping take?
Assistant: Standard shipping takes 3-5 business days. Express shipping is 1-2 business days for an additional fee. Orders over $50 qualify for free shipping.
```

**Other Request:**
```
You: Can you help me with my homework?
Assistant: I'm here to help with bug reports or platform questions (orders, shipping, returns, payments). For other inquiries, I can connect you with human support. Would you like me to do that?
```

## Evaluation

```bash
# 1. Copy test template and add your test cases
cp flow-tests-template.json flow-tests.json

# 2. Generate evaluation dataset
python generate-eval-dataset.py --tests-json flow-tests.json

# 3. Deploy testing stack
aws cloudformation deploy \
  --template-file cloudformation-testing.yaml \
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

# 6. Run Bedrock Evaluation job (see Testing Framework docs)
```
