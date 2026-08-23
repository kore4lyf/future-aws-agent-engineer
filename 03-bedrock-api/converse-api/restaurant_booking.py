import boto3
import json
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------
bedrock = boto3.client("bedrock-runtime", region_name="us-east-1")

MODEL_ID = "amazon.nova-lite-v1:0"

SYSTEM_PROMPT = """\
You are a helpful restaurant booking assistant. Your job is to help the user find a restaurant to book for tonight.

Ask the user about their cuisine preference.
Use the available tools to look up options and check availability before making a recommendation.
Base your recommendation on tool results only — do not invent restaurant names or availability.
Once you have confirmed a restaurant has availability, provide a clear recommendation with its name and area."""

# ---------------------------------------------------------------------------
# Mock data
# ---------------------------------------------------------------------------
RESTAURANTS = [
    {"id": "r1", "name": "Pasta Roma",       "cuisine": "Italian",  "rating": 4.5},
    {"id": "r2", "name": "Sakura Garden",    "cuisine": "Japanese", "rating": 4.7},
    {"id": "r3", "name": "El Mercado",       "cuisine": "Mexican",  "rating": 4.3},
    {"id": "r4", "name": "Spice Route",      "cuisine": "Indian",   "rating": 4.6},
    {"id": "r5", "name": "Le Bistro",        "cuisine": "French",   "rating": 4.8},
    {"id": "r6", "name": "The Grill House",  "cuisine": "American", "rating": 4.2},
    {"id": "r7", "name": "Trattoria Bella",  "cuisine": "Italian",  "rating": 4.4},
    {"id": "r8", "name": "Ramen Yuki",       "cuisine": "Japanese", "rating": 4.9},
]

AVAILABILITY = {
    "r1": True,
    "r2": True,
    "r3": True,
    "r4": True,
    "r5": False,
    "r6": True,
    "r7": True,
    "r8": False,
}

# ---------------------------------------------------------------------------
# Local tool implementations
# ---------------------------------------------------------------------------
def get_cuisines() -> dict:
    cuisines = sorted(set(r["cuisine"] for r in RESTAURANTS))
    return {"cuisines": cuisines}


def search_restaurants(cuisines: list) -> dict:
    cuisines_lower = [c.lower() for c in cuisines]
    results = [
        r for r in RESTAURANTS
        if r["cuisine"].lower() in cuisines_lower
    ]
    return {"restaurants": results}


def get_availability(restaurant_id: str) -> dict:
    available = AVAILABILITY.get(restaurant_id, False)
    return {"restaurant_id": restaurant_id, "available": available}


# ---------------------------------------------------------------------------
# Tool schemas
# ---------------------------------------------------------------------------
TOOLS = [
    {
        "toolSpec": {
            "name": "get_cuisines",
            "description": "Returns the list of cuisine types available in the city.",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "search_restaurants",
            "description": "Searches for restaurants matching one or more cuisine types.",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "cuisines": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "List of cuisine types to filter by.",
                        },
                    },
                    "required": ["cuisines"],
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "get_availability",
            "description": "Checks whether a specific restaurant has availability for tonight.",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "restaurant_id": {
                            "type": "string",
                            "description": "The unique ID of the restaurant to check.",
                        }
                    },
                    "required": ["restaurant_id"],
                }
            },
        }
    },
]

# ---------------------------------------------------------------------------
# Tool dispatcher
# ---------------------------------------------------------------------------
def execute_tool(name: str, tool_input: dict) -> dict:
    if name == "get_cuisines":
        return get_cuisines()
    elif name == "search_restaurants":
        return search_restaurants(tool_input["cuisines"])
    elif name == "get_availability":
        return get_availability(tool_input["restaurant_id"])
    else:
        return {"error": f"Unknown tool: {name}"}


# ---------------------------------------------------------------------------
# Converse loop
# ---------------------------------------------------------------------------
def run_chat() -> None:
    messages = []

    print("Assistant: Hi! I can help you find a restaurant for tonight.")
    print("           What cuisine are you in the mood for?\n")

    while True:
        try:
            user_input = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            break

        if not user_input:
            continue

        messages.append({"role": "user", "content": [{"text": user_input}]})

        # Inner loop: keep calling Converse until the model finishes its turn.
        # The model may call multiple tools before producing a final response.
        while True:
            response = bedrock.converse(
                modelId=MODEL_ID,
                system=[{"text": SYSTEM_PROMPT}],
                messages=messages,
                toolConfig={"tools": TOOLS},
            )

            stop_reason = response["stopReason"]
            output_message = response["output"]["message"]
            messages.append(output_message)

            if stop_reason == "end_turn":
                for block in output_message["content"]:
                    if "text" in block:
                        print(f"\nTravel Assistant: {block['text']}\n")
                break

            elif stop_reason == "tool_use":
                tool_results = []

                for block in output_message["content"]:
                    if "toolUse" in block:
                        tool_name = block["toolUse"]["name"]
                        tool_input = block["toolUse"]["input"]
                        tool_use_id = block["toolUse"]["toolUseId"]

                        print(f"  [tool call] {tool_name}({tool_input})")
                        result = execute_tool(tool_name, tool_input)
                        print(f"  [tool result] {result}")

                        tool_results.append({
                            "toolResult": {
                                "toolUseId": tool_use_id,
                                "content": [{"json": result}],
                            }
                        })

                messages.append({"role": "user", "content": tool_results})


if __name__ == "__main__":
    run_chat()
