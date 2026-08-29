import boto3
import json
import sys
import uuid
from pathlib import Path
from dotenv import load_dotenv

root_dir = Path(__file__).parent.parent.parent.parent.parent
load_dotenv(root_dir / ".env")

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------
bedrock = boto3.client("bedrock-agentcore", region_name="us-east-1")


def load_harness_arn():
    try:
        with open("harness_arn.txt", "r") as f:
            return f.read().strip()
    except FileNotFoundError:
        print("Error: harness_arn.txt not found. Run setup.py first.")
        sys.exit(1)


def invoke_harness(harness_arn, session_id, user_message):
    """Invoke the harness and return the response."""
    try:
        response = bedrock.invoke_harness(
            harnessArn=harness_arn,
            runtimeSessionId=session_id,
            messages=[{"role": "user", "content": [{"text": user_message}]}]
        )

        full_response = []
        stream = response.get("stream", [])
        for event in stream:
            for key, value in event.items():
                if key == "contentBlockDelta":
                    delta = value.get("delta", {})
                    if "text" in delta:
                        text = delta["text"]
                        if "<thinking>" not in text and "</thinking>" not in text:
                            full_response.append(text)

        return "".join(full_response)

    except Exception as e:
        if "stream" in str(e).lower():
            print("[stream error — retry this message]")
            return None
        print(f"Error: {e}")
        return None


def main():
    harness_arn = load_harness_arn()
    session_id = str(uuid.uuid4()).replace("-", "")
    while len(session_id) < 33:
        session_id += str(uuid.uuid4()).replace("-", "")
    session_id = session_id[:43]

    print("=== Incident Report Coordinator ===")
    print(f"Session: {session_id}")
    print("Submit your incident report. The coordinator will ask follow-up questions.")
    print("Type 'quit' to exit.\n")

    while True:
        try:
            user_input = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            break

        if user_input.lower() == "quit":
            print("Goodbye!")
            break

        if not user_input:
            continue

        response = invoke_harness(harness_arn, session_id, user_input)
        if response:
            print(f"\nCoordinator: {response}\n")


if __name__ == "__main__":
    main()
