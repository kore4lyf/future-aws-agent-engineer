# Bedrock API - Meeting Notes Summarizer

A simple script demonstrating the Amazon Bedrock API using `invoke_model` to summarize meeting notes.

## What It Does

Takes informal meeting notes and produces:
1. Key decisions made
2. Action items with owners

## How It Works

1. Takes meeting notes as input
2. Sends them to Amazon Nova Pro via Bedrock's `invoke_model` API
3. Returns a structured summary

## Files

| File | Purpose |
|------|---------|
| `invoke-api/summarize_meetings.py` | InvokeModel (non-streaming) |
| `invoke-api/summarize_meetings_stream.py` | InvokeModelWithResponseStream (streaming) |
| `converse-api/travel_assistant.py` | Converse API (multi-turn chat) |
| `converse-api/restaurant_booking.py` | Converse API with tool use |
| `chaining-critique/email_classifier.py` | Classifier-then-specialist chain |
| `chaining-critique/outreach_refiner.py` | Critique-and-refine loop |
| `travel-planner/travel_planner.py` | Converse API with tools (exercise) |
| `prompt-refinement/demo-1-prompt-template/prompt_template.md` | Prompt template with variables |
| `prompt-refinement/demo-1-prompt-template/email_support.py` | Bedrock Prompt Management API |
| `prompt-refinement/demo-2-guardrails/guardrail_config.md` | Guardrail configuration |
| `prompt-refinement/demo-2-guardrails/guardrail_demo.py` | Bedrock Guardrails API |
| `prompt-refinement/demo-3-evals/eval_documentation.md` | Eval metrics documentation |
| `prompt-refinement/demo-3-evals/eval_runner.py` | Bedrock Evaluations API |
| `prompt-refinement/faq-assistant-eval/faq_assistant.py` | FAQ Assistant eval script |
| `prompt-refinement/faq-assistant-eval/template.yaml` | S3 bucket for eval results |
| `requirements.txt` | Dependencies |

## Usage

```bash
cd future-aws-agent-engineer/bedrock-api
pip install -r requirements.txt

# InvokeModel (non-streaming)
python invoke-api/summarize_meetings.py

# InvokeModelWithResponseStream (streaming)
python invoke-api/summarize_meetings_stream.py

# Converse API (multi-turn chat)
python converse-api/travel_assistant.py

# Converse API with tool use (restaurant booking)
python converse-api/restaurant_booking.py

# Chaining: classifier-then-specialist
python chaining-critique/email_classifier.py

# Chaining: critique-and-refine loop
python chaining-critique/outreach_refiner.py

# Exercise: Travel Planner with Tools
python travel-planner/travel_planner.py

# Prompt Refinement: Bedrock Prompt Management
python prompt-refinement/demo-1-prompt-template/email_support.py

# Prompt Refinement: Bedrock Guardrails
python prompt-refinement/demo-2-guardrails/guardrail_demo.py

# Prompt Refinement: Bedrock Evaluations
python prompt-refinement/demo-3-evals/eval_runner.py

# Exercise: FAQ Assistant with Evaluation
python prompt-refinement/faq-assistant-eval/faq_assistant.py
```

## API Calls

**Non-streaming (`invoke_model`):**
```python
response = bedrock.invoke_model(
    modelId="amazon.nova-pro-v1:0",
    body=json.dumps(body),
    contentType="application/json",
    accept="application/json",
)
result = json.loads(response["body"].read())
```

**Streaming (`invoke_model_with_response_stream`):**
```python
response = bedrock.invoke_model_with_response_stream(
    modelId="amazon.nova-pro-v1:0",
    body=json.dumps(body),
    contentType="application/json",
    accept="application/json",
)

for event in response["body"]:
    chunk = json.loads(event["chunk"]["bytes"])
    if "contentBlockDelta" in chunk:
        print(chunk["contentBlockDelta"]["delta"].get("text", ""), end="", flush=True)
```

## Key Points

- **Model:** Amazon Nova Pro (`amazon.nova-pro-v1:0`)
- **APIs:** `invoke_model` (simple) vs `invoke_model_with_response_stream` (streaming)
- **Temperature:** 0.0 (deterministic output)
- **Max tokens:** 512 (enough for summary)
