import boto3
import json
import re
import sys
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

    print("=== Customer Support Chatbot ===")
    print(f"Session: {session_id}")
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
            print(f"\nAssistant: {response}\n")


if __name__ == "__main__":
    main()
