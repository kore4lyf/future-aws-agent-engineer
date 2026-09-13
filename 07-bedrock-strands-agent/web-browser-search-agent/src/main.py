import logging
from bedrock_agentcore.runtime import BedrockAgentCoreApp
from strands import Agent
from strands.models import BedrockModel
from strands_tools.browser import AgentCoreBrowser

from src.prompts.system import SYSTEM_PROMPT

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

app = BedrockAgentCoreApp()

MODEL_ID = "us.amazon.nova-pro-v1:0"
model = BedrockModel(model_id=MODEL_ID)


@app.entrypoint
async def invoke(payload: dict, context=None):
    user_message = payload.get("message", "Hello!")
    logger.info(f"User message: {user_message}")

    browser = AgentCoreBrowser(session_timeout=600)

    agent = Agent(
        model=model,
        system_prompt=SYSTEM_PROMPT,
        tools=[browser.browser],
    )
    return agent(user_message, limits={"turns": 5})


if __name__ == "__main__":
    app.run()
