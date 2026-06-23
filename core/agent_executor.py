"""Agent executor — wraps core.agent_orchestrator for cowork build workflows."""
from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger(__name__)


async def run_overnight_build(goal: str, output_dir: str = ".") -> dict:
    """Run a build goal as a background task via the orchestrator."""
    try:
        from core.agent_orchestrator import AgentOrchestrator
        orch = AgentOrchestrator()
        result = await orch.build(command=goal, path=output_dir)
        logger.info("[AgentExecutor] overnight build complete: %s", result.get("status"))
        return result
    except Exception as e:
        logger.error("[AgentExecutor] overnight build failed: %s", e)
        return {"status": "failed", "error": str(e)}
