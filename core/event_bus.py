from __future__ import annotations

import asyncio
import fnmatch
import inspect
import json
import logging
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

from fastapi import WebSocket

logger = logging.getLogger(__name__)


# ── Constants ─────────────────────────────────────────────────────────────────

SYSTEM_NAMESPACE = "system"
"""Reserved namespace for core system events.  Plugins must not subscribe
to events with this namespace."""


# ── Data types ────────────────────────────────────────────────────────────────

@dataclass
class Event:
    type: str
    source: str
    payload: dict
    id: str = ""
    timestamp: str = ""
    priority: int = 0
    namespace: str = SYSTEM_NAMESPACE
    """Event namespace for isolation. ``system`` for core events,
    ``plugin`` for plugin events, ``workflow`` for workflow events."""
    resource_scope: dict | None = None
    """Canonical resource scope for tenant-aware routing.
    Every event that originates from a pipeline request MUST carry
    resource_scope to enable logical tenant partitioning."""

    def __post_init__(self):
        if not self.id:
            self.id = str(uuid.uuid4())
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()


@dataclass
class Subscription:
    pattern: str
    handler: Callable
    once: bool = False
    priority: int = 0
    namespace: str | None = None
    """Optional namespace filter.  When set, this subscription only receives
    events whose ``namespace`` matches (fnmatch).  ``None`` matches all."""
    tenant_id: str | None = None
    """Optional tenant filter.  When set, this subscription only receives
    events whose ``resource_scope.tenant_id`` matches.  ``__system__``
    receives system events."""
    _id: str = ""

    def __post_init__(self):
        if not self._id:
            self._id = str(uuid.uuid4())


# ── Canonical EventBus ────────────────────────────────────────────────────────

