import boto3
import json
import re
import uuid
import argparse
from pathlib import Path
from dotenv import load_dotenv

root_dir = Path(__file__).parent.parent
harness_dir = root_dir / "implementation" / "harness"
load_dotenv(root_dir / ".env")

bedrock = boto3.client("bedrock-agentcore", region_name="us-east-1")


def load_harness_arn():
    try:
        with open(harness_dir / "agentcore_config.json", "r") as f:
            config = json.load(f)
            return config.get("harness_arn")
    except FileNotFoundError:
        print("Error: agentcore_config.json not found. Run create_harness.py first.")
        return None


def invoke_harness(harness_arn, session_id, user_message):
    """Invoke the harness and return the response."""
    try:
        response = bedrock.invoke_harness(
            harnessArn=harness_arn,
            runtimeSessionId=session_id,
            messages=[{"role": "user", "content": [{"text": user_message}]}]
        )

        full_response = []
        tool_calls = []

        for event in response.get("stream", []):
            if "contentBlockDelta" in event:
                delta = event["contentBlockDelta"].get("delta", {})
                if "text" in delta:
                    full_response.append(delta["text"])
            elif "contentBlockStart" in event:
                start = event["contentBlockStart"].get("start", {})
                if "toolUse" in start:
                    tool_name = start["toolUse"].get("name", "unknown")
                    tool_calls.append(tool_name)

        text = "".join(full_response)
        text = re.sub(r'<thinking>.*?</thinking>', '', text, flags=re.DOTALL)

        if tool_calls:
            text = text + "\n[tool call] " + ", ".join(tool_calls)

        return text.strip()

    except Exception as e:
        return f"[HARNESS_ERROR] {e}"


# ---------------------------------------------------------------------------
# BDD Scenarios (Given / When / Then)
# ---------------------------------------------------------------------------

BUG_REPORT_SCENARIOS = [
    {
        "scenario": "Bug report with all fields in one message",
        "given": "A customer reports a platform issue with complete details",
        "when": "The customer sends: 'Bug: login shows blank screen on Safari iOS 15. Steps: open app, tap login. Environment: iPhone 12, Safari, iOS 15.4.'",
        "then": "The chatbot files a bug report and returns a ticket ID",
        "conversation": [
            {"role": "user", "content": "Bug: login shows blank screen on Safari iOS 15. Steps: open app, tap login. Environment: iPhone 12, Safari, iOS 15.4."}
        ],
        "expected": "Files a bug report with the create_bug_report tool and returns a ticket ID"
    },
    {
        "scenario": "Bug report missing fields — multi-turn collection",
        "given": "A customer reports a crash but provides no steps or environment details",
        "when": "The customer sends: 'The checkout page crashes every time I click Pay.' then '1. Add to cart 2. Go to checkout 3. Click Pay. Chrome 120 on macOS Sonoma.'",
        "then": "The chatbot asks for environment details, then files the bug report after receiving all fields",
        "conversation": [
            {"role": "user", "content": "The checkout page crashes every time I click Pay."},
            {"role": "user", "content": "1. Add to cart 2. Go to checkout 3. Click Pay. Chrome 120 on macOS Sonoma."}
        ],
        "expected": "Files a bug report with the create_bug_report tool and returns a ticket ID"
    },
    {
        "scenario": "Bug report partial info — description only",
        "given": "A customer mentions a bug but provides only a description",
        "when": "The customer sends: 'The search results page is blank when I filter by price.'",
        "then": "The chatbot acknowledges the bug and asks for steps to reproduce",
        "conversation": [
            {"role": "user", "content": "The search results page is blank when I filter by price."}
        ],
        "expected": "Acknowledges the bug and asks for steps to reproduce or environment details"
    },
    {
        "scenario": "Bug report with environment but no steps",
        "given": "A customer provides environment details but no reproduction steps",
        "when": "The customer sends: 'The app freezes on the profile page. iPhone 14, iOS 17.2, app version 3.1.0.'",
        "then": "The chatbot asks for steps to reproduce",
        "conversation": [
            {"role": "user", "content": "The app freezes on the profile page. iPhone 14, iOS 17.2, app version 3.1.0."}
        ],
        "expected": "Acknowledges the bug and asks for steps to reproduce or environment details"
    }
]

PLATFORM_QUESTION_SCENARIOS = [
    {
        "scenario": "FAQ-covered question — shipping",
        "given": "A customer asks about shipping times",
        "when": "The customer sends: 'How long does shipping take?'",
        "then": "The chatbot answers from the FAQ: standard shipping 3-5 business days, express 1-2 business days, free shipping over $50",
        "conversation": [
            {"role": "user", "content": "How long does shipping take?"}
        ],
        "expected": "Answers from the FAQ: standard shipping 3-5 business days, express 1-2 business days, free shipping over $50"
    },
    {
        "scenario": "FAQ-covered question — returns",
        "given": "A customer asks about returning an item",
        "when": "The customer sends: 'Can I return an item I bought?'",
        "then": "The chatbot answers from the FAQ: returns accepted within 30 days, items must be unused and in original packaging, refunds in 5-7 business days",
        "conversation": [
            {"role": "user", "content": "Can I return an item I bought?"}
        ],
        "expected": "Answers from the FAQ: returns accepted within 30 days, items must be unused and in original packaging, refunds in 5-7 business days"
    },
    {
        "scenario": "FAQ-covered question — payments",
        "given": "A customer asks about payment methods",
        "when": "The customer sends: 'What payment methods do you accept?'",
        "then": "The chatbot answers from the FAQ: Visa, Mastercard, American Express, PayPal, Apple Pay",
        "conversation": [
            {"role": "user", "content": "What payment methods do you accept?"}
        ],
        "expected": "Answers from the FAQ: Visa, Mastercard, American Express, PayPal, Apple Pay"
    }
]

