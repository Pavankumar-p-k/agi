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
import uuid

from fastapi import APIRouter, BackgroundTasks, HTTPException

from tools.deep_research import deep_research

router = APIRouter(prefix="/research", tags=["research"])
logger = logging.getLogger("jarvis.api.research")

# In-memory job store (matches pattern from api/website_routes.py)
_jobs: dict[str, dict] = {}

@router.post("/run")
async def start_research(body: dict, background_tasks: BackgroundTasks):
    query = body.get("query")
    if not query:
        raise HTTPException(400, "Query is required")

    job_id = str(uuid.uuid4())[:8]
    _jobs[job_id] = {
        "status": "queued",
        "progress": 0,
        "result": None,
        "created_at": time.time(),
        "query": query
    }

    async def _run():
        try:
            _jobs[job_id]["status"] = "running"
            _jobs[job_id]["progress"] = 10

            result = await deep_research(
                query=query,
                rounds=body.get("rounds", 8),
                max_sources=body.get("max_sources", 15),
            )

            _jobs[job_id]["status"] = "done"
            _jobs[job_id]["progress"] = 100
            _jobs[job_id]["result"] = result
        except Exception as e:
            logger.error(f"Research job {job_id} failed: {e}")
            _jobs[job_id]["status"] = "failed"
            _jobs[job_id]["error"] = str(e)

    background_tasks.add_task(_run)
    return {"job_id": job_id}

@router.get("/status/{job_id}")
async def get_status(job_id: str):
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return job

@router.get("/list")
async def list_jobs():
    return {"jobs": _jobs}
