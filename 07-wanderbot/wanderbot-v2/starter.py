from bedrock_agentcore.runtime import BedrockAgentCoreApp
from strands import Agent
from strands.models import BedrockModel

app = BedrockAgentCoreApp()

MODEL_ID = "us.amazon.nova-2-lite-v1:0"
model = BedrockModel(model_id=MODEL_ID)

SYSTEM_PROMPT = """You are WanderBot, the AI travel assistant for Horizon Travel.
You help travellers with flight searches, hotel bookings, and currency conversions.
Always be friendly, concise, and travel-focused."""


@app.entrypoint
async def invoke(payload: dict, context=None):
    user_message = payload.get("message", "Hello!")
    agent = Agent(
        model=model,
        system_prompt=SYSTEM_PROMPT,
        tools=[],  # TODO: Add tools here
    )
    return agent(user_message)


if __name__ == "__main__":
    app.run()
