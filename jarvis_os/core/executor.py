from __future__ import annotations

import time
from typing import Any

from ..contracts import ExecutionReport, ToolResult


class ExecutionEngine:
    def __init__(self, registry: Any, memory: Any, policy: Any | None = None, telemetry: Any | None = None) -> None:
        self.registry = registry
        self.memory = memory
        self.policy = policy
        self.telemetry = telemetry

    def execute(
        self,
        plan: Any,
        context: dict[str, Any] | None = None,
        *,
        start_index: int = 0,
        existing_results: list[Any] | None = None,
        before_step: Any | None = None,
        after_step: Any | None = None,
    ) -> ExecutionReport:
        prior_results = [self._coerce_result(item) for item in (existing_results or [])]
        report = ExecutionReport(
            goal=plan.goal,
            plan_id=plan.plan_id,
            success=all(item.success for item in prior_results) if prior_results else True,
            status="running",
            results=prior_results,
        )
        context_data = dict(context or {})
        report.started_at = time.time()
        if prior_results and isinstance(prior_results[-1].output, dict):
            context_data["last_output"] = prior_results[-1].output

        # For DAG execution, sort by dependencies (simplified, assume sequential)
        steps = plan.steps[start_index:]

        for index, step in enumerate(steps):
            if before_step is not None:
                before_step(step, index, report, context_data)

            result = self._execute_step_with_retry(step, context_data, max_retries=3)
            report.results.append(result)

            if after_step is not None:
                after_step(step, index, result, report, context_data)

            if self.telemetry is not None:
                self.telemetry.record(
                    "tool.invoke",
                    {
                        "tool": step.tool,
                        "success": result.success,
                        "duration_ms": result.duration_ms,
                        "plan_id": plan.plan_id,
                    },
                )

            self.memory.remember("execution_step", f"{step.tool}: {step.action}", {"success": result.success})

            if not result.success:
                report.success = False
                break

        report.completed_at = time.time()
        report.status = "completed" if report.success else "failed"
        report.summary = self._summarize(report)
        if self.telemetry is not None:
            self.telemetry.record(
                "execution.complete",
                {
                    "plan_id": plan.plan_id,
                    "goal": plan.goal,
                    "success": report.success,
                    "steps": len(report.results),
                },
            )
        return report

    def _execute_step_with_retry(self, step: Any, context_data: dict[str, Any], max_retries: int = 3) -> ToolResult:
        for attempt in range(max_retries):
            started = time.perf_counter()
            try:
                if self.policy is not None:
                    decision = self.policy.evaluate(step, self.registry, context_data)
                    if not decision.allowed:
                        return ToolResult(
                            tool=step.tool,
                            success=False,
                            error=decision.reason,
                            duration_ms=int((time.perf_counter() - started) * 1000),
                            step_id=step.step_id,
                        )

                # Assume registry.invoke is sync
                output = self.registry.invoke(step.tool, **step.arguments, context=context_data)
                success, error = self._normalize_tool_outcome(output)
                step.status = "completed" if success else "failed"
                return ToolResult(
                    tool=step.tool,
                    success=success,
                    output=output,
                    error=error,
                    duration_ms=int((time.perf_counter() - started) * 1000),
                    step_id=step.step_id,
                )
            except Exception as exc:
                if attempt == max_retries - 1:
                    return ToolResult(
                        tool=step.tool,
                        success=False,
                        error=str(exc),
                        duration_ms=int((time.perf_counter() - started) * 1000),
                        step_id=step.step_id,
                    )
                time.sleep(0.1 * (attempt + 1))  # Exponential backoff

        # Should not reach here
        return ToolResult(tool=step.tool, success=False, error="Max retries exceeded", step_id=step.step_id)
