"""Workflow engine: durable step execution with retries, compensation,
idempotent resume, cancellation, and workflow-level timeouts."""

from __future__ import annotations

import asyncio
import inspect
import logging
import time
from datetime import datetime
from typing import Any

from core.workflow.artifact_store import ArtifactStore
from core.workflow.context import ContextManager
from core.workflow.events import (
    IDEMPOTENCY_HIT,
    STEP_COMPLETED,
    STEP_STARTED,
    WORKFLOW_CANCELLED,
    WORKFLOW_COMPLETED,
    WORKFLOW_FAILED,
    WORKFLOW_STARTED,
)
from core.workflow.models import (
    StepDefinition,
    StepStatus,
    WorkflowInstance,
    WorkflowStep,
    WorkflowStatus,
)
from core.workflow.storage import WorkflowStore

logger = logging.getLogger(__name__)

# Pacing yield between steps so workflow-level timeouts can fire between
# steps even when every tool call is near-instant (WP-008).
_STEP_YIELD_SECONDS = 0.01

_TERMINAL_STATUSES = {
    WorkflowStatus.COMPLETED,
    WorkflowStatus.FAILED,
    WorkflowStatus.CANCELLED,
    WorkflowStatus.COMPENSATED,
    WorkflowStatus.COMPENSATION_FAILED,
}


def _result_succeeded(result: Any) -> bool:
    """Interpret a tool result dict as step success/failure."""
    if not isinstance(result, dict):
        return True
    if "success" in result:
        return bool(result["success"])
    if "sent" in result:
        return bool(result["sent"])
    if "exit_code" in result:
        try:
            return int(result["exit_code"]) == 0
        except (TypeError, ValueError):
            return False
    if result.get("error"):
        return False
    return True


def _accepts_context(fn: Any) -> bool:
    """True when fn can receive a ``context=`` keyword (real or mock)."""
    try:
        sig = inspect.signature(fn)
    except (TypeError, ValueError):
        return False
    for param in sig.parameters.values():
        if param.kind == inspect.Parameter.VAR_KEYWORD:
            return True
        if param.name == "context":
            return True
    return False


def _to_workflow_step(step: Any) -> WorkflowStep:
    if isinstance(step, WorkflowStep):
        return step
    src = step if isinstance(step, StepDefinition) else StepDefinition()
    return WorkflowStep(
        tool_name=getattr(src, "tool_name", "") or "",
        input_data=dict(getattr(src, "input_data", None) or {}),
        compensation_tool=getattr(src, "compensation_tool", None),
        compensation_data=getattr(src, "compensation_data", None),
        max_retries=int(getattr(src, "max_retries", 2) or 0),
        timeout_seconds=getattr(src, "timeout_seconds", None),
        idempotency_key=getattr(src, "idempotency_key", None) or "",
    )


