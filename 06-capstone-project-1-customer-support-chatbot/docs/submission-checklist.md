# Submission Checklist

## Required Evidence

### 1. Routing Mechanism
- [x] `system_prompt.txt` shows three-category classification (Bug Report / Platform Question / Other)
- [x] Category definitions are crisp and unambiguous
- [x] Screenshot of routing behavior (chat.py transcript) → `screenshots/chat-transcripts/`

### 2. Bug Report Path
- [x] Chatbot collects `description`, `stepsToReproduce`, `environment` across conversation
- [x] Chatbot calls `create_bug_report` tool only after all fields collected
- [x] Chatbot relays ticket ID to customer
- [x] Record created in `bug-report-tool-stack-bug-reports` DynamoDB table
- [x] Screenshot of DynamoDB table showing ticket → `screenshots/dynamodb-tickets/`
- [x] Screenshot of chat.py transcript showing tool call → `screenshots/chat-transcripts/Bug report (multi-turn).png`

### 3. Platform Question and Other Request Paths
- [x] Platform questions answered from `{{FAQ}}` (embedded in prompt)
- [x] Uncovered questions redirect to human support
- [x] Other requests get polite redirect to support phone line
- [x] Screenshots of test responses → `screenshots/chat-transcripts/Platform question.png`, `Other request.png`

### 4. Testing and Evaluation
- [x] `harness-tests.json` has tests for all three routes
- [x] `generate-eval-dataset.py` produces `output_eval_dataset.jsonl`
- [x] JSONL uploaded to S3 (`s3://customer-support-eval-708026873259/output_eval_dataset.jsonl`)
- [x] Bedrock Evaluation job created (`support-chatbot-eval-run-3`)
- [x] Correctness score: **1.0 / 1.0**
- [x] Screenshot of evaluation results → `screenshots/model-evaluation/`
- [x] Written observations → `docs/eval-observations.md`

## Stand-Out Suggestions
- [ ] Prompt injection hardening
- [ ] Edge-case test prompts (ambiguous, short, injection)
- [ ] Multi-turn bug-report tests
- [ ] Extended FAQ entries
