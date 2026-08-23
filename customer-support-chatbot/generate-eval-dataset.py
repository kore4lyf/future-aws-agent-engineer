import boto3
import json
import uuid
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------
bedrock = boto3.client("bedrock-agentcore", region_name="us-east-1")


def load_harness_arn():
    try:
        with open("agentcore_config.json", "r") as f:
            config = json.load(f)
            return config.get("harness_arn")
    except FileNotFoundError:
        print("Error: agentcore_config.json not found. Run create_harness.py first.")
        return None


def load_test_suite():
    try:
        with open("harness-tests-template.json", "r") as f:
            return json.load(f)
    except FileNotFoundError:
        print("Error: harness-tests-template.json not found.")
        return None


def invoke_harness(harness_arn, session_id, user_message):
    """Invoke the harness and return the response."""
    try:
        response = bedrock.invoke_agent_runtime(
            agentRuntimeArn=harness_arn,
            sessionId=session_id,
            messages=[{"role": "user", "content": user_message}]
        )

        full_response = []
        for event in response.get("events", []):
            if "chunk" in event:
                chunk = event["chunk"]
                if "bytes" in chunk:
                    text = chunk["bytes"].decode("utf-8")
                    # Hide thinking tags
                    if "<thinking>" not in text and "</thinking>" not in text:
                        full_response.append(text)

        return "".join(full_response)

    except Exception as e:
        print(f"Error: {e}")
        return None


def run_test(harness_arn, test):
    """Run a single test and return the results."""
    session_id = str(uuid.uuid4()).replace("-", "")
    while len(session_id) < 33:
        session_id += str(uuid.uuid4()).replace("-", "")
    session_id = session_id[:43]

    print(f"\n{'=' * 60}")
    print(f"Test: {test['name']}")
    print(f"Category: {test['category']}")
    print(f"{'=' * 60}")

    conversation = []
    for turn in test["turns"]:
        user_message = turn["user"]
        print(f"\nUser: {user_message}")

        response = invoke_harness(harness_arn, session_id, user_message)
        if response:
            print(f"Assistant: {response}")
            conversation.append({"user": user_message, "assistant": response})

    return {
        "test_name": test["name"],
        "category": test["category"],
        "conversation": conversation,
        "expected_tool_call": test.get("expected_tool_call"),
        "reference_response": test.get("reference_response")
    }


def main():
    print("=== Generate Evaluation Dataset ===\n")

    harness_arn = load_harness_arn()
    if not harness_arn:
        return

    test_suite = load_test_suite()
    if not test_suite:
        return

    print(f"Loaded {len(test_suite['tests'])} tests\n")

    results = []
    for test in test_suite["tests"]:
        result = run_test(harness_arn, test)
        results.append(result)

    # Write JSONL file
    output_file = "eval_responses.jsonl"
    with open(output_file, "w") as f:
        for result in results:
            record = {
                "prompt": result["conversation"][0]["user"] if result["conversation"] else "",
                "referenceResponse": result["reference_response"],
                "modelResponses": [
                    {
                        "response": result["conversation"][-1]["assistant"] if result["conversation"] else "",
                        "modelIdentifier": "customer-support-chatbot"
                    }
                ]
            }
            f.write(json.dumps(record) + "\n")

    print(f"\nWrote {len(results)} records to {output_file}")
    print("\nNext steps:")
    print("1. Deploy testing stack: aws cloudformation deploy --template-file cloudformation-testing.yaml --stack-name customer-support-eval --capabilities CAPABILITY_NAMED_IAM --region us-east-1")
    print("2. Upload to S3: aws s3 cp eval_responses.jsonl s3://<bucket-name>/eval_responses.jsonl")
    print("3. Run Bedrock Evaluation job")


if __name__ == "__main__":
    main()
