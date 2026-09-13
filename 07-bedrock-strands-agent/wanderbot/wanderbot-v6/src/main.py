from bedrock_agentcore.runtime import BedrockAgentCoreApp
from strands import Agent
from strands.models import BedrockModel

from src.prompts.system import SYSTEM_PROMPT

app = BedrockAgentCoreApp()

MODEL_ID = "us.amazon.nova-2-lite-v1:0"
model = BedrockModel(model_id=MODEL_ID)

MEMORY_ID = "WanderBot-Kp6M1pF0Ge"
GATEWAY_ENDPOINT = "https://wanderbot-gateway-foziumjcew.gateway.bedrock-agentcore.us-east-1.amazonaws.com/mcp"  # v6 fix


@app.entrypoint
async def invoke(payload: dict, context=None):
    from bedrock_agentcore.memory import MemoryClient
    from mcp.client.streamable_http import streamable_http_client
    from strands.tools.mcp.mcp_client import MCPClient

    from src.hooks.memory import ShortTermMemoryHookProvider

    user_message = payload.get("message", "Hello!")
    session_id = context.session_id if context and hasattr(context, "session_id") else payload.get("session_id", "default-session")
    actor_id = payload.get("actor_id", "wanderbot-user")

    try:
        memory_client = MemoryClient(region_name="us-east-1")
    except Exception:
        memory_client = None
    hooks = [ShortTermMemoryHookProvider(memory_client=memory_client, memory_id=MEMORY_ID)] if memory_client else []

    gateway_client = MCPClient(lambda: streamable_http_client(url=GATEWAY_ENDPOINT))
    with gateway_client:
        tools = gateway_client.list_tools_sync()
        agent = Agent(
            model=model,
            system_prompt=SYSTEM_PROMPT,
            tools=tools,
            hooks=hooks,
            state={"session_id": session_id, "actor_id": actor_id},
        )
        return agent(user_message)


if __name__ == "__main__":
    app.run()
