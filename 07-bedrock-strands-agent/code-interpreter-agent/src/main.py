import logging
from bedrock_agentcore.runtime import BedrockAgentCoreApp
from strands import Agent
from strands.models import BedrockModel

from src.prompts.system import SYSTEM_PROMPT
from src.tools.code_executor import calculate_trip_cost

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = BedrockAgentCoreApp()
MODEL_ID = "us.amazon.nova-pro-v1:0"
model = BedrockModel(model_id=MODEL_ID)


@app.entrypoint
async def invoke(payload: dict, context=None):
    user_message = payload.get("prompt") or payload.get("message") or "Hello!"
    logger.info(f"User message: {user_message}")
    agent = Agent(
        model=model,
        system_prompt=SYSTEM_PROMPT,
        tools=[calculate_trip_cost],
    )
    return agent(user_message)


if __name__ == "__main__":
    app.run()
