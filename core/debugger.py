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

"""core.debugger — runtime diagnostics snapshots for the /debug tooling."""
from __future__ import annotations

import platform
import sys
import threading
from typing import Any

import psutil


def runtime_snapshot() -> dict[str, Any]:
    """Return a structured snapshot of live runtime state (sessions/tools/plugins/config)."""
    sessions: list[dict[str, Any]] = []
    for thread in threading.enumerate():
        sessions.append({
            "name": thread.name,
            "daemon": thread.daemon,
            "alive": thread.is_alive(),
        })

    tools: dict[str, Any] = {}
    try:  # optional registry
        from core.tools.registry import tool_registry as _reg

        names = getattr(_reg, "tools", None)
        if isinstance(names, dict):
            tools = {k: {"registered": True} for k in names}
        elif isinstance(names, (list, tuple, set)):
            tools = {k: {"registered": True} for k in names}
    except Exception:
        tools = {"registry": "unavailable"}

    plugins: dict[str, Any] = {}
    try:  # optional registry
        from core.plugins.base import plugin_registry as _preg

        plugins = {name: {"loaded": getattr(p, "_loaded", False)}
                   for name, p in getattr(_preg, "plugins", {}).items()}
    except Exception:
        plugins = {"registry": "unavailable"}

    config: dict[str, Any] = {
        "python": sys.version.split()[0],
        "platform": f"{platform.system()} {platform.release()}",
    }
    try:
        from core.configuration import configuration

        config["chat_model"] = configuration.get("llm.chat_model")
    except Exception:
        config["chat_model"] = None

    proc = psutil.Process()
    return {
        "sessions": sessions,
        "tools": tools,
        "plugins": plugins,
        "config": config,
        "process": {
            "pid": proc.pid,
            "cpu_percent": proc.cpu_percent(None),
            "memory_mb": round(proc.memory_info().rss / (1024 * 1024), 1),
            "threads": proc.num_threads(),
        },
    }


__all__ = ["runtime_snapshot"]
