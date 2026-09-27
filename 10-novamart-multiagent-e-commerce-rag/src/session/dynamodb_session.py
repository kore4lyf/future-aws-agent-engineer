"""
session/dynamodb_session.py
============================
DynamoDB backed conversation manager for persistent session memory.

Stores conversation history in DynamoDB so that multi turn conversations
retain earlier messages across separate agent invocations without relying
solely on AgentCore Memory.
"""

from __future__ import annotations

import json
import logging
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent))

import config
from strands.agent.conversation_manager import ConversationManager
from strands.hooks.events import AfterInvocationEvent
from strands.types.content import Message

logger = logging.getLogger(__name__)


class DynamoDBSessionManager(ConversationManager):
    """
    Conversation manager that persists conversation history to DynamoDB.

    After each agent invocation the full message list is saved to the
    AgentSessionsTable. When a session is loaded the previous messages
    are returned so multi turn conversations retain earlier context.
    """

    def __init__(
        self,
        table_name: str | None = None,
        ttl_days: int = 30,
        proactive_compression: bool | dict | None = True,
    ) -> None:
        super().__init__(proactive_compression=proactive_compression)
        self.table_name = table_name or getattr(config, 'AGENT_SESSIONS_TABLE', '')
        self.ttl_days = ttl_days
        self._current_session_id: str | None = None

    def _table(self):
        import boto3
        return boto3.resource('dynamodb', region_name=config.AWS_REGION).Table(self.table_name)

    def register_hooks(self, registry: Any, **kwargs: Any) -> None:
        super().register_hooks(registry, **kwargs)
        registry.add_callback(AfterInvocationEvent, self._on_after_invocation)

    def _on_after_invocation(self, event: AfterInvocationEvent) -> None:
        session_id = getattr(event.agent, 'session_id', None) or self._current_session_id
        if not session_id:
            return
        try:
            messages = list(event.agent.messages) if hasattr(event.agent, 'messages') else []
            self._persist(session_id, messages)
        except Exception:
            logger.debug("DynamoDBSessionManager persist failed", exc_info=True)

    def _persist(self, session_id: str, messages: list[Message]) -> None:
        if not self.table_name or not messages:
            return
        table = self._table()
        payload = []
        for m in messages:
            if isinstance(m, dict):
                payload.append(m)
            else:
                payload.append(dict(m))
        table.put_item(Item={
            'session_id': session_id,
            'messages': payload,
            'message_count': len(payload),
            'ttl': int(time.time()) + (self.ttl_days * 86400),
        })

    def load_session(self, session_id: str) -> list[Message] | None:
        if not self.table_name or not session_id:
            return None
        try:
            item = self._table().get_item(Key={'session_id': session_id}).get('Item')
            if not item:
                return None
            return item.get('messages', []) or None
        except Exception:
            logger.debug("DynamoDBSessionManager load failed", exc_info=True)
            return None

    def restore_from_session(self, state: dict[str, Any]) -> list[Message] | None:
        super().restore_from_session(state)
        return self.load_session(state.get('session_id', ''))

    def get_state(self) -> dict[str, Any]:
        return {
            'session_id': self._current_session_id,
            **super().get_state(),
        }

    def apply_management(self, agent: Any, **kwargs: Any) -> None:
        pass

    def reduce_context(self, agent: Any, e: Exception | None = None, **kwargs: Any) -> None:
        pass
