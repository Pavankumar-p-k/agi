"""core/routes/scheduler.py — REST API for user-facing Schedules.

Wraps SchedulerStore as HTTP endpoints so frontends can create, list,
pause, resume, and delete schedules that trigger activities or workflows
at recurring intervals. Emits WebSocket events via the active feed.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from core.scheduler.models import ScheduleModel
from core.scheduler.store import SchedulerStore

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/schedules", tags=["Scheduler"])

# ── Singleton store ─────────────────────────────────────────────────────────

_store: SchedulerStore | None = None


def _get_store() -> SchedulerStore:
    global _store
    if _store is None:
        _store = SchedulerStore()
    return _store


# ── WebSocket broadcast ─────────────────────────────────────────────────────

async def _broadcast_schedule_event(event: dict[str, Any]) -> None:
    """Push a schedule event to the active WebSocket feed.

    Imported lazily from activity.py to avoid circular imports.
    """
    try:
        from core.routes.activity import _broadcast_active
        await _broadcast_active(event)
    except Exception as e:
        logger.debug("Schedule WS broadcast skipped: %s", e)


# ── Pydantic request/response models ────────────────────────────────────────


class CreateScheduleRequest(BaseModel):
    name: str
    activity_id: str | None = None
    workflow_id: str | None = None
    cron: str | None = None
    interval_seconds: int | None = None


class ScheduleResponse(BaseModel):
    id: str
    name: str
    activity_id: str | None = None
    workflow_id: str | None = None
    cron: str | None = None
    interval_seconds: int | None = None
    next_run_at: str | None = None
    last_run_at: str | None = None
    status: str = "active"
    created_at: str | None = None


def _to_response(s: ScheduleModel) -> ScheduleResponse:
    return ScheduleResponse(
        id=s.id,
        name=s.name,
        activity_id=s.activity_id,
        workflow_id=s.workflow_id,
        cron=s.cron,
        interval_seconds=s.interval_seconds,
        next_run_at=s.next_run_at.isoformat() if s.next_run_at else None,
        last_run_at=s.last_run_at.isoformat() if s.last_run_at else None,
        status=s.status,
        created_at=s.created_at.isoformat() if s.created_at else None,
    )


# ── Routes ──────────────────────────────────────────────────────────────────


@router.get("")
def list_schedules(
    status: str | None = Query(None, description="Filter by status (active, paused, completed, failed)"),
) -> dict:
    store = _get_store()
    schedules = store.list_schedules(status=status)
    return {
        "schedules": [_to_response(s) for s in schedules],
        "total": len(schedules),
    }


@router.get("/{schedule_id}")
def get_schedule(schedule_id: str) -> ScheduleResponse:
    s = _get_store().get_schedule(schedule_id)
    if s is None:
        raise HTTPException(status_code=404, detail="Schedule not found")
    return _to_response(s)


@router.post("", status_code=201)
async def create_schedule(req: CreateScheduleRequest) -> ScheduleResponse:
    store = _get_store()
    schedule = ScheduleModel(
        id=f"sch_{uuid.uuid4().hex}",
        name=req.name,
        activity_id=req.activity_id,
        workflow_id=req.workflow_id,
        cron=req.cron,
        interval_seconds=req.interval_seconds,
        next_run_at=datetime.utcnow(),
        status="active",
        created_at=datetime.utcnow(),
    )
    store.add_schedule(schedule)
    logger.info("Created schedule %s: %s", schedule.id, schedule.name)
    await _broadcast_schedule_event({
        "event": "schedule_triggered",
        "schedule_id": schedule.id,
        "activity_id": schedule.activity_id,
        "workflow_id": schedule.workflow_id,
        "timestamp": datetime.utcnow().isoformat(),
    })
    return _to_response(schedule)


@router.post("/{schedule_id}/pause")
async def pause_schedule(schedule_id: str) -> dict:
    store = _get_store()
    s = store.get_schedule(schedule_id)
    if s is None:
        raise HTTPException(status_code=404, detail="Schedule not found")
    store.update_schedule_status(schedule_id, "paused")
    logger.info("Paused schedule %s", schedule_id)
    await _broadcast_schedule_event({
        "event": "schedule_failed",
        "schedule_id": schedule_id,
        "error": "paused_by_user",
        "timestamp": datetime.utcnow().isoformat(),
    })
    return {"id": schedule_id, "status": "paused"}


@router.post("/{schedule_id}/resume")
async def resume_schedule(schedule_id: str) -> dict:
    store = _get_store()
    s = store.get_schedule(schedule_id)
    if s is None:
        raise HTTPException(status_code=404, detail="Schedule not found")
    store.update_schedule_status(schedule_id, "active")
    logger.info("Resumed schedule %s", schedule_id)
    await _broadcast_schedule_event({
        "event": "schedule_triggered",
        "schedule_id": schedule_id,
        "timestamp": datetime.utcnow().isoformat(),
    })
    return {"id": schedule_id, "status": "active"}


@router.delete("/{schedule_id}")
async def delete_schedule(schedule_id: str) -> dict:
    store = _get_store()
    s = store.get_schedule(schedule_id)
    if s is None:
        raise HTTPException(status_code=404, detail="Schedule not found")
    store.delete_schedule(schedule_id)
    logger.info("Deleted schedule %s", schedule_id)
    return {"deleted": schedule_id}
