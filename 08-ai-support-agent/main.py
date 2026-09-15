"""
Customer Support AI Agent — Starter Code
==========================================
Your task is to complete this file by implementing all sections marked
with # TODO comments.

Reference the step-by-step solution files and INSTRUCTIONS.md for guidance.
Do NOT copy the solution directly — work through each section yourself.

Run locally (after filling in config values):
  uv run main.py '{"prompt": "Hello", "customer_id": "CUST-123", "session_id": "s1"}'

Deploy to AgentCore:
  agentcore deploy

Invoke deployed agent:
  agentcore invoke '{"prompt": "Hello", "customer_id": "CUST-123", "session_id": "s1"}'
"""

# ── Imports ───────────────────────────────────────────────────────────────────
# These imports are provided. Do not remove them.
import argparse
import asyncio
import importlib.util
import json
import logging
import os
import uuid

import boto3
from pydantic import ValidationError
from bedrock_agentcore.memory import MemoryClient
from conversation import TokenBudgetManager
from schemas import AgentResponse, DiscountInput, DiscountResult, InvokePayload
from bedrock_agentcore.runtime import BedrockAgentCoreApp
from bedrock_agentcore.tools.code_interpreter_client import code_session
from mcp.client.streamable_http import streamable_http_client
from strands import Agent, tool
from strands.hooks import (
    AfterInvocationEvent,
    HookProvider,
    HookRegistry,
    MessageAddedEvent,
)
from strands.models import BedrockModel
from strands.tools.mcp.mcp_client import MCPClient
from strands_tools.browser import AgentCoreBrowser

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger("CSAI_Agent")

# ── TODO 1 — App Initialisation ───────────────────────────────────────────────
# Create a BedrockAgentCoreApp instance.
# This registers the ASGI server for AgentCore deployment.
# There must be exactly one instance per deployment.
#
# Hint: app = BedrockAgentCoreApp()

# TODO: Create the BedrockAgentCoreApp instance
app = BedrockAgentCoreApp()


# Suppress interactive tool-consent prompts (required in headless deployments).
os.environ["BYPASS_TOOL_CONSENT"] = "true"


# Windows-built dependency zips lose Unix exec bits; ensure the Playwright
# driver binary AgentCoreBrowser spawns is executable (best effort).
# Owner-only bit: the runtime executes as the file owner, so 0o700 suffices.
try:
    _pw_spec = importlib.util.find_spec("playwright")
    if _pw_spec and _pw_spec.origin:
        _node_bin = os.path.join(os.path.dirname(_pw_spec.origin), "driver", "node")
        if os.path.exists(_node_bin):
            os.chmod(_node_bin, 0o700)
except Exception as _e:  # noqa: BLE001 - best-effort runtime compat shim
    logger.warning("Could not fix playwright driver perms: %s", _e)


# ── TODO 2 — Configuration ────────────────────────────────────────────────────
# Replace the placeholder strings with your actual AWS resource values.
# You collected these in Part 1 of the INSTRUCTIONS.
#
# GATEWAY_URL format: https://<alias>.gateway.bedrock-agentcore.<region>.amazonaws.com/mcp
# KB_ID       format: 10-character alphanumeric string from the KB console
# REGION:     your AWS region, e.g. "us-east-1"
# MEMORY_ID   format: shown in the AgentCore Memory console

GATEWAY_URL = "https://customersupportgateway-1rvyrs9sm7.gateway.bedrock-agentcore.us-east-1.amazonaws.com/mcp"
KB_ID = "CZGKR1BS45"
REGION = "us-east-1"
MEMORY_ID = "CustomerSupportMemory-dg71VY2DLx"


# ── TODO 3 — Model and Clients ────────────────────────────────────────────────
# Create:
#   1. A BedrockModel using model_id "global.amazon.nova-2-lite-v1:0"
#   2. A MemoryClient with region_name=REGION
#   3. A boto3 client for the "bedrock-agent-runtime" service in REGION
#
# Hint: model = BedrockModel(model_id=model_id)

model_id = "global.amazon.nova-2-lite-v1:0"

model = BedrockModel(model_id=model_id)

memory_client = MemoryClient(region_name=REGION)

_bedrock_runtime = boto3.client("bedrock-agent-runtime", region_name=REGION)


