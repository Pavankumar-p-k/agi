from __future__ import annotations

import logging
import time
from typing import Any

import asyncio

from core.providers.base import (
    ExecutionProvider,
    ExecutionResult,
    ProviderCapabilities,
    ProviderHealth,
    ProviderHealthStatus,
)

logger = logging.getLogger(__name__)


class AutomationProvider(ExecutionProvider):
    provider_id = "automation"
    name = "Workflow Automation"
    version = "1.0.0"
    priority = 10
    installed = True

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            capability_names=[
                "automation",
                "workflow",
                "schedule",
                "background",
                "pipeline",
                "orchestration",
            ],
            features=[
                "workflow_execution",
                "scheduled_tasks",
                "multi_step_pipelines",
                "recovery",
                "compensation",
            ],
        )

    async def health(self) -> ProviderHealth:
        try:
            from core.workflow.engine import WorkflowEngine
            engine = WorkflowEngine()
            logger.debug("[AutomationProvider] Health OK")
            return ProviderHealth(
                status=ProviderHealthStatus.HEALTHY,
                latency_ms=0.0,
                last_checked=time.time(),
            )
        except Exception as e:
            logger.debug("[AutomationProvider] Health check failed: %s", e)
            return ProviderHealth(
                status=ProviderHealthStatus.DOWN,
                error=str(e),
                last_checked=time.time(),
            )

    async def execute(
        self, task: dict[str, Any], context: dict[str, Any] | None = None
    ) -> ExecutionResult:
        workflow_type = task.get("goal", task.get("workflow_type", "generic"))
        steps_data = task.get("steps", [])
        session_id = task.get("session_id", "")
        owner = task.get("owner", "dev")
        start = time.monotonic()

        try:
            from core.workflow.engine import WorkflowEngine
            from core.workflow.models import StepDefinition

            step_defs = []
            for s in steps_data:
                step_defs.append(StepDefinition(
                    tool_name=s.get("tool", s.get("tool_name", "")),
                    input_data=s.get("input", s.get("input_data", {})),
                    max_retries=s.get("max_retries", 2),
                    timeout_seconds=s.get("timeout_seconds"),
                    compensation_tool=s.get("compensation_tool"),
                    compensation_input=s.get("compensation_input"),
                ))

            engine = WorkflowEngine()
            workflow = await engine.start_workflow(
                workflow_type=workflow_type,
                steps=step_defs,
                session_id=session_id,
                owner=owner,
            )

            # Wait for the background workflow task to complete
            task = engine._running.get(workflow.workflow_id)
            if task:
                try:
                    await asyncio.wait_for(asyncio.shield(task), timeout=300)
                except asyncio.TimeoutError:
                    logger.warning("Workflow %s timed out", workflow.workflow_id)

            final = engine._store.get_workflow(workflow.workflow_id)
            elapsed = (time.monotonic() - start) * 1000
            success = final.status.name == "COMPLETED" if final else False

            step_results = []
            if final:
                for step in final.steps:
                    step_results.append({
                        "tool": step.tool_name,
                        "status": step.status.name if hasattr(step.status, "name") else str(step.status),
                        "exit_code": step.exit_code,
                    })

            return ExecutionResult(
                success=success,
                output=str(final.to_dict() if hasattr(final, "to_dict") else final) if final else "",
                exit_code=0 if success else 1,
                duration_ms=elapsed,
                artifacts=final.artifacts if final else {},
                metadata={
                    "provider": "automation",
                    "workflow_id": workflow.workflow_id if workflow else None,
                    "steps_total": len(step_defs),
                    "steps_completed": sum(1 for s in step_results if s.get("status") == "COMPLETED"),
                    "step_results": step_results,
                },
            )
        except Exception as e:
            elapsed = (time.monotonic() - start) * 1000
            logger.exception("[AutomationProvider] Execution failed: %s", e)
            return ExecutionResult(
                success=False,
                output="",
                error=str(e),
                exit_code=1,
                duration_ms=elapsed,
                metadata={"provider": "automation"},
            )

    async def estimate_cost(self, task: dict[str, Any]) -> float:
        return 0.0

    async def estimate_latency(self, task: dict[str, Any]) -> float:
        steps = len(task.get("steps", []))
        return float(steps * 5000)

    async def cancel(self, execution_id: str) -> bool:
        try:
            from core.workflow.engine import WorkflowEngine
            engine = WorkflowEngine()
            await engine.cancel_workflow(execution_id)
            return True
        except Exception as e:
            logger.warning("[AutomationProvider] Cancel failed: %s", e)
            return False
