# Customer Support Chatbot — Submission Notes

## Architecture Note: AgentCore Managed Harness (Not Bedrock Flow)

**This project uses the Amazon Bedrock AgentCore managed harness, not Bedrock Agents Classic or Bedrock Flows.**

Bedrock Agents Classic closed to new customers on July 30, 2026. The course instructions explicitly direct students to use its successor: the **AgentCore managed harness**. The rubric still references flow diagrams and condition nodes from the legacy approach; those artifacts do not exist in this implementation.

**How routing works here:** All three-category routing (bug report / platform question / other) is handled by a single system prompt (`system_prompt.txt`) inside the harness. The harness runs the ReAct loop server-side, manages conversation state via `runtimeSessionId`, and invokes the `create_bug_report` Lambda tool through an AgentCore Gateway when all required fields are collected.

---

## Rubric Mapping

### 1. Implement Classification and Routing

| Rubric Item | Evidence in This Submission |
|-------------|----------------------------|
| Build a routing mechanism that classifies customer messages and routes them across distinct paths | `system_prompt.txt` — lines 3–14 define three crisp categories (BUG REPORT, PLATFORM QUESTION, OTHER); routing is performed by the model reading these definitions and selecting exactly one category per message |
| Classifier output is consistent and unambiguous | `harness-tests.json` — 7 test cases with deterministic expected behaviors; eval score 1.0 confirms consistent routing |
| Messages are routed to distinct paths based on their category | Chat transcripts in `screenshots/chat-transcripts/` show distinct behavior for each category |
| Distinct paths each terminate at a separate output | Bug reports → ticket creation + ticket ID; Platform questions → FAQ-grounded answer; Other → human support redirect |

**Evidence files:**
- `system_prompt.txt` — the classifier/routing prompt
- `screenshots/chat-transcripts/Bug report (multi-turn).png` — bug report path
- `screenshots/chat-transcripts/Platform question.png` — FAQ path
- `screenshots/chat-transcripts/Other request.png` — redirect path

### 2. Implement the Bug Report Path

| Rubric Item | Evidence in This Submission |
|-------------|----------------------------|
| Collects `description`, `stepsToReproduce`, `environment` across conversation | `system_prompt.txt` lines 18–32 specify collection procedure; transcript shows multi-turn collection |
| Calls `create_bug_report` only after all fields collected | Prompt explicitly forbids tool call until all three fields are present; eval confirms correct behavior |
| Relays ticket ID to customer | Prompt line 6: "After filing, respond with EXACTLY: 'Ticket filed: <ticket_id>'" |
| Record created in DynamoDB | `screenshots/dynamodb-tickets/bug-report-tool-stack-bug-reports table items.png` shows OPEN tickets |

**Evidence files:**
- `system_prompt.txt` — bug report collection rules
- `screenshots/chat-transcripts/Bug report (multi-turn).png` — multi-turn collection + tool call
- `screenshots/dynamodb-tickets/bug-report-tool-stack-bug-reports table items.png` — DynamoDB records
- `infrastructure/lambda/create_bug_report.py` — Lambda tool implementation

### 3. Implement Platform Question and Other Request Paths

| Rubric Item | Evidence in This Submission |
|-------------|----------------------------|
| Relevant answer when FAQ covers the question | `system_prompt.txt` embeds `online_shop_faq.md`; transcript shows accurate FAQ-grounded answer for shipping question |
| Redirects to human support when FAQ doesn't cover the question | Prompt line 11: redirect when FAQ doesn't cover the question |
| Separate path for other requests → support phone line | Prompt lines 13–19 define OTHER category with polite redirect |
| Screenshots of covered, uncovered, and other-request responses | `screenshots/chat-transcripts/Platform question.png`, `screenshots/chat-transcripts/Other request.png` |

**Evidence files:**
- `system_prompt.txt` — FAQ grounding and redirect rules
- `online_shop_faq.md` — embedded FAQ document
- `screenshots/chat-transcripts/Platform question.png` — covered FAQ question
- `screenshots/chat-transcripts/Other request.png` — other request redirect

