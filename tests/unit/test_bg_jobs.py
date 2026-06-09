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

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from core.tools.bg_jobs import launch, get_result, cleanup_old_jobs, _jobs, BackgroundJob


@pytest.fixture(autouse=True)
def reset_jobs():
    _jobs.clear()
    yield


@pytest.mark.asyncio
async def test_launch_returns_job_id():
    with patch("core.tools.bg_jobs.asyncio.create_subprocess_shell", new_callable=AsyncMock) as mock_proc:
        mock_process = MagicMock()
        mock_process.communicate = AsyncMock(return_value=(b"out", b"err"))
        mock_process.returncode = 0
        mock_proc.return_value = mock_process

        job_id = await launch("echo hello")
        assert job_id.startswith("bg_")
        assert job_id in _jobs
        assert _jobs[job_id].command == "echo hello"


@pytest.mark.asyncio
async def test_get_result_pending():
    _jobs["bg_test"] = BackgroundJob(id="bg_test", command="sleep 1", start_time=0, done=False)
    result = await get_result("bg_test")
    assert result == {"status": "running", "job_id": "bg_test"}


@pytest.mark.asyncio
async def test_get_result_completed():
    _jobs["bg_test"] = BackgroundJob(
        id="bg_test", command="echo done", start_time=0,
        stdout="done", stderr="", returncode=0, done=True,
    )
    result = await get_result("bg_test")
    assert result["status"] == "completed"
    assert result["stdout"] == "done"
    assert result["returncode"] == 0


@pytest.mark.asyncio
async def test_get_result_nonexistent():
    result = await get_result("nonexistent")
    assert result is None


def test_cleanup_old_jobs_removes_stale():
    import time
    _jobs["old"] = BackgroundJob(id="old", command="x", start_time=time.time() - 7200, done=True)
    _jobs["new"] = BackgroundJob(id="new", command="y", start_time=time.time(), done=False)
    cleanup_old_jobs(max_age_seconds=3600)
    assert "old" not in _jobs
    assert "new" in _jobs


def test_cleanup_old_jobs_preserves_recent():
    import time
    _jobs["recent"] = BackgroundJob(id="recent", command="z", start_time=time.time(), done=True)
    cleanup_old_jobs(max_age_seconds=3600)
    assert "recent" in _jobs
