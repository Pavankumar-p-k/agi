from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any

from brain.reasoning_engine import reasoning_engine
from core.llm_router import complete

logger = logging.getLogger(__name__)

_CORE_TOOL_EXEC = None
_TOOL_BLOCK_CLS = None

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


def _ensure_core_imports():
    global _CORE_TOOL_EXEC, _TOOL_BLOCK_CLS
    if _CORE_TOOL_EXEC is not None:
        return
    from core.tools.execution import execute_tool_block as _e
    from core.tools._constants import ToolBlock as _T
    _CORE_TOOL_EXEC = _e
    _TOOL_BLOCK_CLS = _T


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
    """Unified action executor — runs tools and actions with a standard interface."""

    def __init__(self):
        self._tools: dict[str, Any] = {}

    def register_tool(self, name: str, tool_fn: Any):
        self._tools[name] = tool_fn

    async def execute(self, action_name: str, params: dict | None = None,
                      task_id: str = "", timeout: float = 120.0) -> ActionResult:
        start = time.time()
        params = params or {}

        result = await self._try_core_execution(action_name, params, task_id, timeout, start)
        if result is not None:
            return result

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

                return ActionResult(success=True, output=str(tool_result), confidence=0.8, duration_ms=elapsed)

        except asyncio.TimeoutError:
            elapsed = (time.time() - start) * 1000
            return ActionResult(success=False, error=f"Action timed out after {timeout}s", duration_ms=elapsed)
        except Exception as e:
            elapsed = (time.time() - start) * 1000
            return ActionResult(success=False, error=str(e), duration_ms=elapsed)

        resolved = await self._resolve_unknown_action(
            action_name, params.get("description", "") or params.get("goal", "")
        )
        if resolved:
            tool_name = resolved.get("tool", "")
            tool_params = resolved.get("params", {})
            tool_params.update({k: v for k, v in params.items() if k not in tool_params})
            return await self.execute(tool_name, tool_params, timeout=timeout)

        return ActionResult(
            success=False,
            error=f"Unknown action: {action_name}. Could not resolve to any tool.",
            duration_ms=(time.time() - start) * 1000,
        )

    async def _try_core_execution(
        self, action_name: str, params: dict, task_id: str, timeout: float, start: float,
    ) -> ActionResult | None:
        _ensure_core_imports()
        try:
            content = json.dumps(params) if params else ""
            block = _TOOL_BLOCK_CLS(tool_type=action_name, content=content)
            desc, result = await _CORE_TOOL_EXEC(block, session_id=task_id or None, owner="brain")
        except Exception:
            return None

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

    async def _resolve_unknown_action(self, task_label: str, description: str) -> dict | None:
        try:
            prompt = _RESOLVE_PROMPT.replace("{task_label}", task_label)
            prompt = prompt.replace("{description}", description or task_label)
            result = await complete("code", [
                {"role": "system", "content": _RESOLVE_SYSTEM},
                {"role": "user", "content": prompt},
            ], timeout=30)
            if result.is_err():
                return None
            raw = result.unwrap()
            for prefix in ["```json", "```JSON", "```"]:
                if raw.startswith(prefix):
                    raw = raw[len(prefix):]
            for suffix in ["```"]:
                if raw.endswith(suffix):
                    raw = raw[:-len(suffix)]
            raw = raw.strip()
            data = None
            start = raw.find("{")
            end = raw.rfind("}")
            if start != -1 and end > start:
                try:
                    data = json.loads(raw[start:end + 1])
                except json.JSONDecodeError:
                    pass
            if not isinstance(data, dict) or "tool" not in data:
                return None
            return data
        except Exception:
            return None

    async def execute_graph_node(self, task_label: str, action_name: str,
                                 params: dict | None = None) -> ActionResult:
        result = await self.execute(action_name, params)
        return result


executor = Executor()


@dataclass
class VerificationResult:
    """Result of verifying an action or output."""
    verified: bool
    confidence: float = 0.0
    issues: list[str] = field(default_factory=list)
    evidence: str = ""


VERIFIER_SYSTEM = (
    "You are a verification engine. Your job is to check if an action was successful.\n"
    "Output inside <answer> tags in this exact JSON format:\n"
    "{\"verified\": true/false, \"confidence\": 0.0-1.0, \"issues\": [...], \"evidence\": \"...\"}\n"
    "Be strict: if there is any indication of failure, mark as not verified.\n"
    "Think step by step inside <think> tags."
)


class Verifier:
    """Verification layer — never trust the LLM's output without checking."""

    def __init__(self):
        self._engine = reasoning_engine

    async def verify_action(self, action_description: str, intended_outcome: str, actual_result: str) -> VerificationResult:
        prompt = (
            f"Action: {action_description}\n"
            f"Intended outcome: {intended_outcome}\n"
            f"Actual result: {actual_result}\n\n"
            "Was the action successful? Check carefully for errors."
        )
        result = await self._engine.reason(f"Verify: {action_description}", prompt, system_override=VERIFIER_SYSTEM)
        return self._parse_verification(result.answer)

    async def verify_file_creation(self, file_path: str, expected_content_snippet: str = "") -> VerificationResult:
        import os
        if not os.path.exists(file_path):
            return VerificationResult(verified=False, confidence=0.0, issues=["File does not exist"])
        if expected_content_snippet:
            try:
                with open(file_path, encoding="utf-8", errors="replace") as f:
                    content = f.read()
                if expected_content_snippet not in content:
                    return VerificationResult(
                        verified=False, confidence=0.3,
                        issues=[f"Expected content not found in {file_path}"],
                        evidence=f"File exists ({len(content)} bytes) but expected snippet missing",
                    )
            except Exception as e:
                return VerificationResult(verified=False, confidence=0.5, issues=[f"Could not read file: {e}"])
        return VerificationResult(verified=True, confidence=1.0, evidence=f"File exists at {file_path}")

    async def verify_code_output(self, code_snippet: str, output: str, expected_behavior: str) -> VerificationResult:
        prompt = (
            f"Code:\n```\n{code_snippet}\n```\n"
            f"Output:\n{output}\n"
            f"Expected behavior: {expected_behavior}\n\n"
            "Does the output match the expected behavior?"
        )
        result = await self._engine.reason("Verify code output", prompt, system_override=VERIFIER_SYSTEM)
        return self._parse_verification(result.answer)

    def _parse_verification(self, raw: str) -> VerificationResult:
        import re as _re
        answer_match = _re.search(r"<answer>(.*?)</answer>", raw, _re.DOTALL)
        json_str = answer_match.group(1).strip() if answer_match else raw.strip()
        json_str = _re.sub(r"```(?:json)?\s*", "", json_str).strip()
        try:
            data = json.loads(json_str)
            return VerificationResult(
                verified=bool(data.get("verified", False)),
                confidence=float(data.get("confidence", 0.0)),
                issues=data.get("issues", []),
                evidence=data.get("evidence", ""),
            )
        except (json.JSONDecodeError, ValueError):
            verified = "success" in raw.lower() or "verified" in raw.lower()
            return VerificationResult(
                verified=verified, confidence=0.5 if verified else 0.3,
                issues=["Could not parse verification response"],
                evidence=raw[:200],
            )


verifier = Verifier()
