from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from core.runtime.context import RuntimeContext
from core.runtime.protocols import (
    ActivityService,
    EventBus,
    MemoryService,
    MetricsService,
    ObservationService,
    SchedulerService,
)


@dataclass
class RuntimeServices:
    """Container for injected runtime service dependencies.

    Production wires real implementations via ``RuntimeRegistry``.
    Replay tests inject fakes via this container.
    """

    memory: MemoryService
    observation: ObservationService
    scheduler: SchedulerService
    metrics: MetricsService
    event_bus: EventBus
    activity: ActivityService


class ExecutionRuntime:
    """Dependency-injected execution runtime.

    Accepts a ``RuntimeServices`` container and a ``RuntimeContext``
    instead of importing global singletons.  This keeps Execution
    agnostic of how services are constructed.
    """

    def __init__(self, services: RuntimeServices) -> None:
        self._services = services
        self._step_results: list[dict[str, Any]] = []

    @property
    def services(self) -> RuntimeServices:
        return self._services

    async def execute(
        self,
        ctx: RuntimeContext,
        plan: dict[str, Any] | None = None,
        raw_input: str | None = None,
    ) -> dict[str, Any]:
        """Execute a plan or simple input within *ctx*."""
        if plan and plan.get("steps"):
            return await self._execute_plan(ctx, plan)
        return await self._execute_simple(ctx, raw_input or "")

    async def _execute_plan(
        self, ctx: RuntimeContext, plan: dict[str, Any]
    ) -> dict[str, Any]:
        steps = plan.get("steps", [])
        combined: list[str] = []
        for i, step in enumerate(steps):
            intent = step.get("intent", "respond")
            result = await self._run_step(ctx, step)
            self._step_results.append(result)
            await self._services.observation.publish(ctx, result)
            text = result.get("text", "")
            if text:
                combined.append(text)
            if result.get("error"):
                break
        output = "\n\n".join(combined)
        self._services.metrics.record(ctx, {"steps": len(steps), "tokens": 0})
        return {"text": output, "steps": self._step_results}

    async def _execute_simple(
        self, ctx: RuntimeContext, raw_input: str
    ) -> dict[str, Any]:
        result = {"text": "ok", "input": raw_input}
        self._step_results.append(result)
        await self._services.observation.publish(ctx, result)
        self._services.metrics.record(ctx, {"simple": True})
        return {"text": result["text"]}

    async def _run_step(
        self, ctx: RuntimeContext, step: dict[str, Any]
    ) -> dict[str, Any]:
        # Placeholder — actual step execution delegates to provider manager
        return {"text": f"executed: {step.get('objective', '')}", "provider": "runtime"}