class EventBus:
    """Canonical event bus — async-first, typed, pattern-based, with WebSocket broadcast.

    Features:
      - Pattern subscription (exact, wildcard *, multi **)
      - Priority ordering
      - Async + sync publish
      - Streaming queue subscribers
      - In-memory event history ring buffer
      - Dispatch stats
      - WebSocket broadcast (session-scoped + global)
    """

    def __init__(self):
        self._subscriptions: list[Subscription] = []
        self._lock = asyncio.Lock()
        self._stats: dict[str, int] = {}
        self._event_queues: list[asyncio.Queue[dict]] = []
        self._history: list[dict] = []
        self._max_history = 100

        # WebSocket state
        self._ws_by_session: dict[str, set[WebSocket]] = defaultdict(set)
        self._ws_all: set[WebSocket] = set()

    # ── Pattern subscription ──────────────────────────────────

    def subscribe(self, pattern: str, handler: Callable,
                  priority: int = 0, once: bool = False,
                  namespace: str | None = None) -> Subscription:
        sub = Subscription(pattern=pattern, handler=handler,
                           priority=priority, once=once,
                           namespace=namespace)
        self._subscriptions.append(sub)
        self._subscriptions.sort(key=lambda s: -s.priority)
        ns_tag = f" [{namespace}]" if namespace else ""
        logger.debug("[EventBus] subscribed%s %s -> %s", ns_tag, pattern, handler.__name__)
        return sub

    def unsubscribe(self, sub: Subscription) -> None:
        if sub in self._subscriptions:
            self._subscriptions.remove(sub)

    # ── Streaming queue subscribers ───────────────────────────

    def subscribe_stream(self) -> asyncio.Queue[dict]:
        queue: asyncio.Queue[dict] = asyncio.Queue(maxsize=100)
        self._event_queues.append(queue)
        return queue

    def unsubscribe_stream(self, queue: asyncio.Queue[dict]) -> None:
        if queue in self._event_queues:
            self._event_queues.remove(queue)

    # ── WebSocket management ──────────────────────────────────

    def register_ws(self, ws: WebSocket, session_id: str | None = None) -> None:
        self._ws_all.add(ws)
        if session_id:
            self._ws_by_session[session_id].add(ws)

    def unregister_ws(self, ws: WebSocket) -> None:
        self._ws_all.discard(ws)
        for session_set in self._ws_by_session.values():
            session_set.discard(ws)

    async def _broadcast(self, event_data: dict) -> None:
        text = json.dumps(event_data)
        targets: set[WebSocket] = set(self._ws_all)
        session_id = event_data.get("session_id")
        if session_id and session_id in self._ws_by_session:
            targets |= self._ws_by_session[session_id]
        stale: list[WebSocket] = []
        for ws in targets:
            try:
                await ws.send_text(text)
            except Exception:
                stale.append(ws)
        for ws in stale:
            self.unregister_ws(ws)

    # ── Publish ───────────────────────────────────────────────

    async def publish(self, event: Event) -> None:
        self._stats[event.type] = self._stats.get(event.type, 0) + 1
        matched = []

        # Tenant-aware routing: extract tenant_id from resource_scope
        event_tenant = None
        if event.resource_scope and isinstance(event.resource_scope, dict):
            event_tenant = event.resource_scope.get("tenant_id")

        async with self._lock:
            for sub in self._subscriptions:
                if not self._matches(sub.pattern, event.type):
                    continue
                if not self._namespace_matches(sub.namespace, event.namespace):
                    continue
                # Tenant filtering: subscriptions can have a tenant_id attribute
                sub_tenant = getattr(sub, "tenant_id", None)
                if sub_tenant is not None and event_tenant is not None:
                    if sub_tenant != event_tenant and sub_tenant != "__system__":
                        continue
                matched.append(sub)

        for sub in matched:
            try:
                if inspect.iscoroutinefunction(sub.handler):
                    await sub.handler(event)
                else:
                    sub.handler(event)
            except Exception as e:
                logger.exception("[EventBus] handler %s failed for %s: %s",
                                 sub.handler.__name__, event.type, e)
            if sub.once:
                self._subscriptions.remove(sub)

        stream_event = {
            "channel": event.type, "type": event.type,
            "source": event.source, "payload": event.payload,
            "id": event.id, "timestamp": event.timestamp,
            "resource_scope": event.resource_scope,
        }
        for queue in self._event_queues:
            # Tenant filter for stream queues too (if they have tenant_id attr)
            q_tenant = getattr(queue, "_tenant_id", None)
            if q_tenant is not None and event_tenant is not None:
                if q_tenant != event_tenant and q_tenant != "__system__":
                    continue
            try:
                queue.put_nowait(stream_event)
            except asyncio.QueueFull:
                logger.debug("[EventBus] Dropped event for full stream queue: %s", event.type)

        self._history.append({
            "type": event.type, "source": event.source,
            "payload": event.payload, "timestamp": event.timestamp,
            "resource_scope": event.resource_scope,
        })
        if len(self._history) > self._max_history:
            self._history.pop(0)

        try:
            await self._broadcast(stream_event)
        except Exception:
            logger.debug("[EventBus] WebSocket broadcast skipped", exc_info=True)

    def _matches(self, pattern: str, event_type: str) -> bool:
        if pattern == "**":
            return True
        if "/" in pattern:
            return fnmatch.fnmatch(event_type, pattern)
        return fnmatch.fnmatch(event_type, pattern)

    @staticmethod
    def _namespace_matches(sub_namespace: str | None,
                           event_namespace: str) -> bool:
        if sub_namespace is None:
            return True
        if sub_namespace == event_namespace:
            return True
        return fnmatch.fnmatch(event_namespace, sub_namespace)

    def publish_sync(self, event: Event) -> None:
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.ensure_future(self.publish(event))
            else:
                loop.run_until_complete(self.publish(event))
        except RuntimeError:
            asyncio.create_task(self.publish(event))

    # ── In-process handler API (legacy workflow compat) ───────

    def on(self, event_type: str, handler: Callable[[Any], None]) -> None:
        self.subscribe(event_type, handler, namespace=SYSTEM_NAMESPACE)

    def off(self, event_type: str, handler: Callable[[Any], None]) -> None:
        for sub in list(self._subscriptions):
            if sub.pattern == event_type and sub.handler == handler:
                self.unsubscribe(sub)
                return

    def emit(self, event: Any) -> None:
        if isinstance(event, MJEvent):
            ev = Event(
                type=event.type,
                source="workflow",
                payload=event.payload,
                namespace="workflow",
            )
            self.publish_sync(ev)
        elif isinstance(event, Event):
            self.publish_sync(event)
        else:
            self.publish_sync(Event(type=str(event), source="system", payload={}))

    # ── Introspection ─────────────────────────────────────────

    def stats(self) -> dict:
        return dict(self._stats)

    @property
    def history(self) -> list[dict]:
        return list(self._history)

    def clear_history(self) -> None:
        self._history.clear()

    def clear(self) -> None:
        self._subscriptions.clear()
        self._stats.clear()
        self._event_queues.clear()
        self._history.clear()
        self._ws_all.clear()
        self._ws_by_session.clear()


# ── Global singleton ──────────────────────────────────────────

global_event_bus = EventBus()


def register_default_subscribers() -> None:
    """Register subscribers for events that currently have zero subscribers.

    This ensures telemetry-relevant events (rag.*, workflow.idempotency_hit,
    config.validation_error, memory.*, database.*) are at minimum logged.
    Call once during application startup (lifespan).
    """
    _log_subscriber = lambda event: logger.info(
        "[EventBus] %s (source=%s, ns=%s)", event.type, event.source, event.namespace
    )
    _subscribers = [
        RAG_DOCUMENTS_RETRIEVED,
        RAG_DOCUMENT_SCORED,
        RAG_RELEVANCE_FEEDBACK,
        WORKFLOW_IDEMPOTENCY_HIT,
        CONFIG_VALIDATION_ERROR,
        MEMORY_FACT_CONFLICT,
        MEMORY_INDEX_UPDATED,
        DATABASE_CONNECTION_POOLED,
    ]
    for event_type in _subscribers:
        global_event_bus.subscribe(event_type, _log_subscriber)
    logger.info("[EventBus] Registered %d default subscribers", len(_subscribers))


# ── System event types ─────────────────────────────────────────────────────────

CONFIG_CHANGED = "config.changed"
CONFIG_RELOADED = "config.reloaded"
CONFIG_VALIDATION_ERROR = "config.validation_error"

