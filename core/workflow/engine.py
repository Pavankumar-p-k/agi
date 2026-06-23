from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from datetime import datetime
from typing import Any

from core.tools._constants import ToolBlock
from core.workflow.artifact_store import ArtifactStore
from core.workflow.context import ContextManager, ExecutionContext
from core.workflow.events import (
    COMPENSATION_FAILED,
    COMPENSATION_STARTED,
    COMPENSATION_STEP_COMPLETED,
    COMPENSATION_STEP_FAILED,
    COMPENSATION_STEP_STARTED,
    STEP_COMPLETED,
    STEP_FAILED,
    STEP_STARTED,
    WORKFLOW_CANCELLED,
    WORKFLOW_COMPENSATED,
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
    def __init__(self, store: WorkflowStore | None = None,
                 activity_recorder: Any = None) -> None:
        self._store = store or WorkflowStore()
        self._context_manager = ContextManager(self._store)
        self._artifact_store = ArtifactStore(self._store)
        self._running: dict[str, asyncio.Task] = {}
        self._activity_recorder = activity_recorder

    @property
    def store(self) -> WorkflowStore:
        return self._store

    @property
    def context_manager(self) -> ContextManager:
        return self._context_manager

    @property
    def artifact_store(self) -> ArtifactStore:
        return self._artifact_store

    async def start_workflow(
        self,
        workflow_type: str,
        steps: list[StepDefinition],
        session_id: str = "",
        owner: str = "",
        timeout_seconds: int | None = None,
        execution_context: dict | None = None,
        parent_workflow_id: str | None = None,
        retry_budget: int = 0,
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
                compensation_tool=step_def.compensation_tool,
                compensation_data=step_def.compensation_data,
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
            retry_budget=retry_budget,
        )

        wf = self._store.create_workflow(wf)
        if self._activity_recorder:
            self._activity_recorder.record_goal(f"Workflow: {workflow_type}")
            self._activity_recorder.link_workflow(workflow_id)
            for step in workflow_steps:
                self._activity_recorder.record_agent_tasks([{
                    "agent_id": wf.owner or "system",
                    "goal": step.tool_name,
                    "step": step.tool_name,
                    "parameters": step.input_data or {},
                }])
        self._context_manager.create_context(
            workflow_id=workflow_id,
            owner=owner,
            session_id=session_id,
            variables=execution_context or {},
            metadata={"_store_path": self._store._db_path},
        )
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
        if wf.status in (WorkflowStatus.COMPLETED, WorkflowStatus.CANCELLED,
                         WorkflowStatus.FAILED, WorkflowStatus.COMPENSATED,
                         WorkflowStatus.COMPENSATION_FAILED):
            return wf
        if wf.status in (WorkflowStatus.RUNNING, WorkflowStatus.RECOVERING):
            wf.status = WorkflowStatus.RUNNING
            self._store.update_workflow(wf)
            task = asyncio.create_task(self._run_workflow(wf))
            self._running[workflow_id] = task
        if wf.status == WorkflowStatus.COMPENSATING:
            task = asyncio.create_task(self._compensate_workflow(wf))
            self._running[workflow_id] = task
        return wf

    async def cancel_workflow(self, workflow_id: str) -> WorkflowInstance | None:
        wf = self._store.get_workflow(workflow_id)
        if wf is None:
            return None
        if wf.status in (WorkflowStatus.COMPLETED, WorkflowStatus.CANCELLED,
                         WorkflowStatus.FAILED, WorkflowStatus.COMPENSATED,
                         WorkflowStatus.COMPENSATION_FAILED):
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
        if wf.status == WorkflowStatus.COMPENSATING:
            await self._compensate_workflow(wf)
            return

        wf.status = WorkflowStatus.RUNNING
        self._store.update_workflow(wf)
        start_time = time.monotonic()

        context = self._context_manager.get_context(wf.workflow_id)
        if context is None:
            context = self._context_manager.create_context(
                workflow_id=wf.workflow_id,
                owner=wf.owner,
                session_id=wf.session_id,
            )

        try:
            while wf.current_step < len(wf.steps):
                wf.last_heartbeat = datetime.utcnow()
                self._store.update_workflow(wf)
                step = wf.steps[wf.current_step]
                if step.status == StepStatus.COMPLETED:
                    wf.current_step += 1
                    continue

                if step.status == StepStatus.PENDING:
                    success = await self._execute_step(wf, step, context)
                elif step.status == StepStatus.FAILED:
                    budget_exceeded = wf.retry_budget > 0 and wf.retry_count >= wf.retry_budget
                    if not budget_exceeded and step.retry_count < step.max_retries:
                        step.status = StepStatus.PENDING
                        step.retry_count += 1
                        wf.retry_count += 1
                        self._store.update_step(step)
                        self._store.update_workflow(wf)
                        success = await self._execute_step(wf, step, context)
                    else:
                        success = False
                else:
                    success = True

                if not success:
                    budget_exceeded = wf.retry_budget > 0 and wf.retry_count >= wf.retry_budget
                    if not budget_exceeded and step.retry_count < step.max_retries:
                        continue
                    current = self._store.get_workflow(wf.workflow_id)
                    if current and current.status == WorkflowStatus.CANCELLED:
                        return

                    if await self._compensate_workflow(wf):
                        return

                    current = self._store.get_workflow(wf.workflow_id)
                    if current and current.status == WorkflowStatus.COMPENSATION_FAILED:
                        return

                    wf.status = WorkflowStatus.FAILED
                    self._store.update_workflow(wf)
                    if self._activity_recorder:
                        self._activity_recorder.record_failure(step.error or "Workflow step failed")
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
            if self._activity_recorder:
                self._activity_recorder.record_completion({"state": "COMPLETE", "elapsed": elapsed})
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

    async def _execute_step(self, wf: WorkflowInstance, step: WorkflowStep,
                            context: ExecutionContext | None = None) -> bool:
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

            coro = execute_tool_block(
                block=tool_block,
                session_id=wf.session_id,
                owner=wf.owner,
                context=context,
            )
            if step.timeout_seconds and step.timeout_seconds > 0:
                desc, result = await asyncio.wait_for(coro, timeout=step.timeout_seconds)
            else:
                desc, result = await coro

            exit_code = result.get("exit_code", 0)
            error_text = result.get("error")

            if exit_code != 0 or error_text:
                step.status = StepStatus.FAILED
                step.error = error_text or f"exit code {exit_code}"
                step.output_data = result
                step.completed_at = datetime.utcnow()
                self._store.update_step(step)
                if self._activity_recorder:
                    self._activity_recorder.record_task_result(
                        {"agent_id": wf.owner or "system", "goal": step.tool_name,
                         "step": step.tool_name},
                        success=False, error=step.error,
                    )
                self._store.append_event(WorkflowEvent(
                    event_id=f"evt_{uuid.uuid4().hex}",
                    workflow_id=wf.workflow_id,
                    event_type=STEP_FAILED,
                    data={
                        "step_id": step.step_id,
                        "tool_name": step.tool_name,
                        "error": step.error,
                        "exit_code": exit_code,
                    },
                ))
                return False

            step.output_data = result
            step.status = StepStatus.COMPLETED
            step.completed_at = datetime.utcnow()
            self._store.update_step(step)
            wf.current_step += 1
            self._store.update_workflow(wf)

            if self._activity_recorder:
                self._activity_recorder.record_task_result(
                    {"agent_id": wf.owner or "system", "goal": step.tool_name,
                     "step": step.tool_name},
                    success=True,
                    output={"artifacts": result.get("_artifacts", {})},
                )
                if result.get("_artifacts"):
                    self._activity_recorder.record_task_artifacts(
                        {"agent_id": wf.owner or "system", "goal": step.tool_name,
                         "step": step.tool_name},
                        result["_artifacts"],
                    )

            if result.get("output"):
                wf.artifacts.append({
                    "step": wf.current_step - 1,
                    "tool": step.tool_name,
                    "summary": str(result["output"])[:200],
                })

            if result.get("_artifacts") and context is not None:
                for name, art_id in result["_artifacts"].items():
                    context.artifacts[name] = art_id
                self._context_manager.update_context(context)

            self._store.append_event(WorkflowEvent(
                event_id=f"evt_{uuid.uuid4().hex}",
                workflow_id=wf.workflow_id,
                event_type=STEP_COMPLETED,
                data={
                    "step_id": step.step_id,
                    "tool_name": step.tool_name,
                    "exit_code": exit_code,
                },
            ))
            return True
        except asyncio.CancelledError:
            raise
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

    async def _compensate_workflow(self, wf: WorkflowInstance) -> bool:
        completed_steps = [s for s in wf.steps if s.status == StepStatus.COMPLETED and s.compensation_tool]
        if not completed_steps:
            return False

        wf.status = WorkflowStatus.COMPENSATING
        wf.last_heartbeat = datetime.utcnow()
        self._store.update_workflow(wf)
        self._store.append_event(WorkflowEvent(
            event_id=f"evt_{uuid.uuid4().hex}",
            workflow_id=wf.workflow_id,
            event_type=COMPENSATION_STARTED,
            data={"step_count": len(completed_steps)},
        ))

        for comp_step in reversed(completed_steps):
            if wf.status == WorkflowStatus.CANCELLED:
                return True

            wf.last_heartbeat = datetime.utcnow()
            self._store.update_workflow(wf)
            self._store.append_event(WorkflowEvent(
                event_id=f"evt_{uuid.uuid4().hex}",
                workflow_id=wf.workflow_id,
                event_type=COMPENSATION_STEP_STARTED,
                data={
                    "step_id": comp_step.step_id,
                    "original_tool": comp_step.tool_name,
                    "compensation_tool": comp_step.compensation_tool,
                },
            ))

            try:
                from core.tools._constants import ToolBlock
                from core.tools.execution import execute_tool_block

                tool_block = ToolBlock(
                    tool_type=comp_step.compensation_tool,
                    content=json.dumps(comp_step.compensation_data),
                )
                desc, result = await execute_tool_block(
                    block=tool_block,
                    session_id=wf.session_id,
                    owner=wf.owner,
                )

                exit_code = result.get("exit_code", 0)
                error_text = result.get("error")

                if exit_code != 0 or error_text:
                    comp_step.compensated = False
                    self._store.update_step(comp_step)
                    self._store.append_event(WorkflowEvent(
                        event_id=f"evt_{uuid.uuid4().hex}",
                        workflow_id=wf.workflow_id,
                        event_type=COMPENSATION_STEP_FAILED,
                        data={
                            "step_id": comp_step.step_id,
                            "error": error_text or f"exit code {exit_code}",
                        },
                    ))
                    wf.status = WorkflowStatus.COMPENSATION_FAILED
                    wf.updated_at = datetime.utcnow()
                    self._store.update_workflow(wf)
                    self._store.append_event(WorkflowEvent(
                        event_id=f"evt_{uuid.uuid4().hex}",
                        workflow_id=wf.workflow_id,
                        event_type=COMPENSATION_FAILED,
                        data={
                            "step_id": comp_step.step_id,
                            "compensation_tool": comp_step.compensation_tool,
                            "error": error_text or f"exit code {exit_code}",
                        },
                    ))
                    return False

                comp_step.compensated = True
                self._store.update_step(comp_step)
                if comp_step.step_id not in wf.compensated_steps:
                    wf.compensated_steps.append(comp_step.step_id)

                self._store.append_event(WorkflowEvent(
                    event_id=f"evt_{uuid.uuid4().hex}",
                    workflow_id=wf.workflow_id,
                    event_type=COMPENSATION_STEP_COMPLETED,
                    data={
                        "step_id": comp_step.step_id,
                        "compensation_tool": comp_step.compensation_tool,
                    },
                ))
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.warning("Compensation step %s failed: %s", comp_step.step_id, e)
                self._store.append_event(WorkflowEvent(
                    event_id=f"evt_{uuid.uuid4().hex}",
                    workflow_id=wf.workflow_id,
                    event_type=COMPENSATION_STEP_FAILED,
                    data={
                        "step_id": comp_step.step_id,
                        "error": str(e),
                    },
                ))
                wf.status = WorkflowStatus.COMPENSATION_FAILED
                self._store.update_workflow(wf)
                self._store.append_event(WorkflowEvent(
                    event_id=f"evt_{uuid.uuid4().hex}",
                    workflow_id=wf.workflow_id,
                    event_type=COMPENSATION_FAILED,
                    data={"step_id": comp_step.step_id, "error": str(e)},
                ))
                return False

        wf.status = WorkflowStatus.COMPENSATED
        wf.updated_at = datetime.utcnow()
        self._store.update_workflow(wf)
        self._store.append_event(WorkflowEvent(
            event_id=f"evt_{uuid.uuid4().hex}",
            workflow_id=wf.workflow_id,
            event_type=WORKFLOW_COMPENSATED,
            data={"compensated_steps": wf.compensated_steps},
        ))
        return True