# ── TODO 4 — Namespace Helper ─────────────────────────────────────────────────
# Implement get_namespaces() to return a dict mapping strategy type to
# namespace template string.
#
# Steps:
#   1. Call mem_client.get_memory_strategies(memory_id) to get strategy list
#   2. Return a dict: { strategy["type"]: strategy["namespaces"][0] for each strategy }
#
# Example output:
#   { "SEMANTIC": "cs_agent/{actorId}/facts",
#     "USER_PREFERENCE": "cs_agent/{actorId}/preferences" }


def get_namespaces(mem_client: MemoryClient, memory_id: str) -> dict:
    """Return a dict mapping strategy type → namespace template string."""
    strats = mem_client.get_memory_strategies(memory_id)
    if isinstance(strats, dict):
        strats = strats.get("memoryStrategies", strats.get("strategies", []))
    return {
        s["type"]: (s.get("namespaceTemplates") or s.get("namespaces"))[0]
        for s in strats
    }


# ── TODO 5 — Memory Hook ──────────────────────────────────────────────────────
# Implement MemoryHook, a HookProvider subclass that adds long-term memory.
#
# The class needs:
#   __init__(self, actor_id, session_id, memory_client, memory_id)
#     — store all four as instance attributes
#     — call get_namespaces() and store the result as self.namespaces
#
#   retrieve_customer_context(self, event: MessageAddedEvent)
#     — only runs for plain-text user messages (not tool results)
#     — for each strategy namespace, call memory_client.retrieve_memories(
#          memory_id, namespace (formatted with actorId), query, top_k=5)
#     — collect non-empty memory texts tagged with their strategy type
#     — if any memories found, prepend them to the user message as:
#          "Customer Context:\n<memories>\n\n<original_message>"
#
#   save_support_interaction(self, event: AfterInvocationEvent)
#     — walk the message list backwards to find the last plain-text user
#       query and the last assistant response
#     — call memory_client.create_event(memory_id, actor_id, session_id,
#          messages=[(customer_query, "USER"), (agent_response, "ASSISTANT")])
#
#   register_hooks(self, registry: HookRegistry)
#     — register retrieve_customer_context on MessageAddedEvent
#     — register save_support_interaction on AfterInvocationEvent


class MemoryHook(HookProvider):
    """Long-term memory hook for the customer support agent."""

    def __init__(
        self,
        actor_id: str,
        session_id: str,
        memory_client: MemoryClient,
        memory_id: str,
    ):
        self.actor_id = actor_id
        self.session_id = session_id
        self.memory_client = memory_client
        self.memory_id = memory_id
        self.namespaces = get_namespaces(memory_client, memory_id)

    def retrieve_customer_context(self, event: MessageAddedEvent):
        """Retrieve relevant memories and prepend them to the user message."""
        messages = event.agent.messages
        if not messages:
            return
        last = messages[-1]
        if last.get("role") != "user":
            return
        content = last.get("content", [])
        if (
            not content
            or not isinstance(content[0], dict)
            or "toolResult" in content[0]
        ):
            return
        query = content[0].get("text", "")
        if not query:
            return
        found = []
        for strategy_type, ns in self.namespaces.items():
            resolved = ns.format(actorId=self.actor_id)
            try:
                memories = self.memory_client.retrieve_memories(
                    memory_id=self.memory_id,
                    namespace=resolved,
                    query=query,
                    top_k=5,
                )
            except Exception as e:
                logger.warning("Memory retrieve failed (%s): %s", strategy_type, e)
                continue
            for mem in memories or []:
                text = mem.get("content", {}).get("text", "").strip()
                if text:
                    found.append(f"[{strategy_type}] {text}")
        if found:
            content[0]["text"] = (
                "Customer Context:\n" + "\n".join(found) + "\n\n" + query
            )

    def save_support_interaction(self, event: AfterInvocationEvent):
        """Save the completed turn to memory after the agent responds."""
        messages = event.agent.messages
        user_text = None
        asst_text = None
        for msg in reversed(messages):
            content = msg.get("content", [])
            if not content or not isinstance(content[0], dict):
                continue
            if "toolResult" in content[0]:
                continue
            text = content[0].get("text", "")
            if not text:
                continue
            if msg.get("role") == "assistant" and asst_text is None:
                asst_text = text
            elif msg.get("role") == "user" and user_text is None:
                if text.startswith("Customer Context:\n") and "\n\n" in text:
                    text = text.split("\n\n", 1)[1]
                user_text = text
            if user_text is not None and asst_text is not None:
                break
        if user_text and asst_text:
            try:
                self.memory_client.create_event(
                    memory_id=self.memory_id,
                    actor_id=self.actor_id,
                    session_id=self.session_id,
                    messages=[(user_text, "USER"), (asst_text, "ASSISTANT")],
                )
            except Exception as e:
                logger.warning("Memory save failed: %s", e)

    def register_hooks(self, registry: HookRegistry) -> None:  # type: ignore
        """Register both memory callbacks."""
        registry.add_callback(MessageAddedEvent, self.retrieve_customer_context)
        registry.add_callback(AfterInvocationEvent, self.save_support_interaction)


