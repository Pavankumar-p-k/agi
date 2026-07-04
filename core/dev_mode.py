"""core/dev_mode.py
Tracks developer mode state and dev dependency installation status.
"""
from __future__ import annotations

import json
import logging
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DEV_STATE_DIR = Path.home() / ".jarvis"
DEV_STATE_FILE = DEV_STATE_DIR / "dev_mode.json"

DEV_DEPENDENCIES = [
    "pytest",
    "pytest-asyncio",
    "pytest-cov",
    "ruff",
    "mypy",
    "pre-commit",
    "httpx",
    "slack-sdk",
    "slack-bolt",
    "discord.py",
    "python-telegram-bot",
    "google-generativeai",
    "anthropic",
    "groq",
    "openai",
    "sounddevice",
    "webrtcvad",
    "faster-whisper",
    "edge-tts",
    "psutil",
]


@dataclass
class DevModeState:
    enabled: bool = False
    deps_installed: bool = False
    installed_deps: list[str] = field(default_factory=list)


def _load() -> DevModeState:
    if DEV_STATE_FILE.exists():
        try:
            data = json.loads(DEV_STATE_FILE.read_text(encoding="utf-8"))
            return DevModeState(
                enabled=data.get("enabled", False),
                deps_installed=data.get("deps_installed", False),
                installed_deps=data.get("installed_deps", []),
            )
        except Exception:
            pass
    return DevModeState()


def _save(state: DevModeState) -> None:
    DEV_STATE_DIR.mkdir(parents=True, exist_ok=True)
    DEV_STATE_FILE.write_text(
        json.dumps({
            "enabled": state.enabled,
            "deps_installed": state.deps_installed,
            "installed_deps": state.installed_deps,
        }, indent=2),
        encoding="utf-8",
    )


def is_enabled() -> bool:
    return _load().enabled


def enable() -> bool:
    state = _load()
    if state.enabled:
        return True
    state.enabled = True
    _save(state)
    if not state.deps_installed:
        print("Dev dependencies not installed. Run `jarvis dev deps-install` when ready.")
    return True


def disable() -> bool:
    state = _load()
    if not state.enabled:
        return True
    state.enabled = False
    _save(state)
    print("Developer mode disabled. Run `jarvis dev on` to re-enable.")
    return True


def status() -> dict[str, Any]:
    state = _load()
    return {
        "enabled": state.enabled,
        "deps_installed": state.deps_installed,
        "installed_count": len(state.installed_deps),
    }


def install_deps() -> bool:
    state = _load()
    return _install_deps(state)


def _install_deps(state: DevModeState) -> bool:
    python = sys.executable
    all_ok = True
    installed = []
    for dep in DEV_DEPENDENCIES:
        try:
            result = subprocess.run(
                [python, "-m", "pip", "install", dep],
                capture_output=True, text=True, timeout=120,
            )
            if result.returncode == 0:
                installed.append(dep)
                print(f"  ✓ {dep}")
            else:
                print(f"  ✗ {dep} — {result.stderr.strip()[:80]}")
                all_ok = False
        except Exception as e:
            print(f"  ✗ {dep} — {e}")
            all_ok = False
    state.deps_installed = all_ok
    state.installed_deps = installed
    _save(state)
    return all_ok
