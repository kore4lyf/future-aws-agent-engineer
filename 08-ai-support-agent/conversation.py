import json
import logging

from strands.agent.conversation_manager import SummarizingConversationManager
from strands.hooks import AfterInvocationEvent, HookRegistry

logger = logging.getLogger("CSAI_Agent")

TOKEN_BUDGET = 20000
SUMMARY_RATIO = 0.3
KEEP_RECENT_MESSAGES = 10
CHARS_PER_TOKEN = 4


def estimate_tokens(messages) -> int:
    chars = 0
    for message in messages or []:
        chars += len(message.get("role", ""))
        chars += _content_chars(message.get("content", []))
    return chars // CHARS_PER_TOKEN


def _content_chars(content) -> int:
    if isinstance(content, str):
        return len(content)
    if not isinstance(content, list):
        return 0
    chars = 0
    for block in content:
        if not isinstance(block, dict):
            continue
        chars += len(block.get("text") or "")
        tool_use = block.get("toolUse") or {}
        chars += len(json.dumps(tool_use.get("input", {}), default=str))
        tool_result = block.get("toolResult") or {}
        chars += _content_chars(tool_result.get("content") or [])
    return chars


class TokenBudgetManager(SummarizingConversationManager):
    def __init__(
        self,
        token_budget: int = TOKEN_BUDGET,
        summary_ratio: float = SUMMARY_RATIO,
        keep_recent: int = KEEP_RECENT_MESSAGES,
    ):
        super().__init__(
            summary_ratio=summary_ratio,
            preserve_recent_messages=keep_recent,
            proactive_compression=True,
        )
        self.token_budget = token_budget

    def register_hooks(self, registry: HookRegistry, **kwargs) -> None:
        super().register_hooks(registry, **kwargs)
        registry.add_callback(AfterInvocationEvent, self.enforce_token_budget)

    def enforce_token_budget(self, event: AfterInvocationEvent) -> None:
        if estimate_tokens(event.agent.messages) <= self.token_budget:
            return
        try:
            self.reduce_context(agent=event.agent)
        except Exception as e:
            logger.warning("Token-budget summarization failed: %s", e)
