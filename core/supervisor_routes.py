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
"""core/supervisor_routes.py
FastAPI routes for JARVIS Supervisor — start builds, check status.
"""
import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core.shared_context import SharedContext
from core.supervisor_agent import supervisor
from notifications.notifier import notifier

logger = logging.getLogger("supervisor_routes")
router = APIRouter(prefix="/api/supervisor", tags=["Supervisor"])


class StartBuildRequest(BaseModel):
    goal: str
    workspace: str | None = None
    auto_approve: bool = True
    max_parallel: int = 2


class BuildStatusResponse(BaseModel):
    build_id: str
    goal: str
    project: str
    status: str
    completed: list[str]
    failed: list[str]
    tasks: int


@router.post("/start")
async def start_build(req: StartBuildRequest):
    if not req.goal or len(req.goal.strip()) < 5:
        raise HTTPException(status_code=422, detail="Goal must be at least 5 characters")
    supervisor.auto_approve = req.auto_approve
    supervisor.max_parallel = min(req.max_parallel, 4)
    supervisor.on_notify(notifier.notify)
    build = await supervisor.start_build(req.goal, req.workspace)
    return {
        "build_id": build["id"],
        "project": build["project"],
        "workspace": build["workspace"],
        "status": build["status"],
        "tasks": len(build["tasks"]),
        "goal": build["goal"],
    }


@router.get("/status/{build_id}")
async def get_status(build_id: str):
    build = supervisor.get_status(build_id)
    if not build:
        raise HTTPException(status_code=404, detail="Build not found")
    return {
        "build_id": build["id"],
        "goal": build["goal"],
        "project": build["project"],
        "status": build["status"],
        "completed": build["completed"],
        "failed": build["failed"],
        "tasks": len(build["tasks"]),
        "current_agent": build.get("current_agent"),
    }


@router.get("/list")
async def list_builds():
    return {"builds": supervisor.list_builds()}


@router.post("/cancel/{build_id}")
async def cancel_build(build_id: str):
    ok = supervisor.cancel_build(build_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Build not found")
    return {"status": "cancelled", "build_id": build_id}


@router.get("/context/{project}")
async def get_context(project: str):
    ctx = SharedContext(project)
    return ctx.get_progress()
