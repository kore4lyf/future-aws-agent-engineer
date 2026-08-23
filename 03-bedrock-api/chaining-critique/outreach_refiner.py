import boto3
import json
import re
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------
bedrock = boto3.client("bedrock-runtime", region_name="us-east-1")

MODEL_ID = "amazon.nova-pro-v1:0"

QUALITY_THRESHOLD = 8
MAX_ATTEMPTS = 5

# ---------------------------------------------------------------------------
# Flow
# ---------------------------------------------------------------------------
#
#  ┌──────────────────┐
#  │  Outreach        │
#  │  Context         │
#  └────────┬─────────┘
#           │
#           ▼
#  ┌──────────────────┐
#  │  LLM Call 1:     │
#  │  Draft Email     │
#  └────────┬─────────┘
#           │
#           ▼
#  ┌──────────────────┐
#  │  LLM Call 2:     │
#  │  Critique &      │ ◄──────────────────────────┐
#  │  Score Email     │                            │
#  └────────┬─────────┘                            │
#           │                                      │
#     score >= threshold?                          │
#      ┌────┴─────┐                                │
#     Yes         No                               │
#      │          │                                │
#      ▼          ▼                                │
#    Done  ┌──────────────────┐                    │
#          │  LLM Call 3:     │                    │
#          │  Refine Email    │                    │
#          └────────┬─────────┘                    │
#                   └──────────────────────────────┘
#                        (up to MAX_ATTEMPTS times)
#
# ---------------------------------------------------------------------------
# Outreach context
# ---------------------------------------------------------------------------
OUTREACH_CONTEXT = """\
Sender: organiser of a local AWS community meetup
Recipient: a senior engineering manager at a fintech startup
Goal: invite them to give a 20-minute talk about their experience
      migrating backend services to serverless on AWS
"""


# ---------------------------------------------------------------------------
# Helper: single InvokeModel call
# ---------------------------------------------------------------------------
def invoke(prompt: str, temperature: float = 0.7) -> str:
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
# Step 1 – Draft the email
# ---------------------------------------------------------------------------
def draft_email(context: str) -> str:
    prompt = f"""\
Write a professional cold outreach email for the following scenario:

{context}
Include a subject line, greeting, body (2-3 short paragraphs), and sign-off.
"""
    return invoke(prompt)


# ---------------------------------------------------------------------------
# Step 2 – Critique and score the email
# ---------------------------------------------------------------------------
def critique_email(email: str) -> tuple[int, str]:
    prompt = f"""\
You are an expert in professional communication.
Critique the cold outreach email below.

Evaluate it on: tone, clarity, and persuasiveness.
Your response MUST start with exactly this line:
SCORE: X/10

Then list up to 3 specific improvements as bullet points.
Do NOT rewrite the email.

Email:
{email}
"""
    response = invoke(prompt, temperature=0.0)

    match = re.search(r"SCORE:\s*(\d+)", response)
    score = int(match.group(1)) if match else 0
    return score, response


# ---------------------------------------------------------------------------
# Step 3 – Refine the email based on the critique
# ---------------------------------------------------------------------------
def refine_email(email: str, critique: str) -> str:
    prompt = f"""\
Rewrite the email below to address the critique provided.
Output only the improved email — no explanation.

Original email:
{email}

Critique:
{critique}
"""
    return invoke(prompt)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    email = draft_email(OUTREACH_CONTEXT)

    for attempt in range(1, MAX_ATTEMPTS + 1):
        print(f"=== Attempt {attempt} ===\n")
        print(email)

        score, critique = critique_email(email)
        print(f"\nScore: {score}/10")

        if score >= QUALITY_THRESHOLD:
            print("\nQuality threshold met. Done.")
            break

        print(f"\nCritique:\n{critique}")
        print("\n" + "-" * 60 + "\n")
        email = refine_email(email, critique)
    else:
        print(f"\nReached maximum of {MAX_ATTEMPTS} attempts.")
