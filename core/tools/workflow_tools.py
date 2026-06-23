from __future__ import annotations

import json
import logging
from typing import Any

from core.workflow.models import StepDefinition

logger = logging.getLogger(__name__)


async def do_workflow_start(
    content: str,
    session_id: str | None = None,
    owner: str | None = None,
    **kwargs: Any,
) -> dict:
    try:
        data = json.loads(content) if content.strip() else {}
    except (json.JSONDecodeError, TypeError):
        data = {}

    workflow_type = data.get("workflow_type", "custom")
    raw_steps = data.get("steps", [])

    steps = []
    for s in raw_steps:
        steps.append(StepDefinition(
            tool_name=s["tool_name"],
            input_data=s.get("input_data", {}),
            timeout_seconds=s.get("timeout_seconds"),
            max_retries=s.get("max_retries", 3),
        ))

    engine = kwargs.get("workflow_engine")
    if engine is None:
        from core.workflow import WorkflowEngine
        engine = WorkflowEngine()

    wf = await engine.start_workflow(
        workflow_type=workflow_type,
        steps=steps,
        session_id=session_id or "",
        owner=owner or "",
        timeout_seconds=data.get("timeout_seconds"),
        execution_context=data.get("execution_context"),
    )

    completed = sum(1 for s in wf.steps if s.status.value == "COMPLETED")
    return {
        "output": json.dumps({
            "workflow_id": wf.workflow_id,
            "status": wf.status.value,
            "total_steps": len(wf.steps),
            "completed_steps": completed,
            "message": f"Workflow {wf.workflow_id} started ({len(steps)} steps)",
        }),
    }


async def do_workflow_resume(
    content: str,
    **kwargs: Any,
) -> dict:
    try:
        data = json.loads(content) if content.strip() else {}
    except (json.JSONDecodeError, TypeError):
        data = {}

    workflow_id = data.get("workflow_id")
    if not workflow_id:
        return {"error": "workflow_id is required", "exit_code": 1}

    engine = kwargs.get("workflow_engine")
    if engine is None:
        from core.workflow import WorkflowEngine
        engine = WorkflowEngine()

    wf = await engine.resume_workflow(workflow_id)
    if wf is None:
        return {"error": f"Workflow {workflow_id} not found", "exit_code": 1}

    completed = sum(1 for s in wf.steps if s.status.value == "COMPLETED")
    return {
        "output": json.dumps({
            "workflow_id": wf.workflow_id,
            "status": wf.status.value,
            "current_step": wf.current_step,
            "total_steps": len(wf.steps),
            "completed_steps": completed,
        }),
    }


async def do_workflow_cancel(
    content: str,
    **kwargs: Any,
) -> dict:
    try:
        data = json.loads(content) if content.strip() else {}
    except (json.JSONDecodeError, TypeError):
        data = {}

    workflow_id = data.get("workflow_id")
    if not workflow_id:
        return {"error": "workflow_id is required", "exit_code": 1}

    engine = kwargs.get("workflow_engine")
    if engine is None:
        from core.workflow import WorkflowEngine
        engine = WorkflowEngine()

    wf = await engine.cancel_workflow(workflow_id)
    if wf is None:
        return {"error": f"Workflow {workflow_id} not found", "exit_code": 1}

    return {
        "output": json.dumps({
            "workflow_id": wf.workflow_id,
            "status": wf.status.value,
            "message": f"Workflow {workflow_id} cancelled at step {wf.current_step}",
        }),
    }


async def do_workflow_status(
    content: str,
    **kwargs: Any,
) -> dict:
    try:
        data = json.loads(content) if content.strip() else {}
    except (json.JSONDecodeError, TypeError):
        data = {}

    workflow_id = data.get("workflow_id")
    if not workflow_id:
        return {"error": "workflow_id is required", "exit_code": 1}

    engine = kwargs.get("workflow_engine")
    if engine is None:
        from core.workflow import WorkflowEngine
        engine = WorkflowEngine()

    status = await engine.get_status(workflow_id)
    if status is None:
        return {"error": f"Workflow {workflow_id} not found", "exit_code": 1}

    return {"output": json.dumps(status)}


async def do_workflow_list(
    content: str,
    **kwargs: Any,
) -> dict:
    try:
        data = json.loads(content) if content.strip() else {}
    except (json.JSONDecodeError, TypeError):
        data = {}

    engine = kwargs.get("workflow_engine")
    if engine is None:
        from core.workflow import WorkflowEngine
        engine = WorkflowEngine()

    workflows = await engine.list_workflows(
        status=data.get("status"),
        limit=data.get("limit", 50),
    )

    if not workflows:
        return {"output": json.dumps({"workflows": [], "message": "No workflows found"})}

    return {"output": json.dumps({"workflows": workflows, "count": len(workflows)})}
