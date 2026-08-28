from dotenv import load_dotenv
import os
from pathlib import Path

# Load from root .env (one level up from this folder)
root_dir = Path(__file__).parent.parent
load_dotenv(root_dir / ".env")

import boto3
import json
import sys
import uuid

def load_config():
    with open("demo_config.json", "r") as f:
        return json.load(f)

def chat(user_message, session_id=None, debug=False):
    config = load_config()

    bedrock = boto3.client("bedrock-agentcore", region_name=config["region"])

    if session_id is None:
        session_id = str(uuid.uuid4()).replace("-", "")[:43]
        while len(session_id) < 33:
            session_id += str(uuid.uuid4()).replace("-", "")[:10]
        session_id = session_id[:43]

    print(f"\nSession: {session_id}")
    print(f"User: {user_message}\n")

    try:
        response = bedrock.invoke_harness(
            harnessArn=config["harness_arn"],
            runtimeSessionId=session_id,
            messages=[{"role": "user", "content": [{"text": user_message}]}]
        )

        # AgentCore returns an event stream under the "stream" key (botocore EventStream).
        # Event names: messageStart, contentBlockDelta, contentBlockStop, messageStop,
        # toolUse, toolResult, etc. We print deltas as they arrive and also collect
        # the full assistant text and any tool calls/results.
        full_response = []
        tool_calls = []

        stream = response["stream"]
        for event in stream:
            if debug:
                print(f"[DEBUG] event keys: {list(event.keys())}")
            for key, value in event.items():
                # Converse-style streaming deltas
                if key == "messageStart":
                    pass
                elif key == "contentBlockStart":
                    tool_use = value.get("start", {}).get("toolUse")
                    if tool_use:
                        tool_calls.append({
                            "name": tool_use.get("name"),
                            "arguments": "",
                            "id": tool_use.get("toolUseId"),
                        })
                elif key == "contentBlockDelta":
                    delta = value.get("delta", {})
                    if "text" in delta:
                        text = delta["text"]
                        full_response.append(text)
                        print(text, end="", flush=True)
                    if "toolUse" in delta:
                        # incremental arguments as a JSON string chunk
                        chunk = delta["toolUse"].get("input", "")
                        if tool_calls and "arguments" in tool_calls[-1]:
                            tool_calls[-1]["arguments"] += chunk
                elif key == "contentBlockStop":
                    pass
                elif key == "messageStop":
                    if tool_calls:
                        for tc in tool_calls:
                            print(f"\n-> tool call: {tc['name']}({tc.get('arguments','')})")
                    pass
                elif key == "metadata":
                    if debug:
                        print(f"[DEBUG] metadata: {json.dumps(value, default=str)[:200]}")

        print()  # newline after streamed text
        final_text = "".join(full_response)

        # Try to pretty-print final tool call args now that we have full JSON
        for tc in tool_calls:
            try:
                tc["arguments"] = json.loads(tc["arguments"]) if isinstance(tc["arguments"], str) else tc["arguments"]
            except Exception:
                pass

        return {
            "session_id": session_id,
            "response": final_text,
            "tool_calls": tool_calls,
        }

    except Exception as e:
        print(f"Error: {e}")
        return None

def interactive_mode(debug=False):
    config = load_config()
    session_id = str(uuid.uuid4()).replace("-", "")[:43]
    while len(session_id) < 33:
        session_id += str(uuid.uuid4()).replace("-", "")[:10]
    session_id = session_id[:43]

    print("=== Helpful Home AI Travel Assistant ===")
    print(f"Session: {session_id}")
    print("Type 'quit' to exit, 'debug' to toggle debug mode\n")

    while True:
        try:
            user_input = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            break

        if user_input.lower() == "quit":
            print("Goodbye!")
            break
        elif user_input.lower() == "debug":
            debug = not debug
            print(f"Debug mode: {'ON' if debug else 'OFF'}")
            continue
        elif not user_input:
            continue

        chat(user_input, session_id, debug)
        print()

def main():
    debug = "--debug" in sys.argv
    args = [a for a in sys.argv[1:] if not a.startswith("--")]

    if args:
        message = " ".join(args)
        chat(message, debug=debug)
    else:
        interactive_mode(debug)

if __name__ == "__main__":
    main()
