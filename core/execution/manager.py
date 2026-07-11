from __future__ import annotations

import logging
import uuid
from typing import Any

from core.event_bus import Event, global_event_bus
from core.execution.context import ExecutionContext
from core.workflow.engine import WorkflowEngine
from core.workflow.models import StepDefinition, WorkflowStatus

logger = logging.getLogger(__name__)

_EXECUTION_NAMESPACE = "execution"


class ExecutionManager:
    """Single orchestrator for all execution paths.

    Wraps ``WorkflowEngine`` for orchestration, ``EventBus`` for lifecycle
    events, and ``MemoryFacade`` for execution traces.

    Both ``ControlLoop`` and ``AutomationLoop`` should use this manager
    instead of implementing execution concerns themselves.
    """

    def __init__(self, engine: WorkflowEngine | None = None) -> None:
        self._engine = engine or WorkflowEngine()
        self._bus = global_event_bus
        self._memory = None

    @property
    def engine(self) -> WorkflowEngine:
        return self._engine

    # ── Workflow lifecycle ────────────────────────────────────────────

    async def start_workflow(
        self,
        workflow_type: str,
        steps: list[StepDefinition],
        context: ExecutionContext,
        *,
        timeout_seconds: int | None = None,
        retry_budget: int = 0,
    ) -> str:
        wf = await self._engine.start_workflow(
            workflow_type=workflow_type,
            steps=steps,
            session_id=context.user_id or "",
            owner=context.user_id,
            timeout_seconds=timeout_seconds,
            execution_context=context.metadata,
            retry_budget=retry_budget,
        )
        context.workflow_id = wf.workflow_id
        self._publish_event("workflow_started", context, {
            "workflow_type": workflow_type,
            "step_count": len(steps),
        })
        self.record_trace(context, "workflow_start", f"Started {workflow_type}", True)
        return wf.workflow_id

    async def cancel(self, context: ExecutionContext) -> bool:
        result = await self._engine.cancel_workflow(context.workflow_id)
        cancelled = result is not None
        if cancelled:
            self._publish_event("workflow_cancelled", context)
            self.record_trace(context, "workflow_cancel", "Cancelled by user", False)
        return cancelled

    async def get_status(self, context: ExecutionContext) -> dict | None:
        return await self._engine.get_status(context.workflow_id)

    async def resume(self, context: ExecutionContext) -> bool:
        result = await self._engine.resume_workflow(context.workflow_id)
        resumed = result is not None
        if resumed:
            self._publish_event("workflow_resumed", context)
            self.record_trace(context, "workflow_resume", "Resumed after interruption", True)
        return resumed

    # ── Event publication ─────────────────────────────────────────────

    def _publish_event(
        self,
        event_type: str,
        context: ExecutionContext,
        extra_payload: dict | None = None,
    ) -> None:
        payload = context.to_event_payload()
        if extra_payload:
            payload.update(extra_payload)
        event = Event(
            type=f"execution.{event_type}",
            source=context.source or "execution",
            payload=payload,
            namespace=_EXECUTION_NAMESPACE,
        )
        self._bus.publish_sync(event)

    def publish_progress(
        self,
        context: ExecutionContext,
        message: str,
        progress_pct: float | None = None,
    ) -> None:
        extra = {"message": message}
        if progress_pct is not None:
            extra["progress_pct"] = progress_pct
        self._publish_event("progress", context, extra)

    def publish_completed(self, context: ExecutionContext, result: dict | None = None) -> None:
        context.status = "completed"
        self._publish_event("completed", context, result)

    def publish_failed(self, context: ExecutionContext, error: str) -> None:
        context.status = "failed"
        self._publish_event("failed", context, {"error": error})

    # ── Memory recording ──────────────────────────────────────────────

    def record_trace(
        self,
        context: ExecutionContext,
        action_name: str,
        observation: str,
        success: bool = True,
        action_params: dict | None = None,
        duration_ms: float = 0.0,
        tags: list[str] | None = None,
    ) -> None:
        try:
            from memory.memory_facade import memory
            memory.store_trace(
                action_name=action_name,
                action_params=action_params,
                observation=observation,
                success=success,
                duration_ms=duration_ms,
                task_id=context.workflow_id,
                context=context.to_event_payload(),
                tags=tags or [],
                user_id=context.user_id or "default",
            )
        except Exception as e:
            logger.debug("Memory trace recording skipped: %s", e)

    def record_decision(
        self,
        context: ExecutionContext,
        decision: str,
        outcome: str,
        success: bool = True,
    ) -> None:
        try:
            from memory.memory_facade import memory
            memory.store_decision(
                context=context.phase,
                decision=decision,
                outcome=outcome,
                success=success,
                user_id=context.user_id or "default",
            )
        except Exception as e:
            logger.debug("Memory decision recording skipped: %s", e)

    # ── Convenience factory ───────────────────────────────────────────

    @staticmethod
    def create_context(
        *,
        source: str = "",
        user_id: str = "",
        request_id: str = "",
        metadata: dict | None = None,
    ) -> ExecutionContext:
        return ExecutionContext(
            workflow_id="",
            execution_id=uuid.uuid4().hex,
            request_id=request_id or uuid.uuid4().hex,
            user_id=user_id,
            source=source,
            phase="init",
            status="started",
            metadata=metadata or {},
        )
