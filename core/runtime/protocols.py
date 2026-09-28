"""Runtime service protocols — typed interfaces for runtime side-effects."""
from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class MemoryService(Protocol):
    # ``resource_scope`` carries the tenant/workspace partition for every
    # persisted artifact (architecture Rule 30).
    async def store_facts(self, ctx: Any, facts: list, *,
                          resource_scope: Any = None, tenant_id: str = "") -> int: ...
    async def search_facts(self, ctx: Any, query: str, **kwargs) -> list: ...
    async def get_user_facts(self, ctx: Any, user_id: str) -> list: ...


@runtime_checkable
class ObservationService(Protocol):
    async def publish(self, ctx: Any, observation: Any) -> None: ...


@runtime_checkable
class SchedulerService(Protocol):
    async def create_activity(self, ctx: Any, goal: str, **kwargs) -> str: ...
    async def get_queue(self, ctx: Any) -> list: ...


@runtime_checkable
class MetricsService(Protocol):
    def record(self, ctx: Any, metrics: dict) -> None: ...


@runtime_checkable
class EventBusProtocol(Protocol):
    async def publish(self, ctx: Any, event: Any) -> None: ...
    async def subscribe(self, ctx: Any, handler: Any) -> None: ...


@runtime_checkable
class ActivityService(Protocol):
    async def create_activity(self, ctx: Any, goal: str) -> Any: ...
    async def create_node(self, ctx: Any, activity_id: str, **kwargs) -> Any: ...


__all__ = [
    "MemoryService", "ObservationService", "SchedulerService",
    "MetricsService", "EventBusProtocol", "ActivityService",
]
