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
| Messages are routed to distinct paths based on their category | Chat transcripts in `evidence/rubric-1-routing/` and `evidence/rubric-3-faq-other/` show distinct behavior for each category |
| Distinct paths each terminate at a separate output | Bug reports → ticket creation + ticket ID; Platform questions → FAQ-grounded answer; Other → human support redirect |

**Evidence files:**
- `system_prompt.txt` — the classifier/routing prompt
- `evidence/rubric-1-routing/flow-diagram.md` — flow diagram documentation
- `evidence/rubric-1-routing/classifier-prompt.txt` — classifier prompt text
- `evidence/rubric-1-routing/condition-nodes.txt` — condition node expressions
- `evidence/rubric-2-bug-report/Bug report (multi-turn).png` — bug report path transcript
- `evidence/rubric-3-faq-other/Platform question.png` — FAQ path
- `evidence/rubric-3-faq-other/Other request.png` — redirect path

### 2. Implement the Bug Report Path

| Rubric Item | Evidence in This Submission |
|-------------|----------------------------|
| Collects `description`, `stepsToReproduce`, `environment` across conversation | `system_prompt.txt` lines 18–32 specify collection procedure; transcript shows multi-turn collection |
| Calls `create_bug_report` only after all fields collected | Prompt explicitly forbids tool call until all three fields are present; eval confirms correct behavior |
| Relays ticket ID to customer | Prompt line 6: "After filing, respond with EXACTLY: 'Ticket filed: <ticket_id>'" |
| Record created in DynamoDB | `evidence/rubric-2-bug-report/bug-report-tool-stack-bug-reports table items.png` shows OPEN tickets |

**Evidence files:**
- `system_prompt.txt` — bug report collection rules
- `evidence/rubric-2-bug-report/Bug report (multi-turn).png` — multi-turn collection + tool call
- `evidence/rubric-2-bug-report/bug-report-tool-stack-bug-reports table items.png` — DynamoDB records
- `infrastructure/lambda/create_bug_report.py` — Lambda tool implementation

### 3. Implement Platform Question and Other Request Paths

| Rubric Item | Evidence in This Submission |
|-------------|----------------------------|
| Relevant answer when FAQ covers the question | `system_prompt.txt` embeds `online_shop_faq.md`; transcript shows accurate FAQ-grounded answer for shipping question |
| Redirects to human support when FAQ doesn't cover the question | Prompt line 11: redirect when FAQ doesn't cover the question |
| Separate path for other requests → support phone line | Prompt lines 13–19 define OTHER category with polite redirect |
| Screenshots of covered, uncovered, and other-request responses | `evidence/rubric-3-faq-other/Platform question.png`, `evidence/rubric-3-faq-other/Other request.png` |

**Evidence files:**
- `system_prompt.txt` — FAQ grounding and redirect rules
- `online_shop_faq.md` — embedded FAQ document
- `evidence/rubric-3-faq-other/faq-prompt-node.txt` — FAQ prompt node template
- `evidence/rubric-3-faq-other/Platform question.png` — covered FAQ question
- `evidence/rubric-3-faq-other/Other request.png` — other request redirect

### 4. Testing and Evaluation

| Rubric Item | Evidence in This Submission |
|-------------|----------------------------|
| Test suite covers all three routes | `harness-tests.json` — 7 tests: bug report (2), FAQ (3), other (1), ambiguous (1) |
| Eval dataset generated | `output_eval_dataset.jsonl` — 7 records; `output_bdd_eval_dataset.jsonl` — 10 BDD scenarios |
| JSONL uploaded to S3 | Uploaded to `s3://customer-support-eval-708026873259/output_eval_dataset.jsonl` |
| Bedrock Evaluation job created | `support-chatbot-eval-run-3` (ARN: `arn:aws:bedrock:us-east-1:708026873259:evaluation-job/2kl0fuuex06t`) |
| Correctness score close to 1 | **1.0 / 1.0** (7/7 tests passed) |
| Written observations | `docs/eval-observations.md` |

**Evidence files:**
- `tests/harness-tests.json` — test suite
- `tests/output_eval_dataset.jsonl` — eval dataset (7 records)
- `tests/output_bdd_eval_dataset.jsonl` — BDD-based eval dataset (10 scenarios)
- `tests/generate-bdd-eval-dataset.py` — BDD scenario generator
- `evidence/rubric-4-evaluation/final-model-evaluation-report.png` — eval results screenshot
- `evidence/rubric-4-evaluation/model-evaluation-list.png` — eval job list screenshot
- `docs/eval-observations.md` — written observations

