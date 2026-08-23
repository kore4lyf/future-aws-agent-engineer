import boto3
import json
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------
bedrock = boto3.client("bedrock-runtime", region_name="us-east-1")

# TODO: Fill in after completing the console steps in the README.
PROMPT_VERSION_ARN = "<YOUR_PROMPT_VERSION_ARN>"

OUTPUT_FILE = "eval_responses.jsonl"

# ---------------------------------------------------------------------------
# Product FAQ (provided)
# ---------------------------------------------------------------------------
PRODUCT_FAQ = """\
Product FAQ

Pricing:
- Individual plan: $29 per month
- Team plan: $99 per month (up to 10 users)
- Enterprise: contact sales for custom pricing

Free Trial:
- 14-day free trial available for all plans
- No credit card required to start

Features:
- Task management with priority levels and due dates
- Time tracking built into each task
- Gantt chart view for project timelines
- Integrations: Slack and Google Workspace only

Storage:
- Individual plan: 10 GB per user
- Team plan: 100 GB shared across the team

Supported Platforms:
- Web browsers (Chrome, Firefox, Safari, Edge)
- iOS and Android mobile apps

Security:
- SOC 2 Type II certified
- All data encrypted at rest and in transit

Support:
- Email support for all plans
- Live chat support for Team and Enterprise plans only\
"""

# ---------------------------------------------------------------------------
# Eval dataset – answerable and unanswerable questions
# ---------------------------------------------------------------------------
EVAL_QUESTIONS = [
    # Answerable questions (answers in FAQ)
    {
        "prompt": "What is the price of the team plan?",
        "referenceResponse": "The team plan is $99 per month for up to 10 users.",
    },
    {
        "prompt": "How long is the free trial?",
        "referenceResponse": "The free trial is 14 days and no credit card is required to start.",
    },
    {
        "prompt": "What integrations do you support?",
        "referenceResponse": "We support integrations with Slack and Google Workspace only.",
    },
    {
        "prompt": "How much storage do I get with the individual plan?",
        "referenceResponse": "The individual plan includes 10 GB of storage per user.",
    },
    {
        "prompt": "Is the platform SOC 2 certified?",
        "referenceResponse": "Yes, we are SOC 2 Type II certified and all data is encrypted at rest and in transit.",
    },
    # Unanswerable questions (not in FAQ)
    {
        "prompt": "Do you offer a discount for nonprofits?",
        "referenceResponse": "I'm sorry, but I don't have information about nonprofit discounts in my FAQ. Please contact our sales team for custom pricing options.",
    },
    {
        "prompt": "Can I integrate with Jira or Trello?",
        "referenceResponse": "I'm sorry, but I don't have information about Jira or Trello integrations. Our current integrations are limited to Slack and Google Workspace.",
    },
]


# ---------------------------------------------------------------------------
# Invoke the stored prompt template
# ---------------------------------------------------------------------------
def invoke(question: str) -> str:
    response = bedrock.invoke_model(
        modelId=PROMPT_VERSION_ARN,
        body=json.dumps({
            "promptVariables": {
                "faq":               {"text": PRODUCT_FAQ},
                "customer_question": {"text": question},
            }
        }),
        contentType="application/json",
        accept="application/json",
    )
    result = json.loads(response["body"].read())
    return result["output"]["message"]["content"][0]["text"]


# ---------------------------------------------------------------------------
# Main – run eval and write results
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    records = []

    print("Running FAQ Assistant Eval\n")
    print("=" * 60)

    for item in EVAL_QUESTIONS:
        question = item["prompt"]
        reference = item["referenceResponse"]
        response = invoke(question)

        print(f"Question:  {question}")
        print(f"Expected:  {reference}")
        print(f"Response:  {response}")
        print("-" * 60)

        records.append({
            "prompt": question,
            "referenceResponse": reference,
            "modelResponses": [
                {
                    "response": response,
                    "modelIdentifier": "faq-assistant",
                }
            ],
        })

    with open(OUTPUT_FILE, "w") as f:
        for record in records:
            f.write(json.dumps(record) + "\n")

    print(f"\nWrote {len(records)} records to {OUTPUT_FILE}")
