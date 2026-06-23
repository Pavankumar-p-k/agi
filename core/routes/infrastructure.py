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
import logging
import time

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from ..auth import require_scope
from ..authz import Scope

logger = logging.getLogger("jarvis")

router = APIRouter(tags=["Infrastructure"])


@router.get("/api/sandbox/status")
async def sandbox_status():
    from core.sandbox.docker_sandbox import docker_sandbox
    return {"available": docker_sandbox.available}


class SandboxExecRequest(BaseModel):
    code: str = ""
    timeout: int = 30


@router.post("/api/sandbox/exec", dependencies=[Depends(require_scope(Scope.TOOLS_EXECUTE_HIGH))])
async def sandbox_exec(body: SandboxExecRequest):
    from core.sandbox.docker_sandbox import docker_sandbox
    if not docker_sandbox.available:
        raise HTTPException(503, "Docker sandbox not available")
    if not body.code:
        raise HTTPException(400, "code is required")
    result = await docker_sandbox.exec_python(code=body.code, timeout=body.timeout)
    return result


@router.get("/api/failover/status", dependencies=[Depends(require_scope(Scope.LLM_FAILOVER_MANAGE))])
async def failover_status():
    from core.config_schema import jarvis_config
    from core.llm_failover import llm_failover

    profiles = []
    if not llm_failover.pm._vault_loaded:
        await llm_failover.pm._load_vault_profiles()

    for p in llm_failover.pm._profiles:
        in_cooldown = p.name in llm_failover.pm._cooldowns
        wakeup = llm_failover.pm._cooldowns.get(p.name, 0)
        profiles.append({
            "name": p.name,
            "provider": p.provider,
            "priority": p.priority,
            "healthy": not in_cooldown,
            "cooldown_remaining_s": max(0, round(wakeup - time.time(), 1)) if in_cooldown else 0,
            "failures": llm_failover.pm._failure_counts.get(p.name, 0),
        })
    return {"profiles": profiles, "enabled": jarvis_config.failover.enabled}


@router.post("/api/backup/create")
async def backup_create(request: Request):
    bm = getattr(request.app.state, "backup_manager", None)
    if not bm:
        raise HTTPException(503, "Backup manager not available")
    result = await bm.create_backup()
    return result


@router.get("/api/backup/list")
async def backup_list(request: Request):
    bm = getattr(request.app.state, "backup_manager", None)
    if not bm:
        return {"backups": []}
    return {"backups": bm.list_backups()}


class BackupRestoreRequest(BaseModel):
    path: str = ""


@router.post("/api/backup/restore")
async def backup_restore(request: Request, body: BackupRestoreRequest):
    bm = getattr(request.app.state, "backup_manager", None)
    if not bm:
        raise HTTPException(503, "Backup manager not available")
    result = await bm.restore_backup(body.path)
    return result


@router.get("/api/cron/jobs")
async def cron_list_jobs(request: Request):
    cs = getattr(request.app.state, "scheduler", None)
    if not cs:
        return {"jobs": []}
    return {"jobs": cs.list_jobs()}


@router.get("/api/scheduler/jobs")
async def scheduler_list_jobs(request: Request):
    cs = getattr(request.app.state, "scheduler", None)
    if not cs:
        return {"jobs": []}
    return {"jobs": cs.list_jobs()}


class CronAddJobRequest(BaseModel):
    id: str = ""
    schedule: str = "24h"
    action: str = "custom"
    params: dict = {}


@router.post("/api/cron/jobs")
async def cron_add_job(request: Request, body: CronAddJobRequest):
    cs = getattr(request.app.state, "scheduler", None)
    if not cs:
        raise HTTPException(503, "Cron scheduler not available")
    job = cs.add_job(
        job_id=body.id or f"job_{len(cs.list_jobs())}",
        schedule=body.schedule,
        action=body.action,
        params=body.params,
    )
    return job


@router.delete("/api/cron/jobs/{job_id}")
async def cron_remove_job(request: Request, job_id: str):
    cs = getattr(request.app.state, "scheduler", None)
    if not cs:
        raise HTTPException(503, "Cron scheduler not available")
    ok = cs.remove_job(job_id)
    return {"removed": ok}
