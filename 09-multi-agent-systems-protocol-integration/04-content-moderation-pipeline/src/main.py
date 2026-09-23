import json
import os

from dotenv import load_dotenv
from strands import Agent, tool
from strands.models import BedrockModel

load_dotenv()

AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
NOVA_LITE_MODEL = os.environ.get("NOVA_LITE_MODEL", "amazon.nova-lite-v1:0")
CLAUDE_MODEL = os.environ.get(
    "CLAUDE_MODEL", "us.anthropic.claude-sonnet-4-5-20250929-v1:0"
)
NOVA_PRO_MODEL = os.environ.get("NOVA_PRO_MODEL", "amazon.nova-pro-v1:0")

POSTS = [
    {
        "id": "POST-001",
        "text": "Here is my favorite pasta recipe with fresh tomatoes, basil, and garlic.",
    },
    {
        "id": "POST-002",
        "text": "A sunset photo from my walk along the river this evening.",
    },
    {
        "id": "POST-003",
        "text": "My book review: the mystery was clever, the pacing was strong, and the ending surprised me.",
    },
    {
        "id": "POST-004",
        "text": "We should destroy the people who disagree with us; they are subhuman and should suffer.",
    },
    {
        "id": "POST-005",
        "text": "Send me your bank password and I will double your money today. This investment opportunity is a scam.",
    },
    {
        "id": "POST-006",
        "text": "People from that group are subhuman. They do not deserve to live here.",
    },
    {
        "id": "POST-007",
        "text": "The support team are idiots and their service is terrible. I am furious about this ban from the forum.",
    },
    {
        "id": "POST-008",
        "text": "Skip your medication and use this supplement instead. Doctors do not want you to know this cure.",
    },
    {
        "id": "POST-009",
        "text": "That movie was so boring I want to gag my eyes out. The plot and acting were terrible.",
    },
]

HARMFUL_KEYWORDS = [
    "destroy",
    "suffers",
    "subhuman",
    "scam",
]
BORDERLINE_KEYWORDS = [
    "idiots",
    "terrible",
    "ban from",
    "medication",
    "supplement",
    "gag",
]

DEEP_REVIEW_VERDICTS = {
    "POST-007": {
        "verdict": "safe",
        "reason": "Frustration and mild insults do not constitute a policy violation.",
    },
    "POST-008": {
        "verdict": "harmful",
        "reason": "The post promotes dangerous medical misinformation.",
    },
    "POST-009": {
        "verdict": "safe",
        "reason": "The phrase is figurative movie-review language, not a literal threat.",
    },
}

NOTICE_TEMPLATES = {
    "harmful": "Your post was removed because it violates our community guidelines. Please review our policies before posting again.",
}

screening_cache = {}
review_cache = {}
notice_cache = {}


def build_screening_agent() -> Agent:
    model = BedrockModel(
        model_id=NOVA_LITE_MODEL,
        region_name=AWS_REGION,
        temperature=0.0,
    )

    @tool
    def screen_post(post_id: str) -> str:
        post = next(item for item in POSTS if item["id"] == post_id)
        text = post["text"].lower()

        if any(keyword in text for keyword in HARMFUL_KEYWORDS):
            result = {
                "classification": "harmful",
                "confidence": "HIGH",
            }
        elif any(keyword in text for keyword in BORDERLINE_KEYWORDS):
            result = {
                "classification": "borderline",
                "confidence": "MEDIUM",
            }
        else:
            result = {
                "classification": "safe",
                "confidence": "HIGH",
            }

        screening_cache[post_id] = result
        return json.dumps(result, indent=2)

    system_prompt = """You are a content screening agent. Your ONLY job:
1. Call screen_post with the post_id
2. Report the classification in exactly 2 lines:
   Classification: <SAFE|HARMFUL|BORDERLINE>
   Confidence: <HIGH|MEDIUM|LOW>"""

    return Agent(model=model, system_prompt=system_prompt, tools=[screen_post])


def build_review_agent() -> Agent:
    model = BedrockModel(
        model_id=CLAUDE_MODEL,
        region_name=AWS_REGION,
        temperature=0.1,
    )

    @tool
    def deep_review_post(post_id: str) -> str:
        result = DEEP_REVIEW_VERDICTS[post_id]
        review_cache[post_id] = result
        return json.dumps(result, indent=2)

    system_prompt = """You are a deep content review agent. Your ONLY job:
1. Call deep_review_post with the post_id
2. Report the final verdict and one-sentence reason in exactly 2 lines:
   Verdict: <SAFE|HARMFUL>
   Reason: <one sentence>"""

    return Agent(model=model, system_prompt=system_prompt, tools=[deep_review_post])


def build_notice_agent() -> Agent:
    model = BedrockModel(
        model_id=NOVA_PRO_MODEL,
        region_name=AWS_REGION,
        temperature=0.3,
    )

    @tool
    def draft_notice(post_id: str, violation_type: str) -> str:
        result = {
            "post_id": post_id,
            "message": NOTICE_TEMPLATES[violation_type],
        }
        notice_cache[post_id] = result
        return json.dumps(result, indent=2)

    system_prompt = """You are a moderation notice agent. Your ONLY job:
1. Call draft_notice with the post_id and violation_type
2. Return the final user-facing moderation message.
Use a clear, calm, and respectful tone."""

    return Agent(model=model, system_prompt=system_prompt, tools=[draft_notice])


def run_moderation_pipeline(post: dict) -> dict:
    post_id = post["id"]

    build_screening_agent()(f"Screen post {post_id}")
    classification = screening_cache.get(post_id, {}).get("classification", "safe")
    final_verdict = classification

    if classification == "borderline":
        build_review_agent()(f"Deep review post {post_id}")
        final_verdict = review_cache.get(post_id, {}).get("verdict", "safe")

    if final_verdict == "harmful":
        build_notice_agent()(
            f"Generate moderation notice for post {post_id}. Violation type is harmful."
        )

    return {
        "post_id": post_id,
        "classification": classification,
        "final_verdict": final_verdict,
        "review": review_cache.get(post_id),
        "notice": notice_cache.get(post_id),
    }


def main() -> None:
    for post in POSTS:
        print(json.dumps(run_moderation_pipeline(post), indent=2))


if __name__ == "__main__":
    main()
