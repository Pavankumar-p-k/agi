"""core/history/service.py
Unified Conversation History Service backed by MemoryFacade.

Consolidates fragmented history implementations (WhatsApp, chat, builds, etc.)
into a single service that stores/retrieves via MemoryFacade.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Any

from memory.memory_facade import memory as memory_facade

logger = logging.getLogger(__name__)


class ConversationHistoryService:
    """Single source of truth for all conversation history."""

    def __init__(self, memory=None):
        self._memory = memory or memory_facade

    async def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Add a message to conversation history."""
        message_id = str(uuid.uuid4())
        entry = {
            "id": message_id,
            "session_id": session_id,
            "role": role,
            "content": content,
            "timestamp": datetime.utcnow().isoformat(),
            "metadata": metadata or {},
        }
        await self._memory.store_episodic(
            key=f"conversation:{session_id}:{message_id}",
            value=entry,
            metadata={"session_id": session_id, "role": role, "type": "conversation"},
        )
        return message_id

    async def get_history(
        self,
        session_id: str,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """Retrieve conversation history for a session."""
        # Search episodic memory for conversation entries
        results = await self._memory.search_episodic(
            query=f"session_id:{session_id}",
            limit=limit + offset,
        )
        # Filter and sort by timestamp
        conversations = [
            r for r in results
            if r.get("metadata", {}).get("type") == "conversation"
        ]
        conversations.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
        return conversations[offset:offset + limit]

    async def get_recent_context(
        self,
        session_id: str,
        max_tokens: int = 4000,
    ) -> list[dict[str, Any]]:
        """Get recent conversation context for LLM prompt."""
        history = await self.get_history(session_id, limit=50)
        # Format for LLM context
        context = []
        for entry in reversed(history):  # chronological order
            context.append({
                "role": entry.get("role"),
                "content": entry.get("content"),
            })
        return context

    async def add_build_event(
        self,
        project_name: str,
        event: str,
        data: dict[str, Any],
    ) -> str:
        """Add a build lifecycle event to history."""
        entry = {
            "type": "build_event",
            "project": project_name,
            "event": event,
            "data": data,
            "timestamp": datetime.utcnow().isoformat(),
        }
        key = f"build:{project_name}:{event}:{datetime.utcnow().timestamp()}"
        await self._memory.store_episodic(key=key, value=entry, metadata={"type": "build_event", "project": project_name})
        return key

    async def get_build_history(
        self,
        project_name: str,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Retrieve build history for a project."""
        results = await self._memory.search_episodic(
            query=f"project:{project_name} type:build_event",
            limit=limit,
        )
        return results

    async def add_agent_interaction(
        self,
        session_id: str,
        agent: str,
        action: str,
        input_data: dict[str, Any],
        output_data: dict[str, Any] | None = None,
    ) -> str:
        """Record an agent interaction for debugging/replay."""
        entry = {
            "type": "agent_interaction",
            "session_id": session_id,
            "agent": agent,
            "action": action,
            "input": input_data,
            "output": output_data,
            "timestamp": datetime.utcnow().isoformat(),
        }
        key = f"agent:{session_id}:{agent}:{action}:{datetime.utcnow().timestamp()}"
        await self._memory.store_episodic(key=key, value=entry, metadata={"type": "agent_interaction", "session_id": session_id})
        return key


# Singleton instance
_history_service: ConversationHistoryService | None = None


def get_history_service() -> ConversationHistoryService:
    """Get the singleton history service instance."""
    global _history_service
    if _history_service is None:
        _history_service = ConversationHistoryService()
    return _history_service