import boto3
import json
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------
bedrock = boto3.client("bedrock-runtime", region_name="us-east-1")

# ARN of the versioned prompt created in the Bedrock Prompt Management console.
# Replace this with the ARN copied from your prompt version (e.g., version 1).
PROMPT_VERSION_ARN = "<YOUR_PROMPT_VERSION_ARN>"

# ---------------------------------------------------------------------------
# Sample customer email
# ---------------------------------------------------------------------------
EMAIL = """\
Subject: Order hasn't arrived
I placed order #A4821 five days ago and it still hasn't shown up.
I need this for an event tomorrow. What is going on?
"""

POLICY_TEXT = """\
- Standard shipping: 3-5 business days
- Expedited replacement available for wrong-item cases within 30 days of purchase
- Always acknowledge the customer's specific concern before offering a solution
- Never promise same-day delivery unless an expedited option is confirmed available
- Escalate to a human agent if the customer mentions legal action"""

BRAND_VOICE = "Professional, empathetic, and solution-focused. Avoid corporate jargon."


# ---------------------------------------------------------------------------
# Invoke the stored prompt template with variable values
# ---------------------------------------------------------------------------
def respond(email: str) -> str:
    response = bedrock.invoke_model(
        modelId=PROMPT_VERSION_ARN,
        body=json.dumps({
            "promptVariables": {
                "customer_email": {"text": email},
                "policy": {"text": POLICY_TEXT},
                "brand_voice": {"text": BRAND_VOICE},
            }
        }),
        contentType="application/json",
        accept="application/json",
    )
    result = json.loads(response["body"].read())
    return result["output"]["message"]["content"][0]["text"]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print("Customer Email:")
    print(EMAIL.strip())
    print("---------------------------------------------")
    print("\nGenerated response:\n\n")
    print(respond(EMAIL))
