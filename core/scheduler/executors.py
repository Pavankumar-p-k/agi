"""Scheduler executors — adapter layer between scheduler and real subsystems.

Each executor receives (activity_id, goal, metadata) from the scheduler
and maps to the real function's parameter signature.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

# Maps from opportunity target_system to appropriate executor type
OPPORTUNITY_TARGET_TO_EXECUTOR: dict[str, str] = {
    "research_infrastructure": "research",
    "browser_automation": "research",
    "coding_intelligence": "research",
    "memory_learning": "research",
    "collaboration": "research",
    "generalization": "research",
    "belief_quality": "research",
    "strategic_reasoning": "research",
    "autonomous_improvement": "research",
    "activity_scheduler": "research",
    "automated_build": "research",
    "build_benchmark": "research",
    "self_modification": "research",
    "opportunity_discovery": "research",
    "voice_assistant": "research",
    "execution_infrastructure": "research",
}


async def research_executor(
    activity_id: str, goal: str, metadata: dict[str, Any],
) -> dict[str, Any]:
    """Execute a research activity via browser_research."""
    from core.tools.browser_research import do_browser_research
    question = metadata.get("question") or goal
    max_pages = metadata.get("max_pages", 5)
    result = await do_browser_research(
        question=question,
        max_pages=max_pages,
    )
    return result


async def build_executor(
    activity_id: str, goal: str, metadata: dict[str, Any],
) -> dict[str, Any]:
    """Execute a build activity via build_project."""
    from core.tools.build_tools import do_build_project
    project_dir = metadata.get("project_dir", ".")
    task = metadata.get("task") or goal
    result = await do_build_project(task=task, project_dir=project_dir)
    return result


async def repair_executor(
    activity_id: str, goal: str, metadata: dict[str, Any],
) -> dict[str, Any]:
    """Execute a repair activity via repair_project."""
    from core.tools.build_tools import do_repair_project
    project_dir = metadata.get("project_dir", ".")
    build_output = metadata.get("build_output", "")
    result = await do_repair_project(
        project_dir=project_dir,
        build_output=build_output,
    )
    return result


async def email_executor(
    activity_id: str, goal: str, metadata: dict[str, Any],
) -> dict[str, Any]:
    """Send an email via the MCP email tool dispatch."""
    to = metadata.get("to", "")
    subject = metadata.get("subject") or goal
    body = metadata.get("body", "")
    if not to:
        return {"error": "no_recipient", "activity_id": activity_id}
    try:
        from core.tools.execution import _call_mcp_tool
        content = json.dumps({
            "to": to,
            "subject": subject,
            "body": body,
            **({k: metadata[k] for k in ("cc", "bcc", "attachments") if k in metadata}),
        })
        result = await _call_mcp_tool("mcp__email__send_email", content)
        return {"sent": True, "to": to, "subject": subject, "result": result}
    except Exception as e:
        logger.error("email_executor: failed for %s: %s", activity_id, e)
        return {"error": str(e), "activity_id": activity_id}


async def benchmark_executor(
    activity_id: str, goal: str, metadata: dict[str, Any],
) -> dict[str, Any]:
    """Execute a benchmark activity via run_benchmark."""
    from core.coding.build_benchmark import run_benchmark
    project_dir = metadata.get("project_dir", ".")
    goal_type = metadata.get("goal_type", "build")
    session = await run_benchmark(
        goal=goal,
        project_dir=project_dir,
        goal_type=goal_type,
    )
    return {
        "benchmark_id": session.session_id if hasattr(session, "session_id") else str(id(session)),
        "comparison": session.comparison.to_dict() if hasattr(session, "comparison") and hasattr(session.comparison, "to_dict") else {},
    }


async def opportunity_executor(
    activity_id: str, goal: str, metadata: dict[str, Any],
) -> dict[str, Any]:
    """Execute an opportunity-driven research activity.

    Maps the opportunity's target_system to a research question and
    delegates to the research executor for investigation.
    """
    target_system = metadata.get("target_system", "general")
    opportunity_id = metadata.get("opportunity_id", "")
    description = metadata.get("description", goal)

    logger.info("opportunity_executor: %s (%s) — researching %s",
                activity_id, opportunity_id, target_system)

    try:
        result = await research_executor(
            activity_id=activity_id,
            goal=f"Research improvement opportunity: {description[:200]}",
            metadata={
                "question": f"Investigate and propose improvements for {target_system}: {description[:200]}",
                "max_pages": 3,
                "opportunity_id": opportunity_id,
                "target_system": target_system,
            },
        )
        return {
            "status": "completed",
            "target_system": target_system,
            "opportunity_id": opportunity_id,
            "result": result,
        }
    except Exception as e:
        logger.error("opportunity_executor: failed for %s: %s", activity_id, e)
        return {"status": "failed", "error": str(e), "activity_id": activity_id}


# ── Default executor (fallback when no specific executor is registered) ──


async def default_executor(
    activity_id: str, goal: str, metadata: dict[str, Any],
) -> dict[str, Any]:
    """Fallback executor for unregistered activity types.

    Attempts to run the activity through the workflow engine as a single-step
    tool call, using metadata.tool_type to pick which tool to call.
    """
    tool_type = metadata.get("tool_type", "")
    if not tool_type:
        return {
            "status": "skipped",
            "reason": f"no_executor_for_type:{metadata.get('node_type', 'unknown')}",
        }
    try:
        from core.tools.execution import execute_tool_block
        from core.tools._constants import ToolBlock
        block = ToolBlock(tool_type=tool_type, content=json.dumps(metadata.get("args", {})))
        result = await execute_tool_block(block)
        return {"tool": tool_type, "result": result}
    except Exception as e:
        logger.error("default_executor: failed for %s: %s", activity_id, e)
        return {"error": str(e)}
