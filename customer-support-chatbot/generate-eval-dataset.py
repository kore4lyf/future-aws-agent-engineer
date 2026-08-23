import boto3
import json
import re
import uuid
import argparse
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


def invoke_harness(harness_arn, session_id, user_message):
    """Invoke the harness and return the response."""
    try:
        response = bedrock.invoke_harness(
            harnessArn=harness_arn,
            runtimeSessionId=session_id,
            messages=[{"role": "user", "content": [{"text": user_message}]}]
        )

        full_response = []
        for event in response.get("stream", []):
            if "contentBlockDelta" in event:
                delta = event["contentBlockDelta"].get("delta", {})
                if "text" in delta:
                    full_response.append(delta["text"])

        # Join and remove thinking tags
        text = "".join(full_response)
        text = re.sub(r'<thinking>.*?</thinking>', '', text, flags=re.DOTALL)
        return text.strip()

    except Exception as e:
        print(f"Error: {e}")
        return f"[HARNESS_ERROR] {e}"


def run_test(harness_arn, test):
    """Run a single test and return the results."""
    session_id = str(uuid.uuid4()).replace("-", "")
    while len(session_id) < 33:
        session_id += str(uuid.uuid4()).replace("-", "")
    session_id = session_id[:43]

    test_id = test["id"]
    prompt = test["prompt"]
    expected = test["expected"]

    print(f"\n{'=' * 60}")
    print(f"Test: {test_id}")
    print(f"Prompt: {prompt}")
    print(f"{'=' * 60}")

    response = invoke_harness(harness_arn, session_id, prompt)
    print(f"Response: {response}")

    return {
        "prompt": prompt,
        "referenceResponse": expected,
        "modelResponses": [
            {
                "response": response,
                "modelIdentifier": "my-support-chatbot"
            }
        ]
    }


def main():
    parser = argparse.ArgumentParser(description="Generate evaluation dataset from harness tests")
    parser.add_argument("--tests-json", default="flow-tests.json", help="Path to tests JSON file (default: flow-tests.json)")
    args = parser.parse_args()

    print("=== Generate Evaluation Dataset ===\n")

    harness_arn = load_harness_arn()
    if not harness_arn:
        return

    try:
        with open(args.tests_json, "r") as f:
            test_suite = json.load(f)
    except FileNotFoundError:
        print(f"Error: {args.tests_json} not found.")
        print("Copy flow-tests-template.json to flow-tests.json and add your test cases.")
        return

    tests = test_suite.get("tests", [])
    print(f"Loaded {len(tests)} tests from {args.tests_json}\n")

    results = []
    for test in tests:
        result = run_test(harness_arn, test)
        results.append(result)

    output_file = "output_eval_dataset.jsonl"
    with open(output_file, "w") as f:
        for result in results:
            f.write(json.dumps(result) + "\n")

    print(f"\nWrote {len(results)} records to {output_file}")
    print("\nNext steps:")
    print("1. Deploy testing stack: aws cloudformation deploy --template-file cloudformation-testing.yaml --stack-name bug-report-testing-stack --capabilities CAPABILITY_NAMED_IAM --region us-east-1")
    print("2. Get stack outputs: aws cloudformation describe-stacks --stack-name bug-report-testing-stack --query 'Stacks[0].Outputs' --output table --region us-east-1")
    print("3. Upload to S3: aws s3 cp output_eval_dataset.jsonl s3://<EvalDatasetBucketName>/output_eval_dataset.jsonl --region us-east-1")
    print("4. Run Bedrock Evaluation job")


if __name__ == "__main__":
    main()
