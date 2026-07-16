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

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/cowork", tags=["Cowork"])


@router.post("/files/read")
async def cowork_file_read(path: str = ""):
    from ..file_agent import file_agent
    content = await file_agent.read_file(path)
    return {"path": path, "content": content, "size": len(content)}


@router.post("/files/write")
async def cowork_file_write(path: str = "", content: str = ""):
    from ..file_agent import file_agent
    await file_agent.write_file(path, content)
    return {"path": path, "written": True, "size": len(content)}


@router.post("/files/organize")
async def cowork_file_organize(folder: str = "", instruction: str = ""):
    from ..file_agent import file_agent
    result = await file_agent.organize_folder(folder, instruction)
    return result


@router.post("/files/generate")
async def cowork_file_generate(template: str = "", data: dict | None = None, output_path: str = ""):
    data = data or {}
    from ..file_agent import file_agent
    await file_agent.generate_document(template, data, output_path)
    return {"output_path": output_path, "status": "generated"}


@router.get("/files/list")
async def cowork_file_list(folder: str = "", pattern: str = ""):
    from ..file_agent import file_agent
    files = await file_agent.list_files(folder, pattern)
    return {"folder": folder, "files": files, "count": len(files)}


@router.post("/skills/create")
async def cowork_skill_create(name: str = "", description: str = "", template: str = ""):
    from sqlalchemy import select

    from ..database import AsyncSessionLocal, JarvisSkill
    async with AsyncSessionLocal() as session:
        existing = await session.execute(select(JarvisSkill).where(JarvisSkill.name == name))
        if existing.scalar_one_or_none():
            raise HTTPException(400, f"Skill '{name}' already exists")
        skill = JarvisSkill(name=name, description=description, template=template)
        session.add(skill)
        await session.commit()
        await session.refresh(skill)
        return {"id": skill.id, "name": skill.name, "status": "created"}


@router.get("/skills/list")
async def cowork_skills_list():
    from sqlalchemy import select

    from ..database import AsyncSessionLocal, JarvisSkill
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(JarvisSkill).order_by(JarvisSkill.name))
        skills = result.scalars().all()
        return {"skills": [{"id": s.id, "name": s.name, "description": s.description, "template": s.template[:100]} for s in skills]}


class SkillRunRequest(BaseModel):
    variables: dict = {}


@router.post("/skills/run/{skill_name}")
async def cowork_skill_run(skill_name: str, req: SkillRunRequest):
    from sqlalchemy import select

    from ..database import AsyncSessionLocal, JarvisSkill
    from ..llm_router import complete as llm_complete
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(JarvisSkill).where(JarvisSkill.name == skill_name))
        skill = result.scalar_one_or_none()
    if not skill:
        raise HTTPException(404, f"Skill '{skill_name}' not found")
    filled = skill.template
    for k, v in req.variables.items():
        filled = filled.replace("{" + k + "}", str(v))
    output = (await llm_complete("creative", [{"role": "user", "content": filled}])).unwrap_or("")
    return {"skill": skill_name, "input": filled, "output": output.strip()}


class BuildRequest(BaseModel):
    goal: str
    output_dir: str = "."


@router.post("/build/overnight")
async def cowork_overnight_build(req: BuildRequest):
    import asyncio

    from ..agent_executor import run_overnight_build
    task = asyncio.create_task(run_overnight_build(req.goal, req.output_dir))
    return {"status": "started", "goal": req.goal, "output_dir": req.output_dir, "message": "Overnight build running in background"}


class TaskAddRequest(BaseModel):
    task_id: str
    schedule: str
    action_type: str = "custom"
    params: dict = {}


@router.post("/schedule/add")
async def cowork_schedule_add(req: TaskAddRequest):
    from ..scheduler import scheduler
    scheduler.add_task(req.task_id, req.schedule, {"type": req.action_type, "params": req.params})
    return {"task_id": req.task_id, "schedule": req.schedule, "status": "scheduled"}


@router.get("/schedule/list")
async def cowork_schedule_list():
    from ..scheduler import scheduler
    return {"tasks": scheduler.get_tasks()}


@router.post("/schedule/remove/{task_id}")
async def cowork_schedule_remove(task_id: str):
    from ..scheduler import scheduler
    scheduler.remove_task(task_id)
    return {"task_id": task_id, "status": "removed"}