### 4. Testing and Evaluation

| Rubric Item | Evidence in This Submission |
|-------------|----------------------------|
| Test suite covers all three routes | `harness-tests.json` — 7 tests: bug report (2), FAQ (3), other (1), ambiguous (1) |
| Eval dataset generated | `output_eval_dataset.jsonl` — 7 records |
| JSONL uploaded to S3 | Uploaded to `s3://customer-support-eval-708026873259/output_eval_dataset.jsonl` |
| Bedrock Evaluation job created | `support-chatbot-eval-run-3` (ARN: `arn:aws:bedrock:us-east-1:708026873259:evaluation-job/2kl0fuuex06t`) |
| Correctness score close to 1 | **1.0 / 1.0** (7/7 tests passed) |
| Written observations | `docs/eval-observations.md` |

**Evidence files:**
- `harness-tests.json` — test suite
- `output_eval_dataset.jsonl` — eval dataset
- `screenshots/model-evaluation/final-model-evaluation-report.png` — eval results screenshot
- `docs/eval-observations.md` — written observations

---

## Why There Is No Bedrock Flow

The rubric references Bedrock Flow artifacts (flow diagram, condition node expressions, FAQ prompt node template). This project uses the **AgentCore managed harness** instead, as directed by the course instructions (Module 14). The harness accomplishes the same routing behavior through prompt engineering rather than visual node-based orchestration.

**Equivalent artifacts:**

| Rubric asks for | This project provides |
|-----------------|----------------------|
| Flow diagram | `system_prompt.txt` (the routing logic lives here) |
| Classifier prompt configuration | `system_prompt.txt` lines 3–14 (category definitions) |
| Condition node expressions | No condition nodes — routing is done by the model reading the category definitions |
| FAQ Prompt node template | `system_prompt.txt` lines 34–40 (FAQ embedded via `{{FAQ}}` placeholder) |
| Flow test responses | `screenshots/chat-transcripts/` (chat.py output) |
| `flow-tests.json` | `harness-tests.json` (same purpose, harness-based) |

---

## File Inventory

```
customer-support-chatbot/
├── system_prompt.txt                    # Main deliverable: routing + behavior prompt
├── online_shop_faq.md                   # FAQ document embedded in prompt
├── harness-tests.json                   # Test suite (7 tests, all 3 routes)
├── output_eval_dataset.jsonl            # Eval dataset (7 records)
├── eval-job-config.json                 # Eval job configuration
├── requirements.txt
├── README.md
├── docs/
│   ├── submission-checklist.md          # All rubric items checked
│   └── eval-observations.md             # Eval results write-up
├── scripts/
│   ├── aws/
│   │   ├── setup_gateway.py             # Creates AgentCore Gateway + Target
│   │   ├── create_harness.py            # Creates/updates the managed harness
│   │   ├── chat.py                      # Interactive chat client
│   │   ├── cleanup_agentcore.py         # Deletes harness, gateway
│   │   └── debug_tools.py               # Debug gateway/tools
│   └── bedrock/
│       ├── generate-eval-dataset.py     # Runs harness → JSONL for Evaluations
│       └── create_eval_job.py           # Creates Bedrock Evaluation job
├── infrastructure/
│   ├── cloudformation-tool.yaml         # DynamoDB, Lambda, IAM roles
│   ├── cloudformation-testing.yaml      # S3 bucket + eval IAM role
│   └── lambda/
│       └── create_bug_report.py         # Lambda function code
└── screenshots/
    ├── chat-transcripts/
    │   ├── Bug report (multi-turn).png
    │   ├── Platform question.png
    │   └── Other request.png
    ├── dynamodb-tickets/
    │   ├── bug-report-tool-stack-bug-reports table items.png
    │   └── tables.png
    └── model-evaluation/
        ├── final-model-evaluation-report.png
        └── model-evaluation-list.png
```