# ── TODO 6 — Knowledge Base Tool ─────────────────────────────────────────────
# Implement search_knowledge_base(query) using the @tool decorator.
#
# Steps:
#   1. Guard: if KB_ID is empty return "Knowledge base not configured."
#   2. Call _bedrock_runtime.retrieve(
#          knowledgeBaseId=KB_ID,
#          retrievalQuery={"text": query}
#      )
#   3. Extract resp["retrievalResults"]; return a message if empty
#   4. Join the text chunks with "\n---\n" and return the result
#
# The docstring is the tool description — the model uses it to decide when
# to call this tool, so keep it clear and accurate.


@tool
def search_knowledge_base(query: str) -> str:
    """
    Search the Amazon product catalog and support knowledge base.
    Use this for product specifications, return policies, warranty
    information, loyalty program details, and order status definitions.

    Args:
        query: The question or topic to search for

    Returns:
        Relevant information retrieved from the knowledge base
    """
    if not KB_ID or KB_ID.startswith("<"):
        return "Knowledge base not configured."
    resp = _bedrock_runtime.retrieve(
        knowledgeBaseId=KB_ID,
        retrievalQuery={"text": query},
    )
    results = resp.get("retrievalResults", [])
    if not results:
        return f"No information found for: {query}"
    return "\n---\n".join(r["content"]["text"] for r in results)


# ── TODO 7 — Loyalty Discount Tool (Code Interpreter) ────────────────────────
# Implement calculate_loyalty_discount() using the @tool decorator.
#
# The tool must:
#   1. Build a self-contained Python code string that:
#        • Defines earn_rates: {"standard": 1, "device": 2, "fresh": 5}
#        • Defines tier_rates: {"Silver": 0.00, "Gold": 0.10, "Platinum": 0.15}
#        • Calculates points_redeemed (floor to nearest 500, cap at 50% of order)
#        • Calculates tier_discount (applied to subtotal after points)
#        • Calculates final_total, total_savings, points_earned, remaining_points
#        • Prints a JSON result dict
#   2. Execute the code with code_session(REGION).invoke("executeCode", {...})
#      using language="python" and clearContext=True
#   3. Return the first result event as a JSON string
#   4. Include a fallback that computes only the tier discount if the
#      Code Interpreter is unavailable


@tool
def calculate_loyalty_discount(
    loyalty_points: int,
    tier: str,
    order_total: float,
    product_category: str = "standard",
) -> str:
    """
    Calculate the loyalty discount for a customer order using the
    AgentCore Code Interpreter. Runs exact arithmetic in a secure sandbox.

    Args:
        loyalty_points:   Customer's current points balance
        tier:             Customer tier — Silver, Gold, or Platinum
        order_total:      Order total in USD
        product_category: standard, device, or fresh

    Returns:
        Full discount breakdown and final price
    """
    try:
        validated_input = DiscountInput(
            loyalty_points=loyalty_points,
            tier=tier,
            order_total=order_total,
            product_category=product_category,
        )
    except ValidationError as e:
        return json.dumps({"error": f"Invalid discount input: {e.errors()}"})
    loyalty_points = validated_input.loyalty_points
    tier = validated_input.tier
    order_total = validated_input.order_total
    product_category = validated_input.product_category
    code = f"""
import json
loyalty_points = {loyalty_points}
tier = "{tier}"
order_total = {order_total}
product_category = "{product_category}"
earn_rates = {{"standard": 1, "device": 2, "fresh": 5}}
tier_rates = {{"Silver": 0.00, "Gold": 0.10, "Platinum": 0.15}}
cap_points = int(order_total * 50)
usable = min(loyalty_points, cap_points)
points_redeemed = (usable // 500) * 500
redemption = points_redeemed / 100
subtotal = order_total - redemption
tier_pct = tier_rates.get(tier, 0.00)
tier_discount = round(subtotal * tier_pct, 2)
final_total = round(subtotal - tier_discount, 2)
total_savings = round(redemption + tier_discount, 2)
points_earned = int(final_total * earn_rates.get(product_category, 1))
remaining_points = loyalty_points - points_redeemed + points_earned
print(json.dumps({{"points_redeemed": points_redeemed, "tier_discount_pct": int(tier_pct * 100), "tier_discount": tier_discount, "final_total": final_total, "total_savings": total_savings, "points_earned": points_earned, "remaining_points": remaining_points}}))
"""
    print(f"\nGenerated Code:\n{code}\n")

    try:
        with code_session(REGION) as code_client:
            resp = code_client.invoke(
                "executeCode",
                {"code": code, "language": "python", "clearContext": True},
            )
        for event in resp["stream"]:
            raw = event["result"]
            try:
                DiscountResult(**raw)
            except ValidationError as e:
                return json.dumps({"error": f"Invalid discount result: {e.errors()}"})
            return json.dumps(raw)
        return json.dumps({"error": "Empty code interpreter result"})

    except Exception as e:
        logger.warning("Code Interpreter unavailable, tier-only fallback: %s", e)
        tier_pct = {"Silver": 0.00, "Gold": 0.10, "Platinum": 0.15}.get(tier, 0.00)
        tier_discount = round(order_total * tier_pct, 2)
        final_total = round(order_total - tier_discount, 2)
        return json.dumps(
            {
                "points_redeemed": 0,
                "tier_discount_pct": int(tier_pct * 100),
                "tier_discount": tier_discount,
                "final_total": final_total,
                "total_savings": tier_discount,
                "points_earned": 0,
                "remaining_points": loyalty_points,
                "note": "Code Interpreter unavailable; tier-only discount applied.",
            }
        )


