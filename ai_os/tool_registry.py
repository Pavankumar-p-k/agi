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

import os, subprocess, webbrowser
from typing import Any, Callable
from .sandbox import get_sandbox


class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, dict[str, Any]] = {}

    def register(self, name: str, schema: dict[str, Any], handler: Callable[[dict[str, Any]], Any]) -> None:
        self._tools[name] = {"schema": schema, "handler": handler}

    def catalog(self) -> list[dict[str, Any]]:
        return [{"name": n, "schema": v["schema"]} for n, v in self._tools.items()]

    def execute(self, step: dict[str, Any]) -> dict[str, Any]:
        tool = step.get("tool")
        args = step.get("args", {}) or {}
        if tool not in self._tools:
            raise ValueError(f"Unknown tool '{tool}'")
        return self._tools[tool]["handler"](args)


def open_app_handler(args: dict[str, Any]) -> dict[str, Any]:
    path = args.get("path") or args.get("app")
    if not path:
        return {"success": False, "error": "Missing path/app"}
    if os.path.exists(path):
        try:
            os.startfile(path)
            return {"success": True, "message": f"Launched {path}"}
        except Exception as e:
            return {"success": False, "error": str(e)}
    try:
        os.startfile(path)
        return {"success": True, "message": f"Launched {path}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def safe_shell_handler(args: dict[str, Any]) -> dict[str, Any]:
    """Execute shell command via sandboxed executor."""
    cmd = args.get("cmd", "")
    if not cmd:
        return {"success": False, "error": "Missing cmd"}
    
    # Use sandboxed executor instead of raw subprocess
    sandbox = get_sandbox()
    result = sandbox.execute(cmd)
    
    # Map sandbox result to tool result format
    return {
        "success": result["success"],
        "stdout": result.get("stdout", ""),
        "stderr": result.get("stderr", ""),
        "returncode": result.get("returncode", -1),
        "error": result.get("error"),
        "sandbox_blocked": result.get("sandbox_blocked", False),
    }


def file_ops_handler(args: dict[str, Any]) -> dict[str, Any]:
    op = args.get("op")
    path = args.get("path")
    content = args.get("content")
    try:
        if op == "read":
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                return {"success": True, "content": f.read()}
        if op == "write":
            with open(path, "w", encoding="utf-8") as f:
                f.write(content or "")
            return {"success": True}
        if op == "delete":
            os.remove(path)
            return {"success": True}
        return {"success": False, "error": f"Unknown file op: {op}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def browser_control_handler(args: dict[str, Any]) -> dict[str, Any]:
    url = args.get("url")
    if not url:
        return {"success": False, "error": "Missing url"}
    try:
        webbrowser.open(url)
        return {"success": True, "message": f"Opened {url}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def code_agent_handler(args: dict[str, Any]) -> dict[str, Any]:
    task = args.get("task")
    return {"success": True, "message": f"Code agent would run: {task}"}


def get_default_tool_registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register("open_app", {"path": "str"}, open_app_handler)
    registry.register("safe_shell", {"cmd": "str"}, safe_shell_handler)
    registry.register("file_ops", {"op": "str", "path": "str", "content": "str"}, file_ops_handler)
    registry.register("browser_control", {"url": "str"}, browser_control_handler)
    registry.register("code_agent", {"task": "str"}, code_agent_handler)
    return registry