RAG_DOCUMENTS_RETRIEVED = "rag.documents_retrieved"
RAG_DOCUMENT_SCORED = "rag.document_scored"
RAG_RELEVANCE_FEEDBACK = "rag.relevance_feedback"

WORKFLOW_IDEMPOTENCY_HIT = "workflow.idempotency_hit"

MEMORY_FACT_CONFLICT = "memory.fact_conflict"
MEMORY_INDEX_UPDATED = "memory.index_updated"

DATABASE_CONNECTION_POOLED = "database.connection_pooled"


# ── Workflow event types ──────────────────────────────────────────────────────

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
IDEMPOTENCY_HIT = "idempotency_hit"

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


# ── Build event types ──────────────────────────────────────────────────────────

BUILD_STARTED = "build.started"
BUILD_COMPLETED = "build.completed"
BUILD_FAILED = "build.failed"
BUILD_FIX_REQUESTED = "build.fix_requested"


# ── Execution trace/decision event types ───────────────────────────────────────
EXECUTION_TRACE = "execution.trace"
EXECUTION_DECISION = "execution.decision"
EXECUTION_PROGRESS = "execution.progress"


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


# ── Legacy singleton (workflow compat) ────────────────────────────────────────

_bus: EventBus | None = None


def get_bus() -> EventBus:
    global _bus
    if _bus is None:
        _bus = EventBus()
    return _bus


def reset_bus() -> None:
    global _bus
    _bus = None


def emit_event(
    type: str,
    payload: dict | None = None,
    session_id: str | None = None,
    goal_id: str | None = None,
) -> MJEvent:
    event = MJEvent(type=type, payload=payload, session_id=session_id, goal_id=goal_id)
    get_bus().emit(event)
    return event


# ── Backward-compat helpers (legacy brain.event_bus API) ─────

_sub_map: dict[tuple[str, Callable], Subscription] = {}


def subscribe_event(pattern: str, handler: Callable) -> None:
    sub = global_event_bus.subscribe(pattern, handler)
    _sub_map[(pattern, handler)] = sub


def unsubscribe_event(pattern: str, handler: Callable) -> None:
    sub = _sub_map.pop((pattern, handler), None)
    if sub:
        global_event_bus.unsubscribe(sub)


def fire_event(event: str, data=None) -> None:
    payload = data if isinstance(data, dict) else {"data": data}
    ev = Event(type=event, source="system", payload=payload, namespace=SYSTEM_NAMESPACE)
    global_event_bus.publish_sync(ev)


def get_task_scheduler():
    try:
        from core.scheduler import scheduler
        return scheduler
    except ImportError:
        logger.warning("scheduler not available")
        return None


# ── PluginEventBus adapter (deprecated) ──────────────────────

import warnings as _warnings


class PluginEventBus:
    """Adapter that routes plugin events through the canonical bus + plugin hooks.

    .. deprecated::
        Use ``global_event_bus`` directly with ``namespace="plugin"`` instead.
        PluginEventBus will be removed in a future release.
    """

    _instance: PluginEventBus | None = None

    def __init__(self):
        self._bus = global_event_bus
        self._direct_handlers: dict[str, list[Callable]] = {}

    @classmethod
    def instance(cls) -> PluginEventBus:
        _warnings.warn(
            "PluginEventBus is deprecated — use global_event_bus with namespace='plugin' instead",
            DeprecationWarning, stacklevel=2,
        )
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def subscribe(self, event_type: str, handler: Callable) -> None:
        _warnings.warn(
            "PluginEventBus.subscribe() is deprecated — use global_event_bus.subscribe()",
            DeprecationWarning, stacklevel=2,
        )
        self._direct_handlers.setdefault(event_type, []).append(handler)
        self._bus.subscribe(event_type, handler, namespace="plugin")

    def unsubscribe(self, event_type: str, handler: Callable) -> None:
        self._direct_handlers[event_type] = [
            h for h in self._direct_handlers.get(event_type, []) if h is not handler
        ]

    async def emit(self, event_type: str, **data: Any) -> list[Any]:
        _warnings.warn(
            "PluginEventBus.emit() is deprecated — use global_event_bus.publish()",
            DeprecationWarning, stacklevel=2,
        )
        results = []

        for handler in self._direct_handlers.get(event_type, []):
            try:
                if asyncio.iscoroutinefunction(handler):
                    r = await handler(event_type=event_type, **data)
                else:
                    r = handler(event_type=event_type, **data)
                results.append(r)
            except Exception as e:
                logger.exception("[PluginEventBus] Handler %s failed on %s: %s",
                                 getattr(handler, "__name__", "?"), event_type, e)

        ev = Event(type=event_type, source="plugin", payload=data, namespace="plugin")
        await self._bus.publish(ev)

        try:
            from core.plugins.base import plugin_registry
            await plugin_registry.run_hook(event_type, **data)
        except Exception:
            logger.debug("PluginEventBus run_hook failed", exc_info=True)

        return results

    @property
    def history(self) -> list[dict]:
        return self._bus.history

    def clear_history(self) -> None:
        self._bus.clear_history()
