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
        response = bedrock.invoke_agent_runtime(
            agentRuntimeId=config["harness_id"],
            sessionId=session_id,
            messages=[{"role": "user", "content": user_message}]
        )

        full_response = []
        tool_calls = []

        for event in response.get("events", []):
            if "chunk" in event:
                chunk = event["chunk"]
                if "bytes" in chunk:
                    text = chunk["bytes"].decode("utf-8")
                    full_response.append(text)

                    if debug:
                        print(f"[DEBUG] Raw chunk: {text}")

            elif "toolCall" in event:
                tool_call = event["toolCall"]
                tool_name = tool_call.get("name", "unknown")
                tool_args = tool_call.get("arguments", {})
                tool_calls.append({"name": tool_name, "arguments": tool_args})
                print(f"-> tool call: {tool_name}({json.dumps(tool_args)})")

            elif "toolResult" in event:
                tool_result = event["toolResult"]
                tool_name = tool_result.get("name", "unknown")
                result = tool_result.get("result", {})
                print(f"<- result ({tool_name}): {json.dumps(result)[:200]}...")

        final_text = "".join(full_response)
        print(f"\nAssistant: {final_text}")

        return {
            "session_id": session_id,
            "response": final_text,
            "tool_calls": tool_calls
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
