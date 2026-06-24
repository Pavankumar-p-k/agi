"""Executor registry — maps activity types to concrete executor callables.

Allows any subsystem (research, build, browser, email) to register an
executor function. The scheduler picks the right executor based on the
activity's node_type or metadata.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Awaitable, Callable

logger = logging.getLogger(__name__)

ExecutorFn = Callable[..., Awaitable[dict[str, Any]]]


class SchedulerRegistry:
    """Maps activity node types to executor functions.

    Usage:
        registry = SchedulerRegistry()
        registry.register("research", do_browser_research)
        registry.register("build", build_project)

        executor = registry.get("research")  # returns do_browser_research
        result = await executor(question="...")
    """

    def __init__(self):
        self._executors: dict[str, ExecutorFn] = {}

    def register(self, activity_type: str, executor: ExecutorFn) -> None:
        """Register an executor for an activity type.

        Args:
            activity_type: e.g. "research", "build", "email", "browser"
            executor: async callable that takes **kwargs and returns a dict
        """
        if not asyncio.iscoroutinefunction(executor):
            logger.warning(
                "SchedulerRegistry: %s executor for %s is not async",
                executor.__name__, activity_type,
            )
        self._executors[activity_type] = executor
        logger.debug("SchedulerRegistry: registered %s → %s", activity_type, executor.__name__)

    def get(self, activity_type: str) -> ExecutorFn | None:
        return self._executors.get(activity_type)

    def unregister(self, activity_type: str) -> None:
        self._executors.pop(activity_type, None)

    def list_types(self) -> list[str]:
        return list(self._executors.keys())

    def resolve(self, activity_type: str, default: ExecutorFn | None = None) -> ExecutorFn | None:
        """Resolve an executor, falling back to a default."""
        return self._executors.get(activity_type) or default


# Module-level convenience
_registry: SchedulerRegistry | None = None


def get_registry() -> SchedulerRegistry:
    global _registry
    if _registry is None:
        _registry = SchedulerRegistry()
    return _registry
