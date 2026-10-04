"""Developer-mode gate for dev-only CLI commands (rebuilt in STEP 4).

The previous body was a 16-line FAKE-SUCCESS deleted in STEP 2:

* ``is_enabled()`` returned a constant ``True`` — every "developer command"
  was reachable for everyone, and the dev gate in ``jarvis.py`` was decorative.
* ``install_deps()`` was ``pass`` yet ``jarvis dev deps-install`` printed
  "All developer dependencies installed." — a lie on stdout.

Pinned specs
------------
* ``jarvis.py`` — ``from core.dev_mode import is_enabled`` gates ``_DEV_COMMANDS``.
* ``jarvis-export/cli/cli_commands.py::cmd_dev`` —::

      s = status()
      s["enabled"]            # bool
      s["installed_count"]    # int

  so ``status()`` must return a **dict**, not the bool the stub returned.

State lives in ``~/.jarvis/dev_mode.json``; the dev-dependency set is the
console scripts/modules the developer commands actually import.
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict

logger = logging.getLogger(__name__)

JARVIS_DIR = Path.home() / ".jarvis"
STATE_PATH = JARVIS_DIR / "dev_mode.json"

#: Modules the developer commands import at runtime.
DEV_MODULES = (
    "pytest",
    "rich",
    "httpx",
    "playwright",
    "psutil",
)

#: Packages installed by ``jarvis dev deps-install`` (the dev extras).
DEV_PACKAGES = (
    "pytest",
    "pytest-asyncio",
    "rich",
    "httpx",
    "psutil",
)


def _read() -> Dict[str, Any]:
    try:
        if STATE_PATH.exists():
            data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
    except (OSError, ValueError) as exc:
        logger.warning("dev-mode state unreadable (%s) — treating as off", exc)
    return {}


def _write(state: Dict[str, Any]) -> bool:
    try:
        JARVIS_DIR.mkdir(parents=True, exist_ok=True)
        STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")
        return True
    except OSError as exc:
        logger.error("could not persist dev-mode state: %s", exc)
        return False


def is_enabled() -> bool:
    """True only when dev mode was explicitly switched on."""
    env = os.getenv("JARVIS_DEV_MODE", "").strip().lower()
    if env in {"1", "true", "yes", "on"}:
        return True
    if env in {"0", "false", "no", "off"}:
        return False
    return bool(_read().get("enabled", False))


def enable() -> None:
    """Turn developer mode on (persisted)."""
    state = _read()
    state["enabled"] = True
    if not _write(state):
        raise RuntimeError(f"could not write {STATE_PATH}")


def disable() -> None:
    """Turn developer mode off (persisted)."""
    state = _read()
    state["enabled"] = False
    if not _write(state):
        raise RuntimeError(f"could not write {STATE_PATH}")


def installed_modules() -> list[str]:
    """Which dev modules are actually importable right now."""
    import importlib.util
    return [m for m in DEV_MODULES if importlib.util.find_spec(m) is not None]


def status() -> Dict[str, Any]:
    """Live status dict — counts come from real import probes."""
    installed = installed_modules()
    state = _read()
    return {
        "enabled": is_enabled(),
        "installed_count": len(installed),
        "total": len(DEV_MODULES),
        "installed": installed,
        "missing": [m for m in DEV_MODULES if m not in installed],
        "state_path": str(STATE_PATH),
    }


def install_deps() -> bool:
    """Install the developer packages. Returns True only if all succeeded."""
    if not DEV_PACKAGES:
        return True
    cmd = [sys.executable, "-m", "pip", "install", *DEV_PACKAGES]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
    except (OSError, subprocess.SubprocessError) as exc:
        logger.error("pip invocation failed: %s", exc)
        print(f"pip failed to run: {exc}")
        return False
    ok = proc.returncode == 0
    if not ok:
        tail = (proc.stderr or proc.stdout or "").strip().splitlines()[-5:]
        for line in tail:
            print(line)
    # Report from a fresh probe rather than trusting pip's exit code alone.
    still_missing = status()["missing"]
    if still_missing:
        print(f"still missing after install: {', '.join(still_missing)}")
        return False
    return ok


__all__ = ["is_enabled", "enable", "disable", "status", "install_deps",
           "installed_modules", "STATE_PATH"]
