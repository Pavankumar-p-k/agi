from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any

from core.llm_router import complete

logger = logging.getLogger(__name__)

# Canonical execution path — all tool execution routes through here for
# RBAC, path confinement, sandboxing, and approval gates.
_CORE_TOOL_EXEC = None
_TOOL_BLOCK_CLS = None


def _ensure_core_imports():
    global _CORE_TOOL_EXEC, _TOOL_BLOCK_CLS
    if _CORE_TOOL_EXEC is not None:
        return
    from core.tools.execution import execute_tool_block as _e
    from core.tools._constants import ToolBlock as _T
    _CORE_TOOL_EXEC = _e
    _TOOL_BLOCK_CLS = _T

_RESOLVE_SYSTEM = (
    "You map high-level tasks to available tools. "
    "Available tools: create_directory, write_file, read_file, edit_file_text, "
    "delete_file, list_directory, run_command, compile_java, run_tests, build_project. "
    "Respond with JSON: {\"tool\": \"tool_name\", \"params\": {...}}."
)

_RESOLVE_PROMPT = """Task: {task_label}
Description: {description}

Which tool should be called and with what parameters?
Respond with JSON only: {{"tool": "tool_name", "params": {{"key": "value"}}}}
"""


@dataclass
class ActionResult:
    """Standardized result from any tool or action execution."""
    success: bool
    output: str = ""
    evidence: str = ""
    confidence: float = 0.0
    error: str = ""
    duration_ms: float = 0.0
    metadata: dict = field(default_factory=dict)


