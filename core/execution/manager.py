from __future__ import annotations

import uuid
from typing import Any

from core.event_bus import Event, global_event_bus

from .context import ExecutionContext


class ExecutionManager:
    """Thin orchestration layer over WorkflowEngine with event publishing
    and memory recording."""

    def __init__(self, engine: Any = None) -> None:
        self._engine = engine
        self._bus = global_event_bus

    @property
    def engine(self):
        if self._engine is None:
            from core.workflow.engine import WorkflowEngine

            self._engine = WorkflowEngine()
        return self._engine

    @staticmethod
    def create_context(source: str = "", user_id: str | None = None,
                       **kwargs) -> ExecutionContext:
        kwargs.setdefault("request_id", str(uuid.uuid4()))
        return ExecutionContext(
            execution_id=str(uuid.uuid4()),
            source=source,
            user_id=user_id if user_id is not None else "",
            **kwargs,
        )

    # ── Workflow lifecycle ────────────────────────────────────────────

    async def start_workflow(self, workflow_type: str, steps: list,
                             ctx: ExecutionContext, timeout_seconds: int | None = None,
                             retry_budget: int = 0) -> str:
        wf = await self.engine.start_workflow(
            workflow_type=workflow_type,
            steps=steps,
            session_id=ctx.user_id,
            owner=ctx.user_id,
            timeout_seconds=timeout_seconds,
            execution_context=ctx.metadata,
            retry_budget=retry_budget,
        )
        workflow_id = getattr(wf, "workflow_id", "") or ""
        ctx.workflow_id = workflow_id
        self._bus.publish_sync(Event(
            type="execution.workflow_started",
            payload={
                "workflow_type": workflow_type,
                "step_count": len(steps),
                "workflow_id": workflow_id,
            },
        ))
        self.record_trace(
            ctx, "workflow_start", f"workflow {workflow_type} started", True
        )
        return workflow_id

    async def cancel(self, ctx: ExecutionContext) -> bool:
        result = await self.engine.cancel_workflow(ctx.workflow_id)
        if not result:
            return False
        self._bus.publish_sync(Event(
            type="execution.workflow_cancelled",
            payload={"workflow_id": ctx.workflow_id},
        ))
        return True

    async def get_status(self, ctx: ExecutionContext):
        return await self.engine.get_status(ctx.workflow_id)

    async def resume(self, ctx: ExecutionContext) -> bool:
        result = await self.engine.resume_workflow(ctx.workflow_id)
        if not result:
            return False
        self._bus.publish_sync(Event(
            type="execution.workflow_resumed",
            payload={"workflow_id": ctx.workflow_id},
        ))
        return True

    # ── Event publishing ──────────────────────────────────────────────

    def publish_progress(self, ctx: ExecutionContext, message: str,
                         progress_pct: float | None = None) -> None:
        payload: dict[str, Any] = {"message": message}
        if progress_pct is not None:
            payload["progress_pct"] = progress_pct
        self._bus.publish_sync(Event(type="execution.progress", payload=payload))

    def publish_completed(self, ctx: ExecutionContext,
                          result: dict | None = None) -> None:
        ctx.status = "completed"
        self._bus.publish_sync(Event(
            type="execution.completed",
            payload={"workflow_id": ctx.workflow_id, "result": result},
        ))

    def publish_failed(self, ctx: ExecutionContext, error: str) -> None:
        ctx.status = "failed"
        self._bus.publish_sync(Event(
            type="execution.failed",
            payload={"workflow_id": ctx.workflow_id, "error": error},
        ))

    # ── Memory recording (never raises) ───────────────────────────────

    def record_trace(self, ctx: ExecutionContext, action: str,
                     observation: str, success: bool,
                     action_params: dict | None = None,
                     duration_ms: float | None = None,
                     tags: list | None = None) -> None:
        try:
            from memory import memory_facade

            memory_facade.memory.store_trace(
                action_name=action,
                action_params=dict(action_params or {}),
                observation=observation,
                success=success,
                duration_ms=duration_ms,
                task_id=ctx.workflow_id,
                context=ctx.to_event_payload(),
                tags=list(tags or []),
                user_id=ctx.user_id,
            )
        except Exception:  # noqa: BLE001 — memory must never break execution
            pass

    def record_decision(self, ctx: ExecutionContext, decision: str,
                        outcome: str, success: bool) -> None:
        try:
            from memory import memory_facade

            memory_facade.memory.store_decision(
                context=ctx.phase,
                decision=decision,
                outcome=outcome,
                success=success,
                user_id=ctx.user_id,
            )
        except Exception:  # noqa: BLE001
            pass
