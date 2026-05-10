from __future__ import annotations

import os
import platform
import subprocess
import sys

from ..contracts import ToolSpec
from ..utils import context_workspace_root


def register_system_tools(registry) -> None:
    registry.register(
        ToolSpec("open_application", "Open a desktop application by name.", ["application"], parameters={"application": {"type": "string", "required": True}}, category="system", keywords=["open", "application", "app"]),
        lambda application, **_: _open_application(application),
    )
    registry.register(
        ToolSpec("run_terminal_command", "Run a shell command.", ["command"], parameters={"command": {"type": "string", "required": True}}, category="system", permission="elevated", keywords=["terminal", "shell", "command"]),
        lambda command, context=None, **_: _run_terminal_command(registry, command, context=context),
    )
    registry.register(
        ToolSpec("system_information", "Return system metadata.", [], category="system", read_only=True, keywords=["system", "information", "status"]),
        lambda **_: _system_information(),
    )
    registry.register(
        ToolSpec("cpu_usage", "Return CPU usage data.", [], category="system", read_only=True, keywords=["cpu", "processor", "usage"]),
        lambda **_: _cpu_usage(),
    )
    registry.register(
        ToolSpec("memory_usage", "Return memory usage data.", [], category="system", read_only=True, keywords=["memory", "ram", "usage"]),
        lambda **_: _memory_usage(),
    )


def _open_application(application: str) -> dict:
    if os.name == "nt":
        subprocess.Popen(["cmd", "/c", "start", "", application], shell=False)
    else:
        subprocess.Popen([application], shell=False)
    return {"success": True, "application": application}


def _run_terminal_command(registry, command: str, context: dict | None = None) -> dict:
    if os.name == "nt":
        cmd = ["powershell", "-NoProfile", "-Command", command]
    else:
        cmd = ["/bin/sh", "-lc", command]
    cwd = str(context_workspace_root(context, registry.config.workspace_root))
    completed = subprocess.run(
        cmd,
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=registry.config.shell_timeout_s,
    )
    return {
        "success": completed.returncode == 0,
        "returncode": completed.returncode,
        "stdout": completed.stdout[-4000:],
        "stderr": completed.stderr[-4000:],
        "cwd": cwd,
    }


def _system_information() -> dict:
    return {
        "platform": platform.platform(),
        "python": sys.version.split()[0],
        "cwd": str(Path.cwd()),
        "pid": os.getpid(),
    }


def _cpu_usage() -> dict:
    try:
        load = os.getloadavg()
        return {"loadavg": load}
    except Exception:
        return {"loadavg": None, "note": "load average unavailable on this platform"}


def _memory_usage() -> dict:
    try:
        import psutil  # type: ignore

        vm = psutil.virtual_memory()
        return {"total": vm.total, "available": vm.available, "percent": vm.percent}
    except Exception:
        return {"note": "psutil unavailable", "process_rss": None}
