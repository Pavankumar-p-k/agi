from __future__ import annotations

from typing import Any

from core.pipeline.base import PipelineStage, StageOutcome, StageResult
from core.pipeline.context import PipelineContext


class PlannerStage(PipelineStage):
    @property
    def name(self) -> str:
        return "planner"

    async def execute(self, context: PipelineContext) -> StageResult:
        assessment = context.reasoning_assessment or {}
        raw_input = context.raw_input or ""
        complexity = assessment.get("complexity", "simple")

        if complexity == "simple":
            steps = [self._build_step("respond", f"Respond to: {raw_input[:200]}", {})]
        else:
            steps = self._decompose(raw_input, assessment)

        context.plan = {
            "goal": raw_input,
            "steps": steps,
        }
        return StageResult(outcome=StageOutcome.CONTINUE, context=context)

    def _build_step(self, intent: str, objective: str, constraints: dict[str, Any]) -> dict[str, Any]:
        return {
            "intent": intent,
            "objective": objective,
            "constraints": constraints,
        }

    def _decompose(self, raw_input: str, assessment: dict[str, Any]) -> list[dict[str, Any]]:
        steps: list[dict[str, Any]] = []
        requirements = assessment.get("requirements", [])
        constraints = {c: True for c in assessment.get("constraints", [])}

        if "research" in requirements:
            steps.append(self._build_step(
                "search_web",
                f"Research: {raw_input[:200]}",
                {**constraints, "task": "research"},
            ))
        if "browser" in requirements:
            steps.append(self._build_step(
                "browse_web",
                f"Browse: {raw_input[:200]}",
                {**constraints, "task": "browse"},
            ))
        if "coding" in requirements:
            steps.append(self._build_step(
                "write_code",
                f"Implement: {raw_input[:200]}",
                {**constraints, "task": "coding"},
            ))

        steps.append(self._build_step(
            "respond",
            f"Respond to: {raw_input[:200]}",
            constraints,
        ))

        return steps
