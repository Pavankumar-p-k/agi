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
"""Background job management for long-running bash commands (#!bg marker)."""
import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

@dataclass
class BackgroundJob:
    id: str
    command: str
    start_time: float
    process: Optional[asyncio.subprocess.Process] = None
    stdout: str = ""
    stderr: str = ""
    returncode: Optional[int] = None
    done: bool = False

_jobs: dict[str, BackgroundJob] = {}
_job_counter: int = 0


async def launch(command: str, cwd: Optional[str] = None, env: Optional[dict] = None) -> str:
    global _job_counter
    _job_counter += 1
    job_id = f"bg_{int(time.time())}_{_job_counter}"
    proc = await asyncio.create_subprocess_shell(
        command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=cwd,
        env=env,
    )
    job = BackgroundJob(id=job_id, command=command, start_time=time.time(), process=proc)
    _jobs[job_id] = job
    asyncio.create_task(_watch_job(job_id))
    return job_id


async def _watch_job(job_id: str):
    job = _jobs.get(job_id)
    if not job:
        return
    try:
        stdout, stderr = await job.process.communicate()
        job.stdout = stdout.decode(errors="replace") if stdout else ""
        job.stderr = stderr.decode(errors="replace") if stderr else ""
        job.returncode = job.process.returncode
    except Exception as e:
        logger.error("Background job %s failed: %s", job_id, e)
    finally:
        job.done = True


async def get_result(job_id: str) -> Optional[dict]:
    job = _jobs.get(job_id)
    if not job:
        return None
    if not job.done:
        return {"status": "running", "job_id": job_id}
    return {
        "status": "completed",
        "job_id": job_id,
        "stdout": job.stdout,
        "stderr": job.stderr,
        "returncode": job.returncode,
    }


def cleanup_old_jobs(max_age_seconds: int = 3600):
    now = time.time()
    stale = [jid for jid, j in _jobs.items() if now - j.start_time > max_age_seconds]
    for jid in stale:
        _jobs.pop(jid, None)
