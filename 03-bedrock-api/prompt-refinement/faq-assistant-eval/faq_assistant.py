import boto3
import json
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------
bedrock = boto3.client("bedrock-runtime", region_name="us-east-1")

# ARN of the versioned prompt created in the Bedrock Prompt Management console.
PROMPT_VERSION_ARN = "<YOUR_PROMPT_VERSION_ARN>"

OUTPUT_FILE = "eval_responses.jsonl"

# ---------------------------------------------------------------------------
# Product FAQ
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
# Eval dataset
# ---------------------------------------------------------------------------
EVAL_QUESTIONS = [
    # Answerable questions
    {
        "prompt": "What is the price of the team plan?",
        "referenceResponse": "The team plan is $99 per month and supports up to 10 users.",
    },
    {
        "prompt": "Does the product offer a free trial?",
        "referenceResponse": "Yes, a 14-day free trial is available for all plans with no credit card required.",
    },
    {
        "prompt": "How much storage does the individual plan include?",
        "referenceResponse": "The individual plan includes 10 GB of storage per user.",
    },
    {
        "prompt": "What integrations does the product support?",
        "referenceResponse": "The product integrates with Slack and Google Workspace only.",
    },
    # Unanswerable questions
    {
        "prompt": "Does the product integrate with Microsoft Teams?",
        "referenceResponse": "That information is not available in the FAQ. The FAQ mentions Slack and Google Workspace integrations only.",
    },
    {
        "prompt": "Is the product HIPAA compliant?",
        "referenceResponse": "That information is not available in the FAQ. The FAQ mentions SOC 2 Type II certification only.",
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
