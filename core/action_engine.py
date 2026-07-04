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

import logging
import json
from typing import Any, Optional

logger = logging.getLogger(__name__)

class ActionEngine:
    """
    Central execution layer for JARVIS.
    Bridges the gap between LLM reasoning and physical tool execution.
    Integrates with Plugins, Skills, Automation, and MCP.
    """

    def __init__(self):
        self._CHR = chr(10)

    async def execute(self, action: str, params: dict[str, Any], session_id: str = "default") -> dict:
        """
        Generic execution entry point.
        Maps action names to internal implementations.
        """
        handler = getattr(self, action, None)
        if handler and callable(handler):
            try:
                return await handler(**params)
            except Exception as e:
                logger.error(f"ActionEngine: {action} failed: {e}")
                return self._format_result(False, action, error=str(e))
        
        # Fallback to existing execute_tool_block for non-core actions
        return await self._execute_via_block(action, params, session_id)

    async def open_url(self, url: str) -> dict:
        """Open a URL in the default browser via DesktopController."""
        try:
            from core.desktop.controller import desktop_controller
            result = desktop_controller.open_url(url)
            return self._format_result(result.success, "open_url", result=f"Opened {url}" if result.success else None)
        except Exception as e:
            return self._format_result(False, "open_url", error=str(e))

    async def launch_app(self, app_name: str) -> dict:
        """Launch a system application via DesktopController."""
        try:
            from core.desktop.controller import desktop_controller
            result = desktop_controller.launch_app(app_name)
            return self._format_result(result.success, "launch_app", 
                                     result=f"Launched {app_name}" if result.success else None,
                                     error=result.error)
        except Exception as e:
            return self._format_result(False, "launch_app", error=str(e))

    async def read_file(self, path: str) -> dict:
        """Read a file from the filesystem using confined native tools."""
        res = await self._execute_native("read_file", path)
        return self._format_native_result(res, "read_file")

    async def write_file(self, path: str, content: str) -> dict:
        """Write a file to the filesystem using confined native tools."""
        res = await self._execute_native("write_file", f"{path}{self._CHR}{content}")
        return self._format_native_result(res, "write_file")

    async def list_folder(self, path: str) -> dict:
        """List contents of a directory using confined native tools."""
        res = await self._execute_native("list_folder", path)
        return self._format_native_result(res, "list_folder")

    async def run_command(self, command: str) -> dict:
        """Run a shell command using confined native tools."""
        res = await self._execute_native("bash", command)
        return self._format_native_result(res, "run_command")

    # ── Internal Helpers ──────────────────────────────────────────────────

    def _format_result(self, success: bool, action: str, result: Any = None, error: Optional[str] = None) -> dict:
        return {
            "success": success,
            "action": action,
            "result": str(result) if result is not None else "",
            "error": error
        }

    async def _execute_native(self, tool: str, content: str) -> dict:
        from core.tools.execution import _direct_fallback
        return await _direct_fallback(tool, content)

    def _format_native_result(self, native_res: dict, action: str) -> dict:
        exit_code = native_res.get("exit_code", 1)
        success = exit_code == 0
        result = native_res.get("output", "")
        error = native_res.get("error")
        return self._format_result(success, action, result=result, error=error)

    async def _execute_via_block(self, action: str, params: dict, session_id: str) -> dict:
        from core.tools.execution import execute_tool_block
        from collections import namedtuple
        ToolBlock = namedtuple("ToolBlock", ["tool_type", "content"])
        
        # Determine content string for block (legacy support)
        if "content" in params:
            content = params["content"]
        elif "path" in params and "content" in params: # for write_file if called this way
             content = f"{params['path']}{self._CHR}{params['content']}"
        else:
            content = json.dumps(params)
            
        block = ToolBlock(tool_type=action, content=content)
        desc, res = await execute_tool_block(block, session_id=session_id)
        
        # Map execute_tool_block result back to structured format
        success = res.get("exit_code") == 0 if "exit_code" in res else True
        return self._format_result(success, action, result=res.get("output") or res, error=res.get("error"))

    def get_prompt_fragment(self) -> str:
        """Return a system prompt fragment describing available actions."""
        return (
            "\n### SYSTEM CAPABILITIES (ACTION ENGINE)\n"
            "You have direct access to the host system via the Action Engine. "
            "To execute an action, output a code block with the action name, for example:\n"
            "```open_url\n"
            "https://www.google.com\n"
            "```\n"
            "Supported actions:\n"
            "- open_url: Provide a URL to open in the browser.\n"
            "- launch_app: Provide the name of an application to start.\n"
            "- read_file: Provide a file path to read content.\n"
            "- write_file: Provide path on the first line, then content.\n"
            "- list_folder: Provide a directory path to see its contents.\n"
            "- run_command: Provide a shell command to execute.\n"
            "\nAlways wait for the execution result before proceeding.\n"
        )

# Global singleton
action_engine = ActionEngine()
