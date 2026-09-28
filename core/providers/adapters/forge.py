"""Forge provider adapter — code generation via the configured code model."""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class ForgeProvider:
    """Code provider: routes codegen tasks through the execution gateway."""

    def __init__(self, **kwargs: Any):
        self.config = kwargs

    async def generate(self, task: str, lang: str = "Python", **kwargs: Any) -> str:
        # LLM access goes through the Execution stage gateway (Rule 1).
        from core.pipeline.stages.execution import complete_async
        result = await complete_async(
            f"Write {lang} code for the following task. Output ONLY code.\n\n{task}",
            role="code",
        )
        if result.is_err():
            raise result.unwrap()
        return result.unwrap()


class ForgeSubAgent:
    """SubAgent-style wrapper: run({'task': ...}) -> {'success', 'output', ...}."""

    def __init__(self, **kwargs: Any):
        self.provider = ForgeProvider(**kwargs)

    async def run(self, params: dict[str, Any]) -> dict[str, Any]:
        task = str((params or {}).get("task") or "").strip()
        if not task:
            return {"success": False, "error": "missing 'task' parameter", "output": ""}
        try:
            lang = str((params or {}).get("lang") or "Python")
            output = await self.provider.generate(task, lang=lang)
            return {"success": True, "output": output, "agent": "forge"}
        except Exception as exc:  # noqa: BLE001
            logger.warning("ForgeSubAgent.run failed: %s", exc)
            return {"success": False, "error": str(exc), "output": ""}
