"""MemoryAgent — failure memory, pattern storage, and learning."""

from __future__ import annotations

import json

from core.agents.base import BaseAgent
from core.pattern_failure_memory import PatternFailureMemory
from core.tools._constants import ToolBlock
from core.tools.execution import execute_tool_block


class MemoryAgent(BaseAgent):
    agent_id = "memory"
    capabilities = ["memory", "remember", "learn", "pattern", "store", "recall"]

    async def execute(self, context=None) -> dict:
        action = context.variables.get("memory_action", "record") if context else "record"
        key = context.variables.get("key", "") if context else ""
        value = context.variables.get("value", "") if context else ""

        memory = PatternFailureMemory()

        if action == "record" and key and value:
            memory.record_success(key, value)
            return {"output": f"Recorded: {key}", "exit_code": 0}

        if action == "recall" and key:
            results = memory.match(key)
            output = json.dumps(results, indent=2) if results else f"No matches for: {key}"
            return {"output": output, "exit_code": 0}

        if action == "list":
            patterns = memory.list_patterns()
            output = json.dumps(patterns, indent=2) if patterns else "No patterns stored"
            return {"output": output, "exit_code": 0}

        return {"output": f"Memory agent: unknown action={action}", "exit_code": 1}
