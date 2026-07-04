"""core/doctor.py — JARVIS system diagnostics module."""
from __future__ import annotations

import dataclasses
import logging
import os
import sys
from typing import Any

logger = logging.getLogger(__name__)


@dataclasses.dataclass
class DoctorReport:
    ollama_running: bool
    ollama_models: list[str]
    browser_installed: bool
    backend_running: bool
    api_keys_configured: dict[str, bool]
    overall_healthy: bool
    details: dict[str, Any] = dataclasses.field(default_factory=dict)


async def run_doctor() -> DoctorReport:
    ollama_running = await _check_ollama()
    ollama_models = await _get_ollama_models()
    browser_installed = _check_browser()
    backend_running = await _check_backend()
    api_keys = _check_api_keys()

    all_checks = [
        ollama_running,
        browser_installed,
        backend_running,
    ]
    overall_healthy = all(all_checks)

    return DoctorReport(
        ollama_running=ollama_running,
        ollama_models=ollama_models,
        browser_installed=browser_installed,
        backend_running=backend_running,
        api_keys_configured=api_keys,
        overall_healthy=overall_healthy,
        details={
            "ollama_error": None,
            "backend_error": None,
        },
    )


async def _check_ollama() -> bool:
    try:
        import httpx
        async with httpx.AsyncClient(timeout=3.0) as client:
            r = await client.get("http://127.0.0.1:11434/api/tags")
            return r.status_code == 200
    except Exception as e:
        logger.debug("Ollama check failed: %s", e)
        return False


async def _get_ollama_models() -> list[str]:
    try:
        import httpx
        async with httpx.AsyncClient(timeout=3.0) as client:
            r = await client.get("http://127.0.0.1:11434/api/tags")
            if r.status_code == 200:
                data = r.json()
                return [m["name"] for m in data.get("models", [])]
    except Exception as e:
        logger.debug("Ollama models fetch failed: %s", e)
    return []


def _check_browser() -> bool:
    try:
        import playwright  # noqa: F401
        return True
    except ImportError:
        pass
    try:
        from core.tools.browser_fsm import BrowserFSM  # noqa: F401
        return True
    except ImportError:
        pass
    return False


async def _check_backend() -> bool:
    try:
        import httpx
        async with httpx.AsyncClient(timeout=3.0) as client:
            r = await client.get("http://127.0.0.1:8000/health")
            return r.status_code == 200
    except Exception:
        pass
    try:
        import httpx
        async with httpx.AsyncClient(timeout=2.0) as client:
            r = await client.get("http://127.0.0.1:8000/api/health")
            return r.status_code == 200
    except Exception as e:
        logger.debug("Backend health check failed: %s", e)
        return False


def _check_api_keys() -> dict[str, bool]:
    providers = ["OPENAI", "ANTHROPIC", "GEMINI", "GROQ", "OPENROUTER"]
    result: dict[str, bool] = {}
    for p in providers:
        env_val = os.getenv(f"{p}_API_KEY", "")
        vault_val = _get_vault_key(p)
        result[p.lower()] = bool(env_val) or bool(vault_val)
    return result


def _get_vault_key(provider: str) -> str | None:
    try:
        from core.api_key_vault import vault
        return vault.get(f"{provider}_API_KEY")
    except Exception:
        return None


async def auto_fix(report: DoctorReport) -> dict[str, bool]:
    """
    Attempt to auto-fix common issues.
    Returns a dict mapping fix name to success status.
    """
    fixes: dict[str, bool] = {}

    if not report.ollama_running:
        fixes["ollama"] = await _fix_ollama()

    if not report.browser_installed:
        fixes["browser"] = _fix_browser()

    if not report.backend_running:
        fixes["backend"] = await _fix_backend()

    return fixes


async def _fix_ollama() -> bool:
    """Attempt to start Ollama."""
    import subprocess
    import shutil

    ollama_path = shutil.which("ollama")
    if not ollama_path:
        logger.warning("Ollama binary not found on PATH")
        return False

    try:
        if sys.platform == "win32":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            proc = subprocess.Popen(
                [ollama_path, "serve"],
                startupinfo=startupinfo,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        else:
            proc = subprocess.Popen(
                [ollama_path, "serve"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        import asyncio
        await asyncio.sleep(3)
        return proc.poll() is None
    except Exception as e:
        logger.warning("Failed to start Ollama: %s", e)
        return False


def _fix_browser() -> bool:
    """Install Playwright browsers."""
    import subprocess
    try:
        subprocess.check_call(
            [sys.executable, "-m", "playwright", "install", "chromium"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=120,
        )
        return True
    except Exception as e:
        logger.warning("Failed to install Playwright: %s", e)
        return False


async def _fix_backend() -> bool:
    """Start the JARVIS backend server."""
    import subprocess

    try:
        proc = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "core.main:app", "--host", "127.0.0.1", "--port", "8000"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        import asyncio
        await asyncio.sleep(3)
        return proc.poll() is None
    except Exception as e:
        logger.warning("Failed to start backend: %s", e)
        return False
