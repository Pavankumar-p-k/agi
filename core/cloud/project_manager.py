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
# core/cloud/project_manager.py
# ProjectManager — creates and manages long-running projects/goals in Supabase.
from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from .supabase_client import get_client, is_connected

logger = logging.getLogger("jarvis.cloud.projects")

_DEFAULT_USER = "local"


# ------------------------------------------------------------------ #
# Dataclasses
# ------------------------------------------------------------------ #

@dataclass
class Step:
    id: str
    project_id: str
    description: str
    status: str = "pending"        # pending | completed
    result: Any = None
    created_at: str = ""

    @classmethod
    def from_dict(cls, d: dict) -> Step:
        return cls(
            id          = d.get("id", str(uuid.uuid4())),
            project_id  = d.get("project_id", ""),
            description = d.get("description", ""),
            status      = d.get("status", "pending"),
            result      = d.get("result"),
            created_at  = d.get("created_at", datetime.utcnow().isoformat()),
        )

    def to_dict(self) -> dict:
        return {
            "id": self.id, "project_id": self.project_id,
            "description": self.description, "status": self.status,
            "result": self.result, "created_at": self.created_at,
        }


@dataclass
class Project:
    id: str
    name: str
    description: str
    goal: str
    status: str = "active"
    steps: list[Step] = field(default_factory=list)
    created_at: str = ""
    metadata: dict = field(default_factory=dict)

    @classmethod
    def from_dict(cls, d: dict) -> Project:
        steps_raw = d.get("steps") or []
        steps = [Step.from_dict(s) if isinstance(s, dict) else s for s in steps_raw]
        return cls(
            id          = d.get("id", str(uuid.uuid4())),
            name        = d.get("name", "Untitled"),
            description = d.get("description", ""),
            goal        = d.get("goal", ""),
            status      = d.get("status", "active"),
            steps       = steps,
            created_at  = d.get("created_at", datetime.utcnow().isoformat()),
            metadata    = d.get("metadata") or {},
        )

    def to_dict(self) -> dict:
        return {
            "id": self.id, "name": self.name, "description": self.description,
            "goal": self.goal, "status": self.status,
            "steps": [s.to_dict() for s in self.steps],
            "created_at": self.created_at, "metadata": self.metadata,
        }


# ------------------------------------------------------------------ #
# Manager
# ------------------------------------------------------------------ #

class ProjectManager:
    def __init__(self, user_id: str = _DEFAULT_USER):
        self._user_id = user_id
        # In-memory fallback when Supabase is offline
        self._local: dict[str, Project] = {}

    # ------------------------------------------------------------------ #
    # CRUD – projects
    # ------------------------------------------------------------------ #

    async def create_project(self, name: str, description: str = "", goal: str = "") -> Project:
        project = Project(
            id          = str(uuid.uuid4()),
            name        = name,
            description = description,
            goal        = goal,
            created_at  = datetime.utcnow().isoformat(),
        )
        if is_connected():
            try:
                await asyncio.to_thread(self._sb_upsert, project)
                return project
            except Exception as exc:
                logger.warning("Supabase create_project failed, storing locally: %s", exc)
        self._local[project.id] = project
        return project

    async def list_projects(self, status: str | None = None) -> list[Project]:
        if is_connected():
            try:
                return await asyncio.to_thread(self._sb_list, status)
            except Exception as exc:
                logger.warning("Supabase list_projects failed: %s", exc)
        projects = list(self._local.values())
        if status:
            projects = [p for p in projects if p.status == status]
        return projects

    async def get_project(self, project_id: str) -> Project | None:
        if is_connected():
            try:
                return await asyncio.to_thread(self._sb_get, project_id)
            except Exception as exc:
                logger.warning("Supabase get_project failed: %s", exc)
        return self._local.get(project_id)

    async def update_project(self, project_id: str, **fields) -> bool:
        project = await self.get_project(project_id)
        if not project:
            return False
        for k, v in fields.items():
            if hasattr(project, k):
                setattr(project, k, v)
        if is_connected():
            try:
                await asyncio.to_thread(self._sb_upsert, project)
                return True
            except Exception as exc:
                logger.warning("Supabase update_project failed: %s", exc)
        self._local[project_id] = project
        return True

    async def delete_project(self, project_id: str) -> bool:
        if is_connected():
            try:
                await asyncio.to_thread(self._sb_delete, project_id)
            except Exception as exc:
                logger.warning("Supabase delete_project failed: %s", exc)
        self._local.pop(project_id, None)
        return True

    # ------------------------------------------------------------------ #
    # CRUD – steps
    # ------------------------------------------------------------------ #

    async def add_step(self, project_id: str, step_description: str) -> Step | None:
        project = await self.get_project(project_id)
        if not project:
            return None
        step = Step(
            id          = str(uuid.uuid4()),
            project_id  = project_id,
            description = step_description,
            created_at  = datetime.utcnow().isoformat(),
        )
        project.steps.append(step)
        await self.update_project(project_id, steps=project.steps)
        return step

    async def complete_step(self, step_id: str) -> bool:
        """Mark a step as completed across all projects."""
        projects = await self.list_projects()
        for project in projects:
            for step in project.steps:
                if step.id == step_id:
                    step.status = "completed"
                    await self.update_project(project.id, steps=project.steps)
                    return True
        return False

    async def get_steps(self, project_id: str) -> list[Step]:
        project = await self.get_project(project_id)
        if not project:
            return []
        return project.steps

    # ------------------------------------------------------------------ #
    # Supabase helpers (blocking — called via asyncio.to_thread)
    # ------------------------------------------------------------------ #

    def _sb_upsert(self, project: Project) -> None:
        d = project.to_dict()
        d["user_id"] = self._user_id
        d["steps"] = [s.to_dict() for s in project.steps]
        get_client().table("jarvis_goals").upsert(d, on_conflict="id").execute()

    def _sb_get(self, project_id: str) -> Project | None:
        res = (
            get_client().table("jarvis_goals")
            .select("*")
            .eq("user_id", self._user_id)
            .eq("id", project_id)
            .single()
            .execute()
        )
        if res.data:
            return Project.from_dict(res.data)
        return None

    def _sb_list(self, status: str | None) -> list[Project]:
        q = (
            get_client().table("jarvis_goals")
            .select("*")
            .eq("user_id", self._user_id)
        )
        if status:
            q = q.eq("status", status)
        res = q.order("created_at", desc=True).execute()
        return [Project.from_dict(r) for r in (res.data or [])]

    def _sb_delete(self, project_id: str) -> None:
        get_client().table("jarvis_goals").delete().eq("id", project_id).execute()
