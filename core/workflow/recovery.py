from __future__ import annotations

import logging
from typing import Any

from core.execution import ExecutionManager
from core.workflow.engine import WorkflowEngine
from core.workflow.events import WORKFLOW_RECOVERED, WorkflowEvent
from core.workflow.models import WorkflowStatus

logger = logging.getLogger(__name__)


async def recover_active_workflows(
    engine: WorkflowEngine,
    execution_manager: ExecutionManager | None = None,
) -> list[dict[str, Any]]:
    em = execution_manager or ExecutionManager()
    ctx = em.create_context(source="workflow_recovery", request_id="recovery_main")
    em.publish_progress(ctx, "recovery.started")

    active = engine.store.list_workflows(status=WorkflowStatus.RUNNING.value)
    active += engine.store.list_workflows(status=WorkflowStatus.RECOVERING.value)
    active += engine.store.list_workflows(status=WorkflowStatus.COMPENSATING.value)
    recovered: list[dict[str, Any]] = []

    for wf in active:
        if wf.status in (WorkflowStatus.RUNNING, WorkflowStatus.COMPENSATING) and not wf.is_stale:
            logger.info("Workflow %s still alive (heartbeat %s ago) — skipping recovery",
                         wf.workflow_id, _age(wf.last_heartbeat))
            continue

        old_status = wf.status
        wf.status = WorkflowStatus.RECOVERING
        engine.store.update_workflow(wf)

        wf = await engine.resume_workflow(wf.workflow_id)
        if wf is None:
            continue

        engine.store.append_event(WorkflowEvent(
            event_id=f"recovery_{wf.workflow_id}",
            workflow_id=wf.workflow_id,
            event_type=WORKFLOW_RECOVERED,
            data={
                "previous_status": old_status.value,
                "step_index": wf.current_step,
                "heartbeat_age_seconds": _age_seconds(wf.last_heartbeat),
            },
        ))
        if old_status == WorkflowStatus.COMPENSATING:
            label = f"compensating at step {wf.current_step}/{len(wf.steps)}"
        else:
            label = f"step {wf.current_step}/{len(wf.steps)}"
        recovered.append({
            "workflow_id": wf.workflow_id,
            "workflow_type": wf.workflow_type,
            "current_step": wf.current_step,
            "total_steps": len(wf.steps),
        })
        logger.info("Recovered workflow %s from %s at %s",
                     wf.workflow_id, old_status.value, label)

    if not recovered:
        logger.info("[WORKFLOW] No stale workflows to recover [OK]")

    em.publish_completed(ctx, {"recovered_count": len(recovered)})
    em.record_trace(ctx, "recovery", f"recovered {len(recovered)} workflows", True)
    return recovered


def _age_seconds(last: Any) -> float | None:
    if last is None:
        return None
    from datetime import datetime
    return (datetime.utcnow() - last).total_seconds()


def _age(last: Any) -> str:
    secs = _age_seconds(last)
    if secs is None:
        return "never"
    if secs < 60:
        return f"{secs:.0f}s"
    return f"{secs / 60:.1f}m"
