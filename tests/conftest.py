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
