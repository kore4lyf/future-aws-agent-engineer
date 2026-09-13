from strands.hooks import AgentInitializedEvent, HookProvider, HookRegistry, MessageAddedEvent


class ShortTermMemoryHookProvider(HookProvider):
    def __init__(self, memory_client, memory_id, last_k_turns=5):
        self.memory_client = memory_client
        self.memory_id = memory_id
        self.last_k_turns = last_k_turns

    def register_hooks(self, registry: HookRegistry) -> None:
        registry.add_callback(AgentInitializedEvent, self.on_agent_initialized)
        registry.add_callback(MessageAddedEvent, self.on_message_added)

    def on_agent_initialized(self, event: AgentInitializedEvent) -> None:
        actor_id = event.agent.state.get("actor_id")
        session_id = event.agent.state.get("session_id")
        if not actor_id or not session_id:
            return

        recent_turns = self.memory_client.get_last_k_turns(
            memory_id=self.memory_id,
            actor_id=actor_id,
            session_id=session_id,
            k=self.last_k_turns,
        )
        if not recent_turns:
            return

        lines = []
        for turn in recent_turns:
            for m in turn:
                role = m.get("role", "unknown").capitalize()
                text = m.get("content", {}).get("text", "")
                if text:
                    lines.append(f"{role}: {text}")
        if lines:
            event.agent.system_prompt += "\n\nRecent conversation:\n" + "\n".join(lines)

    def on_message_added(self, event: MessageAddedEvent) -> None:
        actor_id = event.agent.state.get("actor_id")
        session_id = event.agent.state.get("session_id")
        if not actor_id or not session_id:
            return

        message = event.message
        content = message.get("content", [])
        text = content[0].get("text") if content and isinstance(content[0], dict) else None
        if not text:
            return

        self.memory_client.create_event(
            memory_id=self.memory_id,
            actor_id=actor_id,
            session_id=session_id,
            messages=[(text, message.get("role", "").upper())],
        )
