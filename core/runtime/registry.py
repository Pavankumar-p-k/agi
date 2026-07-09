from __future__ import annotations

from typing import Any

from core.runtime.context import RuntimeContext
from core.runtime.providers import ExecutionRuntime, RuntimeServices
from core.runtime.protocols import (
    ActivityService,
    EventBus,
    MemoryService,
    MetricsService,
    ObservationService,
    SchedulerService,
)

# Module-level singleton
_registry_instance: RuntimeRegistry | None = None


class RuntimeRegistry:
    """Single place that owns construction of all runtime services.

    Production wires real implementations.  Tests replace the registry
    to inject fakes.

    Only ``RuntimeRegistry`` may construct ``RuntimeServices`` (Rule 32).
    """

    def __init__(self) -> None:
        self._services: RuntimeServices | None = None

    def build(self) -> RuntimeServices:
        """Build the production service graph.

        Called once at startup.  Subsequent calls return the same
        instance.
        """
        if self._services is not None:
            return self._services

        self._services = RuntimeServices(
            memory=self._build_memory(),
            observation=self._build_observation(),
            scheduler=self._build_scheduler(),
            metrics=self._build_metrics(),
            event_bus=self._build_event_bus(),
            activity=self._build_activity(),
        )
        return self._services

    def build_with(
        self,
        *,
        memory: MemoryService | None = None,
        observation: ObservationService | None = None,
        scheduler: SchedulerService | None = None,
        metrics: MetricsService | None = None,
        event_bus: EventBus | None = None,
        activity: ActivityService | None = None,
    ) -> RuntimeServices:
        """Build with optional override services (for tests)."""
        base = self.build()
        self._services = RuntimeServices(
            memory=memory or base.memory,
            observation=observation or base.observation,
            scheduler=scheduler or base.scheduler,
            metrics=metrics or base.metrics,
            event_bus=event_bus or base.event_bus,
            activity=activity or base.activity,
        )
        return self._services

    def create_execution_runtime(self, services: RuntimeServices | None = None) -> ExecutionRuntime:
        """Create an ``ExecutionRuntime`` wired to *services* (or the registry's)."""
        svc = services or self.build()
        return ExecutionRuntime(services=svc)

    # ── Private builders (subclasses override for different wiring) ──────────

    def _build_memory(self) -> MemoryService:
        import importlib as _il
        return _il.import_module("memory.fact_store").FactStore()  # type: ignore[return-value]

    def _build_observation(self) -> ObservationService:
        from core.observation.hub import ObservationHub, get_hub

        return get_hub()

    def _build_scheduler(self) -> SchedulerService:
        from core.scheduler.queue import SchedulerQueue

        return SchedulerQueue()  # type: ignore[return-value]

    def _build_metrics(self) -> MetricsService:
        from core.pipeline.architecture_metrics import ArchitectureMetrics

        return ArchitectureMetrics  # type: ignore[return-value]

    def _build_event_bus(self) -> EventBus:
        from core.event_bus import global_event_bus

        return global_event_bus

    def _build_activity(self) -> ActivityService:
        import importlib as _il
        ActivityManager = _il.import_module("core.activity.manager").ActivityManager

        return ActivityManager()  # type: ignore[return-value]


def get_registry() -> RuntimeRegistry:
    global _registry_instance
    if _registry_instance is None:
        _registry_instance = RuntimeRegistry()
    return _registry_instance


def set_registry(registry: RuntimeRegistry | None) -> None:
    global _registry_instance
    _registry_instance = registry