class Executor:
    """Unified action executor — runs tools and actions with a standard interface.

    Every execution produces an ActionResult with success, output, evidence,
    and confidence. This replaces ad-hoc tool calling patterns.
    """

    def __init__(self):
        self._tools: dict[str, Any] = {}

    def register_tool(self, name: str, tool_fn: Any):
        """Register a callable tool by name."""
        self._tools[name] = tool_fn
        logger.debug("[Executor] registered tool: %s", name)

    async def execute(self, action_name: str, params: dict | None = None,
                      task_id: str = "", timeout: float = 120.0) -> ActionResult:
        """Execute an action by name with params. Returns ActionResult.

        Routes through the canonical ``execute_tool_block`` for all tools
        known to the core execution engine, then falls back to locally
        registered tools, then to LLM-based resolution.
        """
        start = time.time()
        params = params or {}

        # 1. Try canonical execution path (RBAC, sandbox, approval gates)
        result = await self._try_core_execution(action_name, params, task_id, timeout, start)
        if result is not None:
            return result

        # 2. Try locally registered tool
        try:
            if action_name in self._tools:
                tool_fn = self._tools[action_name]
                if asyncio.iscoroutinefunction(tool_fn):
                    tool_result = await asyncio.wait_for(tool_fn(**params), timeout=timeout)
                else:
                    tool_result = await asyncio.wait_for(
                        asyncio.to_thread(tool_fn, **params),
                        timeout=timeout,
                    )

                elapsed = (time.time() - start) * 1000

                if isinstance(tool_result, ActionResult):
                    tool_result.duration_ms = elapsed
                    return tool_result

                if isinstance(tool_result, dict):
                    return ActionResult(
                        success=tool_result.get("success", False),
                        output=str(tool_result.get("output", tool_result.get("result", ""))),
                        evidence=str(tool_result.get("evidence", "")),
                        confidence=float(tool_result.get("confidence", 0.5)),
                        error=str(tool_result.get("error", "")),
                        duration_ms=elapsed,
                        metadata=tool_result.get("metadata", {}),
                    )

                return ActionResult(
                    success=True,
                    output=str(tool_result),
                    confidence=0.8,
                    duration_ms=elapsed,
                )

        except asyncio.TimeoutError:
            elapsed = (time.time() - start) * 1000
            logger.warning("[Executor] action %s timed out after %.1fs", action_name, timeout)
            return ActionResult(
                success=False,
                error=f"Action timed out after {timeout}s",
                duration_ms=elapsed,
            )
        except Exception as e:
            elapsed = (time.time() - start) * 1000
            logger.exception("[Executor] action %s failed: %s", action_name, e)
            return ActionResult(
                success=False,
                error=str(e),
                duration_ms=elapsed,
            )

        # 3. Unknown action — try to resolve via LLM
        resolved = await self._resolve_unknown_action(
            action_name, params.get("description", "") or params.get("goal", "")
        )
        if resolved:
            tool_name = resolved.get("tool", "")
            tool_params = resolved.get("params", {})
            tool_params.update({k: v for k, v in params.items()
                                if k not in tool_params})
            logger.info("[Executor] resolved '%s' -> %s(%s)",
                        action_name, tool_name, tool_params)
            return await self.execute(tool_name, tool_params, timeout=timeout)

        return ActionResult(
            success=False,
            error=f"Unknown action: {action_name}. Could not resolve to any tool.",
            duration_ms=(time.time() - start) * 1000,
        )

    async def _try_core_execution(
        self, action_name: str, params: dict,
        task_id: str, timeout: float, start: float,
    ) -> ActionResult | None:
        """Attempt execution via ``execute_tool_block``.

        Returns ``None`` when the tool type is unknown to the core engine,
        so the caller falls through to local registration or LLM resolution.
        """
        _ensure_core_imports()
        import json as _json
        try:
            content = _json.dumps(params) if params else ""
            block = _TOOL_BLOCK_CLS(tool_type=action_name, content=content)
            desc, result = await _CORE_TOOL_EXEC(
                block,
                session_id=task_id or None,
                owner="brain",
            )
        except Exception:
            logger.debug("[Executor] core exec bypassed for %s", action_name, exc_info=True)
            return None

        # Unknown tool type — let caller try local path
        if result.get("error", "").startswith("Unknown tool type"):
            return None

        elapsed = (time.time() - start) * 1000

        success = result.get("exit_code", 0) == 0 or not result.get("error")
        output = result.get("output", result.get("stdout", ""))
        error = result.get("error", "")
        if not error and result.get("stderr"):
            error = result["stderr"]

        return ActionResult(
            success=success,
            output=str(output) if output else desc,
            error=str(error) if error else "",
            duration_ms=elapsed,
            metadata={"core_desc": desc, **{k: v for k, v in result.items()
                      if k not in ("output", "error", "exit_code", "stdout", "stderr")}},
        )

    async def _resolve_unknown_action(self, task_label: str,
                                       description: str) -> dict | None:
        """Ask the LLM to map a high-level task to a tool + params."""
        try:
            prompt = _RESOLVE_PROMPT.replace("{task_label}", task_label)
            prompt = prompt.replace("{description}", description or task_label)
            result = await complete(
                "code",
                [
                    {"role": "system", "content": _RESOLVE_SYSTEM},
                    {"role": "user", "content": prompt},
                ],
                timeout=30,
            )
            if result.is_err():
                logger.warning("[Executor] resolve failed: %s", str(result._error if hasattr(result, '_error') else result))
                return None
            raw = result.unwrap()
            # Strip code fences
            for prefix in ["```json", "```JSON", "```"]:
                if raw.startswith(prefix):
                    raw = raw[len(prefix):]
            for suffix in ["```"]:
                if raw.endswith(suffix):
                    raw = raw[:-len(suffix)]
            raw = raw.strip()
            # Find JSON object in response
            data = None
            start = raw.find("{")
            end = raw.rfind("}")
            if start != -1 and end > start:
                try:
                    data = json.loads(raw[start:end + 1])
                except json.JSONDecodeError:
                    pass
            if not isinstance(data, dict) or "tool" not in data:
                logger.warning("[Executor] resolve bad response: %s", raw[:200])
                return None
            return data
        except Exception as e:
            logger.warning("[Executor] resolve exception: %s", e)
            return None

    async def execute_graph_node(self, task_label: str, action_name: str,
                                 params: dict | None = None) -> ActionResult:
        """Execute and log for a task graph node."""
        result = await self.execute(action_name, params)
        logger.info(
            "[Executor] node '%s' action=%s success=%s duration=%.0fms",
            task_label, action_name, result.success, result.duration_ms,
        )
        return result


executor = Executor()
