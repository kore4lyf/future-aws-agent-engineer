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

## Files

| File | Purpose |
|------|---------|
| `system_prompt.txt` | Main system prompt (main deliverable) |
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

# 2. Deploy CloudFormation stack
aws cloudformation deploy \
  --template-file cloudformation-tool.yaml \
  --stack-name customer-support-tools \
  --capabilities CAPABILITY_NAMED_IAM \
  --region us-east-1

# 3. Create Gateway
python setup_gateway.py

# 4. Create Harness
python create_harness.py

# 5. Chat
python chat.py

# 6. Cleanup
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
