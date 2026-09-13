import logging
import os
from bedrock_agentcore.runtime import BedrockAgentCoreApp
from strands import Agent
from strands.models import BedrockModel
from bedrock_agentcore.memory import MemoryClient
from strands.hooks import AfterInvocationEvent, HookProvider, HookRegistry, MessageAddedEvent

from src.prompts.system import SYSTEM_PROMPT
from src.hooks.memory import TravelerMemoryHook

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = BedrockAgentCoreApp()
MODEL_ID = "us.amazon.nova-pro-v1:0"
model = BedrockModel(model_id=MODEL_ID)

MEMORY_ID = os.getenv("MEMORY_ID", "WanderBot-Kp6M1pF0Ge")
memory_client = MemoryClient(region_name=os.getenv("AWS_REGION", "us-east-1"))


@app.entrypoint
async def invoke(payload: dict, context=None) -> dict:
    user_message = payload.get("message", "Hello!")
    session_id = getattr(context, "session_id", None) or (context or {}).get("session_id") if isinstance(context, dict) else getattr(context, "session_id", "session-001")
    if not session_id:
        session_id = payload.get("session_id", "session-001")
    actor_id = payload.get("actor_id", "wanderbot-user")
    logger.info(f"Actor: {actor_id} Session: {session_id}")

    memory_hook = TravelerMemoryHook(
        memory_client=memory_client,
        memory_id=MEMORY_ID,
    )

    agent = Agent(
        model=model,
        system_prompt=SYSTEM_PROMPT,
        tools=[],
        state={"session_id": session_id, "actor_id": actor_id},
        hooks=[memory_hook],
    )
    return agent(user_message)


if __name__ == "__main__":
    app.run()