# ── TODO 8 — Agent Entrypoint ─────────────────────────────────────────────────
# Implement the invoke() function decorated with @app.entrypoint.
#
# Steps:
#   1. Extract user_input, actor_id, and session_id from the payload
#      (generate a UUID if session_id is missing)
#   2. Instantiate MemoryHook for this actor/session
#   3. Instantiate AgentCoreBrowser(region=REGION)
#   4. Build the tools list: [search_knowledge_base, calculate_loyalty_discount,
#                              agent_core_browser.browser]
#   5. Connect to the Gateway via MCPClient, load gateway_tools, extend tools list
#   6. Create and invoke the Agent with all tools, hooks, and system_prompt
#   7. Return the text from the first content block of the response
#   8. Handle exceptions gracefully


@app.entrypoint
async def invoke(payload, context=None):
    """
    Main handler called by AgentCore for every incoming request.

    Expected payload keys:
      prompt      (str, required) — the customer's message
      customer_id (str, optional) — unique customer identifier
      session_id  (str, optional) — session identifier; generated if absent
    """
    try:
        validated = InvokePayload(**(payload or {}))
    except ValidationError as e:
        return f"Error: invalid input: {e.errors()}"
    prompt = validated.prompt
    actor_id = validated.customer_id
    session_id = validated.session_id or str(uuid.uuid4())
    browser = AgentCoreBrowser(region=REGION)
    tools = [search_knowledge_base, calculate_loyalty_discount, browser.browser]
    hook = MemoryHook(actor_id, session_id, memory_client, MEMORY_ID)
    try:
        with MCPClient(lambda: streamable_http_client(url=GATEWAY_URL)) as mcp_client:
            gateway_tools = mcp_client.list_tools_sync()
            tools.extend(gateway_tools)
            agent = Agent(
                model=model,
                system_prompt="You are a customer support assistant. Use Gateway tools for orders.",
                tools=tools,
                hooks=[hook],
                conversation_manager=TokenBudgetManager(),
                state={"session_id": session_id, "actor_id": actor_id},
            )
            result = agent(prompt)
            try:
                text = result.message["content"][0]["text"]
            except Exception:
                text = str(result)
            try:
                return AgentResponse(response=text).response
            except ValidationError:
                return "Error: agent returned an empty response"
    except Exception as e:
        return f"Error: {e}"


# ── CLI entry point (do not modify) ──────────────────────────────────────────
def main():
    """Run one invocation from the command line for local testing."""
    parser = argparse.ArgumentParser()
    parser.add_argument("payload", type=str)
    args = parser.parse_args()
    try:
        payload = json.loads(args.payload)
    except json.JSONDecodeError as e:
        parser.error(f"Invalid JSON payload: {e}")
    response = asyncio.run(invoke(payload))
    print(response)


if __name__ == "__main__":
    app.run()
    # Uncomment the line below and comment app.run() for local CLI testing:
    # main()
