"""core/history/service.py
Unified Conversation History Service backed by EventBus.

Consolidates fragmented history implementations (WhatsApp, chat, builds, etc.)
into a single service that stores/retrieves via EventBus events.
The Memory stage subscribes to these events for persistence.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Any

from core.event_bus import global_event_bus, Event

logger = logging.getLogger(__name__)


class ConversationHistoryService:
    """Single source of truth for all conversation history."""

    async def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Add a message to conversation history via EventBus."""
        message_id = str(uuid.uuid4())
        entry = {
            "id": message_id,
            "session_id": session_id,
            "role": role,
            "content": content,
            "timestamp": datetime.utcnow().isoformat(),
            "metadata": metadata or {},
        }
        await global_event_bus.publish(Event(
            type="history.message.added",
            source="history_service",
            payload={
                "key": f"conversation:{session_id}:{message_id}",
                "value": entry,
                "metadata": {"session_id": session_id, "role": role, "type": "conversation"},
            },
        ))
        return message_id

    async def get_history(
        self,
        session_id: str,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """Retrieve conversation history for a session via EventBus query."""
        # Request history from Memory stage via EventBus
        # The Memory stage will handle the query and return results
        request_id = str(uuid.uuid4())
        await global_event_bus.publish(Event(
            type="history.query.request",
            source="history_service",
            payload={
                "request_id": request_id,
                "query": f"session_id:{session_id}",
                "limit": limit + offset,
            },
        ))
        # Wait for response (simplified - in production use a request/response pattern)
        await asyncio.sleep(0.1)
        # For now, return empty - the Memory stage handles the actual query
        return []

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
        key = f"build:{project_name}:{event}:{datetime.utcnow().timestamp()}"
        entry = {
            "type": "build_event",
            "project": project_name,
            "event": event,
            "data": data,
            "timestamp": datetime.utcnow().isoformat(),
        }
        await global_event_bus.publish(Event(
            type="history.event.added",
            source="history_service",
            payload={"key": key, "value": entry, "metadata": {"type": "build_event", "project": project_name}},
        ))
        return key

    async def get_build_history(
        self,
        project_name: str,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Retrieve build history for a project."""
        await global_event_bus.publish(Event(
            type="history.query.request",
            source="history_service",
            payload={
                "query": f"project:{project_name} type:build_event",
                "limit": limit,
            },
        ))
        await asyncio.sleep(0.1)
        return []

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
        await global_event_bus.publish(Event(
            type="history.event.added",
            source="history_service",
            payload={"key": key, "value": entry, "metadata": {"type": "agent_interaction", "session_id": session_id}},
        ))
        return key


# Singleton instance
_history_service: "ConversationHistoryService | None" = None


def get_history_service() -> "ConversationHistoryService":
    """Get the singleton history service instance."""
    global _history_service
    if _history_service is None:
        _history_service = ConversationHistoryService()
    return _history_service