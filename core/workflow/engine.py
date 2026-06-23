from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from datetime import datetime
from typing import Any

from core.tools._constants import ToolBlock
from core.workflow.events import (
    STEP_COMPLETED,
    STEP_FAILED,
    STEP_STARTED,
    WORKFLOW_CANCELLED,
    WORKFLOW_COMPLETED,
    WORKFLOW_FAILED,
    WORKFLOW_STARTED,
    WorkflowEvent,
)
from core.workflow.models import (
    StepDefinition,
    StepStatus,
    WorkflowInstance,
    WorkflowStatus,
    WorkflowStep,
)
from core.workflow.storage import WorkflowStore

logger = logging.getLogger(__name__)


class WorkflowEngine:
    def __init__(self, store: WorkflowStore | None = None) -> None:
        self._store = store or WorkflowStore()
        self._running: dict[str, asyncio.Task] = {}

    @property
    def store(self) -> WorkflowStore:
        return self._store

    async def start_workflow(
        self,
        workflow_type: str,
        steps: list[StepDefinition],
        session_id: str = "",
        owner: str = "",
        timeout_seconds: int | None = None,
        execution_context: dict | None = None,
        parent_workflow_id: str | None = None,
    ) -> WorkflowInstance:
        workflow_id = f"wf_{uuid.uuid4().hex}"
        now = datetime.utcnow()

        workflow_steps: list[WorkflowStep] = []
        for idx, step_def in enumerate(steps):
            step = WorkflowStep(
                step_id=f"{workflow_id}_s{idx:04d}",
                idempotency_key=f"{workflow_id}_step_{idx}",
                tool_name=step_def.tool_name,
                status=StepStatus.PENDING,
                input_data=step_def.input_data,
                timeout_seconds=step_def.timeout_seconds,
                max_retries=step_def.max_retries,
            )
            workflow_steps.append(step)

        wf = WorkflowInstance(
            workflow_id=workflow_id,
            workflow_type=workflow_type,
            status=WorkflowStatus.PENDING,
            current_step=0,
            created_at=now,
            session_id=session_id,
            owner=owner,
            timeout_seconds=timeout_seconds,
            steps=workflow_steps,
            execution_context=execution_context or {},
            parent_workflow_id=parent_workflow_id,
        )

        wf = self._store.create_workflow(wf)
        self._store.append_event(WorkflowEvent(
            event_id=f"evt_{uuid.uuid4().hex}",
            workflow_id=workflow_id,
            event_type=WORKFLOW_STARTED,
            data={"workflow_type": workflow_type, "step_count": len(steps)},
        ))

        task = asyncio.create_task(self._run_workflow(wf))
        self._running[workflow_id] = task
        return wf

    async def resume_workflow(self, workflow_id: str) -> WorkflowInstance | None:
        if workflow_id in self._running:
            return self._store.get_workflow(workflow_id)
        wf = self._store.get_workflow(workflow_id)
        if wf is None:
            return None
        if wf.status in (WorkflowStatus.COMPLETED, WorkflowStatus.CANCELLED, WorkflowStatus.FAILED):
            return wf
        if wf.status in (WorkflowStatus.RUNNING, WorkflowStatus.RECOVERING):
            wf.status = WorkflowStatus.RUNNING
            self._store.update_workflow(wf)
            task = asyncio.create_task(self._run_workflow(wf))
            self._running[workflow_id] = task
        return wf

    async def cancel_workflow(self, workflow_id: str) -> WorkflowInstance | None:
        wf = self._store.get_workflow(workflow_id)
        if wf is None:
            return None
        if wf.status in (WorkflowStatus.COMPLETED, WorkflowStatus.CANCELLED, WorkflowStatus.FAILED):
            return wf
        wf.status = WorkflowStatus.CANCELLED
        wf.updated_at = datetime.utcnow()
        self._store.update_workflow(wf)
        self._store.append_event(WorkflowEvent(
            event_id=f"evt_{uuid.uuid4().hex}",
            workflow_id=workflow_id,
            event_type=WORKFLOW_CANCELLED,
            data={"current_step": wf.current_step},
        ))
        if workflow_id in self._running:
            self._running[workflow_id].cancel()
            del self._running[workflow_id]
        return wf

    async def get_status(self, workflow_id: str) -> dict[str, Any] | None:
        wf = self._store.get_workflow(workflow_id)
        if wf is None:
            return None
        completed_steps = sum(1 for s in wf.steps if s.status == StepStatus.COMPLETED)
        total_steps = len(wf.steps)
        return {
            "workflow_id": wf.workflow_id,
            "workflow_type": wf.workflow_type,
            "status": wf.status.value,
            "current_step": wf.current_step,
            "completed_steps": completed_steps,
            "total_steps": total_steps,
            "progress": f"{completed_steps}/{total_steps}",
            "created_at": wf.created_at.isoformat() if wf.created_at else None,
            "updated_at": wf.updated_at.isoformat() if wf.updated_at else None,
            "owner": wf.owner,
            "artifacts": wf.artifacts,
        }

    async def list_workflows(
        self, status: str | None = None, limit: int = 50
    ) -> list[dict[str, Any]]:
        workflows = self._store.list_workflows(status=status, limit=limit)
        return [
            {
                "workflow_id": w.workflow_id,
                "workflow_type": w.workflow_type,
                "status": w.status.value,
                "current_step": w.current_step,
                "total_steps": len(w.steps),
                "created_at": w.created_at.isoformat() if w.created_at else None,
                "updated_at": w.updated_at.isoformat() if w.updated_at else None,
                "owner": w.owner,
            }
            for w in workflows
        ]

    async def _run_workflow(self, wf: WorkflowInstance) -> None:
        wf.status = WorkflowStatus.RUNNING
        self._store.update_workflow(wf)
        start_time = time.monotonic()

        try:
            while wf.current_step < len(wf.steps):
                step = wf.steps[wf.current_step]
                if step.status == StepStatus.COMPLETED:
                    wf.current_step += 1
                    continue

                if step.status == StepStatus.PENDING:
                    success = await self._execute_step(wf, step)
                elif step.status == StepStatus.FAILED:
                    if step.retry_count < step.max_retries:
                        step.status = StepStatus.PENDING
                        step.retry_count += 1
                        wf.retry_count += 1
                        self._store.update_step(step)
                        self._store.update_workflow(wf)
                        success = await self._execute_step(wf, step)
                    else:
                        success = False
                else:
                    success = True

                if not success:
                    wf.status = WorkflowStatus.FAILED
                    self._store.update_workflow(wf)
                    self._store.append_event(WorkflowEvent(
                        event_id=f"evt_{uuid.uuid4().hex}",
                        workflow_id=wf.workflow_id,
                        event_type=WORKFLOW_FAILED,
                        data={
                            "step_index": wf.current_step,
                            "tool_name": step.tool_name,
                            "error": step.error,
                        },
                    ))
                    return

            wf.status = WorkflowStatus.COMPLETED
            wf.updated_at = datetime.utcnow()
            self._store.update_workflow(wf)
            elapsed = time.monotonic() - start_time
            self._store.append_event(WorkflowEvent(
                event_id=f"evt_{uuid.uuid4().hex}",
                workflow_id=wf.workflow_id,
                event_type=WORKFLOW_COMPLETED,
                data={"elapsed_seconds": round(elapsed, 2)},
            ))
        except asyncio.CancelledError:
            pass
        finally:
            self._running.pop(wf.workflow_id, None)

    async def _execute_step(self, wf: WorkflowInstance, step: WorkflowStep) -> bool:
        step.status = StepStatus.RUNNING
        step.started_at = datetime.utcnow()
        self._store.update_step(step)
        self._store.append_event(WorkflowEvent(
            event_id=f"evt_{uuid.uuid4().hex}",
            workflow_id=wf.workflow_id,
            event_type=STEP_STARTED,
            data={"step_id": step.step_id, "tool_name": step.tool_name},
        ))

        try:
            from core.tools._constants import ToolBlock
            from core.tools.execution import execute_tool_block

            tool_block = ToolBlock(
                tool_type=step.tool_name,
                content=json.dumps(step.input_data),
            )

            desc, result = await execute_tool_block(
                block=tool_block,
                session_id=wf.session_id,
                owner=wf.owner,
            )

            step.output_data = result
            step.status = StepStatus.COMPLETED
            step.completed_at = datetime.utcnow()
            self._store.update_step(step)
            wf.current_step += 1
            self._store.update_workflow(wf)

            if result.get("output"):
                wf.artifacts.append({
                    "step": wf.current_step - 1,
                    "tool": step.tool_name,
                    "summary": str(result["output"])[:200],
                })

            self._store.append_event(WorkflowEvent(
                event_id=f"evt_{uuid.uuid4().hex}",
                workflow_id=wf.workflow_id,
                event_type=STEP_COMPLETED,
                data={
                    "step_id": step.step_id,
                    "tool_name": step.tool_name,
                    "exit_code": result.get("exit_code", 0),
                },
            ))
            return True
        except Exception as e:
            logger.warning("Step %s failed: %s", step.step_id, e)
            step.status = StepStatus.FAILED
            step.error = str(e)
            step.completed_at = datetime.utcnow()
            self._store.update_step(step)
            self._store.append_event(WorkflowEvent(
                event_id=f"evt_{uuid.uuid4().hex}",
                workflow_id=wf.workflow_id,
                event_type=STEP_FAILED,
                data={
                    "step_id": step.step_id,
                    "tool_name": step.tool_name,
                    "error": str(e),
                },
            ))
            return False