OTHER_REQUEST_SCENARIOS = [
    {
        "scenario": "Non-platform request — essay help",
        "given": "A customer asks for help with an essay",
        "when": "The customer sends: 'Can you help me write an essay?'",
        "then": "The chatbot politely redirects to human support for non-platform questions",
        "conversation": [
            {"role": "user", "content": "Can you help me write an essay?"}
        ],
        "expected": "Politely redirects to human support for non-platform questions"
    },
    {
        "scenario": "Non-platform request — general advice",
        "given": "A customer asks for relationship advice",
        "when": "The customer sends: 'I need advice on my relationship.'",
        "then": "The chatbot politely redirects to human support",
        "conversation": [
            {"role": "user", "content": "I need advice on my relationship."}
        ],
        "expected": "Politely redirects to human support for non-platform questions"
    }
]

AMBIGUOUS_SCENARIOS = [
    {
        "scenario": "Mixed bug report and FAQ question",
        "given": "A customer combines a bug report with a platform question",
        "when": "The customer sends: 'I can't checkout and also how do I return an item?'",
        "then": "The chatbot addresses the bug report aspect and answers the return question from the FAQ",
        "conversation": [
            {"role": "user", "content": "I can't checkout and also how do I return an item?"}
        ],
        "expected": "Addresses the bug report aspect and answers the return question from the FAQ"
    }
]


def run_conversation(harness_arn, conversation):
    """Run a multi-turn conversation and return the final response."""
    session_id = str(uuid.uuid4()).replace("-", "")
    while len(session_id) < 33:
        session_id += str(uuid.uuid4()).replace("-", "")
    session_id = session_id[:43]

    response = None
    for turn in conversation:
        response = invoke_harness(harness_arn, session_id, turn["content"])

    return response if response else ""


def run_test(harness_arn, test):
    """Run a single BDD test and return the results."""
    test_id = test.get("id", "unknown")
    scenario = test.get("scenario", "")
    given = test.get("given", "")
    when = test.get("when", "")
    then = test.get("then", "")
    conversation = test.get("conversation", [])
    expected = test.get("expected", "")

    print(f"\n{'=' * 70}")
    print(f"Scenario: {scenario}")
    print(f"Given: {given}")
    print(f"When: {when}")
    print(f"Then: {then}")
    print(f"{'=' * 70}")

    response = run_conversation(harness_arn, conversation)
    print(f"Response: {response[:200]}...")

    return {
        "prompt": conversation[-1]["content"] if conversation else "",
        "referenceResponse": expected,
        "modelResponses": [
            {
                "response": response,
                "modelIdentifier": "my-support-chatbot"
            }
        ]
    }


def main():
    parser = argparse.ArgumentParser(description="Generate BDD-based evaluation dataset")
    parser.add_argument("--category", choices=["bug", "faq", "other", "all"], default="all", help="Category to generate")
    parser.add_argument("--output", default="output_bdd_eval_dataset.jsonl", help="Output file path")
    args = parser.parse_args()

    print("=== BDD Evaluation Dataset Generator ===\n")

    harness_arn = load_harness_arn()
    if not harness_arn:
        return

    all_scenarios = []

    if args.category in ["bug", "all"]:
        for i, scenario in enumerate(BUG_REPORT_SCENARIOS, 1):
            scenario["id"] = f"bdd_bug_{i}"
            all_scenarios.append(scenario)

    if args.category in ["faq", "all"]:
        for i, scenario in enumerate(PLATFORM_QUESTION_SCENARIOS, 1):
            scenario["id"] = f"bdd_faq_{i}"
            all_scenarios.append(scenario)

    if args.category in ["other", "all"]:
        for i, scenario in enumerate(OTHER_REQUEST_SCENARIOS, 1):
            scenario["id"] = f"bdd_other_{i}"
            all_scenarios.append(scenario)

    if args.category == "all":
        for i, scenario in enumerate(AMBIGUOUS_SCENARIOS, 1):
            scenario["id"] = f"bdd_ambiguous_{i}"
            all_scenarios.append(scenario)

    print(f"Loaded {len(all_scenarios)} BDD scenarios\n")

    results = []
    for scenario in all_scenarios:
        result = run_test(harness_arn, scenario)
        results.append(result)

    output_file = root_dir / "tests" / args.output
    with open(output_file, "w") as f:
        for result in results:
            f.write(json.dumps(result) + "\n")

    print(f"\nWrote {len(results)} records to {output_file}")
    print("\nBDD Scenarios covered:")
    for s in all_scenarios:
        print(f"  - {s['id']}: {s['scenario']}")


if __name__ == "__main__":
    main()
