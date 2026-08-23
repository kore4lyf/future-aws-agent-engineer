import boto3
import json
import sys
import uuid
from dotenv import load_dotenv

load_dotenv()

def load_config():
    with open("demo_config.json", "r") as f:
        return json.load(f)

def invoke_agent(user_message, session_id=None, debug=False):
    """Invoke the restaurant recommendation agent and stream the response."""
    config = load_config()

    bedrock = boto3.client("bedrock-agentcore", region_name=config["region"])

    if session_id is None:
        session_id = str(uuid.uuid4()).replace("-", "")[:43]
        while len(session_id) < 33:
            session_id += str(uuid.uuid4()).replace("-", "")[:10]
        session_id = session_id[:43]

    print(f"\nSession: {session_id}")
    print(f"User: {user_message}\n")

    tools_called = set()
    expected_tools = {"cuisines___get_cuisines", "restaurants___search_restaurants", "availability___get_availability"}

    try:
        response = bedrock.invoke_agent_runtime(
            agentRuntimeId=config["harness_id"],
            sessionId=session_id,
            messages=[{"role": "user", "content": user_message}]
        )

        full_response = []

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
                tools_called.add(tool_name)
                print(f"[tool call] {tool_name}({json.dumps(tool_args)})")

            elif "toolResult" in event:
                tool_result = event["toolResult"]
                tool_name = tool_result.get("name", "unknown")
                result = tool_result.get("result", {})
                print(f"[tool result] {tool_name}: {json.dumps(result)[:200]}...")

        final_text = "".join(full_response)
        print(f"\nAssistant: {final_text}")

        # Check if all expected tools were called
        print(f"\n--- Tool Coverage Check ---")
        print(f"Tools called: {tools_called}")
        print(f"Expected tools: {expected_tools}")

        missing_tools = expected_tools - tools_called
        if missing_tools:
            print(f"MISSING TOOLS: {missing_tools}")
            print("Verdict: FAIL - Agent did not call all required tools")
        else:
            print("All tools called successfully")
            print("Verdict: PASS")

        return {
            "session_id": session_id,
            "response": final_text,
            "tools_called": list(tools_called),
            "missing_tools": list(missing_tools)
        }

    except Exception as e:
        print(f"Error: {e}")
        return None

def main():
    debug = "--debug" in sys.argv
    session_id = None

    # Check for session flag
    for i, arg in enumerate(sys.argv):
        if arg == "--session" and i + 1 < len(sys.argv):
            session_id = sys.argv[i + 1]

    args = [a for a in sys.argv[1:] if not a.startswith("--") and (a == sys.argv[1] or sys.argv[1] != "--session")]

    if args and not args[0].startswith("--"):
        message = " ".join(args)
        invoke_agent(message, session_id, debug)
    else:
        print("=== Restaurant Recommendation Agent ===")
        print("Usage: python invoke_agent.py \"Find me an Italian restaurant for tonight.\"")
        print("       python invoke_agent.py --session <id> \"What about Japanese?\"")
        print("\nExample:")
        print('  python invoke_agent.py "Find me an Italian restaurant for tonight."')

if __name__ == "__main__":
    main()
