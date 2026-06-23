"""BrowserAgent — web automation beyond research (forms, login, scraping)."""

from __future__ import annotations

import json

from core.agents.base import BaseAgent
from core.tools._constants import ToolBlock
from core.tools.execution import execute_tool_block


class BrowserAgent(BaseAgent):
    agent_id = "browser"
    capabilities = ["browse", "navigate", "scrape", "login", "form", "click"]

    async def execute(self, context=None) -> dict:
        url = context.variables.get("url", "https://www.google.com") if context else "https://www.google.com"
        action = context.variables.get("action", "navigate") if context else "navigate"

        results = []

        if action in ("navigate", "all"):
            nav_block = ToolBlock(tool_type="browser_navigate",
                                  content=json.dumps({"url": url}))
            _, nav_result = await execute_tool_block(nav_block, context=context)
            results.append(("navigate", nav_result))

        snap_block = ToolBlock(tool_type="browser_snapshot", content="{}")
        _, snap_result = await execute_tool_block(snap_block, context=context)
        results.append(("snapshot", snap_result))

        output_parts = []
        for step_name, step_result in results:
            out = step_result.get("output") or step_result.get("result") or ""
            if out:
                output_parts.append(f"[{step_name}] {str(out)[:300]}")
            if step_result.get("error"):
                output_parts.append(f"[{step_name}] error: {step_result['error']}")

        return {"output": "\n".join(output_parts), "exit_code": 0}
