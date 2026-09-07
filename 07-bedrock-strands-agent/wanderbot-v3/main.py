from bedrock_agentcore.runtime import BedrockAgentCoreApp
from strands import Agent
from strands.models import BedrockModel
from strands_tools import calculator, current_time

from src.tools import search_flights, search_hotels, get_exchange_rate
from src.prompts.system import SYSTEM_PROMPT

app = BedrockAgentCoreApp()

MODEL_ID = "us.amazon.nova-2-lite-v1:0"
model = BedrockModel(model_id=MODEL_ID)


@app.entrypoint
async def invoke(payload: dict, context=None):
    user_message = payload.get("message", "Hello!")
    agent = Agent(
        model=model,
        system_prompt=SYSTEM_PROMPT,
        tools=[calculator, current_time, search_flights, search_hotels, get_exchange_rate],
    )
    return agent(user_message)


if __name__ == "__main__":
    app.run()
