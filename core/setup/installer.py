"""Install missing components — Playwright, Ollama models, etc."""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from typing import Any

from core.setup.report import InstallResult

logger = logging.getLogger(__name__)

OLLAMA_BASE = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")


def install_playwright(browser: str = "chromium", timeout: int = 120) -> InstallResult:
    try:
        r = subprocess.run(
            [sys.executable, "-m", "playwright", "install", browser],
            capture_output=True, timeout=timeout, text=True,
        )
        if r.returncode == 0:
            return InstallResult("Playwright", True, f"{browser} installed")
        return InstallResult("Playwright", False,
                             f"exit code {r.returncode}: {r.stderr[:200]}")
    except FileNotFoundError:
        # playwright not installed at all — try pip install first
        try:
            subprocess.run(
                [sys.executable, "-m", "pip", "install", "playwright"],
                capture_output=True, timeout=60,
            )
            r = subprocess.run(
                [sys.executable, "-m", "playwright", "install", browser],
                capture_output=True, timeout=timeout, text=True,
            )
            if r.returncode == 0:
                return InstallResult("Playwright", True, f"installed + {browser} downloaded")
            return InstallResult("Playwright", False, r.stderr[:200])
        except Exception as e:
            return InstallResult("Playwright", False, str(e))
    except subprocess.TimeoutExpired:
        return InstallResult("Playwright", False, "timed out (try manually: playwright install)")


def pull_ollama_model(model_id: str, timeout: int = 600) -> InstallResult:
    try:
        r = subprocess.run(
            ["ollama", "pull", model_id],
            capture_output=True, timeout=timeout, text=True,
        )
        if r.returncode == 0:
            return InstallResult(f"Model {model_id}", True, "downloaded")
        return InstallResult(f"Model {model_id}", False, r.stderr[:200])
    except FileNotFoundError:
        return InstallResult(f"Model {model_id}", False, "ollama binary not found")
    except subprocess.TimeoutExpired:
        return InstallResult(f"Model {model_id}", False, "download timed out")


def ensure_ollama_running(timeout: int = 20) -> InstallResult:
    """Start ollama serve if not already running."""
    if _ollama_reachable():
        return InstallResult("Ollama service", True, "already running")

    try:
        subprocess.Popen(
            ["ollama", "serve"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        import time
        for _ in range(timeout):
            if _ollama_reachable():
                return InstallResult("Ollama service", True, "started")
            time.sleep(1)
        return InstallResult("Ollama service", False, "started but not responding")
    except FileNotFoundError:
        return InstallResult("Ollama service", False, "ollama binary not found")


def _ollama_reachable() -> bool:
    try:
        with urllib.request.urlopen(f"{OLLAMA_BASE}/api/tags", timeout=2):
            return True
    except (urllib.error.URLError, OSError):
        return False
