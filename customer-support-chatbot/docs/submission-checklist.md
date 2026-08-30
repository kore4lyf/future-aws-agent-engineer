# Submission Checklist

## Required Evidence

### 1. Routing Mechanism
- [ ] `system_prompt.txt` shows three-category classification (Bug Report / Platform Question / Other)
- [ ] Category definitions are crisp and unambiguous
- [ ] Screenshot of routing behavior (chat.py transcript)

### 2. Bug Report Path
- [ ] Chatbot collects `description`, `stepsToReproduce`, `environment` across conversation
- [ ] Chatbot calls `create_bug_report` tool only after all fields collected
- [ ] Chatbot relays ticket ID to customer
- [ ] Record created in `bug-report-tool-stack-bug-reports` DynamoDB table
- [ ] Screenshot of DynamoDB table showing ticket
- [ ] Screenshot of chat.py transcript showing tool call

### 3. Platform Question and Other Request Paths
- [ ] Platform questions answered from `{{FAQ}}` (embedded in prompt)
- [ ] Uncovered questions redirect to human support
- [ ] Other requests get polite redirect to support phone line
- [ ] Screenshots of test responses for covered question, uncovered question, other request

### 4. Testing and Evaluation
- [ ] `harness-tests.json` has tests for all three routes
- [ ] `generate-eval-dataset.py` produces `output_eval_dataset.jsonl`
- [ ] JSONL uploaded to S3
- [ ] Bedrock Evaluation job created
- [ ] Correctness score close to 1
- [ ] Screenshot of evaluation results
- [ ] Written observations on results

## Stand-Out Suggestions
- [ ] Prompt injection hardening
- [ ] Edge-case test prompts (ambiguous, short, injection)
- [ ] Multi-turn bug-report tests
- [ ] Extended FAQ entries
