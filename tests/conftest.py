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

import os
import shutil
import tempfile
import pytest
import asyncio
import sqlite3
from unittest.mock import AsyncMock, MagicMock, Mock, patch
from typing import AsyncGenerator, Generator


@pytest.fixture(autouse=True)
def mock_external_calls(monkeypatch):
    """Isolate all tests from network, subprocess, and docker.
    Prevents hanging on external service calls during test runs."""
    monkeypatch.setattr("httpx.Client.request", MagicMock(return_value=Mock(status_code=200, text="mocked", json=Mock(return_value={}))))
    monkeypatch.setattr("httpx.AsyncClient.request", AsyncMock(return_value=Mock(status_code=200, text="mocked", json=Mock(return_value={}))))
    monkeypatch.setattr("subprocess.Popen", MagicMock())
    monkeypatch.setattr("subprocess.run", MagicMock(return_value=Mock(returncode=0, stdout=b"", stderr=b"")))
    monkeypatch.setattr("subprocess.check_output", MagicMock(return_value=b""))
    monkeypatch.setattr("subprocess.check_call", MagicMock(return_value=0))


from core.result import Ok


@pytest.fixture
def mock_llm() -> AsyncMock:
    mock = AsyncMock()
    mock.complete.return_value = Ok("Mocked LLM response")
    return mock


@pytest.fixture
def mock_db() -> Generator[sqlite3.Connection, None, None]:
    conn = sqlite3.connect(":memory:")
    yield conn
    conn.close()


@pytest.fixture
def mock_channel() -> MagicMock:
    mock = MagicMock()
    mock.id = "mock_channel"
    mock.send = AsyncMock(return_value=True)
    return mock


@pytest.fixture
async def db_init():
    """Initialize database tables. NOT autouse — tests that need DB must request it."""
    from core.database import engine, Base
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


from core.config_schema import JarvisConfig


@pytest.fixture
def mock_config() -> JarvisConfig:
    return JarvisConfig.load()


@pytest.fixture
def api_client():
    from fastapi.testclient import TestClient
    from core.main import app
    from contextlib import asynccontextmanager

    # Override lifespan to prevent background tasks from starting
    @asynccontextmanager
    async def noop_lifespan(app):
        async def noop():
            pass
        yield {"background_tasks": []}

    app.router.lifespan_context = noop_lifespan
    return TestClient(app)


@pytest.fixture
def sample_user_context() -> dict:
    return {
        "user_id": "test_user",
        "platform": "pytest",
        "auth": True,
        "privacy_tier": "LOCAL",
    }


@pytest.fixture
def isolated_fs():
    """Change to a temp directory and clean up after the test."""
    tmpdir = tempfile.mkdtemp()
    old_cwd = os.getcwd()
    try:
        os.chdir(tmpdir)
        yield tmpdir
    finally:
        os.chdir(old_cwd)
        shutil.rmtree(tmpdir, ignore_errors=True)


@pytest.fixture
def activity_manager(isolated_fs):
    """Create a fresh ActivityManager with an isolated on-disk DB."""
    from core.activity.manager import ActivityManager
    from core.activity.storage import ActivityStore
    from pathlib import Path

    db_path = str(Path(isolated_fs) / "test_activity.db")
    store = ActivityStore(db_path=db_path)
    mgr = ActivityManager(store=store)
    return mgr
