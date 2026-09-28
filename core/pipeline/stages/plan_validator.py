"""PlanValidatorStage — checks plan shape before execution."""
from core.pipeline.base import PipelineStage, StageOutcome, StageResult
from core.pipeline.pipeline import PipelineContext


class PlanValidatorStage(PipelineStage):
    @property
    def name(self) -> str:
        return "plan_validator"

    async def execute(self, context: PipelineContext) -> StageResult:
        plan = context.plan
        valid = bool(plan) and (
            isinstance(plan, dict) and bool(plan.get("steps"))
            or isinstance(plan, list) and bool(plan)
        )
        context.plan_validated = valid
        return StageResult(outcome=StageOutcome.CONTINUE, context=context)


__all__ = ["PlanValidatorStage"]
