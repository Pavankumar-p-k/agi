# Copyright (c) 2024-2026 JARVIS Project
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""api/governance_routes.py
Governance REST API — exposes queue, resource monitor, and task router.

Mount in main.py:
    from api.governance_routes import router as gov_router
    app.include_router(gov_router)

    # At startup, start the work queue:
    @app.on_event("startup")
    async def _startup():
        from core.governance import work_queue
        work_queue.start()
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/governance", tags=["governance"])


# ── Request / Response models ─────────────────────────────────────────────────

class SubmitRequest(BaseModel):
    task:     str
    priority: int = Field(default=5, ge=1, le=10)
    context:  dict = {}


class SubmitResponse(BaseModel):
    task_id:  str
    priority: int
    status:   str = "queued"


class CancelResponse(BaseModel):
    task_id:   str
    cancelled: bool
    message:   str


# ── helpers ───────────────────────────────────────────────────────────────────

def _get_queue():
    from core.governance.work_queue import work_queue
    return work_queue


def _get_monitor():
    from core.governance.resource_monitor import resource_monitor
    return resource_monitor


def _get_router():
    from core.governance.task_router import task_router
    return task_router


# ── routes ────────────────────────────────────────────────────────────────────

@router.get("/status", summary="Queue stats + resource snapshot")
async def governance_status():
    """Returns combined queue status and system resource snapshot."""
    queue   = _get_queue()
    monitor = _get_monitor()
    return {
        "queue":     queue.get_status(),
        "resources": monitor.get_snapshot().to_dict(),
        "concurrency_recommended": monitor.recommend_concurrency(),
        "throttling": monitor.should_throttle(),
    }


@router.get("/queue", summary="List all tasks in the queue")
async def list_queue():
    """Returns all task records (pending, running, done, failed)."""
    queue = _get_queue()
    return {"tasks": queue.list_tasks(), **queue.get_status()}


@router.post("/submit", response_model=SubmitResponse, summary="Submit a task")
async def submit_task(req: SubmitRequest):
    """Enqueue a task for background execution."""
    queue = _get_queue()
    monitor = _get_monitor()

    if monitor.should_reject():
        raise HTTPException(
            status_code=503,
            detail="System is critically overloaded. Try again later.",
        )

    try:
        task_id = await queue.enqueue(req.task, priority=req.priority, context=req.context)
        return SubmitResponse(task_id=task_id, priority=req.priority)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))


@router.post("/cancel/{task_id}", response_model=CancelResponse, summary="Cancel a queued task")
async def cancel_task(task_id: str):
    """Cancel a pending or running task by ID."""
    queue     = _get_queue()
    cancelled = queue.cancel(task_id)
    return CancelResponse(
        task_id   = task_id,
        cancelled = cancelled,
        message   = "Task cancelled." if cancelled else "Task not found or already finished.",
    )


@router.get("/route", summary="Dry-run route a task (no execution)")
async def route_task(task: str = Query(..., description="Task description to route")):
    """Returns the RouteDecision for a task without executing it."""
    task_router = _get_router()
    try:
        decision = await task_router.route(task, {})
        result   = decision.to_dict()
        result["needs_clarification"] = decision.needs_clarification()
        return result
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/tasks/{task_id}", summary="Get a specific task record")
async def get_task(task_id: str):
    """Retrieve a task record by ID."""
    queue  = _get_queue()
    record = queue.get_task(task_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found.")
    return record.to_dict()


@router.get("/resources", summary="System resource snapshot")
async def get_resources():
    """Returns current CPU, RAM, disk, and agent counts."""
    monitor = _get_monitor()
    snap    = monitor.get_snapshot()
    return {
        **snap.to_dict(),
        "throttle":              monitor.should_throttle(),
        "reject":                monitor.should_reject(),
        "recommended_concurrency": monitor.recommend_concurrency(),
    }
