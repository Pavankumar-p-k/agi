# api/cloud_routes.py
# REST API for cloud/Supabase status, sync, and project management.
# Register in your main app:
#   from api.cloud_routes import router as cloud_router
#   app.include_router(cloud_router)

import asyncio
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

from core.cloud.supabase_client import is_connected, get_client
from core.cloud.cloud_memory import CloudMemory
from core.cloud.project_manager import ProjectManager, Project

router = APIRouter(tags=["cloud"])

_memory = CloudMemory()
_pm     = ProjectManager()


# ------------------------------------------------------------------ #
# Request models
# ------------------------------------------------------------------ #

class ProjectCreate(BaseModel):
    name:        str
    description: str = ""
    goal:        str = ""

class ProjectPatch(BaseModel):
    name:        Optional[str] = None
    description: Optional[str] = None
    goal:        Optional[str] = None
    status:      Optional[str] = None

class StepCreate(BaseModel):
    description: str


# ------------------------------------------------------------------ #
# Cloud status & sync
# ------------------------------------------------------------------ #

@router.get("/cloud/status")
async def cloud_status():
    connected = is_connected()
    counts = {}
    if connected:
        try:
            client = get_client()
            for table in ["jarvis_memories", "jarvis_conversations", "jarvis_goals", "jarvis_plugins_settings"]:
                res = client.table(table).select("id", count="exact").execute()
                counts[table] = res.count or 0
        except Exception:
            counts = {"error": "Could not fetch row counts"}
    return {"connected": connected, "row_counts": counts}


@router.post("/cloud/sync")
async def cloud_sync():
    """Push local SQLite → Supabase."""
    n = await _memory.sync_from_local()
    return {"synced_rows": n}


@router.post("/cloud/pull")
async def cloud_pull():
    """Pull Supabase → local SQLite."""
    n = await _memory.sync_to_local()
    return {"pulled_rows": n}


# ------------------------------------------------------------------ #
# Projects
# ------------------------------------------------------------------ #

@router.get("/projects")
async def list_projects(status: Optional[str] = None):
    projects = await _pm.list_projects(status=status)
    return {"projects": [p.to_dict() for p in projects]}


@router.post("/projects", status_code=201)
async def create_project(body: ProjectCreate):
    project = await _pm.create_project(body.name, body.description, body.goal)
    return project.to_dict()


@router.get("/projects/{project_id}")
async def get_project(project_id: str):
    project = await _pm.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project.to_dict()


@router.patch("/projects/{project_id}")
async def update_project(project_id: str, body: ProjectPatch):
    fields = {k: v for k, v in body.dict().items() if v is not None}
    ok = await _pm.update_project(project_id, **fields)
    if not ok:
        raise HTTPException(status_code=404, detail="Project not found")
    return {"status": "updated"}


@router.delete("/projects/{project_id}")
async def delete_project(project_id: str):
    await _pm.delete_project(project_id)
    return {"status": "deleted"}


@router.post("/projects/{project_id}/steps", status_code=201)
async def add_step(project_id: str, body: StepCreate):
    step = await _pm.add_step(project_id, body.description)
    if not step:
        raise HTTPException(status_code=404, detail="Project not found")
    return step.to_dict()


@router.patch("/projects/{project_id}/steps/{step_id}/complete")
async def complete_step(project_id: str, step_id: str):
    ok = await _pm.complete_step(step_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Step not found")
    return {"status": "completed"}
