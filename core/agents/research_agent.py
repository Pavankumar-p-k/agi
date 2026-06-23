"""ResearchAgent — web research and competitor analysis."""

from __future__ import annotations

import json

from core.agents.base import BaseAgent
from core.tools._constants import ToolBlock
from core.tools.execution import execute_tool_block


class ResearchAgent(BaseAgent):
    agent_id = "research"
    capabilities = ["research", "competitor", "market", "trend", "ui trend"]

    async def execute(self, context=None) -> dict:
        goal = context.variables.get("goal", "") if context else ""
        query = context.variables.get("query", goal) if context else goal

        results = []
        nav_block = ToolBlock(tool_type="browser_navigate",
                              content='{"url": "https://www.google.com"}')
        _, nav_result = await execute_tool_block(nav_block, context=context)
        results.append(("navigate", nav_result))

        snap_block = ToolBlock(tool_type="browser_snapshot", content="{}")
        _, snap_result = await execute_tool_block(snap_block, context=context)
        results.append(("snapshot", snap_result))

        fetch_block = ToolBlock(tool_type="web_fetch",
                                content=json.dumps({"query": query[:200]}))
        _, fetch_result = await execute_tool_block(fetch_block, context=context)
        results.append(("fetch", fetch_result))

        output_parts = []
        for step_name, step_result in results:
            out = step_result.get("output") or step_result.get("result") or ""
            if out:
                output_parts.append(f"[{step_name}] {str(out)[:300]}")
            if step_result.get("error"):
                output_parts.append(f"[{step_name}] error: {step_result['error']}")

        output = "\n".join(output_parts) if output_parts else "Research completed"
        return {"output": output, "exit_code": 0, "_artifacts": {}}
