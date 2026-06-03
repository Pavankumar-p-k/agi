"""pytest configuration for JARVIS E2E tests."""
import asyncio
import os
import sys
import pytest
from pathlib import Path


def _uvicorn_runner():
    """Module-level runner used by multiprocessing (pickleable on Windows)."""
    import uvicorn
    from core.main import app
    uvicorn.run(app, host="127.0.0.1", port=8002, log_level="error")


# Ensure project root is on path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

# Use WindowsProactorEventLoopPolicy on Windows
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())


def pytest_configure(config):
    """
    Compatibility shim: expose pytestconfig as a builtin name so older tests
    that evaluate skipif string expressions (e.g. "not pytestconfig.getoption(...)")
    don't raise NameError at import-time.
    """
    import builtins
    builtins.pytestconfig = config

@pytest.fixture(scope="session")
def event_loop():
    """Create a single event loop for the entire test session."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    yield loop
    loop.close()


@pytest.fixture(scope="session")
async def jarvis_server():
    """Start JARVIS server on port 8002 for the test session."""
    import uvicorn
    import multiprocessing
    import time
    import httpx

    server_proc: multiprocessing.Process | None = None

    # Set lightweight test mode so server does not start heavy services (LLMs, voice, scheduled jobs)
    os.environ.setdefault("JARVIS_TEST_MODE", "true")

    # Use ASGI test client to avoid network and multiprocessing issues on Windows
    from core.main import app as jarvis_app
    # Prefer in-memory ASGI client when supported by httpx; fall back to ASGITransport or a live uvicorn server
    try:
        client = httpx.AsyncClient(app=jarvis_app, base_url="http://test")
    except TypeError:
        try:
            from httpx import AsyncClient as _AsyncClient, ASGITransport
            client = _AsyncClient(transport=ASGITransport(app=jarvis_app), base_url="http://test")
        except Exception:
            # Last-resort: start a background uvicorn process and use network client
            import multiprocessing, uvicorn, time
            server_proc = multiprocessing.Process(target=_uvicorn_runner, daemon=True)
            server_proc.start()
            time.sleep(1)
            client = httpx.AsyncClient(base_url="http://127.0.0.1:8002")
    await client.__aenter__()

    yield client

    await client.__aexit__(None, None, None)


@pytest.fixture
async def client(jarvis_server):
    """Provide an HTTP client connected to the test server."""
    yield jarvis_server
