from __future__ import annotations

import logging
from typing import Any

from core.plugins import Plugin, PluginManifest

logger = logging.getLogger(__name__)


class Plugin(Plugin):
    manifest: PluginManifest

    def __init__(self, manifest: PluginManifest):
        super().__init__(manifest)

    async def on_load(self, app_state: dict | None = None) -> None:
        await super().on_load(app_state)
        self.register_tool(
            name="read_file",
            description="Read a file from disk. Supports line ranges: path:start-end or path:line. Output includes line numbers. View source code, config files, logs.",
            handler=self._hdl_read_file,
            input_schema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path, optionally with line range (e.g. foo.py:10-30)"}
                },
                "required": ["path"],
            },
            category="filesystem",
        )
        self.register_tool(
            name="write_file",
            description="Write content to a file on disk. Create new files or overwrite existing ones. Creates parent directories if needed.",
            handler=self._hdl_write_file,
            input_schema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path to write to"},
                    "content": {"type": "string", "description": "File content to write"},
                },
                "required": ["path", "content"],
            },
            category="filesystem",
        )
        self.register_tool(
            name="append_file",
            description="Append content to the end of an existing file. Creates the file if it does not exist.",
            handler=self._hdl_append_file,
            input_schema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path to append to"},
                    "content": {"type": "string", "description": "Content to append"},
                },
                "required": ["path", "content"],
            },
            category="filesystem",
        )
        self.register_tool(
            name="delete_file",
            description="Delete a file from disk. Returns error if the file does not exist or is a directory.",
            handler=self._hdl_delete_file,
            input_schema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path to delete"},
                },
                "required": ["path"],
            },
            category="filesystem",
        )
        self.register_tool(
            name="list_folder",
            description="List all files and directories in a folder. Returns name, kind (file/dir), size, and modification time for each entry.",
            handler=self._hdl_list_folder,
            input_schema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Folder path to list"},
                },
                "required": ["path"],
            },
            category="filesystem",
        )
        logger.info("[FileToolsPlugin] Registered 5 filesystem tools")

    async def on_unload(self) -> None:
        self._tools.clear()
        await super().on_unload()

    async def _hdl_read_file(self, content: str | dict, **kwargs) -> dict:
        return await self._exec_tool("read_file", content)

    async def _hdl_write_file(self, content: str | dict, **kwargs) -> dict:
        return await self._exec_tool("write_file", content)

    async def _hdl_append_file(self, content: str | dict, **kwargs) -> dict:
        return await self._exec_tool("append_file", content)

    async def _hdl_delete_file(self, content: str | dict, **kwargs) -> dict:
        return await self._exec_tool("delete_file", content)

    async def _hdl_list_folder(self, content: str | dict, **kwargs) -> dict:
        return await self._exec_tool("list_folder", content)

    async def _exec_tool(self, tool: str, content: str | dict) -> dict:
        from core.tools.execution import _direct_fallback
        if isinstance(content, dict):
            if tool == "read_file":
                text = content.get("path", "")
            elif tool == "write_file":
                text = f"{content.get('path', '')}\n{content.get('content', '')}"
            elif tool == "append_file":
                text = f"{content.get('path', '')}\n{content.get('content', '')}"
            elif tool == "delete_file":
                text = content.get("path", "")
            elif tool == "list_folder":
                text = content.get("path", "")
            else:
                text = str(content)
        else:
            text = content
        result = await _direct_fallback(tool, text)
        return result or {"error": f"{tool}: execution failed", "exit_code": 1}

    async def health_check(self) -> dict:
        base = await super().health_check()
        base["tools_registered"] = len(self._tools)
        base["tool_names"] = list(self._tools.keys())
        return base
