from __future__ import annotations

import asyncio
import json
import logging
import uuid
from collections import defaultdict
from datetime import datetime
from typing import Any, Callable

from fastapi import WebSocket

logger = logging.getLogger(__name__)

# ── Event type constants (legacy workflow events) ────────────────────────────

WORKFLOW_STARTED = "workflow_started"
WORKFLOW_RESUMED = "workflow_resumed"
STEP_STARTED = "step_started"
STEP_COMPLETED = "step_completed"
STEP_FAILED = "step_failed"
WORKFLOW_COMPLETED = "workflow_completed"
WORKFLOW_FAILED = "workflow_failed"
WORKFLOW_CANCELLED = "workflow_cancelled"
WORKFLOW_RECOVERED = "workflow_recovered"
COMPENSATION_STARTED = "compensation_started"
COMPENSATION_STEP_STARTED = "compensation_step_started"
COMPENSATION_STEP_COMPLETED = "compensation_step_completed"
COMPENSATION_STEP_FAILED = "compensation_step_failed"
WORKFLOW_COMPENSATED = "workflow_compensated"
COMPENSATION_FAILED = "compensation_failed"

# ── New MJ event types ───────────────────────────────────────────────────────

GOAL_CREATED = "goal_created"
GOAL_UPDATED = "goal_updated"
GOAL_COMPLETED = "goal_completed"
GOAL_FAILED = "goal_failed"
NODE_CREATED = "node_created"
NODE_UPDATED = "node_updated"
NODE_COMPLETED = "node_completed"
NODE_FAILED = "node_failed"
NODE_SKIPPED = "node_skipped"
ARTIFACT_CREATED = "artifact_created"
CONFIDENCE_UPDATED = "confidence_updated"
ESTIMATE_UPDATED = "estimate_updated"
NEED_INPUT = "need_input"
WARNING = "warning"
ERROR = "error"
MILESTONE = "milestone"
FOCUS_CHANGED = "focus_changed"


class WorkflowEvent:
    """Legacy workflow event — kept for backward compatibility."""

    def __init__(
        self,
        event_id: str,
        workflow_id: str,
        event_type: str,
        data: dict | None = None,
        timestamp: datetime | None = None,
    ) -> None:
        self.event_id = event_id
        self.workflow_id = workflow_id
        self.event_type = event_type
        self.data = data or {}
        self.timestamp = timestamp or datetime.utcnow()


# ── Unified Event Bus ────────────────────────────────────────────────────────


class MJEvent:
    """Typed event for the unified MJ event bus."""

    def __init__(
        self,
        type: str,
        payload: dict | None = None,
        session_id: str | None = None,
        goal_id: str | None = None,
        timestamp: str | None = None,
    ) -> None:
        self.id = uuid.uuid4().hex[:12]
        self.type = type
        self.payload = payload or {}
        self.session_id = session_id
        self.goal_id = goal_id
        self.timestamp = timestamp or datetime.utcnow().isoformat()

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type,
            "payload": self.payload,
            "session_id": self.session_id,
            "goal_id": self.goal_id,
            "timestamp": self.timestamp,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict())


class EventBus:
    """Unified event bus — in-process pub/sub + WebSocket broadcast."""

    def __init__(self) -> None:
        self._handlers: dict[str, list[Callable[[MJEvent], None]]] = defaultdict(list)
        self._ws_by_session: dict[str, set[WebSocket]] = defaultdict(set)
        self._ws_all: set[WebSocket] = set()

    # ── In-process handlers ──────────────────────────────────────────────

    def on(self, event_type: str, handler: Callable[[MJEvent], None]) -> None:
        self._handlers[event_type].append(handler)

    def off(self, event_type: str, handler: Callable[[MJEvent], None]) -> None:
        handlers = self._handlers.get(event_type, [])
        if handler in handlers:
            handlers.remove(handler)

    def emit(self, event: MJEvent) -> None:
        """Publish an event to both in-process handlers and WebSocket clients."""
        for handler in self._handlers.get(event.type, []):
            try:
                handler(event)
            except Exception as e:
                logger.warning("EventBus handler error for %s: %s", event.type, e)

        for handler in self._handlers.get("*", []):
            try:
                handler(event)
            except Exception as e:
                logger.warning("EventBus wildcard handler error: %s", e)

        try:
            asyncio.create_task(self._broadcast(event))
        except RuntimeError:
            pass  # no event loop running — WebSocket broadcast skipped

    # ── WebSocket management ─────────────────────────────────────────────

    def register_ws(self, ws: WebSocket, session_id: str | None = None) -> None:
        self._ws_all.add(ws)
        if session_id:
            self._ws_by_session[session_id].add(ws)

    def unregister_ws(self, ws: WebSocket) -> None:
        self._ws_all.discard(ws)
        for session_set in self._ws_by_session.values():
            session_set.discard(ws)

    async def _broadcast(self, event: MJEvent) -> None:
        """Send event to matching WebSocket clients."""
        text = event.to_json()
        targets: set[WebSocket] = set(self._ws_all)

        if event.session_id and event.session_id in self._ws_by_session:
            targets |= self._ws_by_session[event.session_id]

        stale: list[WebSocket] = []
        for ws in targets:
            try:
                await ws.send_text(text)
            except Exception:
                stale.append(ws)

        for ws in stale:
            self.unregister_ws(ws)


# ── Global singleton ─────────────────────────────────────────────────────────

_bus: EventBus | None = None


def get_bus() -> EventBus:
    global _bus
    if _bus is None:
        _bus = EventBus()
    return _bus


def reset_bus() -> None:
    global _bus
    _bus = None


# ── Convenience helpers ──────────────────────────────────────────────────────


def emit(
    type: str,
    payload: dict | None = None,
    session_id: str | None = None,
    goal_id: str | None = None,
) -> MJEvent:
    event = MJEvent(
        type=type,
        payload=payload,
        session_id=session_id,
        goal_id=goal_id,
    )
    get_bus().emit(event)
    return event
