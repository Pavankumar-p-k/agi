from __future__ import annotations

import logging
from typing import Any

from core.workflow.engine import WorkflowEngine
from core.workflow.events import WORKFLOW_RECOVERED, WorkflowEvent
from core.workflow.models import WorkflowStatus

logger = logging.getLogger(__name__)


async def recover_active_workflows(
    engine: WorkflowEngine,
) -> list[dict[str, Any]]:
    active = engine.store.list_workflows(status=WorkflowStatus.RUNNING.value)
    active += engine.store.list_workflows(status=WorkflowStatus.RECOVERING.value)
    recovered: list[dict[str, Any]] = []

    for wf in active:
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
            data={"previous_status": old_status.value, "step_index": wf.current_step},
        ))
        recovered.append({
            "workflow_id": wf.workflow_id,
            "workflow_type": wf.workflow_type,
            "current_step": wf.current_step,
            "total_steps": len(wf.steps),
        })
        logger.info("Recovered workflow %s from %s at step %d/%d",
                     wf.workflow_id, old_status.value, wf.current_step, len(wf.steps))

    return recovered
