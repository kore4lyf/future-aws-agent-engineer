import os
import logging
from strands.hooks import HookProvider, HookRegistry, MessageAddedEvent, AfterInvocationEvent
from bedrock_agentcore.memory import MemoryClient

logger = logging.getLogger(__name__)


def get_namespaces(memory_client: MemoryClient, memory_id: str) -> dict:
    try:
        strategies = memory_client.get_memory_strategies(memory_id=memory_id)
    except Exception:
        strategies = []
    namespaces = {}
    for s in strategies:
        s_type = s.get("type") or s.get("memoryStrategyType") or s.get("name", "")
        ns_list = s.get("namespaces") or s.get("namespaceTemplates") or []
        ns = ns_list[0] if isinstance(ns_list, list) and ns_list else s.get("namespace", "")
        if s_type and ns:
            namespaces[s_type] = ns
    if not namespaces:
        namespaces = {
            "SEMANTIC": "/wanderbot/{actorId}/facts",
            "USER_PREFERENCE": "/wanderbot/{actorId}/preferences",
        }
    return namespaces


class WanderBotMemoryHook(HookProvider):
    def __init__(self, memory_client: MemoryClient, memory_id: str):
        self.memory_client = memory_client
        self.memory_id = memory_id
        self.namespaces = get_namespaces(memory_client, memory_id)

    def register_hooks(self, registry: HookRegistry) -> None:
        registry.add_callback(MessageAddedEvent, self._retrieve_travel_context)
        registry.add_callback(AfterInvocationEvent, self._save_interaction)

    def _retrieve_travel_context(self, event: MessageAddedEvent) -> None:
        actor_id = event.agent.state.get("actor_id")
        if not actor_id or not event.agent.messages:
            return
        last_msg = event.agent.messages[-1]
        if last_msg.get("role") != "user":
            return
        if any(c.get("toolResult") for c in last_msg.get("content", []) if isinstance(c, dict)):
            return
        user_query = last_msg["content"][0]["text"] if last_msg.get("content") else ""
        if not user_query:
            return
        all_context = []
        for strategy_type, namespace in self.namespaces.items():
            resolved = namespace.format(actorId=actor_id)
            try:
                memories = self.memory_client.retrieve_memories(
                    memory_id=self.memory_id,
                    namespace=resolved,
                    query=user_query,
                    top_k=5,
                )
                for memory in memories:
                    text = memory.get("content", {}).get("text", "").strip() if isinstance(memory.get("content"), dict) else str(memory.get("content", "")).strip()
                    if text:
                        all_context.append(f"[{strategy_type}] {text}")
            except Exception as e:
                logger.warning(f"retrieve_memories {strategy_type} failed: {e}")
        if all_context:
            event.agent.messages[-1]["content"][0]["text"] = (
                f"Traveller Context:\n" + "\n".join(all_context) + f"\n\n{user_query}"
            )
            logger.info(f"Injected {len(all_context)} memories for {actor_id}")

    def _save_interaction(self, event: AfterInvocationEvent) -> None:
        actor_id = event.agent.state.get("actor_id")
        session_id = event.agent.state.get("session_id")
        if not actor_id or not session_id:
            return
        messages = event.agent.messages or []
        user_text = None
        agent_text = None
        for m in reversed(messages):
            if m.get("role") == "assistant" and agent_text is None:
                c = m.get("content", [])
                agent_text = c[0].get("text", "") if c and isinstance(c[0], dict) else ""
            elif m.get("role") == "user" and user_text is None:
                c = m.get("content", [])
                user_text = c[0].get("text", "") if c and isinstance(c[0], dict) else ""
                if "Traveller Context:\n" in user_text:
                    user_text = user_text.split("\n\n", 1)[-1]
            if user_text and agent_text:
                break
        if not user_text or not agent_text:
            return
        try:
            self.memory_client.create_event(
                memory_id=self.memory_id,
                actor_id=actor_id,
                session_id=session_id,
                messages=[(user_text, "USER"), (agent_text, "ASSISTANT")],
            )
            logger.info(f"Persisted exchange for {actor_id}/{session_id}")
        except Exception as e:
            logger.warning(f"create_event failed: {e}")


LongTermMemoryHookProvider = WanderBotMemoryHook
TravelerMemoryHook = WanderBotMemoryHook
TravellerMemoryHook = WanderBotMemoryHook
