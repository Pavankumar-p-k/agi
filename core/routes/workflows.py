"""core/routes/workflows.py — REST API for the Workflow Engine.

Wraps WorkflowEngine as HTTP endpoints so frontends can list, inspect,
resume, and cancel workflows.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from core.workflow.engine import WorkflowEngine
from core.workflow.storage import WorkflowStore

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/workflows", tags=["Workflows"])

# ── Singleton engine ─────────────────────────────────────────────────────────

_engine: WorkflowEngine | None = None
_store: WorkflowStore | None = None


def _get_engine() -> WorkflowEngine:
    global _engine
    if _engine is None:
        _engine = WorkflowEngine()
    return _engine


def _get_store() -> WorkflowStore:
    global _store
    if _store is None:
        _store = WorkflowStore()
    return _store


# ── Response models ─────────────────────────────────────────────────────────


class WorkflowSummary(BaseModel):
    workflow_id: str
    workflow_type: str
    status: str
    current_step: int
    total_steps: int
    progress: str
    created_at: str | None = None
    updated_at: str | None = None
    owner: str = ""
    artifacts: list = []


class WorkflowDetail(BaseModel):
    workflow_id: str
    workflow_type: str
    status: str
    current_step: int
    total_steps: int
    steps: list[dict] = []
    created_at: str | None = None
    updated_at: str | None = None
    last_heartbeat: str | None = None
    session_id: str = ""
    owner: str = ""
    timeout_seconds: int | None = None
    retry_count: int = 0
    retry_budget: int = 0
    parent_workflow_id: str | None = None
    execution_context: dict = {}
    artifacts: list = []


# ── Routes ──────────────────────────────────────────────────────────────────


@router.get("")
def list_workflows(
    status: str | None = Query(None, description="Filter by status (e.g. RUNNING, FAILED, COMPLETED)"),
    limit: int = Query(50, ge=1, le=500),
) -> dict:
    wfs = _get_store().list_workflows(status=status, limit=limit)
    return {
        "workflows": [
            WorkflowSummary(
                workflow_id=w.workflow_id,
                workflow_type=w.workflow_type,
                status=w.status.value,
                current_step=w.current_step,
                total_steps=len(w.steps),
                progress=f"{w.current_step}/{len(w.steps)}",
                created_at=w.created_at.isoformat() if w.created_at else None,
                updated_at=w.updated_at.isoformat() if w.updated_at else None,
                owner=w.owner,
                artifacts=w.artifacts,
            )
            for w in wfs
        ],
        "total": len(wfs),
    }


@router.get("/{workflow_id}")
def get_workflow(workflow_id: str) -> WorkflowDetail:
    wf = _get_store().get_workflow(workflow_id)
    if wf is None:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return WorkflowDetail(
        workflow_id=wf.workflow_id,
        workflow_type=wf.workflow_type,
        status=wf.status.value,
        current_step=wf.current_step,
        total_steps=len(wf.steps),
        steps=[
            {
                "step_id": s.step_id,
                "tool_name": s.tool_name,
                "status": s.status.value,
                "started_at": s.started_at.isoformat() if s.started_at else None,
                "completed_at": s.completed_at.isoformat() if s.completed_at else None,
                "error": s.error,
                "retry_count": s.retry_count,
            }
            for s in wf.steps
        ],
        created_at=wf.created_at.isoformat() if wf.created_at else None,
        updated_at=wf.updated_at.isoformat() if wf.updated_at else None,
        last_heartbeat=wf.last_heartbeat.isoformat() if wf.last_heartbeat else None,
        session_id=wf.session_id,
        owner=wf.owner,
        timeout_seconds=wf.timeout_seconds,
        retry_count=wf.retry_count,
        retry_budget=wf.retry_budget,
        parent_workflow_id=wf.parent_workflow_id,
        execution_context=wf.execution_context,
        artifacts=wf.artifacts,
    )


@router.post("/{workflow_id}/resume")
async def resume_workflow(workflow_id: str) -> dict:
    wf = await _get_engine().resume_workflow(workflow_id)
    if wf is None:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return {
        "workflow_id": wf.workflow_id,
        "status": wf.status.value,
        "resumed": wf.status == workflow_status_running(wf),
    }


@router.post("/{workflow_id}/cancel")
async def cancel_workflow(workflow_id: str) -> dict:
    wf = await _get_engine().cancel_workflow(workflow_id)
    if wf is None:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return {
        "workflow_id": wf.workflow_id,
        "status": wf.status.value,
        "cancelled": True,
    }


def workflow_status_running(wf) -> bool:
    from core.workflow.models import WorkflowStatus
    return wf.status == WorkflowStatus.RUNNING