class WorkflowEngine:
    """Runs workflows as background asyncio tasks with durable state."""

    def __init__(self, store: WorkflowStore | None = None) -> None:
        self.store = store if store is not None else WorkflowStore()
        self.context_manager = ContextManager(self.store)
        self.artifact_store = ArtifactStore(self.store)
        self._running: dict[str, asyncio.Task] = {}

    # ── Lifecycle ─────────────────────────────────────────────────────

    async def start_workflow(
        self,
        workflow_type: str,
        steps: list,
        *,
        owner: str | None = None,
        session_id: str | None = None,
        timeout_seconds: float | None = None,
        execution_context: dict | None = None,
        retry_budget: int = 0,
    ) -> WorkflowInstance:
        wf = WorkflowInstance(
            workflow_type=workflow_type,
            status=WorkflowStatus.RUNNING,
            steps=[_to_workflow_step(s) for s in (steps or [])],
            execution_context=dict(execution_context or {}),
            owner=owner,
            session_id=session_id,
            retry_budget=int(retry_budget or 0),
            last_heartbeat=datetime.utcnow(),
        )
        self.store.create_workflow(wf)
        self.context_manager.create_context(
            wf.workflow_id,
            owner=owner,
            session_id=session_id,
            variables=dict(execution_context or {}),
            metadata={"_store_path": self.store.db_path},
        )
        self.store.add_event(
            wf.workflow_id,
            WORKFLOW_STARTED,
            {
                "workflow_type": workflow_type,
                "owner": owner,
                "session_id": session_id,
                "step_count": len(wf.steps),
            },
        )
        task = asyncio.create_task(
            self._run_workflow(wf.workflow_id, timeout_seconds=timeout_seconds)
        )
        self._running[wf.workflow_id] = task
        return wf

    async def resume_workflow(self, workflow_id: str) -> WorkflowInstance | None:
        wf = self.store.get_workflow(workflow_id)
        if wf is None:
            return None
        if wf.status in (WorkflowStatus.COMPLETED, WorkflowStatus.CANCELLED):
            return wf
        existing = self._running.get(workflow_id)
        if existing is not None and not existing.done():
            return wf
        if existing is not None:
            self._running.pop(workflow_id, None)
        wf.last_heartbeat = datetime.utcnow()
        self.store.update_workflow(wf)
        task = asyncio.create_task(self._run_workflow(workflow_id))
        self._running[workflow_id] = task
        return wf

    async def cancel_workflow(self, workflow_id: str) -> WorkflowInstance | None:
        wf = self.store.get_workflow(workflow_id)
        if wf is None:
            return None
        if wf.status not in _TERMINAL_STATUSES:
            previous = (
                wf.status.value if hasattr(wf.status, "value") else str(wf.status)
            )
            wf.status = WorkflowStatus.CANCELLED
            wf.last_heartbeat = datetime.utcnow()
            self.store.update_workflow(wf)
            self.store.add_event(
                workflow_id, WORKFLOW_CANCELLED, {"previous_status": previous}
            )
        task = self._running.pop(workflow_id, None)
        if task is not None and not task.done():
            task.cancel()
        return self.store.get_workflow(workflow_id)

    async def get_status(self, workflow_id: str) -> dict | None:
        wf = self.store.get_workflow(workflow_id)
        if wf is None:
            return None
        total = len(wf.steps)
        done = sum(1 for s in wf.steps if s.status == StepStatus.COMPLETED)
        return {
            "workflow_id": wf.workflow_id,
            "workflow_type": wf.workflow_type,
            "status": wf.status.value if hasattr(wf.status, "value") else str(wf.status),
            "current_step": wf.current_step,
            "total_steps": total,
            "completed_steps": done,
            "progress": (done / total) if total else 1.0,
            "retry_count": wf.retry_count,
        }

    # ── Main run loop ─────────────────────────────────────────────────

    async def _run_workflow(
        self, workflow_id: str, timeout_seconds: float | None = None
    ) -> None:
        me = asyncio.current_task()
        try:
            await self._run_inner(workflow_id, timeout_seconds)
        except asyncio.CancelledError:
            # Cancellation is either an explicit cancel_workflow() (status
            # already persisted as CANCELLED) or a simulated crash — in both
            # cases the persisted status must be left untouched.
            pass
        finally:
            if self._running.get(workflow_id) is me:
                self._running.pop(workflow_id, None)

    async def _run_inner(
        self, workflow_id: str, timeout_seconds: float | None
    ) -> None:
        wf = self.store.get_workflow(workflow_id)
        if wf is None or wf.status in _TERMINAL_STATUSES:
            return

        ctx = self._ensure_context(wf)

        if wf.status == WorkflowStatus.COMPENSATING:
            await self._compensate(wf, ctx)
            return

        wf.status = WorkflowStatus.RUNNING
        wf.last_heartbeat = datetime.utcnow()
        self.store.update_workflow(wf)

        started = time.monotonic()
        idx = 0
        while idx < len(wf.steps) and wf.steps[idx].status == StepStatus.COMPLETED:
            step = wf.steps[idx]
            if step.idempotency_key:
                self.store.add_event(
                    workflow_id,
                    IDEMPOTENCY_HIT,
                    {"step_id": step.step_id, "position": idx,
                     "idempotency_key": step.idempotency_key},
                )
            idx += 1

        while idx < len(wf.steps):
            if (timeout_seconds is not None
                    and (time.monotonic() - started) > timeout_seconds):
                wf.status = WorkflowStatus.FAILED
                wf.last_heartbeat = datetime.utcnow()
                self.store.update_workflow(wf)
                self.store.add_event(
                    workflow_id,
                    WORKFLOW_FAILED,
                    {"reason": "workflow_timeout", "step_position": idx,
                     "timeout_seconds": timeout_seconds},
                )
                return

            step = wf.steps[idx]
            wf.last_heartbeat = datetime.utcnow()
            wf.current_step = idx
            self.store.update_workflow(wf)

            ctx = self._ensure_context(wf)
            self.store.add_event(
                workflow_id,
                STEP_STARTED,
                {"step_id": step.step_id, "position": idx,
                 "tool_name": step.tool_name},
            )
            step.status = StepStatus.RUNNING
            step.started_at = datetime.utcnow()
            self.store.update_step(step)

            ok = await self._execute_step_with_retries(wf, step, ctx)
            if not ok:
                await self._handle_failure(wf, ctx, idx)
                return

            result = step.output if isinstance(step.output, dict) else {}
            artifacts = result.get("_artifacts")
            if isinstance(artifacts, dict) and artifacts:
                ctx.artifacts.update(artifacts)
                self.context_manager.update_context(ctx)

            wf.current_step = idx + 1
            wf.last_heartbeat = datetime.utcnow()
            self.store.update_workflow(wf)
            self.store.add_event(
                workflow_id,
                STEP_COMPLETED,
                {"step_id": step.step_id, "position": idx,
                 "tool_name": step.tool_name},
            )
            idx += 1
            await asyncio.sleep(_STEP_YIELD_SECONDS)

        wf.status = WorkflowStatus.COMPLETED
        wf.current_step = len(wf.steps)
        wf.last_heartbeat = datetime.utcnow()
        self.store.update_workflow(wf)
        self.store.add_event(
            workflow_id,
            WORKFLOW_COMPLETED,
            {"steps": len(wf.steps), "current_step": wf.current_step},
        )

    # ── Step execution ────────────────────────────────────────────────

    async def _execute_step_with_retries(
        self, wf: WorkflowInstance, step: WorkflowStep, ctx
    ) -> bool:
        attempts_allowed = max(int(step.max_retries or 0), 0) + 1
        attempt = 0
        result: Any = None

        while attempt < attempts_allowed:
            attempt += 1
            block = StepDefinition(
                tool_name=step.tool_name,
                input_data=dict(step.input_data or {}),
            )
            try:
                if step.timeout_seconds:
                    result = await asyncio.wait_for(
                        self._call_execute(block, wf, ctx),
                        timeout=step.timeout_seconds,
                    )
                else:
                    result = await self._call_execute(block, wf, ctx)
            except (asyncio.TimeoutError, TimeoutError):
                result = {
                    "error": f"step timed out after {step.timeout_seconds}s",
                    "exit_code": 1,
                    "timeout": True,
                }
            except Exception as exc:  # noqa: BLE001 — tool crashes become failures
                result = {"error": f"{type(exc).__name__}: {exc}", "exit_code": 1}

            if _result_succeeded(result):
                step.status = StepStatus.COMPLETED
                step.error = None
                step.completed_at = datetime.utcnow()
                step.output = result if isinstance(result, dict) else {"result": result}
                self.store.update_step(step)
                return True

            if attempt < attempts_allowed:
                if wf.retry_budget > 0 and wf.retry_count >= wf.retry_budget:
                    break
                if wf.retry_budget > 0:
                    wf.retry_count += 1
                    self.store.update_workflow(wf)
                step.retry_count = int(step.retry_count or 0) + 1
                self.store.update_step(step)
                continue
            break

        step.status = StepStatus.FAILED
        err = result.get("error") if isinstance(result, dict) else None
        step.error = str(err or "step failed")
        step.completed_at = datetime.utcnow()
        if isinstance(result, dict):
            step.output = result
        self.store.update_step(step)
        return False

    async def _call_execute(self, block, wf: WorkflowInstance, ctx) -> Any:
        from core.tools.execution import execute_tool_block

        kwargs: dict[str, Any] = {
            "owner": wf.owner,
            "execution_context": dict(ctx.variables) if ctx is not None else None,
        }
        if ctx is not None and _accepts_context(execute_tool_block):
            kwargs["context"] = ctx
        out = await execute_tool_block(block, **kwargs)
        if isinstance(out, tuple) and len(out) == 2:
            _desc, result = out
        else:
            result = out
        if not isinstance(result, dict):
            result = {"result": result}
        return result

    # ── Failure handling / compensation ───────────────────────────────

    async def _handle_failure(
        self, wf: WorkflowInstance, ctx, failed_idx: int
    ) -> None:
        completable = [
            s for s in wf.steps[:failed_idx]
            if s.status == StepStatus.COMPLETED and s.compensation_tool
            and not s.compensated and s.step_id not in wf.compensated_steps
        ]
        if not completable:
            wf.status = WorkflowStatus.FAILED
            wf.last_heartbeat = datetime.utcnow()
            self.store.update_workflow(wf)
            failed = wf.steps[failed_idx]
            self.store.add_event(
                wf.workflow_id,
                WORKFLOW_FAILED,
                {"reason": "step_failed", "step_id": failed.step_id,
                 "position": failed_idx, "error": failed.error},
            )
            return

        wf.status = WorkflowStatus.COMPENSATING
        wf.last_heartbeat = datetime.utcnow()
        self.store.update_workflow(wf)
        await self._compensate(wf, ctx)

    async def _compensate(self, wf: WorkflowInstance, ctx) -> None:
        candidates = [
            s for s in wf.steps
            if s.status == StepStatus.COMPLETED and s.compensation_tool
            and not s.compensated and s.step_id not in wf.compensated_steps
        ]
        candidates.reverse()
        for step in candidates:
            block = StepDefinition(
                tool_name=step.compensation_tool,
                input_data=dict(step.compensation_data or {}),
            )
            result = await self._call_execute(block, wf, ctx)
            if _result_succeeded(result):
                step.compensated = True
                self.store.update_step(step)
                wf.compensated_steps.append(step.step_id)
                self.store.update_workflow(wf)
                continue
            wf.status = WorkflowStatus.COMPENSATION_FAILED
            wf.last_heartbeat = datetime.utcnow()
            self.store.update_workflow(wf)
            err = result.get("error") if isinstance(result, dict) else None
            self.store.add_event(
                wf.workflow_id,
                WORKFLOW_FAILED,
                {"reason": "compensation_failed", "step_id": step.step_id,
                 "error": str(err or "compensation failed")},
            )
            return
        wf.status = WorkflowStatus.COMPENSATED
        wf.last_heartbeat = datetime.utcnow()
        self.store.update_workflow(wf)
        self.store.add_event(
            wf.workflow_id,
            WORKFLOW_COMPLETED,
            {"compensated": list(wf.compensated_steps)},
        )

    # ── Helpers ───────────────────────────────────────────────────────

    def _ensure_context(self, wf: WorkflowInstance):
        ctx = self.context_manager.get_context(wf.workflow_id)
        if ctx is not None:
            return ctx
        return self.context_manager.create_context(
            wf.workflow_id,
            owner=wf.owner,
            session_id=wf.session_id,
            variables=dict(wf.execution_context or {}),
            metadata={"_store_path": self.store.db_path},
        )
