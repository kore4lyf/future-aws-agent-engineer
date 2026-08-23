import boto3
import json
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------
bedrock = boto3.client("bedrock-runtime", region_name="us-east-1")
s3 = boto3.client("s3")

# ARN of the versioned prompt created in Demo 1.
PROMPT_VERSION_ARN = "<VERSION_ARN>"

OUTPUT_FILE = "eval_responses.jsonl"
S3_BUCKET   = "<YOUR_S3_BUCKET_NAME>"
S3_KEY      = "lesson-4/eval_responses.jsonl"

# ---------------------------------------------------------------------------
# Shared context – matches the values used in Demo 1
# ---------------------------------------------------------------------------
POLICY_TEXT = """\
- Standard shipping: 3-5 business days
- Expedited replacement available for wrong-item cases within 30 days of purchase
- Always acknowledge the customer's specific concern before offering a solution
- Never promise same-day delivery unless an expedited option is confirmed available
- Escalate to a human agent if the customer mentions legal action"""

BRAND_VOICE = "Professional, empathetic, and solution-focused. Avoid corporate jargon."

# ---------------------------------------------------------------------------
# Eval inputs – customer email + ideal reference response
# ---------------------------------------------------------------------------
QUESTIONS = [
    {
        "prompt": "Subject: Order hasn't arrived\nI placed order #A4821 five days ago and it still hasn't arrived. I need it for an event this weekend. What is going on?",
        "referenceResponse": "Apologize for the delay, acknowledge the urgency, commit to investigating the shipment immediately, and provide a 24-hour update timeframe.",
    },
    {
        "prompt": "Subject: Wrong item delivered\nYou sent me the wrong item. I ordered a blue jacket (size M) but received a red one in size L. This is very frustrating.",
        "referenceResponse": "Apologize for the error, confirm the correct item will be shipped at no charge, and let the customer know they may keep the incorrect one.",
    },
    {
        "prompt": "Subject: Legal action warning\nI have been waiting 10 days for my order with no updates. I am extremely upset and will be taking you to small claims court if this is not resolved immediately.",
        "referenceResponse": "Apologize sincerely, acknowledge the customer's frustration, and escalate the case to a human agent as the customer has mentioned legal action.",
    },
]


# ---------------------------------------------------------------------------
# Invoke the stored prompt template with guardrail
# ---------------------------------------------------------------------------
def invoke(email: str) -> str:
    response = bedrock.invoke_model(
        modelId=PROMPT_VERSION_ARN,
        body=json.dumps({
            "promptVariables": {
                "customer_email": {"text": email},
                "policy":         {"text": POLICY_TEXT},
                "brand_voice":    {"text": BRAND_VOICE},
            }
        }),
        contentType="application/json",
        accept="application/json",
    )
    result = json.loads(response["body"].read())
    return result["output"]["message"]["content"][0]["text"]


# ---------------------------------------------------------------------------
# Main – generate responses and write JSONL
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    records = []

    for item in QUESTIONS:
        print(f"Processing: {item['prompt'][:60]}...")
        model_response = invoke(item["prompt"])
        records.append({
            "prompt": item["prompt"],
            "referenceResponse": item["referenceResponse"],
            "modelResponses": [
                {
                    "response": model_response,
                    "modelIdentifier": "shopfast-email-agent",
                }
            ],
        })

    with open(OUTPUT_FILE, "w") as f:
        for record in records:
            f.write(json.dumps(record) + "\n")

    print(f"\nWrote {len(records)} records to {OUTPUT_FILE}")

    s3.upload_file(OUTPUT_FILE, S3_BUCKET, S3_KEY)
    print(f"Uploaded to s3://{S3_BUCKET}/{S3_KEY}")
