"""Scheduler executors — adapter layer between scheduler and real subsystems.

Each executor receives (activity_id, goal, metadata) from the scheduler
and routes through the canonical pipeline (process_message) to ensure
auth, rate limiting, capability selection, and memory are applied.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from core.pipeline.messages import Request

from .result import SchedulerResult

logger = logging.getLogger(__name__)


async def _run_via_pipeline(
    activity_id: str,
    text: str,
    user_id: str = "__scheduler__",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Execute a textual request through the canonical pipeline."""
    from core.pipeline.pipeline import process_message

    request = Request(
        text=text,
        transport="scheduler",
        user_id=user_id,
        metadata={
            "activity_id": activity_id,
            "source": "scheduler",
            **(metadata or {}),
        },
    )
    response = await process_message(request)
    if response.error:
        return {"error": response.error, "activity_id": activity_id}
    return {
        "text": response.text,
        "data": response.data or {},
        "metadata": response.metadata or {},
        "activity_id": activity_id,
    }


def _executor_result(
    response: dict[str, Any],
    activity_id: str,
) -> dict[str, Any]:
    if "error" in response:
        return {"error": response["error"], "activity_id": activity_id}
    data = response.get("data", {})
    return {
        **data,
        "activity_id": activity_id,
        "text": response.get("text", ""),
    }

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
    """Execute a research activity through the canonical pipeline."""
    question = metadata.get("question") or goal
    response = await _run_via_pipeline(
        activity_id=activity_id,
        text=question,
        user_id=metadata.get("user_id", "__scheduler__"),
    )
    return _executor_result(response, activity_id)


async def build_executor(
    activity_id: str, goal: str, metadata: dict[str, Any],
) -> dict[str, Any]:
    """Execute a build activity through the canonical pipeline."""
    task = metadata.get("task") or goal
    return await _run_via_pipeline(
        activity_id=activity_id,
        text=task,
        user_id=metadata.get("user_id", "__scheduler__"),
        metadata={"activity_type": "build", **metadata},
    )


async def repair_executor(
    activity_id: str, goal: str, metadata: dict[str, Any],
) -> dict[str, Any]:
    """Execute a repair activity through the canonical pipeline."""
    build_output = metadata.get("build_output", "")
    text = f"Repair build: {goal}" if build_output else goal
    return await _run_via_pipeline(
        activity_id=activity_id,
        text=text,
        user_id=metadata.get("user_id", "__scheduler__"),
        metadata={"activity_type": "repair", **metadata},
    )


async def email_executor(
    activity_id: str, goal: str, metadata: dict[str, Any],
) -> dict[str, Any]:
    """Send an email through the canonical pipeline."""
    to = metadata.get("to", "")
    subject = metadata.get("subject") or goal
    body = metadata.get("body", "")
    if not to:
        return {"error": "no_recipient", "activity_id": activity_id}
    text = f"Send email to {to}: {subject}\n\n{body}"
    cc = metadata.get("cc", "")
    if cc:
        text = f"CC: {cc}\n" + text
    result = await _run_via_pipeline(
        activity_id=activity_id,
        text=text,
        user_id=metadata.get("user_id", "__scheduler__"),
        metadata={"activity_type": "email", **metadata},
    )
    if "error" in result:
        return {"error": result["error"], "activity_id": activity_id}
    return {"sent": True, "to": to, "subject": subject, "result": result}


async def benchmark_executor(
    activity_id: str, goal: str, metadata: dict[str, Any],
) -> dict[str, Any]:
    """Execute a benchmark activity through the canonical pipeline."""
    result = await _run_via_pipeline(
        activity_id=activity_id,
        text=goal,
        user_id=metadata.get("user_id", "__scheduler__"),
        metadata={"activity_type": "benchmark", **metadata},
    )
    if "error" in result:
        return {"error": result["error"], "activity_id": activity_id}
    return {
        "benchmark_id": activity_id,
        "result": result,
    }


async def opportunity_executor(
    activity_id: str, goal: str, metadata: dict[str, Any],
) -> dict[str, Any]:
    """Execute an opportunity-driven research activity through the canonical pipeline."""
    target_system = metadata.get("target_system", "general")
    opportunity_id = metadata.get("opportunity_id", "")
    description = metadata.get("description", goal)

    logger.info("opportunity_executor: %s (%s) — researching %s",
                activity_id, opportunity_id, target_system)

    text = f"Research improvement opportunity for {target_system}: {description[:200]}"
    result = await _run_via_pipeline(
        activity_id=activity_id,
        text=text,
        user_id=metadata.get("user_id", "__scheduler__"),
        metadata={"activity_type": "opportunity", **metadata},
    )
    if "error" in result:
        return {"status": "failed", "error": result["error"], "activity_id": activity_id}
    return {
        "status": "completed",
        "target_system": target_system,
        "opportunity_id": opportunity_id,
        "result": result,
    }


# ── Default executor (fallback when no specific executor is registered) ──


async def default_executor(
    activity_id: str, goal: str, metadata: dict[str, Any],
) -> dict[str, Any]:
    """Fallback executor routes through the canonical pipeline."""
    tool_type = metadata.get("tool_type", "")
    if not tool_type:
        return {
            "status": "skipped",
            "reason": f"no_executor_for_type:{metadata.get('node_type', 'unknown')}",
        }
    result = await _run_via_pipeline(
        activity_id=activity_id,
        text=goal,
        user_id=metadata.get("user_id", "__scheduler__"),
        metadata={"activity_type": "default_tool", "tool_type": tool_type, **metadata},
    )
    if "error" in result:
        return {"error": "Operation failed", "activity_id": activity_id}
    return {"tool": tool_type, "result": result}
