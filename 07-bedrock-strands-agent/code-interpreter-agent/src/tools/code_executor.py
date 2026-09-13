import json
from bedrock_agentcore.tools.code_interpreter_client import code_session
from strands import tool

REGION = "us-east-1"

@tool
def calculate_trip_cost(code: str, description: str = "") -> str:
    """Execute Python code in an isolated AgentCore sandbox and return the output."""

    if description:
        code = f"# {description}\n{code}"

    print(f"\nGenerated Code:\n{code}\n")

    with code_session(REGION) as code_client:
        response = code_client.invoke("executeCode", {
            "code": code,
            "language": "python",
            "clearContext": True,
        })

    for event in response["stream"]:
        return json.dumps(event["result"])

    return json.dumps(response)

execute_python = calculate_trip_cost
