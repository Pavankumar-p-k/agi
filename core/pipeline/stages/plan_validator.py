from __future__ import annotations

from typing import Any

from core.pipeline.base import PipelineStage, StageOutcome, StageResult
from core.pipeline.context import PipelineContext


class PlanValidatorStage(PipelineStage):
    @property
    def name(self) -> str:
        return "plan_validator"

    async def execute(self, context: PipelineContext) -> StageResult:
        plan = context.plan
        if plan is None:
            context.plan_validated = False
            return StageResult(
                outcome=StageOutcome.FAIL,
                context=context,
                error="PlanValidator: plan is None",
            )

        steps = plan.get("steps", [])
        if not isinstance(steps, list) or len(steps) == 0:
            context.plan_validated = False
            return StageResult(
                outcome=StageOutcome.FAIL,
                context=context,
                error="PlanValidator: plan has no steps",
            )

        for i, step in enumerate(steps):
            if not isinstance(step, dict):
                context.plan_validated = False
                return StageResult(
                    outcome=StageOutcome.FAIL,
                    context=context,
                    error=f"PlanValidator: step {i} is not a dict",
                )
            if not step.get("intent"):
                context.plan_validated = False
                return StageResult(
                    outcome=StageOutcome.FAIL,
                    context=context,
                    error=f"PlanValidator: step {i} has no intent",
                )
            if not step.get("objective"):
                context.plan_validated = False
                return StageResult(
                    outcome=StageOutcome.FAIL,
                    context=context,
                    error=f"PlanValidator: step {i} has no objective",
                )
            constraints = step.get("constraints")
            if constraints is not None and not isinstance(constraints, dict):
                context.plan_validated = False
                return StageResult(
                    outcome=StageOutcome.FAIL,
                    context=context,
                    error=f"PlanValidator: step {i} constraints is not a dict",
                )

        context.plan_validated = True
        return StageResult(outcome=StageOutcome.CONTINUE, context=context)
