"""TestAgent — run tests and validate builds."""

from __future__ import annotations

import json

from core.agents.base import BaseAgent
from core.tools._constants import ToolBlock
from core.tools.execution import execute_tool_block


class TestAgent(BaseAgent):
    agent_id = "test"
    capabilities = ["test", "testing", "qa", "validate", "verify", "check"]

    async def execute(self, context=None) -> dict:
        project_dir = context.variables.get("project_dir", ".") if context else "."
        mode = context.variables.get("test_mode", "all") if context else "all"

        results = []

        if mode in ("all", "unit"):
            test_block = ToolBlock(tool_type="run_tests",
                                   content=json.dumps({"project_dir": project_dir}))
            _, test_result = await execute_tool_block(test_block, context=context)
            results.append(("run_tests", test_result))

        if mode in ("all", "validate"):
            val_block = ToolBlock(tool_type="runtime_validate",
                                  content=json.dumps({"project_dir": project_dir}))
            _, val_result = await execute_tool_block(val_block, context=context)
            results.append(("validate", val_result))

        output_parts = []
        all_ok = True
        for step_name, step_result in results:
            out = step_result.get("output") or ""
            if out:
                output_parts.append(f"[{step_name}] {str(out)[:300]}")
            if step_result.get("exit_code", 0) != 0:
                all_ok = False
                output_parts.append(f"[{step_name}] FAILED")

        output = "\n".join(output_parts) if output_parts else "Tests completed"
        return {"output": output, "exit_code": 0 if all_ok else 1}
