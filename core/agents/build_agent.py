"""BuildAgent — compile, repair, and package projects."""

from __future__ import annotations

import json

from core.agents.base import BaseAgent
from core.tools._constants import ToolBlock
from core.tools.execution import execute_tool_block


class BuildAgent(BaseAgent):
    agent_id = "build"
    capabilities = ["build", "compile", "create", "develop", "make", "apk", "package"]

    async def execute(self, context=None) -> dict:
        project_dir = context.variables.get("project_dir", ".") if context else "."
        task = context.variables.get("task", "build") if context else "build"

        build_block = ToolBlock(tool_type="build_project",
                                content=json.dumps({"task": task[:200], "project_dir": project_dir}))
        _, build_result = await execute_tool_block(build_block, context=context)

        return {
            "output": build_result.get("output") or "Build completed",
            "exit_code": build_result.get("exit_code", 0),
            "_artifacts": build_result.get("_artifacts", {}),
        }