---

## Bedrock Flow Artifacts (Rubric Compliance)

In addition to the AgentCore managed harness (the working agent), this project includes a **Bedrock Flow** (`customer-support-flow`) to satisfy rubric requirements for visual flow diagrams, condition nodes, and prompt node templates.

**Flow artifacts:**

| Rubric asks for | This project provides |
|-----------------|----------------------|
| Flow diagram | `evidence/rubric-1-routing/flow-diagram.md` + `evidence/rubric-1-routing/flow-diagram.png.png` |
| Classifier prompt configuration | `evidence/rubric-1-routing/classifier-prompt.txt` |
| Condition node expressions | `evidence/rubric-1-routing/condition-nodes.txt` |
| FAQ Prompt node template | `evidence/rubric-3-faq-other/faq-prompt-node.txt` |
| Flow test responses | `evidence/rubric-1-routing/flow-test-bug-report.txt`, `flow-test-faq.txt`, `flow-test-other.txt` |
| `flow-tests.json` | `tests/harness-tests.json` (same purpose, harness-based) |

**Flow details:**
- **Flow ID:** JA2RHHT2BG
- **Flow ARN:** arn:aws:bedrock:us-east-1:708026873259:flow/JA2RHHT2BG
- **Flow Alias:** ABAVBNIFQQ
- **Status:** Prepared
- **Nodes:** FlowInput → Classifier → RouteByCategory → BugReportHandler/FAQHandler/OtherHandler → 3 Outputs

## Why There Is No Bedrock Flow

The rubric references Bedrock Flow artifacts (flow diagram, condition node expressions, FAQ prompt node template). This project uses the **AgentCore managed harness** instead, as directed by the course instructions (Module 14). The harness accomplishes the same routing behavior through prompt engineering rather than visual node-based orchestration.

---

## File Inventory

```
customer-support-chatbot/
├── .env                                  # AWS credentials
├── system_prompt.txt                     # Main deliverable: routing + behavior prompt
├── online_shop_faq.md                    # FAQ document embedded in prompt
├── requirements.txt
├── README.md
│
├── implementation/
│   ├── harness/                          # AgentCore managed harness (working agent)
│   │   ├── agentcore_config.json
│   │   ├── create_harness.py
│   │   ├── chat.py
│   │   ├── cleanup_agentcore.py
│   │   ├── debug_tools.py
│   │   └── debug_target.py
│   │
│   └── flow/                             # Bedrock Flow (rubric compliance)
│       ├── create_flow.py
│       ├── test_flow.py
│       └── cleanup_flow.py
│
├── tests/
│   ├── harness-tests.json                # Test suite (7 tests, all 3 routes)
│   ├── harness-tests-template.json
│   ├── output_eval_dataset.jsonl         # Eval dataset (7 records)
│   ├── output_bdd_eval_dataset.jsonl     # BDD eval dataset (10 scenarios)
│   ├── eval-job-config.json
│   ├── generate-eval-dataset.py
│   ├── generate-bdd-eval-dataset.py      # BDD scenario generator
│   └── create_eval_job.py
│
├── infrastructure/
│   ├── cloudformation-tool.yaml          # DynamoDB, Lambda, IAM roles
│   ├── cloudformation-testing.yaml       # S3 bucket + eval IAM role
│   └── lambda/
│       └── create_bug_report.py          # Lambda function code
│
├── docs/
│   ├── submission-notes.md               # Rubric mapping + architecture note
│   ├── submission-checklist.md
│   └── eval-observations.md
│
└── evidence/
     ├── rubric-1-routing/                # Flow diagram, classifier, condition nodes, flow tests
     │   ├── flow-diagram.md
     │   ├── flow-diagram.png.png
     │   ├── classifier-prompt.txt
     │   ├── condition-nodes.txt
     │   ├── flow-test-bug-report.txt
     │   ├── flow-test-faq.txt
     │   └── flow-test-other.txt
     ├── rubric-2-bug-report/             # Bug report transcript + DynamoDB
     │   ├── Bug report (multi-turn).png
     │   ├── bug-report-tool-stack-bug-reports table items.png
     │   └── tables.png
     ├── rubric-3-faq-other/              # FAQ transcript + other request
     │   ├── faq-prompt-node.txt
     │   ├── Platform question.png
     │   └── Other request.png
     └── rubric-4-evaluation/             # Eval screenshots + observations
         ├── final-model-evaluation-report.png
         └── model-evaluation-list.png
```
