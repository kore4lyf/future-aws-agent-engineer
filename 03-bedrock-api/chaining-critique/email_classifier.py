import boto3
import json
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------
bedrock = boto3.client("bedrock-runtime", region_name="us-east-1")

MODEL_ID = "amazon.nova-pro-v1:0"

# ---------------------------------------------------------------------------
# Flow
# ---------------------------------------------------------------------------
#
#  ┌─────────────────────────────────────┐
#  │           Customer Email            │────────────┐
#  └──────────────────┬──────────────────┘            │
#                     │                               │ email
#                     ▼                               │
#  ┌─────────────────────────────────────┐            │
#  │             LLM Call 1:             │            │
#  │           Classify Email            │            │
#  └──────────────────┬──────────────────┘            │
#                     │                               │
#       COMPLAINT | QUESTION | REFUND                 │
#                     │                               │
#                     ▼                               │
#  ┌─────────────────────────────────────┐            │
#  │             LLM Call 2:             │            │
#  │          Generate Response          │◄───────────┘
#  └──────────────────┬──────────────────┘
#                     │
#                     ▼
#  ┌─────────────────────────────────────┐
#  │           Final Response            │
#  └─────────────────────────────────────┘
#
# ---------------------------------------------------------------------------
# Sample customer emails
# ---------------------------------------------------------------------------
EMAILS = [
    """\
Hi, I placed an order three weeks ago and it still hasn't arrived.
I've tried tracking it but the link just shows 'in transit' with no updates.
This is really frustrating — I needed it for an event last weekend.
Can someone please look into this?
""",
    """\
Hello, I'm interested in your annual subscription plan.
Does it include access to all features, or are some still behind an upgrade?
Also, can I switch from monthly to annual mid-cycle?
""",
    """\
I returned the headphones two weeks ago as instructed and still haven't
received my refund. The return was confirmed by your warehouse on the 3rd.
My order number is #48821. Please process this as soon as possible.
""",
]

# ---------------------------------------------------------------------------
# Response prompts, one per category
# ---------------------------------------------------------------------------
RESPONSE_PROMPTS = {
    "COMPLAINT": """\
You are a customer support agent. Write an empathetic, professional response
to the following customer complaint. Acknowledge the frustration, apologise,
and promise to investigate within 24 hours.

Customer email:
{email}
""",
    "QUESTION": """\
You are a helpful customer support agent. Write a clear, friendly response
to the following customer question. Be concise and answer each question directly.

Customer email:
{email}
""",
    "REFUND": """\
You are a customer support agent handling refunds. Write a professional response
to the following refund request. Confirm you have located the return, provide
a clear timeline for the refund, and apologise for the delay.

Customer email:
{email}
""",
}

# ---------------------------------------------------------------------------
# Helper: single InvokeModel call
# ---------------------------------------------------------------------------
def invoke(prompt: str, temperature: float = 0.0) -> str:
    body = {
        "messages": [{"role": "user", "content": [{"text": prompt}]}],
        "inferenceConfig": {"maxTokens": 512, "temperature": temperature},
    }

    response = bedrock.invoke_model(
        modelId=MODEL_ID,
        body=json.dumps(body),
        contentType="application/json",
        accept="application/json",
    )

    result = json.loads(response["body"].read())
    return result["output"]["message"]["content"][0]["text"]


# ---------------------------------------------------------------------------
# Call 1 – Classify the email
# ---------------------------------------------------------------------------
def classify_email(email: str) -> str:
    prompt = f"""\
Classify the following customer email into exactly one of these categories:
COMPLAINT, QUESTION, REFUND

Respond with only the category name, nothing else.

Email:
{email}
"""
    return invoke(prompt).strip().upper()


# ---------------------------------------------------------------------------
# Call 2 – Generate a response using the category-specific prompt
# ---------------------------------------------------------------------------
def respond_to_email(email: str, category: str) -> str:
    template = RESPONSE_PROMPTS.get(category, RESPONSE_PROMPTS["COMPLAINT"])
    prompt = template.format(email=email)
    return invoke(prompt, temperature=0.7)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    for i, email in enumerate(EMAILS, start=1):
        print(f"=== Email {i} ===\n")
        print(email)

        category = classify_email(email)
        print(f"Category: {category}\n")

        response = respond_to_email(email, category)
        print(f"Response:\n{response}")
        print("\n" + "-" * 60 + "\n")
